#!/usr/bin/env python3
"""Focused archive-free startup contract for an installed layered package."""

from __future__ import annotations

import hashlib
import json
import shutil
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

    def run_profile(self, profile: Path, map_root: str | None = None,
                    working: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "java", *([] if map_root is None else [
                    "-Dopenrsc.worldBuilderInstalledMapRoot=" + map_root]),
                "-cp", f"{self.classes}:{JSON_JAR}",
                "orsc.InstalledClientProfileHarness", str(profile),
            ],
            cwd=working or ROOT,
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

    def test_external_map_root_is_cwd_independent_and_remains_profile_bound(self) -> None:
        external = Path(self.temp.name) / "external map #?é"
        shutil.copytree(self.package, external)
        working = Path(self.temp.name) / "independent-working-directory"
        working.mkdir()
        before = (external / "manifest.json").read_bytes()
        result = self.run_profile(self.profile, str(external), working)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(str(external), result.stdout.splitlines()[5])
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
