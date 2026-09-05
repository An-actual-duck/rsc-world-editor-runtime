#!/usr/bin/env python3
"""Focused host-integrated startup contract for an installed layered package."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "server/core.jar"

HARNESS = r"""
package com.openrsc.server.io;

import com.openrsc.server.ServerConfiguration;

public final class InstalledServerProfileHarness {
    public static void main(String[] arguments) throws Exception {
        System.setProperty(
            WorldBuilderInstalledServerProfile.PROFILE_PROPERTY, arguments[0]);
        ServerConfiguration configuration = new ServerConfiguration();
        WorldBuilderInstalledServerProfile.apply(configuration);
        System.out.println(configuration.WANT_LAYERED_NATIVE_TERRAIN_PACKAGE);
        System.out.println(configuration.WANT_LAYERED_NATIVE_TERRAIN_RESIDENCY);
        System.out.println(configuration.WANT_LAYERED_NATIVE_TERRAIN_READINESS);
        System.out.println(configuration.WANT_LAYERED_NATIVE_TERRAIN_PREDICTION);
        System.out.println(configuration.WANT_LAYERED_NATIVE_TERRAIN_SYMMETRIC_RESIDENCY);
        System.out.println(configuration.WANT_LAYERED_NATIVE_TERRAIN_ATOMIC_ACTIVATION);
        System.out.println(configuration.LAYERED_NATIVE_TERRAIN_PACKAGE_PATH);
        System.out.println(configuration.LAYERED_NATIVE_TERRAIN_MANIFEST_SHA256);
        System.out.println(configuration.LAYERED_NATIVE_WORLD_RUNTIME_PROFILE);
    }
}
"""


class InstalledWorldBuilderServerBootstrapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not CORE.is_file():
            subprocess.run([str(ROOT / "scripts/build-server.sh")], cwd=ROOT, check=True)
        cls.compiled = tempfile.TemporaryDirectory(
            prefix="installed-world-builder-server-classes-"
        )
        classes = Path(cls.compiled.name)
        harness = classes / "com/openrsc/server/io/InstalledServerProfileHarness.java"
        harness.parent.mkdir(parents=True)
        harness.write_text(HARNESS, encoding="utf-8")
        subprocess.run(
            [
                "javac", "-source", "8", "-target", "8",
                "-cp", str(CORE), "-d", str(classes), str(harness),
                str(ROOT / "server/src/com/openrsc/server/io/WorldBuilderInstalledServerProfile.java"),
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
            prefix="installed-world-builder-server-fixture-"
        )
        self.server = Path(self.temp.name) / "server"
        self.profile = self.server / "world-builder-configs/installed-server.json"
        self.package = self.server / "world-builder/packages" / ("a" * 64) / "package"
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
                    "manifestType": "world-builder-installed-server-profile",
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

    def run_profile(self, profile: Path, map_root: str | None = None,
                    working: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "java", *([] if map_root is None else [
                    "-Dopenrsc.worldBuilderInstalledMapRoot=" + map_root]),
                "-cp", f"{self.classes}:{CORE}",
                "com.openrsc.server.io.InstalledServerProfileHarness", str(profile),
            ],
            cwd=working or ROOT,
            text=True,
            capture_output=True,
        )

    def test_verified_profile_activates_only_layered_runtime_fields(self) -> None:
        result = self.run_profile(self.profile)
        self.assertEqual(0, result.returncode, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(["true"] * 6, lines[:6])
        self.assertEqual(
            "world-builder/packages/" + "a" * 64 + "/package", lines[6]
        )
        self.assertEqual(self.manifest_hash, lines[7])
        self.assertEqual("world-builder-installed", lines[8])

    def test_external_map_root_is_cwd_independent_and_remains_profile_bound(self) -> None:
        external = Path(self.temp.name) / "external map #?é"
        shutil.copytree(self.package, external)
        working = Path(self.temp.name) / "independent-working-directory"
        working.mkdir()
        before = (external / "manifest.json").read_bytes()
        result = self.run_profile(self.profile, str(external), working)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(str(external), result.stdout.splitlines()[6])
        self.assertEqual(before, (external / "manifest.json").read_bytes())
        # A matching legacy copy cannot rescue an explicitly selected bad root.
        (external / "manifest.json").write_text("{}", encoding="utf-8")
        refused = self.run_profile(self.profile, str(external), working)
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("SHA-256", refused.stderr)

    def test_external_map_rejects_missing_alias_and_runtime_overlap_without_fallback(self) -> None:
        external = Path(self.temp.name) / "external-map"
        shutil.copytree(self.package, external)
        alias = Path(self.temp.name) / "map-alias"
        alias.symlink_to(external, target_is_directory=True)
        parent_alias = Path(self.temp.name) / "parent-alias"
        parent_alias.symlink_to(external.parent, target_is_directory=True)
        for value in (
            "", "relative-map", str(external / "missing"), str(alias),
            str(parent_alias / external.name), str(external) + "/../external-map",
            str(ROOT), str(self.classes),
        ):
            with self.subTest(root=value):
                refused = self.run_profile(self.profile, value)
                self.assertNotEqual(0, refused.returncode)
                self.assertIn("External installed map root", refused.stderr)
        self.assertTrue((self.package / "manifest.json").is_file())

    def test_external_map_cannot_silently_disable_a_missing_or_inactive_profile(self) -> None:
        external = Path(self.temp.name) / "external-map"
        shutil.copytree(self.package, external)
        missing = self.run_profile(self.profile.with_name("missing.json"), str(external))
        self.assertNotEqual(0, missing.returncode)
        self.assertIn("requires an active installed profile", missing.stderr)
        document = json.loads(self.profile.read_text())
        document["active"] = False
        self.profile.write_text(json.dumps(document))
        inactive = self.run_profile(self.profile, str(external))
        self.assertNotEqual(0, inactive.returncode)
        self.assertIn("requires an active installed profile", inactive.stderr)

    def test_absent_profile_preserves_legacy_server_behavior(self) -> None:
        result = self.run_profile(self.server / "world-builder-configs/missing.json")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["false"] * 6, result.stdout.splitlines()[:6])

    def test_manifest_drift_fails_closed(self) -> None:
        (self.package / "manifest.json").write_text("{}", encoding="utf-8")
        result = self.run_profile(self.profile)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("manifest SHA-256", result.stderr)


if __name__ == "__main__":
    unittest.main()
