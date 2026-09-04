#!/usr/bin/env python3
"""Executable, content-neutral evidence for the Current Base candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/current-platform/current-base-v1"
IDENTITY = OUTPUT / "composition-identity.json"
BUILD = ROOT / "scripts/build-current-base.py"
VERIFY = ROOT / "scripts/verify-current-base.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_hashes() -> dict[str, str]:
    identity = json.loads(IDENTITY.read_text(encoding="utf-8"))
    return {
        record["bundlePath"]: record["sha256"]
        for record in identity["bundleInventory"]
    }


class CurrentBaseCandidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(
            ["python3", str(BUILD)], cwd=ROOT, check=True, capture_output=True, text=True
        )
        cls.identity = json.loads(IDENTITY.read_text(encoding="utf-8"))
        cls.profile = json.loads(
            (ROOT / "current-platform/runtime/current-base-v1/profile.json").read_text()
        )

    def test_candidate_is_buildable_but_not_claimed_installable_or_released(self) -> None:
        base = json.loads(
            (ROOT / "current-platform/variants/current-base-v1.json").read_text()
        )
        advanced = json.loads(
            (ROOT / "current-platform/variants/current-advanced-v1.json").read_text()
        )
        self.assertEqual("release-candidate", base["releaseStatus"])
        self.assertFalse(base["installable"])
        self.assertNotEqual("released", base["releaseStatus"])
        self.assertFalse(advanced["installable"])
        self.assertEqual("foundation-contract-only", advanced["releaseStatus"])
        self.assertEqual(
            [
                "content-neutral-server-config-and-definitions-v1",
                "transactional-state-migration-row-v1",
            ],
            self.profile["installabilityBlockers"],
        )

    def test_startup_gate_binds_exact_six_field_server_client_identity(self) -> None:
        result = subprocess.run(
            [
                "python3", str(VERIFY), "--identity", str(IDENTITY),
                "--payload-root", str(ROOT),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        evidence = json.loads(result.stdout)
        self.assertEqual("verified", evidence["status"])
        self.assertEqual("current-composition-handshake-v1", evidence["handshakeId"])
        self.assertRegex(evidence["startupHandshakeSha256"], r"^[0-9a-f]{64}$")

        with tempfile.TemporaryDirectory(prefix="current-base-mismatch-") as temporary:
            mismatch = dict(self.identity)
            mismatch["bundleInventoryHash"] = "0" * 64
            mismatch_path = Path(temporary) / "identity.json"
            mismatch_path.write_text(json.dumps(mismatch), encoding="utf-8")
            refused = subprocess.run(
                [
                    "python3", str(VERIFY), "--identity", str(mismatch_path),
                    "--payload-root", str(ROOT),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("differs from provider artifacts", refused.stderr)

    def test_public_plugins_and_canonical_map_bootstraps_are_executable(self) -> None:
        core = OUTPUT / "server/core.jar"
        plugins = OUTPUT / "server/plugins.jar"
        client = OUTPUT / "client/Open_RSC_Client.jar"
        with zipfile.ZipFile(core) as archive:
            core_names = set(archive.namelist())
        with zipfile.ZipFile(plugins) as archive:
            plugin_names = set(archive.namelist())
        with zipfile.ZipFile(client) as archive:
            client_names = set(archive.namelist())
        for required in self.profile["requiredRuntimeClasses"]:
            self.assertIn(required, core_names)
        for required in self.profile["requiredPluginClasses"]:
            self.assertIn(required, plugin_names)
        self.assertIn("orsc/WorldBuilderInstalledClientProfile.class", client_names)

        harness_source = """
package com.openrsc.server.io;
import com.openrsc.server.ServerConfiguration;
public final class CurrentBaseMapHarness {
  public static void main(String[] args) throws Exception {
    System.setProperty(WorldBuilderInstalledServerProfile.PROFILE_PROPERTY, args[0]);
    ServerConfiguration configuration = new ServerConfiguration();
    WorldBuilderInstalledServerProfile.apply(configuration);
    System.out.println(configuration.WANT_LAYERED_NATIVE_TERRAIN_PACKAGE);
    System.out.println(configuration.LAYERED_NATIVE_WORLD_RUNTIME_PROFILE);
  }
}
"""
        with tempfile.TemporaryDirectory(prefix="current-base-map-") as temporary:
            root = Path(temporary)
            package = root / "server/world-builder/packages" / ("a" * 64) / "package"
            package.mkdir(parents=True)
            manifest = {
                "schemaVersion": 1,
                "packageType": "layered-world",
                "packageId": "sealed-fixture-world",
                "packageVersion": "1.0.0",
                "coordinateModel": "signed-layered-v1",
                "worldSpaces": [],
                "levels": [],
                "storage": {},
                "terrainSectors": [],
                "placementSets": [],
            }
            manifest_path = package / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, separators=(",", ":"), sort_keys=True),
                encoding="utf-8",
            )
            profile = root / "server/world-builder-configs/installed-server.json"
            profile.parent.mkdir(parents=True)
            profile.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "manifestType": "world-builder-installed-server-profile",
                        "active": True,
                        "packageId": "sealed-fixture-world",
                        "packageVersion": "1.0.0",
                        "packageFingerprintSha256": "a" * 64,
                        "manifestSha256": sha256(manifest_path),
                        "packageRelativePath": "world-builder/packages/" + "a" * 64 + "/package",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            source = root / "com/openrsc/server/io/CurrentBaseMapHarness.java"
            source.parent.mkdir(parents=True)
            source.write_text(harness_source, encoding="utf-8")
            subprocess.run(
                [
                    "javac", "-source", "8", "-target", "8", "-cp", str(core),
                    "-d", str(root), str(source),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
            )
            executed = subprocess.run(
                [
                    "java", "-cp", f"{root}:{core}",
                    "com.openrsc.server.io.CurrentBaseMapHarness", str(profile),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
        self.assertEqual(["true", "world-builder-installed"], executed.stdout.splitlines())

    def test_advanced_only_plugins_assets_and_configuration_are_absent(self) -> None:
        with zipfile.ZipFile(OUTPUT / "server/plugins.jar") as archive:
            plugins = archive.namelist()
        with zipfile.ZipFile(OUTPUT / "client/Open_RSC_Client.jar") as archive:
            client = archive.namelist()
        for prefix in self.profile["advancedExclusions"]["pluginPrefixes"]:
            self.assertFalse(any(name.startswith(prefix) for name in plugins), prefix)
        for prefix in self.profile["advancedExclusions"]["clientResourcePrefixes"]:
            self.assertFalse(any(name.startswith(prefix) for name in client), prefix)
        self.assertTrue(self.profile["advancedExclusions"]["configuration"])
        self.assertTrue(
            all(
                value is False
                for value in self.profile["advancedExclusions"]["configuration"].values()
            )
        )
        self.assertEqual(
            {
                "contractId": "canonical-public-state-v1",
                "durableLocation": "outside-code-runtime",
                "migration": "transactional",
                "rollback": "exact-predecessor",
            },
            self.profile["statePolicy"],
        )

    def test_repeated_source_build_has_identical_closed_inventory(self) -> None:
        first = candidate_hashes()
        subprocess.run(
            ["python3", str(BUILD)], cwd=ROOT, check=True, capture_output=True, text=True
        )
        second = candidate_hashes()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
