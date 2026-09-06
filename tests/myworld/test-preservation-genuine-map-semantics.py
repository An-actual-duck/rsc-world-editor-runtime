#!/usr/bin/env python3
"""Genuine fused-map semantic evidence; absent external input is unavailable, never invented."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

import preservation_semantic_fixture as fixture

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/current-platform/current-base-v1"
PROBE = os.environ.get("WORLD_BUILDER_PRESERVATION_SEMANTIC_PROBE")


@unittest.skipUnless(PROBE, "genuine sealed external map probe unavailable")
class GenuineMapSemanticsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source, cls.manifest, cls.decoded, cls.reconciliation = fixture.inspect(PROBE)

    def test_sealed_map_raw_source_and_derivation_tampering_refused(self):
        with tempfile.TemporaryDirectory(prefix="genuine-map-tamper-") as temporary:
            copied = Path(temporary) / "probe"
            shutil.copytree(self.source, copied)
            raw = next((copied / "source/migration/decoder/sectors").iterdir())
            canonical = copied / "conversion/package" / self.manifest["terrainSectors"][0]["path"]
            original = copied / "source/original/server/conf/server/defs/TileDef.xml"
            for path in (raw, canonical, original, copied / "source/migration/input/derivation.json"):
                before = path.read_bytes()
                path.write_bytes(before + b"unreviewed")
                with self.assertRaises(ValueError):
                    fixture.inspect(copied)
                path.write_bytes(before)
            fixture.inspect(copied)

    def test_packaged_all_tile_collision_and_full_native_population(self):
        built = subprocess.run(["python3", "scripts/build-current-base.py", "--test-allow-dirty"],
                               cwd=ROOT, capture_output=True, text=True, timeout=240)
        self.assertEqual(0, built.returncode, built.stdout + built.stderr)
        with tempfile.TemporaryDirectory(prefix="genuine-map-runtime-") as temporary:
            root = Path(temporary)
            package = root / "package"
            shutil.copytree(self.source / "conversion/package", package)
            oracle = root / "historical-terrain.bin"
            fixture.terrain_oracle(self.source, self.decoded, oracle)
            runtime = root / "runtime"
            runtime.mkdir()
            with zipfile.ZipFile(OUTPUT / "server/content.zip") as archive:
                archive.extractall(runtime)
            shutil.copyfile(OUTPUT / "server/plugins.jar", runtime / "plugins.jar")
            config = runtime / "current-base.conf"
            config.write_text(config.read_text() + "\n" + "\n".join((
                "want_layered_player_location_authority: true",
                "want_layered_spatial_runtime_authority: true",
                "want_layered_protocol_client_authority: true",
                "want_layered_native_terrain_package: true",
                "layered_native_world_runtime_profile: world-builder-installed",
                "layered_native_terrain_package_path: " + str(package),
                "layered_native_terrain_manifest_sha256: " + fixture.SEALED["conversion/package/manifest.json"],
            )) + "\n")
            source = ROOT / "tests/myworld/fixtures/current-base-public/GenuineMapSemanticsProbe.java"
            classpath = os.pathsep.join(map(str, (root, OUTPUT / "server/core.jar", OUTPUT / "server/plugins.jar")))
            compiled = subprocess.run(["javac", "-source", "8", "-target", "8", "-cp", classpath,
                                       "-d", str(root), str(source)], capture_output=True, text=True, timeout=30)
            self.assertEqual(0, compiled.returncode, compiled.stdout + compiled.stderr)
            executed = subprocess.run(["java", "-Xmx1536m", "-Dopenrsc.currentCompositionIdentityFile="
                                       + str(OUTPUT / "composition-identity.json"), "-cp", classpath,
                                       "com.openrsc.server.GenuineMapSemanticsProbe", str(oracle)],
                                      cwd=runtime, capture_output=True, text=True, timeout=90)
            self.assertEqual(0, executed.returncode, (executed.stdout + executed.stderr)[-18000:])
            self.assertIn("GENUINE_TERRAIN compared=811008 differences=0", executed.stdout)
            self.assertIn("GENUINE_POPULATION npcs=3609 voidBounds=146 sectors=352", executed.stdout)
            fixture.inspect(self.source)


if __name__ == "__main__":
    unittest.main()
