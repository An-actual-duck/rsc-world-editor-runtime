#!/usr/bin/env python3
"""Client/server agreement tests for isolated declarative project content."""

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import textwrap
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[2]
SERVER_JAR = ROOT / "server/core.jar"
CLIENT_JAR = ROOT / "Client_Base/Open_RSC_Client.jar"


CLIENT_HARNESS = r"""
import com.openrsc.client.entityhandling.EntityHandler;
import java.lang.reflect.Method;
import java.nio.file.Path;
import java.nio.file.Paths;
import org.json.JSONArray;
import orsc.ProjectCustomContent;

public final class ProjectCustomContentClientHarness {
    public static void main(String[] args) throws Exception {
        ProjectCustomContent content = ProjectCustomContent.load(
            Paths.get(args[0]), Paths.get(args[1]), Paths.get(args[2]),
            "creator.definitions.v2", "creator.assets.v1");
        if (!content.isPresent()) {
            System.out.println("empty");
            return;
        }
        JSONArray npcs = content.definitions().getJSONArray("npcs");
        if (npcs.length() != 1 || npcs.getJSONObject(0).getInt("id") != 846) {
            throw new AssertionError("beyond-base NPC 846 is missing");
        }
        if (content.texture(55) == null
            || content.animation(1080) == null
            || content.item(3309) == null
            || content.model("creator-crystal") == null
            || content.assetCount() != 4) {
            throw new AssertionError("custom asset family mapping is incomplete");
        }
        EntityHandler.load(true);
        if (EntityHandler.textureCount() != 55
            || EntityHandler.animationCount() != 1080
            || EntityHandler.tileCount() != 26
            || EntityHandler.doorCount() != 214
            || EntityHandler.objectCount() != 1332
            || EntityHandler.npcCount() != 845
            || EntityHandler.itemCount() != 3309) {
            throw new AssertionError("fixture no longer begins at the packaged catalog boundary");
        }
        Method apply = EntityHandler.class.getDeclaredMethod(
            "applyAdaptiveProjectContent", ProjectCustomContent.class);
        apply.setAccessible(true);
        apply.invoke(null, content);
        if (EntityHandler.textureCount() != 56
            || EntityHandler.animationCount() != 1081
            || EntityHandler.tileCount() != 27
            || EntityHandler.doorCount() != 215
            || EntityHandler.objectCount() != 1333
            || EntityHandler.npcCount() != 847
            || EntityHandler.itemCount() != 3310
            || EntityHandler.getNpcDef(845) != null
            || !"Creator NPC".equals(EntityHandler.getNpcDef(846).getName())
            || !"Creator crystal".equals(EntityHandler.getObjectDef(1332).getName())
            || !"Creator wall".equals(EntityHandler.getDoorDef(214).getName())
            || EntityHandler.getTileDef(26).getColour() != 55
            || !"Creator item".equals(EntityHandler.getItemDef(3309).getName())) {
            throw new AssertionError("custom definitions were not applied exactly");
        }
        System.out.println(content.bundleId() + "@" + content.bundleVersion());
    }
}
"""


SERVER_HARNESS = r"""
import com.openrsc.server.ServerConfiguration;
import com.openrsc.server.content.worldedit.AdaptiveWorldBuilderCustomContentCatalog;
import com.openrsc.server.content.worldedit.WorldEditStorageContext;
import java.lang.reflect.Constructor;
import java.nio.file.Path;
import java.nio.file.Paths;
import org.json.JSONArray;

public final class ProjectCustomContentServerHarness {
    public static void main(String[] args) throws Exception {
        Path workspace = Paths.get(args[0]).toRealPath();
        Path working = workspace.resolve("working").toRealPath();
        Constructor<WorldEditStorageContext> constructor =
            WorldEditStorageContext.class.getDeclaredConstructor(
                boolean.class, boolean.class, Path.class, Path.class,
                Path.class, Path.class, Path.class, Path.class, Path.class,
                Path.class);
        constructor.setAccessible(true);
        WorldEditStorageContext storage = constructor.newInstance(
            true, true, workspace, workspace.resolve("source"), working,
            working.resolve("runtime/server"), working.resolve("runtime/client"),
            working.resolve("runtime/server/conf"), workspace.resolve("run/backups"),
            workspace.resolve("source/layered-baseline/package"));
        ServerConfiguration config = new ServerConfiguration();
        config.WORLD_BUILDER_DEFINITION_ID = "creator.definitions.v2";
        config.WORLD_BUILDER_DEFINITION_EVIDENCE_PATH = args[1];
        config.WORLD_BUILDER_DEFINITION_SHA256 = args[3];
        config.WORLD_BUILDER_ASSET_ID = "creator.assets.v1";
        config.WORLD_BUILDER_ASSET_EVIDENCE_PATH = args[2];
        config.WORLD_BUILDER_ASSET_SHA256 = args[4];
        AdaptiveWorldBuilderCustomContentCatalog content =
            AdaptiveWorldBuilderCustomContentCatalog.load(config, storage);
        if (!content.hasCustomContent()) {
            System.out.println("empty");
            return;
        }
        JSONArray npcs = content.definitions().getJSONArray("npcs");
        if (npcs.length() != 1 || npcs.getJSONObject(0).getInt("id") != 846) {
            throw new AssertionError("beyond-base NPC 846 is missing");
        }
        if (content.assets().size() != 4) {
            throw new AssertionError("custom asset family mapping is incomplete");
        }
        System.out.println(content.bundleId() + "@" + content.bundleVersion());
    }
}
"""


def canonical_json(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def write_png(path: Path, width: int, height: int):
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    row = b"\x00" + b"\x40\x80\xc0\xff" * width
    payload = b"\x89PNG\r\n\x1a\n"
    payload += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    payload += chunk(b"IDAT", zlib.compress(row * height))
    payload += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def write_ob3(path: Path):
    # Three zero-valued vertices, one triangular face, and indices 0,1,2.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x00\x03\x00\x01" + b"\x00" * 18
        + b"\x03\x00\x00\x00\x00" + b"\x00\x01\x02"
    )


def entity(name):
    return {
        "name": name, "description": "Project-local fixture",
        "command1": "Use", "command2": "Examine",
    }


def fixture_documents(root: Path):
    evidence = root / "working/runtime/shared/evidence"
    evidence.mkdir(parents=True)
    paths = {
        "animation": evidence / "assets/npc-animation.png",
        "item": evidence / "assets/item.png",
        "model": evidence / "assets/model.ob3",
        "texture": evidence / "assets/texture.png",
    }
    write_png(paths["animation"], 30, 2)
    write_png(paths["item"], 2, 2)
    write_ob3(paths["model"])
    write_png(paths["texture"], 64, 64)
    asset_specs = [
        ("animation.creator", "npc-animation-png", paths["animation"], 30, 2, 15),
        ("item.creator", "item-sprite-png", paths["item"], 2, 2, 1),
        ("model.creator", "scenery-model-ob3", paths["model"], 0, 0, 0),
        ("texture.creator", "texture-png", paths["texture"], 64, 64, 1),
    ]
    assets = []
    for key, kind, path, width, height, frames in asset_specs:
        relative = path.relative_to(evidence).as_posix()
        data = path.read_bytes()
        assets.append({
            "key": key, "kind": kind, "path": relative, "size": len(data),
            "sha256": sha256_bytes(data), "width": width, "height": height,
            "frames": frames,
        })
    inventory = "".join(
        f"{row['key']}\t{row['kind']}\t{row['path']}\t{row['size']}\t"
        f"{row['sha256']}\t{row['width']}\t{row['height']}\t{row['frames']}\n"
        for row in assets
    ).encode()
    manifest = {
        "schemaVersion": 1,
        "manifestType": "world-builder-custom-content-assets",
        "manifestId": "creator.assets.v1",
        "bundleId": "creator.shared-area",
        "bundleVersion": "1.2.3",
        "inventorySha256": sha256_bytes(inventory),
        "assets": assets,
    }
    content = {
        "schemaVersion": 1,
        "bundleId": "creator.shared-area",
        "bundleVersion": "1.2.3",
        "assetManifestId": "creator.assets.v1",
        "textures": [{
            "id": 55, "operation": "add", "dataName": "creator-floor",
            "animationName": "", "assetKey": "texture.creator",
        }],
        "animations": [{
            "id": 1080, "operation": "add", "name": "creator-npc",
            "category": "project", "charColour": 0, "blueMask": 0,
            "genderModel": 0, "hasA": False, "hasF": False,
            "assetKey": "animation.creator", "frameCount": 15,
        }],
        "tiles": [{
            "id": 26, "operation": "add", "colour": 55,
            "tileValue": 0, "objectType": 0,
        }],
        "boundaries": [{
            "id": 214, "operation": "add", **entity("Creator wall"),
            "doorType": 1, "unknown": 0, "wallHeight": 128,
            "modelVar2": 55, "modelVar3": 55,
        }],
        "scenery": [{
            "id": 1332, "operation": "add", **entity("Creator crystal"),
            "type": 1, "width": 1, "height": 1, "groundItemVar": 0,
            "modelName": "creator-crystal", "assetKey": "model.creator",
        }],
        "npcs": [{
            "id": 846, "operation": "add", **entity("Creator NPC"),
            "attack": 1, "strength": 1, "hits": 1, "defense": 1,
            "ranged": False, "projectileRange": 0,
            "meleeOffense": 0, "rangedOffense": 0, "magicOffense": 0,
            "meleeDefense": 0, "rangedDefense": 0, "magicDefense": 0,
            "combatLevel": 1, "members": False, "attackable": False,
            "aggressive": False, "respawnTime": 60,
            "sprites": [1080] + [-1] * 11,
            "hairColour": 0, "topColour": 0, "bottomColour": 0,
            "skinColour": 0, "camera1": 128, "camera2": 128,
            "walkModel": 1, "combatModel": 1, "combatSprite": 0,
            "roundMode": 0,
        }],
        "items": [{
            "id": 3309, "operation": "add", "name": "Creator item",
            "description": "Project-local fixture", "command": "Take",
            "isFemaleOnly": False, "isMembersOnly": False,
            "isStackable": False, "isUntradable": False,
            "isWearable": False, "appearanceId": 0, "wearableId": 0,
            "wearSlot": 0, "requiredLevel": 0, "requiredSkillId": 0,
            "armourBonus": 0, "weaponAimBonus": 0, "weaponPowerBonus": 0,
            "magicBonus": 0, "prayerBonus": 0, "basePrice": 1,
            "isNoteable": False, "meleeOffense": 0, "rangedOffense": 0,
            "magicOffense": 0, "weaponSpeed": 0, "meleeDefense": 0,
            "rangedDefense": 0, "magicDefense": 0, "spriteId": 3309,
            "spriteLocation": "", "assetKey": "item.creator",
        }],
    }
    catalog = {
        "schemaVersion": 2,
        "manifestType": "world-builder-definition-catalog",
        "catalogId": "creator.definitions.v2",
        "tiles": [26], "boundaries": [214], "scenery": [1332],
        "npcs": [846], "groundItems": [3309], "customContent": content,
    }
    return evidence, catalog, manifest, paths


def write_documents(evidence: Path, catalog, manifest):
    catalog_path = evidence / "definitions.json"
    manifest_path = evidence / "assets.json"
    catalog_path.write_bytes(canonical_json(catalog))
    manifest_path.write_bytes(canonical_json(manifest))
    return catalog_path, manifest_path


def refresh_manifest(manifest, evidence: Path):
    for row in manifest["assets"]:
        data = (evidence / row["path"]).read_bytes()
        row["size"] = len(data)
        row["sha256"] = sha256_bytes(data)
    inventory = "".join(
        f"{row['key']}\t{row['kind']}\t{row['path']}\t{row['size']}\t"
        f"{row['sha256']}\t{row['width']}\t{row['height']}\t{row['frames']}\n"
        for row in manifest["assets"]
    ).encode()
    manifest["inventorySha256"] = sha256_bytes(inventory)


class ProjectCustomContentRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SERVER_JAR.is_file() or not CLIENT_JAR.is_file():
            raise RuntimeError("Build client and server before running this test")
        cls.classes = tempfile.TemporaryDirectory(prefix="project-content-classes-")
        classes = Path(cls.classes.name)
        sources = [
            ("ProjectCustomContentClientHarness.java", CLIENT_HARNESS, CLIENT_JAR),
            ("ProjectCustomContentServerHarness.java", SERVER_HARNESS, SERVER_JAR),
        ]
        for name, source, jar in sources:
            source_path = classes / name
            source_path.write_text(textwrap.dedent(source), encoding="utf-8")
            result = subprocess.run(
                ["javac", "-source", "8", "-target", "8", "-cp", str(jar),
                 "-d", str(classes), str(source_path)],
                cwd=ROOT, capture_output=True, text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"Unable to compile {name}:\n{result.stdout}{result.stderr}"
                )
        cls.client_classpath = os.pathsep.join((str(classes), str(CLIENT_JAR)))
        cls.server_classpath = os.pathsep.join((str(classes), str(SERVER_JAR)))

    @classmethod
    def tearDownClass(cls):
        cls.classes.cleanup()

    def run_both(self, root, catalog_path, manifest_path):
        catalog_hash = sha256_bytes(catalog_path.read_bytes())
        manifest_hash = (sha256_bytes(manifest_path.read_bytes())
                         if manifest_path.is_file() else "0" * 64)
        client = subprocess.run(
            ["java", "-cp", self.client_classpath,
             "ProjectCustomContentClientHarness", str(root), str(catalog_path),
             str(manifest_path)], cwd=ROOT, capture_output=True, text=True,
        )
        server = subprocess.run(
            ["java", "-cp", self.server_classpath,
             "ProjectCustomContentServerHarness", str(root), str(catalog_path),
             str(manifest_path), catalog_hash, manifest_hash],
            cwd=ROOT, capture_output=True, text=True,
        )
        return client, server

    def test_all_definition_and_asset_families_agree_with_beyond_base_npc(self):
        with tempfile.TemporaryDirectory(prefix="project-content-valid-") as temp:
            root = Path(temp)
            evidence, catalog, manifest, _ = fixture_documents(root)
            catalog_path, manifest_path = write_documents(evidence, catalog, manifest)
            client, server = self.run_both(root, catalog_path, manifest_path)
            for result in (client, server):
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(
                    "creator.shared-area@1.2.3",
                    result.stdout.strip().splitlines()[-1],
                )

    def test_material_free_schema_one_needs_no_custom_asset_manifest(self):
        with tempfile.TemporaryDirectory(prefix="project-content-empty-") as temp:
            root = Path(temp)
            evidence = root / "working/runtime/shared/evidence"
            evidence.mkdir(parents=True)
            catalog = {
                "schemaVersion": 1,
                "manifestType": "world-builder-definition-catalog",
                "catalogId": "creator.definitions.v2",
                "tiles": [], "boundaries": [], "scenery": [], "npcs": [],
                "groundItems": [],
            }
            catalog_path = evidence / "definitions.json"
            catalog_path.write_bytes(canonical_json(catalog))
            missing = evidence / "absent-assets.json"
            client, server = self.run_both(root, catalog_path, missing)
            for result in (client, server):
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("empty", result.stdout.strip())

    def test_both_sides_reject_hostile_or_disagreeing_evidence(self):
        mutations = {
            "unknown-catalog-key": lambda c, m, e: c.update({"code": "never"}),
            "bundle-disagreement": lambda c, m, e: m.update({"bundleId": "other.bundle"}),
            "wrong-asset-hash": lambda c, m, e: m["assets"][0].update({"sha256": "0" * 64}),
            "traversal": lambda c, m, e: m["assets"][0].update({"path": "../escape.png"}),
            "wrong-kind": lambda c, m, e: m["assets"][0].update({"kind": "texture-png"}),
            "missing-dependency": lambda c, m, e: c["customContent"]["textures"][0].update({"assetKey": "absent"}),
            "unsafe-operation": lambda c, m, e: c["customContent"]["items"][0].update({"operation": "merge"}),
            "duplicate-id": lambda c, m, e: c["customContent"]["tiles"].append(copy.deepcopy(c["customContent"]["tiles"][0])),
            "frame-contract": lambda c, m, e: c["customContent"]["animations"][0].update({"hasA": True}),
            "unreferenced-asset": lambda c, m, e: c["customContent"]["items"].clear(),
            "texture-id-hole": lambda c, m, e: c["customContent"]["textures"][0].update({"id": 56}),
            "undefined-wall-texture": lambda c, m, e: c["customContent"]["boundaries"][0].update({"modelVar2": 56}),
            "undefined-npc-animation": lambda c, m, e: c["customContent"]["npcs"][0]["sprites"].__setitem__(0, 1081),
            "missing-scenery-model": lambda c, m, e: c["customContent"]["scenery"][0].update({"assetKey": ""}),
            "missing-item-sprite": lambda c, m, e: c["customContent"]["items"][0].update({"assetKey": ""}),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                    prefix=f"project-content-{name}-") as temp:
                root = Path(temp)
                evidence, catalog, manifest, _ = fixture_documents(root)
                mutate(catalog, manifest, evidence)
                catalog_path, manifest_path = write_documents(evidence, catalog, manifest)
                client, server = self.run_both(root, catalog_path, manifest_path)
                self.assertNotEqual(0, client.returncode, "client accepted " + name)
                self.assertNotEqual(0, server.returncode, "server accepted " + name)

    def test_both_sides_reject_links_and_malformed_payloads(self):
        cases = ("symlink", "hardlink", "bad-png", "bad-ob3", "bad-texture-size")
        for name in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                    prefix=f"project-content-{name}-") as temp:
                root = Path(temp)
                evidence, catalog, manifest, paths = fixture_documents(root)
                if name == "symlink":
                    original = paths["texture"].read_bytes()
                    target = evidence / "assets/actual-texture.png"
                    target.write_bytes(original)
                    paths["texture"].unlink()
                    paths["texture"].symlink_to(target.name)
                elif name == "hardlink":
                    target = evidence / "assets/actual-texture.png"
                    paths["texture"].rename(target)
                    os.link(target, paths["texture"])
                elif name == "bad-png":
                    paths["texture"].write_bytes(b"not a png")
                elif name == "bad-ob3":
                    paths["model"].write_bytes(b"\x00\x03\x00\x01")
                else:
                    write_png(paths["texture"], 32, 32)
                    texture_row = next(
                        row for row in manifest["assets"]
                        if row["key"] == "texture.creator"
                    )
                    texture_row["width"] = 32
                    texture_row["height"] = 32
                refresh_manifest(manifest, evidence)
                catalog_path, manifest_path = write_documents(evidence, catalog, manifest)
                client, server = self.run_both(root, catalog_path, manifest_path)
                self.assertNotEqual(0, client.returncode, "client accepted " + name)
                self.assertNotEqual(0, server.returncode, "server accepted " + name)


if __name__ == "__main__":
    unittest.main()
