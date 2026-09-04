#!/usr/bin/env python3
"""Executable, content-neutral evidence for the Current Base candidate."""

from __future__ import annotations

import hashlib
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_hashes(identity_path: Path) -> dict[str, str]:
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    return {
        record["bundlePath"]: record["sha256"]
        for record in identity["bundleInventory"]
    }


class CurrentBaseCandidateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checkout = tempfile.TemporaryDirectory(prefix="current-base-clean-checkout-")
        cls.repo = Path(cls.checkout.name) / "runtime"
        subprocess.run(
            ["git", "clone", "--shared", "--quiet", str(ROOT), str(cls.repo)],
            cwd=ROOT,
            check=True,
        )
        cls.output = cls.repo / "output/current-platform/current-base-v1"
        cls.identity_path = cls.output / "composition-identity.json"
        cls.build = cls.repo / "scripts/build-current-base.py"
        cls.verify = cls.repo / "scripts/verify-current-base.py"
        if cls.output.exists():
            raise AssertionError("clean checkout unexpectedly contains ignored candidate output")
        subprocess.run(
            ["python3", str(cls.build)], cwd=cls.repo, check=True,
            capture_output=True, text=True,
        )
        cls.identity = json.loads(cls.identity_path.read_text(encoding="utf-8"))
        cls.profile = json.loads(
            (cls.repo / "current-platform/runtime/current-base-v1/profile.json").read_text()
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.checkout.cleanup()

    def test_candidate_is_installable_but_not_claimed_released(self) -> None:
        base = json.loads(
            (self.repo / "current-platform/variants/current-base-v1.json").read_text()
        )
        advanced = json.loads(
            (self.repo / "current-platform/variants/current-advanced-v1.json").read_text()
        )
        self.assertEqual("release-candidate", base["releaseStatus"])
        self.assertTrue(base["installable"])
        self.assertNotEqual("released", base["releaseStatus"])
        self.assertFalse(advanced["installable"])
        self.assertEqual("foundation-contract-only", advanced["releaseStatus"])
        self.assertEqual([], self.profile["installabilityBlockers"])
        bundle = json.loads((
            self.repo / "current-platform/bundle-specs/current-base-v1.json"
        ).read_text())
        self.assertIn(
            "base-gameplay-state-runtime-execution-v1",
            bundle["requiredExecutableScenarios"],
        )

    def test_candidate_verifier_binds_exact_six_field_artifact_pairing(self) -> None:
        result = subprocess.run(
            [
                "python3", str(self.verify), "--identity", str(self.identity_path),
                "--payload-root", str(self.repo),
            ],
            cwd=self.repo,
            check=True,
            capture_output=True,
            text=True,
        )
        evidence = json.loads(result.stdout)
        self.assertEqual("verified", evidence["status"])
        self.assertEqual("current-composition-handshake-v1", evidence["handshakeId"])
        self.assertRegex(evidence["artifactPairingSha256"], r"^[0-9a-f]{64}$")
        self.assertEqual("verified", evidence["canonicalMapBootstrap"])
        self.assertEqual("verified", evidence["publicPluginInventory"])
        self.assertEqual("verified", evidence["publicStatePolicyContract"])
        self.assertEqual("excluded", evidence["advancedArtifactEffects"])
        self.assertEqual("verified", evidence["serverContent"])

        with tempfile.TemporaryDirectory(prefix="current-base-mismatch-") as temporary:
            mismatch = dict(self.identity)
            mismatch["bundleInventoryHash"] = "0" * 64
            mismatch_path = Path(temporary) / "identity.json"
            mismatch_path.write_text(json.dumps(mismatch), encoding="utf-8")
            refused = subprocess.run(
                [
                    "python3", str(self.verify), "--identity", str(mismatch_path),
                    "--payload-root", str(self.repo),
                ],
                cwd=self.repo,
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(0, refused.returncode)
        self.assertIn("differs from provider artifacts", refused.stderr)

    def test_bundled_preservation_converter_reproduces_reviewed_map_inputs(self) -> None:
        converter = self.output / "tools/layered-maps.jar"
        self.assertTrue(converter.is_file())
        with zipfile.ZipFile(converter) as archive:
            self.assertIn(
                "com/openrsc/layeredmaps/LayeredMapsCli.class", archive.namelist())
        terrain = self.repo / "server/conf/server/data/Authentic_Landscape.orsc"
        terrain_before = sha256(terrain)
        with tempfile.TemporaryDirectory(prefix="current-base-preservation-adapter-") as temp:
            workspace = Path(temp) / "conversion"
            converted = subprocess.run(
                ["java", "-jar", str(converter), "preservation-package",
                 "--root", str(self.repo), "--workspace", str(workspace)],
                cwd=self.repo, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(0, converted.returncode,
                             converted.stdout + converted.stderr)
            report = json.loads((workspace / "generation-report.json").read_text())
            self.assertEqual(1764, report["terrainSectorCount"])
            self.assertEqual(0, report["unconvertedPlacementRecords"])
            self.assertEqual("transitions-pending", report["reviewState"])
            self.assertFalse(report["runtimePromotionApproved"])
            self.assertTrue((workspace / "package/manifest.json").is_file())
        self.assertEqual(terrain_before, sha256(terrain))

    def test_runtime_startup_and_prelogin_handshake_enforce_all_six_fields(self) -> None:
        core = self.output / "server/core.jar"
        client = self.output / "client/Open_RSC_Client.jar"
        property_name = "openrsc.currentCompositionIdentityFile"
        identity_fields = [
            "platformReleaseId",
            "platformManifestHash",
            "variantId",
            "variantManifestHash",
            "moduleSetHash",
            "bundleInventoryHash",
        ]
        for archive, entrypoint, label in (
            (core, "com.openrsc.server.CurrentCompositionIdentity", "server"),
            (client, "orsc.CurrentCompositionIdentity", "client"),
        ):
            accepted = subprocess.run(
                [
                    "java", f"-D{property_name}={self.identity_path}", "-cp",
                    str(archive), entrypoint,
                ],
                cwd=self.repo,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, accepted.returncode, accepted.stdout + accepted.stderr)
            self.assertIn("composition accepted", accepted.stdout)
            missing = subprocess.run(
                ["java", "-cp", str(archive), entrypoint],
                cwd=self.repo,
                capture_output=True,
                text=True,
            )
            self.assertEqual(2, missing.returncode, label)
            self.assertIn("startup refused", missing.stderr)

        server_harness = r"""
import com.openrsc.server.CurrentCompositionIdentity;
import com.openrsc.server.net.Packet;
import io.netty.buffer.Unpooled;
import java.util.Base64;
public final class CurrentCompositionServerHandshakeHarness {
  public static void main(String[] args) {
    CurrentCompositionIdentity.initializeFromSystemProperties();
    byte[] payload = Base64.getDecoder().decode(args[0]);
    CurrentCompositionIdentity.current().requireClientHandshake(
      new Packet(CurrentCompositionIdentity.HANDSHAKE_OPCODE,
        Unpooled.wrappedBuffer(payload)));
    System.out.println("server-prelogin-composition-accepted");
  }
}
"""
        client_harness = r"""
import orsc.CurrentCompositionIdentity;
import orsc.buffers.RSBuffer_Bits;
import java.util.Arrays;
import java.util.Base64;
public final class CurrentCompositionClientHandshakeHarness {
  public static void main(String[] args) {
    CurrentCompositionIdentity.initializeFromSystemProperties();
    RSBuffer_Bits payload = new RSBuffer_Bits(512);
    CurrentCompositionIdentity.current().writeHandshake(payload);
    System.out.println(Base64.getEncoder().encodeToString(
      Arrays.copyOf(payload.dataBuffer, payload.packetEnd)));
  }
}
"""
        with tempfile.TemporaryDirectory(prefix="current-base-runtime-pairing-") as temporary:
            root = Path(temporary)
            server_source = root / "CurrentCompositionServerHandshakeHarness.java"
            server_source.write_text(server_harness, encoding="utf-8")
            client_source = root / "CurrentCompositionClientHandshakeHarness.java"
            client_source.write_text(client_harness, encoding="utf-8")
            subprocess.run(
                [
                    "javac", "-source", "8", "-target", "8", "-cp", str(core),
                    "-d", str(root), str(server_source),
                ],
                cwd=self.repo,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "javac", "-source", "8", "-target", "8", "-cp", str(client),
                    "-d", str(root), str(client_source),
                ],
                cwd=self.repo,
                check=True,
                capture_output=True,
            )
            emitted = subprocess.run(
                [
                    "java", f"-D{property_name}={self.identity_path}", "-cp",
                    f"{client}:{root}", "CurrentCompositionClientHandshakeHarness",
                ],
                cwd=self.repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            accepted = subprocess.run(
                [
                    "java", f"-D{property_name}={self.identity_path}", "-cp",
                    f"{core}:{root}", "CurrentCompositionServerHandshakeHarness",
                    emitted,
                ],
                cwd=self.repo,
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, accepted.returncode, accepted.stdout + accepted.stderr)
            self.assertIn("server-prelogin-composition-accepted", accepted.stdout)

            for index, field in enumerate(identity_fields):
                values = [self.identity[name] for name in identity_fields]
                values[index] = (
                    "0" * 64 if field.endswith("Hash") else "mismatched-composition-v1"
                )
                wire = "current-composition-handshake-v1\n" + "\n".join(values) + "\n"
                refused = subprocess.run(
                    [
                        "java", f"-D{property_name}={self.identity_path}", "-cp",
                        f"{core}:{root}", "CurrentCompositionServerHandshakeHarness",
                        base64.b64encode(wire.encode("ascii")).decode("ascii"),
                    ],
                    cwd=self.repo,
                    capture_output=True,
                    text=True,
                )
                self.assertNotEqual(0, refused.returncode, field)
                self.assertIn("client composition differs at " + field, refused.stderr)

    def test_public_plugins_and_canonical_map_bootstraps_are_executable(self) -> None:
        core = self.output / "server/core.jar"
        plugins = self.output / "server/plugins.jar"
        client = self.output / "client/Open_RSC_Client.jar"
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
                cwd=self.repo,
                check=True,
                capture_output=True,
            )
            executed = subprocess.run(
                [
                    "java", "-cp", f"{root}:{core}",
                    "com.openrsc.server.io.CurrentBaseMapHarness", str(profile),
                ],
                cwd=self.repo,
                check=True,
                capture_output=True,
                text=True,
            )
        self.assertEqual(["true", "world-builder-installed"], executed.stdout.splitlines())

    def test_provider_server_content_loads_vanilla_definition_prefixes(self) -> None:
        core = self.output / "server/core.jar"
        plugins = self.output / "server/plugins.jar"
        content = self.output / "server/content.zip"
        harness_source = r"""
package com.openrsc.server;
public final class CurrentBaseContentHarness {
  public static void main(String[] args) throws Exception {
    CurrentCompositionIdentity.initializeFromSystemProperties();
    Server server = new Server("current-base.conf");
    server.getEntityHandler().load();
    ServerConfiguration config = server.getConfig();
    boolean advanced = config.CUSTOM_IMPROVEMENTS || config.WANT_CUSTOM_LANDSCAPE
      || config.WANT_CUSTOM_SPRITES || config.SPAWN_AUCTION_NPCS
      || config.SPAWN_IRON_MAN_NPCS || config.WANT_BANK_PRESETS
      || config.WANT_CLANS || config.WANT_COMBAT_ODYSSEY
      || config.WANT_CUSTOM_BANKS || config.WANT_CUSTOM_LEATHER
      || config.WANT_CUSTOM_QUESTS || config.WANT_CUSTOM_UI
      || config.WANT_EQUIPMENT_TAB || config.WANT_HARVESTING
      || config.WANT_MYWORLD || config.WANT_NEW_RARE_DROP_TABLES
      || config.WANT_RUNECRAFT;
    if (advanced) throw new AssertionError("Advanced configuration became active");
    if (server.getEntityHandler().getItemDef(1289) == null
        || server.getEntityHandler().getItemDef(1290) != null
        || server.getEntityHandler().getNpcDef(793) == null
        || server.getEntityHandler().getNpcDef(794) != null
        || server.getEntityHandler().getDoorDef(213) == null
        || server.getEntityHandler().getDoorDef(214) != null
        || server.getEntityHandler().getGameObjectDef(1189) == null
        || server.getEntityHandler().getGameObjectDef(1190) != null) {
      throw new AssertionError("definition catalogs exceed vanilla prefixes");
    }
    System.out.println("current-base-content-loaded");
    System.exit(0);
  }
}
"""
        with tempfile.TemporaryDirectory(prefix="current-base-content-") as temporary:
            root = Path(temporary)
            with zipfile.ZipFile(content) as archive:
                archive.extractall(root)
            (root / "plugins.jar").write_bytes(plugins.read_bytes())
            source = root / "com/openrsc/server/CurrentBaseContentHarness.java"
            source.parent.mkdir(parents=True)
            source.write_text(harness_source, encoding="utf-8")
            subprocess.run(
                [
                    "javac", "-source", "8", "-target", "8", "-cp", str(core),
                    "-d", str(root), str(source),
                ],
                cwd=self.repo,
                check=True,
                capture_output=True,
            )
            loaded = subprocess.run(
                [
                    "java", "-Dopenrsc.currentCompositionIdentityFile="
                    + str(self.identity_path), "-cp", f"{core}:{root}",
                    "com.openrsc.server.CurrentBaseContentHarness",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=20,
            )
        self.assertEqual(0, loaded.returncode, loaded.stdout + loaded.stderr)
        self.assertIn("current-base-content-loaded", loaded.stdout)

    def test_advanced_only_plugins_assets_and_configuration_are_absent(self) -> None:
        with zipfile.ZipFile(self.output / "server/plugins.jar") as archive:
            plugins = archive.namelist()
        with zipfile.ZipFile(self.output / "client/Open_RSC_Client.jar") as archive:
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
        first = candidate_hashes(self.identity_path)
        provenance = json.loads(
            (self.output / "runtime/build-provenance.json").read_text(encoding="utf-8")
        )
        self.assertFalse(provenance["sourceTreeDirty"])
        self.assertRegex(provenance["sourceTreeFingerprint"], r"^[0-9a-f]{64}$")
        subprocess.run(
            ["python3", str(self.build)], cwd=self.repo, check=True,
            capture_output=True, text=True,
        )
        second = candidate_hashes(self.identity_path)
        self.assertEqual(first, second)

    def test_dirty_tracked_source_is_rejected_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="current-base-dirty-checkout-") as temporary:
            repo = Path(temporary) / "runtime"
            subprocess.run(
                ["git", "clone", "--shared", "--quiet", str(ROOT), str(repo)],
                cwd=ROOT,
                check=True,
            )
            build_file = repo / "Client_Base/build.xml"
            build_file.write_text(build_file.read_text() + "\n", encoding="utf-8")
            output = repo / "output/current-platform/current-base-v1"
            self.assertFalse(output.exists())
            refused = subprocess.run(
                ["python3", "scripts/build-current-base.py"],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            self.assertEqual(2, refused.returncode)
            self.assertIn("requires a clean provider source tree", refused.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
