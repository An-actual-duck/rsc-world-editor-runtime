#!/usr/bin/env python3
"""Focused archive-free startup contract for an installed layered package."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "Client_Base/src/orsc/WorldBuilderInstalledClientProfile.java"
JSON_JAR = ROOT / "server/lib/json-20190722.jar"

HARNESS = r"""
package orsc;

public final class InstalledClientProfileHarness {
    public static void main(String[] arguments) {
        System.setProperty(
            WorldBuilderInstalledClientProfile.PROFILE_PROPERTY, arguments[0]);
        WorldBuilderInstalledClientProfile.resetForTests();
        WorldBuilderInstalledClientProfile profile =
            WorldBuilderInstalledClientProfile.current();
        System.out.println(profile.isEnabled());
        if (profile.isEnabled()) {
            System.out.println(profile.mapIdentity());
            System.out.println(profile.packageId());
            System.out.println(profile.packageVersion());
            System.out.println(profile.packageFingerprintSha256());
            System.out.println(profile.packageRoot());
        }
    }
}
"""


class InstalledWorldBuilderClientBootstrapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.compiled = tempfile.TemporaryDirectory(
            prefix="installed-world-builder-client-classes-"
        )
        classes = Path(cls.compiled.name)
        harness = classes / "orsc/InstalledClientProfileHarness.java"
        harness.parent.mkdir(parents=True)
        harness.write_text(HARNESS, encoding="utf-8")
        subprocess.run(
            [
                "javac", "-source", "8", "-target", "8",
                "-cp", str(JSON_JAR), "-d", str(classes),
                str(SOURCE), str(harness),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        cls.classes = classes

    @classmethod
    def tearDownClass(cls) -> None:
        cls.compiled.cleanup()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(
            prefix="installed-world-builder-client-fixture-"
        )
        self.client = Path(self.temp.name) / "Client_Base"
        self.profile = self.client / "world-builder-configs/installed-client.json"
        self.package = (
            self.client / "world-builder/packages" / ("a" * 64) / "package"
        )
        self.package.mkdir(parents=True)
        manifest = {
            "schemaVersion": 1,
            "packageType": "layered-world",
            "packageId": "fixture-world",
            "packageVersion": "1.0.0",
            "coordinateModel": "signed-layered-v1",
            "worldSpaces": [],
            "levels": [],
            "storage": {},
            "terrainSectors": [],
            "placementSets": [],
        }
        manifest_path = self.package / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        self.manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        self.profile.parent.mkdir(parents=True)
        self.profile.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "manifestType": "world-builder-installed-client-profile",
                    "active": True,
                    "packageId": "fixture-world",
                    "packageVersion": "1.0.0",
                    "packageFingerprintSha256": "a" * 64,
                    "manifestSha256": self.manifest_hash,
                    "packageRelativePath": (
                        "world-builder/packages/" + "a" * 64 + "/package"
                    ),
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_profile(self, profile: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "java", "-cp", f"{self.classes}:{JSON_JAR}",
                "orsc.InstalledClientProfileHarness", str(profile),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )

    def test_verified_profile_starts_without_a_legacy_landscape(self) -> None:
        self.assertFalse((self.client / "Cache/video/Custom_Landscape.orsc").exists())
        result = self.run_profile(self.profile)
        self.assertEqual(0, result.returncode, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual("true", lines[0])
        self.assertEqual(self.manifest_hash, lines[1])
        self.assertEqual("fixture-world", lines[2])
        self.assertEqual("1.0.0", lines[3])
        self.assertEqual("a" * 64, lines[4])
        self.assertEqual(str(self.package.resolve()), lines[5])

    def test_absent_profile_preserves_legacy_client_behavior(self) -> None:
        result = self.run_profile(self.client / "world-builder-configs/missing.json")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("false\n", result.stdout)

    def test_manifest_drift_fails_closed(self) -> None:
        (self.package / "manifest.json").write_text("{}", encoding="utf-8")
        result = self.run_profile(self.profile)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("manifest SHA-256", result.stderr)

    def test_package_address_must_match_the_bound_fingerprint(self) -> None:
        profile = json.loads(self.profile.read_text(encoding="utf-8"))
        profile["packageFingerprintSha256"] = "b" * 64
        self.profile.write_text(json.dumps(profile), encoding="utf-8")
        result = self.run_profile(self.profile)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("package path is unsafe", result.stderr)

    def test_world_and_login_bootstrap_use_the_shared_native_only_policy(self) -> None:
        world = (ROOT / "Client_Base/src/orsc/graphics/three/World.java").read_text()
        client = (ROOT / "Client_Base/src/orsc/mudclient.java").read_text()
        self.assertIn("WorldBuilderTerrainBootstrap.isNativeOnly()", world)
        self.assertIn("mapHash = WorldBuilderTerrainBootstrap.mapIdentity()", world)
        self.assertIn(
            "return !WorldBuilderTerrainBootstrap.isNativeOnly();", client
        )


if __name__ == "__main__":
    unittest.main()
