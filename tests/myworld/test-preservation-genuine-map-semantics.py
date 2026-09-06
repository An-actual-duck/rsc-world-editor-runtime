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
import importlib.util

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
        self.run_case(False)

    def test_wrong_client_overlay_control_remains_blocked_after_ladder_removal(self):
        self.run_case(True)

    def test_packaged_real_transition_consumers_use_server_selected_map(self):
        spec = importlib.util.spec_from_file_location("transition_fixture", ROOT / "tests/myworld/test-preservation-transition-execution.py")
        transitions = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(transitions)
        harness = transitions.HARNESS
        self.assertEqual(1,harness.count("NativeLayeredWorldRuntimeProfile.PRESERVATION_PACKAGE_ID"))
        harness = harness.replace("NativeLayeredWorldRuntimeProfile.PRESERVATION_PACKAGE_ID",json.dumps(self.manifest["packageId"]))
        harness = harness.replace("NativeLayeredWorldRuntimeProfile.PRESERVATION_R64_REPLACEMENT",
                                  "NativeLayeredWorldRuntimeProfile.WORLD_BUILDER_INSTALLED")
        built = subprocess.run(["python3","scripts/build-current-base.py","--test-allow-dirty"],cwd=ROOT,
                               capture_output=True,text=True,timeout=240)
        self.assertEqual(0,built.returncode,built.stdout+built.stderr)
        with tempfile.TemporaryDirectory(prefix="genuine-map-transitions-") as temporary:
            root=Path(temporary)
            package=root/"package"
            shutil.copytree(self.source/"conversion/package",package)
            runtime=self.make_runtime(root,package)
            source=root/"PreservationTransitionExecution.java"
            source.write_text(harness)
            classpath=os.pathsep.join(map(str,(root,OUTPUT/"server/core.jar",OUTPUT/"server/plugins.jar")))
            compiled=subprocess.run(["javac","-source","8","-target","8","-cp",classpath,"-d",str(root),str(source)],
                                    capture_output=True,text=True,timeout=30)
            self.assertEqual(0,compiled.returncode,compiled.stdout+compiled.stderr)
            executed=subprocess.run(["java","-Xmx1536m","-Dopenrsc.currentCompositionIdentityFile="
                                      +str(OUTPUT/"composition-identity.json"),"-cp",classpath,
                                      "com.openrsc.server.PreservationTransitionExecution"],cwd=runtime,
                                     capture_output=True,text=True,timeout=60)
            self.assertEqual(0,executed.returncode,(executed.stdout+executed.stderr)[-8000:])
            self.assertIn("preservation-transition-execution: verified",executed.stdout)
            fixture.inspect(self.source)

    def make_runtime(self,root,package):
        runtime=root/"runtime"
        runtime.mkdir()
        with zipfile.ZipFile(OUTPUT/"server/content.zip") as archive:
            archive.extractall(runtime)
        shutil.copyfile(OUTPUT/"server/plugins.jar",runtime/"plugins.jar")
        config=runtime/"current-base.conf"
        config.write_text(config.read_text()+"\n"+"\n".join((
            "want_layered_player_location_authority: true",
            "want_layered_spatial_runtime_authority: true",
            "want_layered_protocol_client_authority: true",
            "want_layered_native_terrain_package: true",
            "layered_native_world_runtime_profile: world-builder-installed",
            "layered_native_terrain_package_path: "+str(package),
            "layered_native_terrain_manifest_sha256: "+fixture.digest((package/"manifest.json").read_bytes()),
        ))+"\n")
        return runtime

    def test_packaged_client_cpu_windows_preserve_fields_and_do_not_load_client_only_terrain(self):
        built=subprocess.run(["python3","scripts/build-current-base.py","--test-allow-dirty"],cwd=ROOT,
                             capture_output=True,text=True,timeout=240)
        self.assertEqual(0,built.returncode,built.stdout+built.stderr)
        with tempfile.TemporaryDirectory(prefix="genuine-map-client-cpu-") as temporary:
            root=Path(temporary)
            fingerprint=fixture.digest(b"".join(
                path.relative_to(self.source/"conversion/package").as_posix().encode()+b"\0"
                +str(path.stat().st_size).encode()+b"\0"+fixture.digest(path.read_bytes()).encode()+b"\n"
                for path in sorted((self.source/"conversion/package").rglob("*")) if path.is_file()))
            relative="world-builder/packages/"+fingerprint+"/package"
            shutil.copytree(self.source/"conversion/package",root/relative)
            profile=root/"world-builder-configs/installed-client.json"
            profile.parent.mkdir()
            profile.write_text(json.dumps(dict(schemaVersion=1,manifestType="world-builder-installed-client-profile",
                active=True,packageId=self.manifest["packageId"],packageVersion=self.manifest["packageVersion"],
                packageFingerprintSha256=fingerprint,manifestSha256=fixture.SEALED["conversion/package/manifest.json"],
                packageRelativePath=relative)))
            jar=OUTPUT/"client/Open_RSC_Client.jar"
            artifact_classpath=os.pathsep.join(map(str,(jar,OUTPUT/"server/core.jar")))
            source=ROOT/"tests/myworld/fixtures/current-base-public/GenuineMapClientWindowProbe.java"
            compiled=subprocess.run(["javac","-source","8","-target","8","-cp",artifact_classpath,"-d",str(root),str(source)],
                                    capture_output=True,text=True,timeout=30)
            self.assertEqual(0,compiled.returncode,compiled.stdout+compiled.stderr)
            executed=subprocess.run(["java","-Djava.awt.headless=true","-Xmx768m",
                "-Dopenrsc.currentCompositionIdentityFile="+str(OUTPUT/"composition-identity.json"),
                "-cp",str(root)+os.pathsep+artifact_classpath,"orsc.GenuineMapClientWindowProbe"],cwd=root,
                capture_output=True,text=True,timeout=60)
            self.assertEqual(0,executed.returncode,(executed.stdout+executed.stderr)[-6000:])
            self.assertIn("GENUINE_CLIENT_CPU windows=352",executed.stdout)
            self.assertIn("legacyReads=0",executed.stdout)
            fixture.inspect(self.source)

    def run_case(self, wrong_overlay):
        built = subprocess.run(["python3", "scripts/build-current-base.py", "--test-allow-dirty"],
                               cwd=ROOT, capture_output=True, text=True, timeout=240)
        self.assertEqual(0, built.returncode, built.stdout + built.stderr)
        with tempfile.TemporaryDirectory(prefix="genuine-map-runtime-") as temporary:
            root = Path(temporary)
            package = root / "package"
            shutil.copytree(self.source / "conversion/package", package)
            if wrong_overlay:
                manifest = json.loads((package / "manifest.json").read_text())
                row = next(row for row in manifest["terrainSectors"]
                           if (row["sectorX"],row["sectorY"],row["level"]) == (6,10,-1))
                raw = package / row["path"]
                values = bytearray(raw.read_bytes())
                offset = ((312 % 48)*48 + 516 % 48)*11 + 3
                self.assertEqual(0,values[offset])
                values[offset] = 8
                raw.write_bytes(values)
                row["sha256"] = fixture.digest(values)
                (package / "manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
            oracle = root / "historical-terrain.bin"
            terrain = fixture.terrain_oracle(self.source, self.decoded, oracle)
            population = root / "historical-populated.bin"
            fixture.placement_oracle(self.source, terrain, population)
            tree_diagnostic = root / "diagnostic-owner-tree-projectiles.bin"
            fixture.placement_oracle(self.source, terrain, tree_diagnostic, diagnostic_tree_branch=True)
            npcs = root / "historical-npcs.tsv"
            fixture.npc_expectations(self.source, self.manifest, npcs)
            runtime = self.make_runtime(root,package)
            source = ROOT / "tests/myworld/fixtures/current-base-public/GenuineMapSemanticsProbe.java"
            classpath = os.pathsep.join(map(str, (root, OUTPUT / "server/core.jar", OUTPUT / "server/plugins.jar")))
            compiled = subprocess.run(["javac", "-source", "8", "-target", "8", "-cp", classpath,
                                       "-d", str(root), str(source)], capture_output=True, text=True, timeout=30)
            self.assertEqual(0, compiled.returncode, compiled.stdout + compiled.stderr)
            executed = subprocess.run(["java", "-Xmx1536m", "-Dopenrsc.currentCompositionIdentityFile="
                                       + str(OUTPUT / "composition-identity.json"), "-cp", classpath,
                                       "com.openrsc.server.GenuineMapSemanticsProbe", str(oracle), str(npcs), str(population),
                                       str(tree_diagnostic), str(wrong_overlay).lower()],
                                      cwd=runtime, capture_output=True, text=True, timeout=90)
            diagnostics = "\n".join(line for line in (executed.stdout + executed.stderr).splitlines()
                                    if "GENUINE_" in line or "Exception" in line or "AssertionError" in line or "at com.openrsc" in line)
            self.assertEqual(0, executed.returncode, diagnostics or (executed.stdout + executed.stderr)[-5000:])
            self.assertIn("GENUINE_TERRAIN compared=811008 differences=" + ("1" if wrong_overlay else "0"), executed.stdout)
            self.assertIn("GENUINE_POPULATION npcs=3609 voidBounds=146 sectors=352", executed.stdout)
            self.assertIn("GENUINE_LADDER before=", executed.stdout)
            fixture.inspect(self.source)


if __name__ == "__main__":
    unittest.main()
