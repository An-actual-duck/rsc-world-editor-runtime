#!/usr/bin/env python3
"""Strict client/server tests for project-local custom content v2."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SERVER_JAR = ROOT / "server/core.jar"
CLIENT_JAR = ROOT / "Client_Base/Open_RSC_Client.jar"
FROZEN_EDITOR_FINGERPRINTS = {
    "definitionFingerprintSha256": "6a070461aaf4d8b304ae295e485c909bd04242017f63a539d7fa74d62872dcfe",
    "assetFingerprintSha256": "2320bfd31effa33c0e8cc47ec919e881809f69599b5504c6369e547697f844bc",
    "itemVisualFingerprintSha256": "aa7c9deae89d9cda0497dad1bf00ac7f2f28b0143d127b584acecb9726f9ac6c",
    "bundleFingerprintSha256": "44510eb65894689c510ef55072a3e5406dfae3821d6368c5b0a6869ce516a9e1",
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
    visual = next(
        row for row in manifest["files"] if row["role"] == "metadata.item-visuals"
    )
    digest = hashlib.sha256(b"world-builder-project-content-item-visuals-v1\n")
    digest.update(
        f'{visual["role"]}\0{visual["runtimeRelativePath"]}\0'
        f'{visual["size"]}\0{visual["sha256"]}\n'.encode()
    )
    manifest["itemVisualFingerprintSha256"] = digest.hexdigest()
    manifest["bundleFingerprintSha256"] = "0" * 64
    manifest["bundleFingerprintSha256"] = hashlib.sha256(
        b"world-builder-project-content-bundle-v2\n" + canonical(manifest)
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return manifest


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
    if(b.schemaVersion()!=2||b.itemVisuals().size()!=3||b.itemVisuals().get(9001).pictureMask()!=-1||b.itemVisuals().get(9002).blueMask()!=-16776961)throw new AssertionError("v2 visual semantics absent");
    System.out.println("server-v2-decoded="+b.itemVisuals().size());
  }
}
"""

CLIENT_HARNESS = r"""
import java.nio.file.Paths;
import orsc.ProjectContentBundle;
public final class BundleV2ClientHarness {
  public static void main(String[] args) throws Exception {
    ProjectContentBundle b=ProjectContentBundle.load(Paths.get(args[0]),args[1],"project-local-custom-content-v2",args[2],args[3],args[4],args[5]);
    if(b.schemaVersion()!=2||b.itemVisuals().size()!=3||b.itemVisual(9001).pictureMask()!=-1||b.itemVisual(9002).blueMask()!=-16776961)throw new AssertionError("v2 visual semantics absent");
    System.out.println("client-v2-decoded="+b.itemVisuals().size());
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
            "working/content-bundle", "working/runtime/server",
            "working/runtime/client", "working/runtime/server/conf", "source",
            "source/layered-baseline/package", "run",
        ):
            (workspace / relative).mkdir(parents=True, exist_ok=True)
        manifest, _ = REAL_LOGIN.write_real_project_content_bundle(
            workspace / "working/content-bundle", ROOT / "server", ROOT / "Client_Base"
        )
        self.addCleanup(temporary.cleanup)
        return workspace, manifest

    def run_harnesses(self, workspace, manifest, success=True):
        args = [
            str(workspace), str(workspace / "working/content-bundle"),
            manifest["bundleFingerprintSha256"],
            manifest["definitionFingerprintSha256"],
            manifest["assetFingerprintSha256"],
            manifest["itemVisualFingerprintSha256"],
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

    def test_both_consumers_decode_all_mapping_forms_and_masks(self):
        workspace, manifest = self.workspace()
        outputs = self.run_harnesses(workspace, manifest)
        self.assertTrue(all("v2-decoded=3" in output for output in outputs))
        self.assertEqual(
            {
                "itemId": 9000, "authenticSpriteId": None,
                "customSpriteAssetRole": "asset.sprite.custom",
                "customSpriteSubspace": "items", "customSpriteEntry": "0",
                "pictureMask": 0, "blueMask": 0,
            },
            manifest["itemVisuals"][0],
        )
        self.assertEqual(
            {
                "definitionFingerprintSha256": "6a070461aaf4d8b304ae295e485c909bd04242017f63a539d7fa74d62872dcfe",
                "assetFingerprintSha256": "2320bfd31effa33c0e8cc47ec919e881809f69599b5504c6369e547697f844bc",
                "itemVisualFingerprintSha256": "aa7c9deae89d9cda0497dad1bf00ac7f2f28b0143d127b584acecb9726f9ac6c",
                "bundleFingerprintSha256": "44510eb65894689c510ef55072a3e5406dfae3821d6368c5b0a6869ce516a9e1",
            },
            FROZEN_EDITOR_FINGERPRINTS,
        )
        self.assertEqual(417, manifest["itemVisuals"][1]["authenticSpriteId"])
        self.assertEqual(-1, manifest["itemVisuals"][1]["pictureMask"])
        self.assertEqual(
            "asset.spritepack", manifest["itemVisuals"][2]["customSpriteAssetRole"]
        )
        self.assertEqual(-16776961, manifest["itemVisuals"][2]["blueMask"])

    def test_hostile_missing_duplicate_and_archive_entry_cases_fail_both(self):
        for mutation in ("hostile", "missing", "duplicate", "archive-entry"):
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
                else:
                    document["itemVisuals"][0]["customSpriteEntry"] = "absent"
                    evidence = bundle / "files/server/conf/world-builder/item-visuals-v1.json"
                    evidence_document = json.loads(evidence.read_text())
                    evidence_document["itemVisuals"] = document["itemVisuals"]
                    evidence.write_text(
                        json.dumps(evidence_document, sort_keys=True, indent=2) + "\n"
                    )
                (bundle / "manifest.json").write_text(
                    json.dumps(document, sort_keys=True, indent=2) + "\n"
                )
                if mutation == "archive-entry":
                    manifest = resign(bundle)
                self.run_harnesses(workspace, manifest, success=False)

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
