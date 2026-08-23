#!/usr/bin/env python3
"""Strict client/server tests for project-local custom content v2."""

import hashlib
import importlib.util
import gzip
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
SERVER_JAR = ROOT / "server/core.jar"
CLIENT_JAR = ROOT / "Client_Base/Open_RSC_Client.jar"
EDITOR_FIXTURE = ROOT / "tests/myworld/fixtures/editor-da94ead-project-content-v2"
EDITOR_BUNDLE = EDITOR_FIXTURE / "bundle"
EDITOR_MANIFEST_SHA256 = "ec4f049954860e799d3de822fc8801c1c155f3a595db0baba8a8ec34d041fac9"
EDITOR_FINGERPRINTS = {
    "definitionFingerprintSha256": "f97a96299023e4cf1d738c1f3520af0c2e4339ed95aab952814832cc77e52baf",
    "assetFingerprintSha256": "e0ab18b793a91db852557689b9734eeb1d459e216be61b902d75a69e6e2c5bfa",
    "itemVisualFingerprintSha256": "f9aaf43d6cac1c96bbf10d129e1976f9638562036e1b187f684e7219a7cda8d3",
    "bundleFingerprintSha256": "88542556c723be2c4312f48eb2b42f65fb08a169edd21afa55eda075c6d4aa8b",
}

REAL_LOGIN_PATH = ROOT / "tests/myworld/test-adaptive-builder-real-login.py"
SPEC = importlib.util.spec_from_file_location("adaptive_real_login", REAL_LOGIN_PATH)
REAL_LOGIN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REAL_LOGIN)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def resign(bundle: Path):
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for row in manifest["files"]:
        payload = (bundle / row["bundleRelativePath"]).read_bytes()
        row["size"] = len(payload)
        row["sha256"] = hashlib.sha256(payload).hexdigest()
    definition_roles = {
        role for role, _, _, definition in REAL_LOGIN.CONTENT_SPECS if definition
    }

    def records(domain, definitions):
        digest = hashlib.sha256(domain)
        for row in manifest["files"]:
            if row["role"] == "metadata.item-visuals":
                continue
            if (row["role"] in definition_roles) != definitions:
                continue
            digest.update(
                f'{row["role"]}\0{row["runtimeRelativePath"]}\0'
                f'{row["size"]}\0{row["sha256"]}\n'.encode()
            )
        if definitions:
            digest.update(manifest["definitionCatalog"]["catalogSha256"].encode())
        return digest.hexdigest()

    manifest["definitionFingerprintSha256"] = records(
        b"world-builder-project-content-definitions-v1\n", True
    )
    manifest["assetFingerprintSha256"] = records(
        b"world-builder-project-content-assets-v1\n", False
    )
    digest = hashlib.sha256(b"world-builder-project-content-item-visuals-v1\n")
    digest.update(canonical(manifest["itemVisuals"]))
    manifest["itemVisualFingerprintSha256"] = digest.hexdigest()
    manifest["bundleFingerprintSha256"] = "0" * 64
    manifest["bundleFingerprintSha256"] = hashlib.sha256(
        b"world-builder-project-content-bundle-v2\n" + canonical(manifest)
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return manifest


def deterministic_gzip(payload: bytes) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as archive:
        archive.write(payload)
    return output.getvalue()


SERVER_HARNESS = r"""
import com.openrsc.server.ServerConfiguration;
import com.openrsc.server.content.worldedit.AdaptiveWorldBuilderProjectContentBundle;
import com.openrsc.server.content.worldedit.WorldEditStorageContext;
import java.lang.reflect.Constructor;
import java.nio.file.Path;
import java.nio.file.Paths;
public final class BundleV2ServerHarness {
  public static void main(String[] args) throws Exception {
    Path workspace=Paths.get(args[0]).toRealPath(),working=workspace.resolve("working").toRealPath();
    Constructor<WorldEditStorageContext> c=WorldEditStorageContext.class.getDeclaredConstructor(boolean.class,boolean.class,Path.class,Path.class,Path.class,Path.class,Path.class,Path.class,Path.class,Path.class);
    c.setAccessible(true);
    WorldEditStorageContext storage=c.newInstance(true,true,workspace,workspace.resolve("source"),working,working.resolve("runtime/server"),working.resolve("runtime/client"),working.resolve("runtime/server/conf"),workspace.resolve("run/backups"),workspace.resolve("source/layered-baseline/package"));
    ServerConfiguration config=new ServerConfiguration();
    config.WORLD_BUILDER_CONTENT_BUNDLE_PATH=args[1];config.WORLD_BUILDER_CONTENT_CAPABILITY_ID="project-local-custom-content-v2";
    config.WORLD_BUILDER_CONTENT_BUNDLE_SHA256=args[2];config.WORLD_BUILDER_CONTENT_DEFINITION_SHA256=args[3];config.WORLD_BUILDER_CONTENT_ASSET_SHA256=args[4];config.WORLD_BUILDER_CONTENT_ITEM_VISUAL_SHA256=args[5];
    AdaptiveWorldBuilderProjectContentBundle b=AdaptiveWorldBuilderProjectContentBundle.load(config,storage);
    AdaptiveWorldBuilderProjectContentBundle.ItemVisual custom=b.itemVisuals().get(9000),authentic=b.itemVisuals().get(9001),pack=b.itemVisuals().get(9002);
    if(b.schemaVersion()!=2||b.itemVisuals().size()!=3
      ||!"asset.sprite.custom".equals(custom.customSpriteAssetRole())||!"items".equals(custom.customSpriteSubspace())||!"0".equals(custom.customSpriteEntry())||custom.pictureMask()!=3368601||custom.blueMask()!=1122867
      ||authentic.authenticSpriteId().intValue()!=417||authentic.pictureMask()!=-1||authentic.blueMask()!=0
      ||!"asset.spritepack".equals(pack.customSpriteAssetRole())||!"GUI".equals(pack.customSpriteSubspace())||!"0".equals(pack.customSpriteEntry())||pack.pictureMask()!=4478310||pack.blueMask()!=-16776961)throw new AssertionError("v2 visual semantics absent");
    System.out.println("server-v2-decoded="+b.itemVisuals().size()+" sources=asset.sprite.custom:items:0,asset.sprite.authentic:2567,asset.spritepack:GUI:0 masks=3368601/1122867,-1/0,4478310/-16776961");
  }
}
"""

CLIENT_HARNESS = r"""
import java.nio.file.Paths;
import com.openrsc.client.model.Sprite;
import orsc.ProjectContentBundle;
import orsc.graphics.two.SpriteArchive.Entry;
import orsc.graphics.two.SpriteArchive.Subspace;
import orsc.graphics.two.SpriteArchive.Unpacker;
import orsc.graphics.two.SpriteArchive.Workspace;
public final class BundleV2ClientHarness {
  private static Sprite decoded(ProjectContentBundle b,String role,String subspace,String entry)throws Exception{
    Workspace w=new Unpacker().unpackArchive(b.path(role).toFile());if(w==null)throw new AssertionError("archive did not decode: "+role);
    for(Subspace s:w.getSubspaces())if(subspace.equals(s.getName()))for(Entry e:s.getEntryList())if(entry.equals(e.getID())){
      if(e.getFrames().length<1||e.getFrames()[0]==null||e.getFrames()[0].getSprite()==null)throw new AssertionError("frame absent: "+role);
      return e.getFrames()[0].getSprite();
    }throw new AssertionError("entry absent: "+role);
  }
  private static int nonzero(Sprite sprite){int count=0;for(int pixel:sprite.getPixels())if(pixel!=0)count++;return count;}
  public static void main(String[] args) throws Exception {
    ProjectContentBundle b=ProjectContentBundle.load(Paths.get(args[0]),args[1],"project-local-custom-content-v2",args[2],args[3],args[4],args[5]);
    ProjectContentBundle.ItemVisual custom=b.itemVisual(9000),authentic=b.itemVisual(9001),pack=b.itemVisual(9002);
    Sprite customDecoded=decoded(b,"asset.sprite.custom","items","0"),packDecoded=decoded(b,"asset.spritepack","GUI","0");
    int customPixels=nonzero(customDecoded),packPixels=nonzero(packDecoded);
    int authenticPixels=0;for(int pixel:b.authenticItemSprite(417).getPixels())if(pixel!=0)authenticPixels++;
    if(b.schemaVersion()!=2||b.itemVisuals().size()!=3||customPixels<1||authenticPixels<1||packPixels<1
      ||b.itemSprite(9000).getPixels()[0]!=customDecoded.getPixels()[0]||b.itemSprite(9002).getPixels()[0]!=packDecoded.getPixels()[0]
      ||!"asset.sprite.custom".equals(custom.customSpriteAssetRole())||!"items".equals(custom.customSpriteSubspace())||!"0".equals(custom.customSpriteEntry())||custom.pictureMask()!=3368601||custom.blueMask()!=1122867
      ||authentic.authenticSpriteId().intValue()!=417||authentic.pictureMask()!=-1||authentic.blueMask()!=0
      ||!"asset.spritepack".equals(pack.customSpriteAssetRole())||!"GUI".equals(pack.customSpriteSubspace())||!"0".equals(pack.customSpriteEntry())||pack.pictureMask()!=4478310||pack.blueMask()!=-16776961)throw new AssertionError("v2 visual semantics absent");
    System.out.println("client-v2-decoded="+b.itemVisuals().size()+" customPixels="+customPixels+" authenticPixels="+authenticPixels+" spritepackPixels="+packPixels+" sources=asset.sprite.custom:items:0,asset.sprite.authentic:2567,asset.spritepack:GUI:0 masks=3368601/1122867,-1/0,4478310/-16776961");
  }
}
"""


class BundleV2RuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes = tempfile.TemporaryDirectory(prefix="bundle-v2-classes-")
        classes = Path(cls.classes.name)
        for name, source, jar in (
            ("BundleV2ServerHarness.java", SERVER_HARNESS, SERVER_JAR),
            ("BundleV2ClientHarness.java", CLIENT_HARNESS, CLIENT_JAR),
        ):
            path = classes / name
            path.write_text(source)
            subprocess.run(
                ["javac", "-cp", str(jar), "-d", str(classes), str(path)],
                check=True,
            )

    @classmethod
    def tearDownClass(cls):
        cls.classes.cleanup()

    def workspace(self):
        temporary = tempfile.TemporaryDirectory(prefix="bundle-v2-runtime-")
        workspace = Path(temporary.name)
        for relative in (
            "working/runtime/server", "working/runtime/client",
            "working/runtime/server/conf", "source",
            "source/layered-baseline/package", "run",
        ):
            (workspace / relative).mkdir(parents=True, exist_ok=True)
        shutil.copytree(EDITOR_BUNDLE, workspace / "working/content-bundle")
        manifest = json.loads(
            (workspace / "working/content-bundle/manifest.json").read_text()
        )
        self.addCleanup(temporary.cleanup)
        return workspace, manifest

    def run_harnesses(self, workspace, manifest, success=True, identities=None):
        identities = identities or manifest
        args = [
            str(workspace), str(workspace / "working/content-bundle"),
            identities["bundleFingerprintSha256"],
            identities["definitionFingerprintSha256"],
            identities["assetFingerprintSha256"],
            identities["itemVisualFingerprintSha256"],
        ]
        outputs = []
        for name, jar in (
            ("BundleV2ServerHarness", SERVER_JAR),
            ("BundleV2ClientHarness", CLIENT_JAR),
        ):
            result = subprocess.run(
                ["java", "-cp", f"{self.classes.name}:{jar}", name, *args],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            self.assertEqual(success, result.returncode == 0, result.stdout)
            outputs.append(result.stdout)
        return outputs

    def test_checked_in_fixture_is_byte_identical_to_reviewed_editor_contract(self):
        manifest_bytes = (EDITOR_BUNDLE / "manifest.json").read_bytes()
        self.assertEqual(EDITOR_MANIFEST_SHA256, hashlib.sha256(manifest_bytes).hexdigest())
        for line in (EDITOR_FIXTURE / "SHA256SUMS").read_text().splitlines():
            expected, fixture_path = line.split(None, 1)
            self.assertTrue(fixture_path.startswith("bundle/"), fixture_path)
            relative = fixture_path.removeprefix("bundle/")
            self.assertEqual(
                expected,
                hashlib.sha256((EDITOR_BUNDLE / relative).read_bytes()).hexdigest(),
                relative,
            )
        manifest = json.loads(manifest_bytes)
        evidence = json.loads(
            (EDITOR_BUNDLE / "files/server/conf/world-builder/item-visuals-v1.json")
            .read_text()
        )
        self.assertEqual("world-builder-item-visual-evidence", evidence["manifestType"])
        self.assertEqual(manifest["itemVisuals"], evidence["itemVisuals"])
        calculated_visual = hashlib.sha256(
            b"world-builder-project-content-item-visuals-v1\n"
            + canonical(manifest["itemVisuals"])
        ).hexdigest()
        self.assertEqual(EDITOR_FINGERPRINTS["itemVisualFingerprintSha256"], calculated_visual)
        for role in ("asset.sprite.custom", "asset.spritepack"):
            row = next(row for row in manifest["files"] if row["role"] == role)
            payload = (EDITOR_BUNDLE / row["bundleRelativePath"]).read_bytes()
            self.assertEqual("application/gzip", row["mediaType"])
            self.assertEqual(b"\x1f\x8b", payload[:2])
            self.assertGreater(len(gzip.decompress(payload)), 0)

    def test_both_consumers_decode_all_mapping_forms_and_masks(self):
        workspace, manifest = self.workspace()
        outputs = self.run_harnesses(workspace, manifest)
        self.assertTrue(all("v2-decoded=3" in output for output in outputs))
        self.assertIn("customPixels=", outputs[1])
        self.assertIn("authenticPixels=", outputs[1])
        self.assertIn("spritepackPixels=", outputs[1])
        self.assertTrue(all("masks=3368601/1122867,-1/0,4478310/-16776961" in output for output in outputs))
        self.assertEqual(
            {
                "itemId": 9000, "authenticSpriteId": None,
                "customSpriteAssetRole": "asset.sprite.custom",
                "customSpriteSubspace": "items", "customSpriteEntry": "0",
                "pictureMask": 3368601, "blueMask": 1122867,
            },
            manifest["itemVisuals"][0],
        )
        self.assertEqual(
            EDITOR_FINGERPRINTS,
            {key: manifest[key] for key in EDITOR_FINGERPRINTS},
        )
        self.assertEqual(417, manifest["itemVisuals"][1]["authenticSpriteId"])
        self.assertEqual(-1, manifest["itemVisuals"][1]["pictureMask"])
        self.assertEqual(
            "asset.spritepack", manifest["itemVisuals"][2]["customSpriteAssetRole"]
        )
        self.assertEqual(4478310, manifest["itemVisuals"][2]["pictureMask"])
        self.assertEqual(-16776961, manifest["itemVisuals"][2]["blueMask"])

    def test_hostile_missing_duplicate_and_archive_entry_cases_fail_both(self):
        for mutation in (
            "hostile", "missing", "duplicate", "archive-entry",
            "evidence-identity", "raw-osar", "truncated-gzip",
            "authentic-path", "authentic-payload",
        ):
            with self.subTest(mutation=mutation):
                workspace, manifest = self.workspace()
                bundle = workspace / "working/content-bundle"
                document = json.loads((bundle / "manifest.json").read_text())
                if mutation == "hostile":
                    document["itemVisuals"][0]["authenticSpriteId"] = 1
                elif mutation == "missing":
                    document["itemVisuals"].pop()
                elif mutation == "duplicate":
                    document["itemVisuals"].insert(1, dict(document["itemVisuals"][0]))
                elif mutation == "archive-entry":
                    document["itemVisuals"][0]["customSpriteEntry"] = "absent"
                    evidence = bundle / "files/server/conf/world-builder/item-visuals-v1.json"
                    evidence_document = json.loads(evidence.read_text())
                    evidence_document["itemVisuals"] = document["itemVisuals"]
                    evidence.write_text(
                        json.dumps(evidence_document, sort_keys=True, indent=2) + "\n"
                    )
                elif mutation == "evidence-identity":
                    evidence = bundle / "files/server/conf/world-builder/item-visuals-v1.json"
                    evidence_document = json.loads(evidence.read_text())
                    evidence_document["manifestType"] = "world-builder-item-visuals"
                    evidence.write_text(
                        json.dumps(evidence_document, sort_keys=True, indent=2) + "\n"
                    )
                elif mutation in ("raw-osar", "truncated-gzip"):
                    archive = bundle / "files/client/Cache/video/Custom_Sprites.osar"
                    payload = archive.read_bytes()
                    archive.write_bytes(
                        gzip.decompress(payload) if mutation == "raw-osar" else payload[:-5]
                    )
                elif mutation in ("authentic-path", "authentic-payload"):
                    archive = bundle / "files/client/Cache/video/Authentic_Sprites.orsc"
                    with zipfile.ZipFile(archive) as source:
                        payload = source.read("sprites/417.dat")
                    entry = (
                        "sprites/418.dat"
                        if mutation == "authentic-path" else "sprites/417.dat"
                    )
                    with zipfile.ZipFile(archive, "w") as target:
                        target.writestr(entry, payload if mutation == "authentic-path" else payload[:-4])
                (bundle / "manifest.json").write_text(
                    json.dumps(document, sort_keys=True, indent=2) + "\n"
                )
                if mutation in (
                    "archive-entry", "evidence-identity", "raw-osar",
                    "truncated-gzip", "authentic-path", "authentic-payload",
                ):
                    manifest = resign(bundle)
                self.run_harnesses(workspace, manifest, success=False)

    def test_hostile_launch_identities_fail_both_consumers(self):
        for key in EDITOR_FINGERPRINTS:
            with self.subTest(identity=key):
                workspace, manifest = self.workspace()
                identities = dict(manifest)
                identities[key] = "0" * 64
                self.run_harnesses(
                    workspace, manifest, success=False, identities=identities
                )

    def test_cross_role_collision_retains_role_specific_decoded_storage(self):
        workspace, manifest = self.workspace()
        bundle = workspace / "working/content-bundle"
        custom = bundle / "files/client/Cache/video/Custom_Sprites.osar"
        pack = bundle / "files/client/Cache/video/spritepacks/Menus.osar"
        custom_frame = gzip.decompress(custom.read_bytes())
        pack_frame = gzip.decompress(pack.read_bytes())
        custom.write_bytes(
            deterministic_gzip(b"\x02" + custom_frame[1:] + pack_frame[1:])
        )
        manifest = resign(bundle)
        outputs = self.run_harnesses(workspace, manifest)
        self.assertIn("sources=asset.sprite.custom:items:0", outputs[1])

    def test_duplicate_json_key_and_extra_file_fail_both(self):
        for mutation in ("duplicate-key", "extra-file"):
            with self.subTest(mutation=mutation):
                workspace, manifest = self.workspace()
                bundle = workspace / "working/content-bundle"
                if mutation == "duplicate-key":
                    path = bundle / "manifest.json"
                    text = path.read_text()
                    path.write_text(
                        text.replace(
                            '"schemaVersion": 2,',
                            '"schemaVersion": 2,\n  "schemaVersion": 2,', 1,
                        )
                    )
                else:
                    (bundle / "creator.class").write_bytes(b"forbidden")
                self.run_harnesses(workspace, manifest, success=False)


if __name__ == "__main__":
    unittest.main()
