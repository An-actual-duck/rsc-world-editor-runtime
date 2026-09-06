#!/usr/bin/env python3
"""Closed v5 input and real native save contracts; all packages are disposable."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "server/core.jar"

HARNESS = r'''
import java.nio.file.*;
import java.lang.reflect.*;
import java.util.*;
import com.openrsc.layeredmaps.LayeredWorldPackageManifest;
import com.openrsc.server.io.*;
import com.openrsc.server.content.worldedit.*;

public final class BlockedVoidRoamHarness {
  public static void main(String[] args) throws Exception {
    Path root = Paths.get(args[1]);
    if (args[0].equals("tools")) {
      LayeredWorldPackageManifest.load(root);
    } else {
      NativeLayeredWorldPackage source = NativeLayeredWorldPackage.load(root);
      NativeLayeredWorldRuntimeProfile.WORLD_BUILDER_INSTALLED.validate(
        NativeLayeredWorldPackageCatalog.of(Collections.singletonList(source)));
      if (args[0].equals("save")) {
        // Exercise the actual session snapshot and atomic publisher, not a v5 test writer.
        WorldEditorSessionManager sessions = new WorldEditorSessionManager();
        Method snapshot = sessions.getClass().getDeclaredMethod("adaptiveDraft", NativeLayeredWorldPackage.class);
        snapshot.setAccessible(true);
        AdaptiveWorldBuilderPackagePublisher.Draft draft =
          (AdaptiveWorldBuilderPackagePublisher.Draft)snapshot.invoke(sessions, source);
        Path baseline = Paths.get(args[2]);
        AdaptiveWorldBuilderPackagePublisher.publish(root, baseline,
          AdaptiveWorldBuilderPackageGuard.requireClosedPackage(root).getFingerprint(),
          AdaptiveWorldBuilderPackageGuard.requireClosedPackage(baseline).getFingerprint(),
          draft, value -> {}, AdaptiveWorldBuilderPackagePublisher.NO_OBSERVER);
        NativeLayeredWorldPackage saved = NativeLayeredWorldPackage.load(root);
        if (source.allowsBlockedVoidNpcRoaming() != saved.allowsBlockedVoidNpcRoaming())
          throw new AssertionError("snapshot downgraded coverage");
      }
    }
    System.out.println("accepted");
  }
}
'''


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(value, separators=(",", ":")) + "\n").encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def package(root, version=5):
    root.mkdir()
    terrain = bytes(10 * 48 * 48)
    (root / "terrain.raw").write_bytes(terrain)
    payload = {
        "schemaVersion": version, "encoding": f"layered-world-placements-v{version}",
        "worldSpace": "global", "level": 0,
        "npcs": [{"placementId": "npc-one", "npcId": 11,
                  "start": {"x": 47, "y": 24},
                  "roamBounds": {"minimum": {"x": 46, "y": 22},
                                 "maximum": {"x": 50, "y": 26}},
                  "respawnSeconds": 17}],
        "groundItems": [], "scenery": [], "boundaries": [],
    }
    if version == 5:
        payload["npcRoamCoverage"] = "blocked-void"
    if version == 3:
        del payload["npcs"][0]["respawnSeconds"]
    manifest = {
        "schemaVersion": 1, "packageType": "layered-world",
        "packageId": "test.blocked-void", "packageVersion": "1.0.0",
        "coordinateModel": "signed-layered-v1",
        "storage": {"sectorSize": 48, "presentationChunkSize": 24},
        "worldSpaces": [{"id": "global", "kind": "static"}],
        "levels": [{"worldSpace": "global", "level": 0, "name": "Surface", "role": "surface"}],
        "terrainSectors": [{"worldSpace": "global", "level": 0, "sectorX": 0, "sectorY": 0,
                            "encoding": "raw-layered-sector-v1", "path": "terrain.raw",
                            "sha256": hashlib.sha256(terrain).hexdigest()}],
        "placementSets": [{"id": "global-npcs", "worldSpace": "global", "level": 0,
                           "encoding": payload["encoding"], "path": "placements.json",
                           "sha256": write_json(root / "placements.json", payload)}],
    }
    write_json(root / "manifest.json", manifest)
    return payload


def update(root, payload):
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["placementSets"][0]["sha256"] = write_json(root / "placements.json", payload)
    write_json(root / "manifest.json", manifest)


class BlockedVoidRoamTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CORE.is_file():
            raise RuntimeError("Build the actual server first with scripts/build-server.sh")
        cls.temporary = tempfile.TemporaryDirectory(prefix="blocked-void-roam-classes-")
        cls.classes = Path(cls.temporary.name)
        source = cls.classes / "BlockedVoidRoamHarness.java"
        source.write_text(HARNESS)
        subprocess.run(["javac", "-source", "8", "-target", "8", "-cp", str(CORE),
                        "-d", str(cls.classes), str(source),
                        *map(str, (ROOT / "tools/layered-maps/src").rglob("*.java"))],
                       check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_harness(self, mode, root, *extra):
        return subprocess.run(["java", "-cp", f"{self.classes}:{CORE}",
                               "BlockedVoidRoamHarness", mode, str(root), *map(str, extra)],
                              capture_output=True, text=True, timeout=30)

    def test_schema_v5_is_closed_and_old_schema_fails_closed(self):
        schema_root = ROOT / "tools/layered-maps/schema"
        schemas = [json.loads((schema_root / name).read_text()) for name in (
            "layered-world-placements-v4.schema.json", "layered-world-placements-v5.schema.json")]
        registry = Registry().with_resources((value["$id"], Resource.from_contents(value)) for value in schemas)
        validator = Draft202012Validator(schemas[1], registry=registry)
        with tempfile.TemporaryDirectory(prefix="blocked-void-schema-") as temporary:
            payload = package(Path(temporary) / "package")
            validator.validate(payload)
            self.assertTrue(list(Draft202012Validator(schemas[0]).iter_errors(payload)))
            for policy in (None, "terrain-covered", "unknown"):
                changed = copy.deepcopy(payload)
                if policy is None:
                    changed.pop("npcRoamCoverage")
                else:
                    changed["npcRoamCoverage"] = policy
                self.assertTrue(list(validator.iter_errors(changed)))
            manifest = json.loads((Path(temporary) / "package/manifest.json").read_text())
            manifest_validator = Draft202012Validator(json.loads((schema_root / "layered-world-package-v1.schema.json").read_text()))
            manifest_validator.validate(manifest)
            manifest["placementSets"].append(dict(manifest["placementSets"][0], encoding="layered-world-placements-v4"))
            self.assertTrue(list(manifest_validator.iter_errors(manifest)))

    def test_v5_accepts_exact_bounds_and_both_older_versions_refuse_void(self):
        with tempfile.TemporaryDirectory(prefix="blocked-void-input-") as temporary:
            for version in (3, 4, 5):
                root = Path(temporary) / str(version)
                package(root, version)
                for reader in ("tools", "native"):
                    result = self.run_harness(reader, root)
                    self.assertEqual(version == 5, result.returncode == 0, result.stderr)

    def test_closed_policy_bounds_identity_and_present_anchor(self):
        with tempfile.TemporaryDirectory(prefix="blocked-void-negative-") as temporary:
            root = Path(temporary) / "package"
            original = package(root)
            mutations = [
                lambda p: p.pop("npcRoamCoverage"),
                lambda p: p.update(npcRoamCoverage="terrain-covered"),
                lambda p: p.update(extra=True),
                lambda p: p.update(schemaVersion=4),
                lambda p: p["npcs"][0]["start"].update(x=48),
                lambda p: p["npcs"][0]["start"].update(level=1),
                lambda p: p["npcs"][0]["roamBounds"]["maximum"].update(x=176),
                lambda p: p["npcs"][0]["roamBounds"]["minimum"].update(x=51),
                lambda p: p["npcs"][0]["roamBounds"]["minimum"].update(x=46.5),
                lambda p: p["npcs"].append(copy.deepcopy(p["npcs"][0])),
            ]
            for index, mutate in enumerate(mutations):
                payload = copy.deepcopy(original)
                mutate(payload)
                update(root, payload)
                for reader in ("tools", "native"):
                    with self.subTest(index=index, reader=reader):
                        result = self.run_harness(reader, root)
                        self.assertNotEqual(0, result.returncode, result.stdout)

    def test_actual_session_snapshot_atomic_publish_keeps_v5_without_terrain_growth(self):
        with tempfile.TemporaryDirectory(prefix="blocked-void-save-") as temporary:
            root = Path(temporary) / "working"
            original = package(root)
            duplicate = copy.deepcopy(original["npcs"][0])
            duplicate["placementId"] = "npc-two"
            original["npcs"].append(duplicate)
            update(root, original)
            baseline = Path(temporary) / "baseline"
            shutil.copytree(root, baseline)
            for _ in range(2):
                result = self.run_harness("save", root, baseline)
                self.assertEqual(0, result.returncode, result.stderr)
                manifest = json.loads((root / "manifest.json").read_text())
                self.assertEqual(1, len(manifest["terrainSectors"]))
                declaration = manifest["placementSets"][0]
                self.assertEqual("layered-world-placements-v5", declaration["encoding"])
                payload = json.loads((root / declaration["path"]).read_text())
                self.assertEqual("blocked-void", payload["npcRoamCoverage"])
                self.assertEqual(original["npcs"], payload["npcs"])

    def test_mixed_v5_and_older_payloads_are_rejected_even_when_empty(self):
        with tempfile.TemporaryDirectory(prefix="blocked-void-mixed-") as temporary:
            for empty in (False, True):
                root = Path(temporary) / str(empty)
                payload = package(root)
                if empty:
                    payload["npcs"] = []
                    update(root, payload)
                older = copy.deepcopy(payload)
                older.update(schemaVersion=4, encoding="layered-world-placements-v4")
                older.pop("npcRoamCoverage")
                older["npcs"] = []
                manifest = json.loads((root / "manifest.json").read_text())
                manifest["placementSets"].append({
                    "id": "old-empty", "worldSpace": "global", "level": 0,
                    "encoding": older["encoding"], "path": "older.json",
                    "sha256": write_json(root / "older.json", older),
                })
                write_json(root / "manifest.json", manifest)
                for reader in ("tools", "native"):
                    result = self.run_harness(reader, root)
                    self.assertNotEqual(0, result.returncode)
                    self.assertIn("v5 for every placement set", result.stderr)


if __name__ == "__main__":
    unittest.main()
