#!/usr/bin/env python3
"""Exact client/server contract tests for Editor project-content-bundle-v1."""

import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
SERVER_JAR = ROOT / "server/core.jar"
CLIENT_JAR = ROOT / "Client_Base/Open_RSC_Client.jar"
ZERO = "0" * 64
CAPABILITY = "project-local-custom-content-v1"

SPECS = (
    ("asset.sprite.authentic", "client/Cache/video/Authentic_Sprites.orsc", "application/vnd.openrsc.archive", False),
    ("asset.sprite.custom", "client/Cache/video/Custom_Sprites.osar", "application/gzip", False),
    ("asset.library", "client/Cache/video/library.orsc", "application/vnd.openrsc.archive", False),
    ("asset.model", "client/Cache/video/models.orsc", "application/vnd.openrsc.archive", False),
    ("asset.spritepack", "client/Cache/video/spritepacks/Menus.osar", "application/gzip", False),
    ("definition.boundary", "server/conf/server/defs/DoorDef.xml", "application/xml", True),
    ("definition.scenery", "server/conf/server/defs/GameObjectDef.xml", "application/xml", True),
    ("definition.item.base", "server/conf/server/defs/ItemDefs.json", "application/json", True),
    ("definition.item.custom", "server/conf/server/defs/ItemDefsCustom.json", "application/json", True),
    ("definition.item.patch", "server/conf/server/defs/ItemDefsPatch18.json", "application/json", True),
    ("definition.item.world", "server/conf/server/defs/ItemDefsMyWorld.json", "application/json", True),
    ("definition.npc.base", "server/conf/server/defs/NpcDefs.json", "application/json", True),
    ("definition.npc.custom", "server/conf/server/defs/NpcDefsCustom.json", "application/json", True),
    ("definition.npc.patch", "server/conf/server/defs/NpcDefsPatch18.json", "application/json", True),
    ("definition.npc.world", "server/conf/server/defs/NpcDefsMyWorld.json", "application/json", True),
    ("definition.tile", "server/conf/server/defs/TileDef.xml", "application/xml", True),
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def deterministic_zip(name, payload):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
        entry.create_system = 3
        entry.external_attr = 0o100644 << 16
        entry.compress_type = zipfile.ZIP_STORED
        archive.writestr(entry, payload)
    return output.getvalue()


def deterministic_gzip(payload):
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as archive:
        archive.write(payload)
    return output.getvalue()


def xml_array(root, element, count, body):
    rows = "".join(f"<{element}>{body.format(index=i)}</{element}>" for i in range(count))
    return f"<{root}>{rows}</{root}>\n".encode()


def family_bindings():
    return [
        {"family": "floor", "definitionRoles": ["definition.tile"], "assetRoles": ["asset.sprite.custom"]},
        {"family": "ground-item", "definitionRoles": ["definition.item.base", "definition.item.custom", "definition.item.patch", "definition.item.world"], "assetRoles": ["asset.library", "asset.sprite.authentic", "asset.sprite.custom", "asset.spritepack"]},
        {"family": "npc", "definitionRoles": ["definition.npc.base", "definition.npc.custom", "definition.npc.patch", "definition.npc.world"], "assetRoles": ["asset.library", "asset.sprite.authentic", "asset.sprite.custom", "asset.spritepack"]},
        {"family": "scenery", "definitionRoles": ["definition.scenery"], "assetRoles": ["asset.library", "asset.model", "asset.sprite.custom"]},
        {"family": "wall", "definitionRoles": ["definition.boundary"], "assetRoles": ["asset.sprite.custom"]},
    ]


def fixture_payloads():
    return {
        "client/Cache/video/Authentic_Sprites.orsc": deterministic_zip("sprites/fixture.dat", b"authentic sprite fixture\n"),
        "client/Cache/video/Custom_Sprites.osar": deterministic_gzip(b"custom sprites: npc=846 item=9000 floor=31 wall=219 scenery=59\n"),
        "client/Cache/video/library.orsc": b"fixture library archive bytes v1\n",
        "client/Cache/video/models.orsc": b"fixture model archive: scenery=59\n",
        "client/Cache/video/spritepacks/Menus.osar": deterministic_gzip(b"fixture inventory sprites: item=9000\n"),
        "server/conf/server/defs/DoorDef.xml": xml_array("DoorDef-array", "DoorDef", 220, "<name>fixture-wall-{index}</name>"),
        "server/conf/server/defs/GameObjectDef.xml": xml_array("GameObjectDef-array", "GameObjectDef", 60, "<name>fixture-scenery-{index}</name><width>1</width><height>1</height>"),
        "server/conf/server/defs/ItemDefs.json": pretty({"item": [{"id": 0, "name": "fixture-base-item"}]}),
        "server/conf/server/defs/ItemDefsCustom.json": pretty({"items": [{"id": 9000, "name": "fixture-custom-item"}]}),
        "server/conf/server/defs/ItemDefsPatch18.json": pretty({"items": [{"id": 9002, "name": "fixture-patch-item"}]}),
        "server/conf/server/defs/ItemDefsMyWorld.json": pretty({"items": [{"id": 9001, "name": "fixture-world-item"}]}),
        "server/conf/server/defs/NpcDefs.json": pretty({"npcs": [{"id": 0, "name": "fixture-base-npc"}]}),
        "server/conf/server/defs/NpcDefsCustom.json": pretty({"npcs": [{"id": 12, "name": "fixture-appended-npc"}]}),
        "server/conf/server/defs/NpcDefsPatch18.json": pretty({"npcs": [{"id": 100, "name": "fixture-patch-npc"}]}),
        "server/conf/server/defs/NpcDefsMyWorld.json": pretty({"npcs": [{"id": 846, "name": "fixture-world-npc"}]}),
        "server/conf/server/defs/TileDef.xml": xml_array("TileDef-array", "TileDef", 32, "<colour>{index}</colour>"),
    }


def self_hash(value, field):
    copy = dict(value)
    copy[field] = ZERO
    return sha(canonical(copy))


def create_bundle(root):
    payloads = fixture_payloads()
    records = []
    for role, runtime_path, media, definition in sorted(SPECS, key=lambda row: row[1]):
        payload = payloads[runtime_path]
        destination = root / "files" / runtime_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        records.append({"role": role, "bundleRelativePath": "files/" + runtime_path,
                        "runtimeRelativePath": runtime_path, "mediaType": media,
                        "size": len(payload), "sha256": sha(payload)})
    catalog = {"schemaVersion": 1, "manifestType": "world-builder-definition-catalog",
               "catalogId": "target-adopted-content-v1", "tiles": list(range(32)),
               "boundaries": list(range(220)), "scenery": list(range(60)),
               "npcs": [0, 1, 100, 846], "groundItems": [0, 9000, 9001, 9002],
               "catalogSha256": ZERO}
    catalog["catalogSha256"] = self_hash(catalog, "catalogSha256")

    def domain_fingerprint(domain, definition):
        digest = hashlib.sha256(domain)
        definition_roles = {role for role, _, _, is_definition in SPECS if is_definition}
        for row in records:
            if (row["role"] in definition_roles) != definition:
                continue
            digest.update(f'{row["role"]}\0{row["runtimeRelativePath"]}\0{row["size"]}\0{row["sha256"]}\n'.encode())
        if definition:
            digest.update(catalog["catalogSha256"].encode())
        return digest.hexdigest()

    manifest = {"schemaVersion": 1, "manifestType": "world-builder-project-content-bundle",
                "capabilityId": CAPABILITY, "sourceKind": "target-adopted",
                "definitionCatalog": catalog, "familyBindings": family_bindings(), "files": records,
                "definitionFingerprintSha256": domain_fingerprint(b"world-builder-project-content-definitions-v1\n", True),
                "assetFingerprintSha256": domain_fingerprint(b"world-builder-project-content-assets-v1\n", False),
                "bundleFingerprintSha256": ZERO}
    manifest["bundleFingerprintSha256"] = sha(b"world-builder-project-content-bundle-v1\n" + canonical(manifest))
    (root / "manifest.json").write_bytes(pretty(manifest))
    return manifest


SERVER_HARNESS = r"""
import com.openrsc.server.ServerConfiguration;
import com.openrsc.server.content.worldedit.AdaptiveWorldBuilderProjectContentBundle;
import com.openrsc.server.content.worldedit.WorldEditStorageContext;
import java.lang.reflect.Constructor;
import java.nio.file.Path;
import java.nio.file.Paths;
public final class BundleServerHarness {
  public static void main(String[] args) throws Exception {
    Path workspace=Paths.get(args[0]).toRealPath(), working=workspace.resolve("working").toRealPath();
    Constructor<WorldEditStorageContext> c=WorldEditStorageContext.class.getDeclaredConstructor(boolean.class,boolean.class,Path.class,Path.class,Path.class,Path.class,Path.class,Path.class,Path.class,Path.class);
    c.setAccessible(true);
    WorldEditStorageContext storage=c.newInstance(true,true,workspace,workspace.resolve("source"),working,working.resolve("runtime/server"),working.resolve("runtime/client"),working.resolve("runtime/server/conf"),workspace.resolve("run/backups"),workspace.resolve("source/layered-baseline/package"));
    ServerConfiguration config=new ServerConfiguration();
    config.WORLD_BUILDER_CONTENT_BUNDLE_PATH=args[1]; config.WORLD_BUILDER_CONTENT_CAPABILITY_ID="project-local-custom-content-v1";
    config.WORLD_BUILDER_CONTENT_BUNDLE_SHA256=args[2]; config.WORLD_BUILDER_CONTENT_DEFINITION_SHA256=args[3]; config.WORLD_BUILDER_CONTENT_ASSET_SHA256=args[4];
    config.WORLD_BUILDER_CONTENT_ITEM_VISUAL_SHA256="0000000000000000000000000000000000000000000000000000000000000000";
    AdaptiveWorldBuilderProjectContentBundle bundle=AdaptiveWorldBuilderProjectContentBundle.load(config,storage);
    if (!bundle.isPresent() || !bundle.catalog().getJSONArray("npcs").toList().contains(846)) throw new AssertionError("NPC 846 absent");
    System.out.println(bundle.bundleSha256());
  }
}
"""


CLIENT_HARNESS = r"""
import java.nio.file.Paths;
import orsc.ProjectContentBundle;
public final class BundleClientHarness {
  public static void main(String[] args) throws Exception {
    ProjectContentBundle bundle=ProjectContentBundle.load(Paths.get(args[0]),args[1],"project-local-custom-content-v1",args[2],args[3],args[4]);
    if (!bundle.isPresent() || !bundle.catalog().getJSONArray("groundItems").toList().contains(9000)) throw new AssertionError("item 9000 absent");
    System.out.println(bundle.path("asset.model"));
  }
}
"""


CLIENT_ITEM_VISUAL_HARNESS = r"""
import com.openrsc.client.entityhandling.EntityHandler;
import com.openrsc.client.entityhandling.defs.ItemDef;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import org.json.JSONArray;
public final class BundleClientItemVisualHarness {
  public static void main(String[] args) throws Exception {
    Method apply=EntityHandler.class.getDeclaredMethod(
      "applyProjectItems", JSONArray.class, ItemDef[].class, boolean.class);
    apply.setAccessible(true);
    JSONArray rows=new JSONArray("[{\"id\":9000,\"name\":\"new item\"}]");
    try {
      apply.invoke(null, rows, new ItemDef[0], false);
      throw new AssertionError("bundle-v1 guessed a visual for new item 9000");
    } catch (InvocationTargetException failure) {
      Throwable cause=failure.getCause();
      if (!(cause instanceof IllegalArgumentException)
          || !cause.getMessage().contains("no authoritative client visual mapping")) {
        throw failure;
      }
      System.out.println(cause.getMessage());
    }
  }
}
"""


class BundleV1RuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = tempfile.TemporaryDirectory(prefix="bundle-v1-classes-")
        classes = Path(cls.classes.name)
        for name, source, jar in (("BundleServerHarness.java", SERVER_HARNESS, SERVER_JAR),
                                  ("BundleClientHarness.java", CLIENT_HARNESS, CLIENT_JAR),
                                  ("BundleClientItemVisualHarness.java", CLIENT_ITEM_VISUAL_HARNESS, CLIENT_JAR)):
            path = classes / name
            path.write_text(source)
            subprocess.run(["javac", "-cp", str(jar), "-d", str(classes), str(path)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.classes.cleanup()

    def workspace(self):
        temporary = tempfile.TemporaryDirectory(prefix="bundle-v1-runtime-")
        workspace = Path(temporary.name)
        for relative in ("working/content-bundle", "working/runtime/server", "working/runtime/client",
                         "working/runtime/server/conf", "source", "source/layered-baseline/package", "run"):
            (workspace / relative).mkdir(parents=True, exist_ok=True)
        manifest = create_bundle(workspace / "working/content-bundle")
        self.addCleanup(temporary.cleanup)
        return workspace, manifest

    def run_harness(self, name, jar, workspace, manifest, success=True):
        command = ["java", "-cp", f"{self.classes.name}:{jar}", name, str(workspace),
                   str(workspace / "working/content-bundle"), manifest["bundleFingerprintSha256"],
                   manifest["definitionFingerprintSha256"], manifest["assetFingerprintSha256"]]
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(0 if success else 1, 0 if result.returncode == 0 else 1, result.stdout)
        return result.stdout

    def test_canonical_editor_fixture_hashes_and_both_consumers(self):
        workspace, manifest = self.workspace()
        self.assertEqual("20a86967a205f0f63f502e5a333e8a5d30299df28a89b13251a36761de2e8420", manifest["definitionCatalog"]["catalogSha256"])
        self.assertEqual("50a1a2958fca3483dcae4fe5e8d9243a4262d79db4ce53109f009fd777e7f3a7", manifest["definitionFingerprintSha256"])
        self.assertEqual("3f035094478cf32a0e809083214524f4595d5847acde78a98291c3758112e70e", manifest["assetFingerprintSha256"])
        self.assertEqual("985489d7674e571ed99587adf97e6ff4121692096fec2b7bf00442dc2b325cd9", manifest["bundleFingerprintSha256"])
        self.run_harness("BundleServerHarness", SERVER_JAR, workspace, manifest)
        self.run_harness("BundleClientHarness", CLIENT_JAR, workspace, manifest)

    def test_unknown_key_extra_file_and_payload_tamper_fail_closed(self):
        for mutation in ("unknown", "extra", "payload", "hardlink"):
            workspace, manifest = self.workspace()
            bundle = workspace / "working/content-bundle"
            if mutation == "unknown":
                document = json.loads((bundle / "manifest.json").read_text())
                document["creatorCode"] = "forbidden"
                (bundle / "manifest.json").write_bytes(pretty(document))
            elif mutation == "extra":
                (bundle / "creator.class").write_bytes(b"forbidden")
            elif mutation == "payload":
                path = bundle / "files/server/conf/server/defs/NpcDefsCustom.json"
                path.write_bytes(path.read_bytes() + b" ")
            else:
                path = bundle / "files/server/conf/server/defs/NpcDefsCustom.json"
                os.link(path, workspace / "outside-hardlink.json")
            self.run_harness("BundleServerHarness", SERVER_JAR, workspace, manifest, success=False)
            self.run_harness("BundleClientHarness", CLIENT_JAR, workspace, manifest, success=False)

    def test_new_item_without_client_visual_metadata_fails_closed(self):
        result = subprocess.run(
            ["java", "-cp", f"{self.classes.name}:{CLIENT_JAR}",
             "BundleClientItemVisualHarness"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("Project item 9000 has no authoritative client visual mapping", result.stdout)


if __name__ == "__main__":
    unittest.main()
