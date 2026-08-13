#!/usr/bin/env python3
"""Launch the built adaptive server and desktop client through real login."""

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "server/core.jar"
PLUGINS = ROOT / "server/plugins.jar"
CLIENT = ROOT / "Client_Base/Open_RSC_Client.jar"


def canonical_json(value) -> bytes:
    return (json.dumps(value, separators=(",", ":")) + "\n").encode("utf-8")


def write_integration_package(root: Path) -> None:
    initial_x = 120
    initial_y = 648
    sector_x = initial_x // 48
    sector_y = initial_y // 48
    local_x = initial_x % 48
    local_y = initial_y % 48
    terrain_path = f"terrain/global/lp0/xp{sector_x}-yp{sector_y}.raw"
    placement_path = "placements/global/lp0.json"
    terrain = bytearray(
        bytes((0, 1, 8, 0, 0, 0, 0, 0, 0, 0)) * (48 * 48)
    )
    for x in range(local_x - 1, local_x + 2):
        for y in range(local_y - 1, local_y + 2):
            offset = (x * 48 + y) * 10
            terrain[offset:offset + 10] = bytes(10)
    terrain = bytes(terrain)
    placements = canonical_json({
        "schemaVersion": 3,
        "encoding": "layered-world-placements-v3",
        "worldSpace": "global",
        "level": 0,
        "npcs": [],
        "groundItems": [],
        "scenery": [],
        "boundaries": [],
    })
    (root / terrain_path).parent.mkdir(parents=True)
    (root / placement_path).parent.mkdir(parents=True)
    (root / terrain_path).write_bytes(terrain)
    (root / placement_path).write_bytes(placements)
    manifest = {
        "schemaVersion": 1,
        "packageType": "layered-world",
        "packageId": "integration.neutral.standalone-empty",
        "packageVersion": "1.0.0",
        "coordinateModel": "signed-layered-v1",
        "storage": {"sectorSize": 48, "presentationChunkSize": 24},
        "worldSpaces": [{"id": "global", "kind": "static"}],
        "levels": [{
            "worldSpace": "global", "level": 0,
            "name": "Empty level", "role": "empty-authoring-level",
        }],
        "terrainSectors": [{
            "worldSpace": "global", "level": 0,
            "sectorX": sector_x, "sectorY": sector_y,
            "encoding": "raw-layered-sector-v1", "path": terrain_path,
            "sha256": hashlib.sha256(terrain).hexdigest(),
        }],
        "placementSets": [{
            "id": "integration.global.lp0", "worldSpace": "global", "level": 0,
            "encoding": "layered-world-placements-v3", "path": placement_path,
            "sha256": hashlib.sha256(placements).hexdigest(),
        }],
    }
    (root / "manifest.json").write_bytes(canonical_json(manifest))


def inventory_fingerprint(package: Path, classes: Path) -> str:
    source = classes / "PackageFingerprint.java"
    source.write_text(
        """
import com.openrsc.server.io.AdaptiveWorldBuilderPackageGuard;
import java.nio.file.Paths;
public final class PackageFingerprint {
  public static void main(String[] args) throws Exception {
    System.out.println(AdaptiveWorldBuilderPackageGuard
      .requireClosedPackage(Paths.get(args[0])).getFingerprint());
  }
}
""".strip() + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["javac", "-source", "8", "-target", "8", "-cp", str(CORE),
         "-d", str(classes), str(source)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    result = subprocess.run(
        ["java", "-cp", os.pathsep.join((str(CORE), str(classes))),
         "PackageFingerprint", str(package)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    value = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise AssertionError("invalid package fingerprint: " + value)
    return value


def replace_config(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^(\s*{re.escape(key)}:\s*).*$")
    updated, count = pattern.subn(rf"\g<1>{value}", text, count=1)
    if count != 1:
        raise AssertionError("missing base configuration key: " + key)
    return updated


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_for(path: Path, process: subprocess.Popen, timeout: float, label: str,
             diagnostic: Path = None) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return
        if process.poll() is not None:
            details = ""
            if diagnostic is not None and diagnostic.is_file():
                details = "\n" + diagnostic.read_text(
                    encoding="utf-8", errors="replace"
                )
            raise AssertionError(
                f"{label} process exited early with {process.returncode}{details}"
            )
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {label}: {path}")


def wait_for_text(path: Path, needle: str, process: subprocess.Popen,
                  timeout: float, label: str) -> str:
    deadline = time.monotonic() + timeout
    latest = ""
    while time.monotonic() < deadline:
        if path.is_file():
            latest = path.read_text(encoding="utf-8", errors="replace")
            if needle in latest:
                return latest
        if process.poll() is not None:
            raise AssertionError(
                f"{label} process exited early with {process.returncode}\n{latest}"
            )
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {label} marker {needle!r}\n{latest}")


@unittest.skipUnless(os.environ.get("DISPLAY"), "real desktop-client integration needs DISPLAY")
class AdaptiveBuilderRealLoginTest(unittest.TestCase):
    def test_built_client_authenticates_binds_and_reaches_native_readiness(self):
        manual_test = os.environ.get("OPENRSC_WORLD_BUILDER_MANUAL_TEST") == "1"
        for artifact in (CORE, PLUGINS, CLIENT):
            self.assertTrue(artifact.is_file(), f"build artifact missing: {artifact}")

        with tempfile.TemporaryDirectory(prefix="adaptive-real-login-") as temp:
            fixture = Path(temp)
            project = fixture / "project"
            working = project / "working"
            package = working / "layered-world/package"
            baseline = project / "source/layered-baseline/package"
            server_root = working / "runtime/server"
            client_root = working / "runtime/client"
            control = project / "run/world-builder"
            evidence = working / "evidence"
            write_integration_package(package)
            shutil.copytree(package, baseline)
            classes = fixture / "classes"
            classes.mkdir()
            inventory = inventory_fingerprint(package, classes)
            manifest_sha = hashlib.sha256((package / "manifest.json").read_bytes()).hexdigest()

            server_root.mkdir(parents=True)
            client_root.mkdir(parents=True)
            control.parent.mkdir(parents=True)
            evidence.mkdir(parents=True)
            for directory in ("conf", "database", "lib"):
                shutil.copytree(ROOT / "server" / directory, server_root / directory)
            for name in ("alertwords.txt", "badwords.txt", "goodwords.txt", "globalrules.txt"):
                shutil.copy2(ROOT / "server" / name, server_root / name)
            shutil.copy2(CORE, server_root / "core.jar")
            shutil.copy2(PLUGINS, server_root / "plugins.jar")
            (server_root / "inc/sqlite").mkdir(parents=True)
            shutil.copy2(
                ROOT / "server/inc/sqlite/myworld_seed.db",
                server_root / "inc/sqlite/world_builder.db",
            )
            shutil.copy2(ROOT / "server/connections.conf", server_root / "connections.conf")

            shutil.copy2(CLIENT, client_root / "Open_RSC_Client.jar")
            shutil.copytree(ROOT / "Client_Base/Cache", client_root / "Cache")
            for legacy in (
                client_root / "Cache/video/Authentic_Landscape.orsc",
                client_root / "Cache/video/Custom_Landscape.orsc",
            ):
                legacy.unlink()
            # Keep the unrelated Discord native integration out of this bounded
            # process-lifecycle test; the lock file is confined to the fixture.
            (client_root / "Cache/discord_inuse.txt").write_text("1", encoding="ascii")
            definitions = evidence / "definitions.bin"
            assets = evidence / "assets.bin"
            definitions.write_bytes(b"integration-neutral-definition-evidence-v1\n")
            assets.write_bytes(b"integration-neutral-asset-evidence-v1\n")
            definition_sha = hashlib.sha256(definitions.read_bytes()).hexdigest()
            asset_sha = hashlib.sha256(assets.read_bytes()).hexdigest()

            port = free_port()
            config = (ROOT / "server/myworld.conf").read_text(encoding="utf-8")
            replacements = {
                "db_name": "world_builder",
                "server_name": "Adaptive Login Integration",
                "server_name_welcome": "Adaptive Login Integration",
                "server_port": str(port),
                "ws_server_port": str(port + 1),
                "want_feature_websockets": "false",
                "max_players": "1",
                "max_players_per_ip": "1",
                "allow_in_game_world_editor": "true",
                "want_packet_register": "false",
                "want_sync_scene_baseline": "true",
                "monitor_online": "false",
                "custom_landscape": "false",
                "want_myworld": "false",
            }
            for key, value in replacements.items():
                config = replace_config(config, key, value)
            config += """

# Explicit isolated adaptive Builder integration profile.
world_builder_mode: true
world_builder_layered_review_mode: true
world_builder_adaptive_mode: true
want_layered_player_location_authority: true
want_layered_spatial_runtime_authority: true
want_layered_protocol_client_authority: true
want_layered_native_terrain_package: true
want_layered_native_terrain_residency: true
want_layered_native_terrain_readiness: true
want_layered_native_terrain_prediction: true
want_layered_native_terrain_symmetric_residency: true
want_layered_native_terrain_atomic_activation: true
layered_native_world_runtime_profile: adaptive-world-builder
world_builder_project_origin: standalone-empty
world_builder_definition_id: integration.neutral.definitions.v1
world_builder_asset_id: integration.neutral.assets.v1
world_builder_initial_world_space: global
world_builder_initial_level: 0
world_builder_initial_x: 120
world_builder_initial_y: 648
"""
            (server_root / "world-builder.conf").write_text(config, encoding="utf-8")

            credential = server_root / "inc/sqlite/world-builder.credential"
            binding = control / "runtime-binding.properties"
            ready = control / "ready"
            shutdown = control / "shutdown.request"
            server_log = fixture / "server.log"
            client_log = fixture / "client.log"
            client_runtime_log = fixture / "client-runtime.log"
            source_revision = "a" * 64
            baseline_inventory = inventory_fingerprint(baseline, classes)

            common_server_properties = {
                "openrsc.worldBuilderWorkspaceRoot": str(project),
                "openrsc.worldBuilderControlDirectory": str(control),
                "openrsc.worldBuilderCredentialFile": str(credential),
                "openrsc.worldBuilderAdaptiveMode": "true",
                "openrsc.layeredNativeWorldRuntimeProfile": "adaptive-world-builder",
                "openrsc.layeredNativeTerrainPackagePath": str(package),
                "openrsc.layeredNativeTerrainManifestSha256": manifest_sha,
                "openrsc.layeredNativeTerrainInventorySha256": inventory,
                "openrsc.worldBuilderProjectOrigin": "standalone-empty",
                "openrsc.worldBuilderDefinitionId": "integration.neutral.definitions.v1",
                "openrsc.worldBuilderDefinitionSha256": definition_sha,
                "openrsc.worldBuilderDefinitionEvidencePath": str(definitions),
                "openrsc.worldBuilderAssetId": "integration.neutral.assets.v1",
                "openrsc.worldBuilderAssetSha256": asset_sha,
                "openrsc.worldBuilderAssetEvidencePath": str(assets),
                "openrsc.worldBuilderSourceBaselineInventorySha256": baseline_inventory,
                "openrsc.worldBuilderInitialWorldSpace": "global",
                "openrsc.worldBuilderInitialLevel": "0",
                "openrsc.worldBuilderInitialX": "120",
                "openrsc.worldBuilderInitialY": "648",
            }
            server_command = ["java", "-Xms128m", "-Xmx768m"]
            server_command.extend(f"-D{key}={value}" for key, value in common_server_properties.items())
            server_command.extend([
                "-cp", os.pathsep.join(("lib/*", "core.jar", "plugins.jar")),
                "com.openrsc.server.Server", "world-builder.conf",
            ])

            server_output = server_log.open("w", encoding="utf-8")
            client_output = None
            server = subprocess.Popen(
                server_command, cwd=server_root, stdout=server_output,
                stderr=subprocess.STDOUT, text=True,
            )
            client = None
            try:
                wait_for(ready, server, 45, "server readiness", server_log)
                wait_for(credential, server, 5, "generated credential", server_log)
                wait_for(binding, server, 5, "runtime binding", server_log)
                self.assertEqual(20, len(credential.read_text(encoding="ascii")))

                client_properties = {
                    "openrsc.worldBuilderMode": "true",
                    "openrsc.worldBuilderAdaptiveMode": "true",
                    "openrsc.worldBuilderHost": "127.0.0.1",
                    "openrsc.worldBuilderPort": str(port),
                    "openrsc.worldBuilderCredentialFile": str(credential),
                    "openrsc.worldBuilderProjectName": "Integration Project",
                    "openrsc.worldBuilderSourceRevision": source_revision,
                    "openrsc.worldBuilderRuntimeBindingFile": str(binding),
                    "openrsc.worldBuilderDefinitionEvidenceFile": str(definitions),
                    "openrsc.worldBuilderAssetEvidenceFile": str(assets),
                    "spoiledmilk.clientLog": str(client_runtime_log),
                    "sun.java2d.opengl": "false",
                }
                if not manual_test:
                    client_properties[
                        "openrsc.worldBuilderAutomatedPlacementProbe"
                    ] = "place"
                client_command = ["java", "-Xms256m", "-Xmx1024m"]
                client_command.extend(
                    f"-D{key}={value}" for key, value in client_properties.items()
                )
                client_command.extend(["-jar", "Open_RSC_Client.jar"])
                client_output = client_log.open("w", encoding="utf-8")
                client = subprocess.Popen(
                    client_command, cwd=client_root, stdout=client_output,
                    stderr=subprocess.STDOUT, text=True,
                )
                if manual_test:
                    print(
                        "MANUAL_WORLD_BUILDER_READY "
                        f"workspace={project} logs={fixture}",
                        flush=True,
                    )
                    client.wait()
                    return
                runtime_evidence = wait_for_text(
                    client_runtime_log,
                    "ADAPTIVE_WORLD_BUILDER_PLACEMENTS_SAVED status=0",
                    client, 90, "adaptive client readiness",
                )
                self.assertEqual(0, client.wait(timeout=20), "desktop client clean shutdown")
                client_output.flush()
                client_evidence = client_log.read_text(
                    encoding="utf-8", errors="replace"
                )
                server_output.flush()
                server_evidence = server_log.read_text(
                    encoding="utf-8", errors="replace"
                )
                self.assertEqual(1, server_evidence.count("Player Loaded: Builder"))
                self.assertEqual(
                    1, server_evidence.count("Processed login request for Builder response: 86")
                )
                self.assertEqual(
                    1,
                    server_evidence.count(
                        "Adaptive World Builder binding accepted for authenticated player Builder"
                    ),
                )
                self.assertIn(
                    "location=WorldLocation{worldSpace=global, "
                    "coordinate=WorldCoordinate{x=120, y=648, level=0}}",
                    server_evidence,
                )
                self.assertIn("nativeTerrain=true initialRegion=true binding=true", runtime_evidence)
                self.assertIn(
                    "ADAPTIVE_WORLD_BUILDER_PLACEMENTS_VISIBLE mode=place "
                    "scenery=0@119,648 npc=0@120,649 item=10@121,648",
                    runtime_evidence,
                )
                self.assertIn(
                    "Layered scenery placement refused: "
                    "There is already scenery in that spot.",
                    runtime_evidence,
                )
                for family in ("scenery", "npc", "ground-item"):
                    self.assertEqual(
                        1,
                        server_evidence.count(
                            "WORLD_BUILDER_PLACEMENT_ACCEPTED family=" + family
                        ),
                    )
                self.assertIn(
                    "WORLD_BUILDER_PLACEMENT_REFUSED family=scenery id=0 "
                    "x=119 y=648 reason=There is already scenery in that spot.",
                    server_evidence,
                )
                for command in (
                    "worldeditormode", "aobject", "cnpc",
                    "buildergrounditem", "saveworldedits",
                ):
                    self.assertIn(
                        "Development.onCommand : [[Player:0:Builder @ (120, 648)], "
                        + command,
                        server_evidence,
                    )
                self.assertNotIn("Default.onCommand", server_evidence)
                self.assertIn(
                    "Skipping legacy terrain archives for explicit adaptive World Builder profile",
                    server_evidence,
                )
                self.assertEqual(1, client_evidence.count("login response:86"))
                combined = (
                    server_evidence + "\n" + runtime_evidence + "\n" + client_evidence
                ).lower()
                self.assertNotIn("socket timeout", combined)
                self.assertNotIn("sockettimeoutexception", combined)
                self.assertNotIn("login retry", combined)
                self.assertNotIn("lost connection", combined)
                self.assertNotIn("legacy landscape", combined)
                self.assertNotIn("fallback", combined)
                self.assertFalse((client_root / "Cache/video/Authentic_Landscape.orsc").exists())
                self.assertFalse((client_root / "Cache/video/Custom_Landscape.orsc").exists())

                placement_document = json.loads(
                    (package / "placements/global/lp0.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(
                    [(0, 119, 648, 0)],
                    [
                        (row["sceneryId"], row["position"]["x"],
                         row["position"]["y"], row["direction"])
                        for row in placement_document["scenery"]
                    ],
                )
                self.assertEqual(
                    [(0, 120, 649, 120, 649, 120, 649)],
                    [
                        (row["npcId"], row["start"]["x"], row["start"]["y"],
                         row["roamBounds"]["minimum"]["x"],
                         row["roamBounds"]["minimum"]["y"],
                         row["roamBounds"]["maximum"]["x"],
                         row["roamBounds"]["maximum"]["y"])
                        for row in placement_document["npcs"]
                    ],
                )
                self.assertEqual(
                    [(10, 1, 30, 121, 648)],
                    [
                        (row["itemId"], row["amount"], row["respawnSeconds"],
                         row["position"]["x"], row["position"]["y"])
                        for row in placement_document["groundItems"]
                    ],
                )

                reopened_runtime_log = fixture / "client-reopened-runtime.log"
                reopened_client_log = fixture / "client-reopened.log"
                reopened_properties = dict(client_properties)
                reopened_properties["openrsc.worldBuilderAutomatedPlacementProbe"] = "verify"
                reopened_properties["spoiledmilk.clientLog"] = str(
                    reopened_runtime_log
                )
                reopened_command = ["java", "-Xms256m", "-Xmx1024m"]
                reopened_command.extend(
                    f"-D{key}={value}"
                    for key, value in reopened_properties.items()
                )
                reopened_command.extend(["-jar", "Open_RSC_Client.jar"])
                with reopened_client_log.open("w", encoding="utf-8") as reopened_output:
                    reopened_client = subprocess.Popen(
                        reopened_command, cwd=client_root, stdout=reopened_output,
                        stderr=subprocess.STDOUT, text=True,
                    )
                    try:
                        reopened_evidence = wait_for_text(
                            reopened_runtime_log,
                            "ADAPTIVE_WORLD_BUILDER_PLACEMENTS_REOPENED status=0",
                            reopened_client, 90, "reopened adaptive client",
                        )
                        self.assertEqual(
                            0, reopened_client.wait(timeout=20),
                            "reopened desktop client clean shutdown",
                        )
                    finally:
                        if reopened_client.poll() is None:
                            reopened_client.terminate()
                            reopened_client.wait(timeout=10)
                self.assertIn(
                    "ADAPTIVE_WORLD_BUILDER_PLACEMENTS_VISIBLE mode=verify "
                    "scenery=0@119,648 npc=0@120,649 item=10@121,648",
                    reopened_evidence,
                )

                shutdown_started = time.monotonic()
                shutdown.write_text("shutdown\n", encoding="ascii")
                self.assertEqual(0, server.wait(timeout=30), "server clean shutdown")
                shutdown_elapsed = time.monotonic() - shutdown_started
                self.assertLess(
                    shutdown_elapsed, 20,
                    f"control-channel shutdown took {shutdown_elapsed:.3f}s",
                )
                server_output.flush()
                shutdown_evidence = server_log.read_text(
                    encoding="utf-8", errors="replace"
                )
                self.assertEqual(
                    1,
                    shutdown_evidence.count(
                        "World Builder launcher requested a clean local shutdown"
                    ),
                )
                self.assertIn("Server stop requested", shutdown_evidence)
                self.assertIn("Server unloaded", shutdown_evidence)
                self.assertIn("Exiting server process", shutdown_evidence)
                self.assertNotIn("Server thread termination failed", shutdown_evidence)
                self.assertFalse(shutdown.exists(), "shutdown request cleanup")
                self.assertFalse(ready.exists(), "readiness cleanup")
            finally:
                if client is not None and client.poll() is None:
                    client.terminate()
                    try:
                        client.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        client.kill()
                        client.wait(timeout=10)
                if server.poll() is None:
                    try:
                        shutdown.parent.mkdir(parents=True, exist_ok=True)
                        shutdown.write_text("shutdown\n", encoding="ascii")
                        server.wait(timeout=15)
                    except (OSError, subprocess.TimeoutExpired):
                        server.terminate()
                        server.wait(timeout=10)
                if client_output is not None:
                    client_output.close()
                server_output.close()


if __name__ == "__main__":
    unittest.main()
