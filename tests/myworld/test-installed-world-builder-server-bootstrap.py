#!/usr/bin/env python3
"""Focused host-integrated startup contract for an installed layered package."""

from __future__ import annotations

import hashlib
import json
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

    def run_profile(self, profile: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "java", "-cp", f"{self.classes}:{CORE}",
                "com.openrsc.server.io.InstalledServerProfileHarness", str(profile),
            ],
            cwd=ROOT,
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
