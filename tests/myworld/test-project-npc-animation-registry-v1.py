#!/usr/bin/env python3
"""Client/server contract tests for project NPC animation registry v1."""

import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/myworld/fixtures/editor-da94ead-project-content-v2/bundle"
SERVER = ROOT / "server/core.jar"
CLIENT = ROOT / "Client_Base/Open_RSC_Client.jar"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sprite_entry(frames=15):
    # Type 0, frame count, two-colour palette, then 1x1 frames.  Zero legacy
    # bounds are legal: the real client decoder preserves them and render-time
    # code falls back to the frame width/height.
    payload = bytearray((0, frames, 1, 0, 0, 0, 255, 0, 255))
    for _ in range(frames):
        payload.extend(struct.pack(">HHBhhHHB", 1, 1, 0, 0, 0, 0, 0, 1))
    return bytes(payload)


def add_custom_animation(path: Path):
    raw = bytearray(gzip.decompress(path.read_bytes()))
    raw[0] += 1
    raw.extend(b"npc\0" + struct.pack(">H", 1) + b"foreign\0" + sprite_entry())
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as stream:
        stream.write(raw)
    path.write_bytes(output.getvalue())


def add_authentic_frames(path: Path):
    output = io.BytesIO()
    hashes = []
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(output, "w") as target:
        for info in source.infolist():
            target.writestr(info, source.read(info.filename))
        for offset in range(15):
            payload = f"foreign-frame-{offset}\n".encode()
            hashes.append(hashlib.sha256(payload).hexdigest())
            info = zipfile.ZipInfo(f"sprites/{100 + offset}.dat", (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100644 << 16
            target.writestr(info, payload)
    path.write_bytes(output.getvalue())
    return hashes


HARNESS = r"""
import java.nio.file.Paths;
import orsc.ProjectContentBundle;
public final class NpcAnimationV1Harness {
  public static void main(String[] args)throws Exception{
    ProjectContentBundle b=ProjectContentBundle.load(Paths.get(args[0]),args[1],
      "project-local-custom-content-v3",args[2],args[3],args[4],args[5]);
    com.openrsc.client.entityhandling.defs.extras.AnimationDef a=
      b.npcAnimations().get(Integer.valueOf(2000)).animationDef();
    if(b.schemaVersion()!=3||b.npcAnimations().size()!=1
      ||!"foreign".equals(a.getName())||!"npc".equals(a.category)
      ||a.getCharColour()!=1193046||a.getBlueMask()!=6636321
      ||a.getGenderModel()!=2||a.hasA()||a.hasF()||a.getNumber()!=100)
      throw new AssertionError("NPC animation registry semantics absent");
    System.out.println("npc-animation-v1 id=2000 name=foreign frames=15");
  }
}
"""

SERVER_HARNESS = r"""
import com.openrsc.server.ServerConfiguration;
import com.openrsc.server.content.worldedit.AdaptiveWorldBuilderProjectContentBundle;
import com.openrsc.server.content.worldedit.WorldEditStorageContext;
import java.lang.reflect.Constructor;
import java.nio.file.Path;
import java.nio.file.Paths;
public final class NpcAnimationV1ServerHarness {
  public static void main(String[] args)throws Exception{
    Path workspace=Paths.get(args[0]).toRealPath(),working=workspace.resolve("working").toRealPath();
    Constructor<WorldEditStorageContext> c=WorldEditStorageContext.class.getDeclaredConstructor(boolean.class,boolean.class,Path.class,Path.class,Path.class,Path.class,Path.class,Path.class,Path.class,Path.class);
    c.setAccessible(true);
    WorldEditStorageContext storage=c.newInstance(true,true,workspace,workspace.resolve("source"),working,working.resolve("runtime/server"),working.resolve("runtime/client"),working.resolve("runtime/server/conf"),workspace.resolve("run/backups"),workspace.resolve("source/layered-baseline/package"));
    ServerConfiguration config=new ServerConfiguration();
    config.WORLD_BUILDER_CONTENT_BUNDLE_PATH=args[1];
    config.WORLD_BUILDER_CONTENT_CAPABILITY_ID="project-local-custom-content-v3";
    config.WORLD_BUILDER_CONTENT_BUNDLE_SHA256=args[2];
    config.WORLD_BUILDER_CONTENT_DEFINITION_SHA256=args[3];
    config.WORLD_BUILDER_CONTENT_ASSET_SHA256=args[4];
    config.WORLD_BUILDER_CONTENT_ITEM_VISUAL_SHA256=args[5];
    AdaptiveWorldBuilderProjectContentBundle b=AdaptiveWorldBuilderProjectContentBundle.load(config,storage);
    if(b.schemaVersion()!=3)throw new AssertionError("server did not accept bundle v3");
    System.out.println("server-npc-animation-v1 schema=3");
  }
}
"""


class ProjectNpcAnimationRegistryV1Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([str(ROOT / "scripts/build-client.sh")], check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run([str(ROOT / "scripts/build-server.sh")], check=True,
                       stdout=subprocess.DEVNULL)
        cls.classes = tempfile.TemporaryDirectory(prefix="npc-animation-v1-classes-")
        for filename, source_text, jar in (
            ("NpcAnimationV1Harness.java", HARNESS, CLIENT),
            ("NpcAnimationV1ServerHarness.java", SERVER_HARNESS, SERVER),
        ):
            source = Path(cls.classes.name) / filename
            source.write_text(source_text)
            subprocess.run(["javac", "-cp", str(jar), "-d", cls.classes.name,
                            str(source)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.classes.cleanup()

    def bundle(self):
        temporary = tempfile.TemporaryDirectory(prefix="npc-animation-v1-")
        workspace = Path(temporary.name)
        bundle = workspace / "working/content-bundle"
        shutil.copytree(FIXTURE, bundle)
        for relative in ("working/runtime/server", "working/runtime/client",
                         "working/runtime/server/conf", "source",
                         "source/layered-baseline/package", "run"):
            (workspace / relative).mkdir(parents=True, exist_ok=True)
        custom = bundle / "files/client/Cache/video/Custom_Sprites.osar"
        authentic = bundle / "files/client/Cache/video/Authentic_Sprites.orsc"
        add_custom_animation(custom)
        frame_hashes = add_authentic_frames(authentic)
        registry = {
            "schemaVersion": 1,
            "manifestType": "world-builder-npc-animation-registry",
            "animations": [{
                "animationId": 2000, "name": "foreign", "category": "npc",
                "charColour": 1193046, "blueMask": 6636321, "genderModel": 2,
                "hasCombatFrames": False, "hasSpecialCombatFrames": False,
                "requiredFrameCount": 15, "customSpriteSubspace": "npc",
                "customSpriteEntry": "foreign", "customEntrySha256": "a" * 64,
                "authenticBaseSpriteId": 100,
                "authenticFrameSha256s": frame_hashes,
            }],
        }
        registry_path = bundle / "files/server/conf/world-builder/npc-animations-v1.json"
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(json.dumps(registry, sort_keys=True, indent=2) + "\n")
        manifest_path = bundle / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["schemaVersion"] = 3
        manifest["capabilityId"] = "project-local-custom-content-v3"
        manifest["files"].append({
            "role": "metadata.npc-animations",
            "bundleRelativePath": "files/server/conf/world-builder/npc-animations-v1.json",
            "runtimeRelativePath": "server/conf/world-builder/npc-animations-v1.json",
            "mediaType": "application/json", "size": 0, "sha256": "",
        })
        manifest["files"].sort(key=lambda row: row["runtimeRelativePath"])
        for row in manifest["files"]:
            payload = (bundle / row["bundleRelativePath"]).read_bytes()
            row["size"] = len(payload)
            row["sha256"] = hashlib.sha256(payload).hexdigest()
        manifest["bundleFingerprintSha256"] = "0" * 64
        manifest["bundleFingerprintSha256"] = hashlib.sha256(
            b"world-builder-project-content-bundle-v3\n" + canonical(manifest)
        ).hexdigest()
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        self.addCleanup(temporary.cleanup)
        return workspace, bundle, manifest, registry_path

    def run_consumers(self, workspace, bundle, manifest, success=True):
        args = [str(workspace), str(bundle), manifest["bundleFingerprintSha256"],
                manifest["definitionFingerprintSha256"],
                manifest["assetFingerprintSha256"],
                manifest["itemVisualFingerprintSha256"]]
        outputs = []
        for name, jar in (("NpcAnimationV1Harness", CLIENT),
                          ("NpcAnimationV1ServerHarness", SERVER)):
            result = subprocess.run([
                "java", "-cp", f"{self.classes.name}:{jar}", name, *args,
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(success, result.returncode == 0, result.stdout)
            outputs.append(result.stdout)
        return outputs

    def test_foreign_animation_registry_loads_exact_semantics(self):
        workspace, bundle, manifest, _ = self.bundle()
        outputs = self.run_consumers(workspace, bundle, manifest)
        self.assertIn("npc-animation-v1 id=2000", outputs[0])
        self.assertIn("server-npc-animation-v1 schema=3", outputs[1])

    def test_malformed_semantics_and_asset_drift_fail_closed(self):
        for mutation in ("duplicate-id", "frame-shape", "custom-entry", "authentic-hash"):
            with self.subTest(mutation=mutation):
                workspace, bundle, manifest, registry_path = self.bundle()
                registry = json.loads(registry_path.read_text())
                if mutation == "duplicate-id":
                    registry["animations"].append(dict(registry["animations"][0]))
                elif mutation == "frame-shape":
                    registry["animations"][0]["requiredFrameCount"] = 18
                elif mutation == "custom-entry":
                    registry["animations"][0]["customSpriteEntry"] = "absent"
                else:
                    registry["animations"][0]["authenticFrameSha256s"][0] = "f" * 64
                registry_path.write_text(json.dumps(registry, sort_keys=True, indent=2) + "\n")
                row = next(row for row in manifest["files"] if row["role"] == "metadata.npc-animations")
                payload = registry_path.read_bytes()
                row["size"] = len(payload); row["sha256"] = hashlib.sha256(payload).hexdigest()
                manifest["bundleFingerprintSha256"] = "0" * 64
                manifest["bundleFingerprintSha256"] = hashlib.sha256(
                    b"world-builder-project-content-bundle-v3\n" + canonical(manifest)
                ).hexdigest()
                (bundle / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
                self.run_consumers(workspace, bundle, manifest, success=False)


if __name__ == "__main__":
    unittest.main()
