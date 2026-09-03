#!/usr/bin/env python3

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ACTIVATION = (
    ROOT
    / "server/src/com/openrsc/server/content/worldedit/"
    "WorldEditorPlacementActivation.java"
)


class WorldEditorPlacementActivationTest(unittest.TestCase):
    def test_success_commits_once_and_failure_restores_current(self):
        harness = textwrap.dedent(
            """
            package com.openrsc.server.content.worldedit;

            import java.util.ArrayList;
            import java.util.Arrays;
            import java.util.List;

            public final class WorldEditorPlacementActivationHarness {
                private static final class FakeRuntime implements
                        WorldEditorPlacementActivation.Runtime<String> {
                    private final List<String> events = new ArrayList<String>();
                    private boolean refusePublished;

                    @Override
                    public void retire() {
                        events.add("retire");
                    }

                    @Override
                    public void populate(String value) {
                        events.add("populate-" + value);
                        if (refusePublished && "published".equals(value)) {
                            throw new IllegalStateException("refused");
                        }
                    }
                }

                public static void main(String[] arguments) {
                    FakeRuntime success = new FakeRuntime();
                    WorldEditorPlacementActivation.replace(
                        "current", "published", success);
                    require(success.events.equals(Arrays.asList(
                        "retire", "populate-published")), "success sequence");

                    FakeRuntime failure = new FakeRuntime();
                    failure.refusePublished = true;
                    try {
                        WorldEditorPlacementActivation.replace(
                            "current", "published", failure);
                        throw new AssertionError("failure was accepted");
                    } catch (IllegalStateException expected) {
                        require("refused".equals(expected.getMessage()),
                            "original failure preserved");
                    }
                    require(failure.events.equals(Arrays.asList(
                        "retire", "populate-published",
                        "retire", "populate-current")), "rollback sequence");
                }

                private static void require(boolean value, String message) {
                    if (!value) throw new AssertionError(message);
                }
            }
            """
        )
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            source = work / "WorldEditorPlacementActivationHarness.java"
            source.write_text(harness, encoding="utf-8")
            subprocess.run(
                [
                    "javac", "-Xlint:all", "-source", "8", "-target", "8",
                    "-d", str(work), str(ACTIVATION), str(source),
                ],
                cwd=ROOT,
                check=True,
            )
            subprocess.run(
                [
                    "java", "-cp", str(work),
                    "com.openrsc.server.content.worldedit."
                    "WorldEditorPlacementActivationHarness",
                ],
                cwd=ROOT,
                check=True,
            )

    def test_session_routes_post_activation_reads_through_active_package(self):
        manager = (
            ROOT
            / "server/src/com/openrsc/server/content/worldedit/"
            "WorldEditorSessionManager.java"
        ).read_text(encoding="utf-8")

        self.assertIn("activeNativePackage(player)", manager)
        self.assertIn(
            "findNativeTerrainSector(nativeAdoptedPackage,",
            manager,
        )
        self.assertEqual(
            2,
            manager.count(".getNativeLayeredWorldPackage()"),
            "only the adoption baseline and centralized active-package "
            "resolver may read the startup package directly",
        )


if __name__ == "__main__":
    unittest.main()
