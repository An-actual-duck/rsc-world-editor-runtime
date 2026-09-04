#!/usr/bin/env python3
"""Execute the built Current Base pair through login, map, state, and restart."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/current-platform/current-base-v1"
IDENTITY = OUTPUT / "composition-identity.json"
CONTRACT = ROOT / "current-platform/runtime/current-base-v1/state-migration.json"


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, separators=(",", ":")) + "\n").encode("utf-8")


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def replace_config(text: str, key: str, value: str) -> str:
    updated, count = re.subn(
        rf"(?m)^(\s*{re.escape(key)}:\s*).*$", rf"\g<1>{value}", text, count=1
    )
    if count != 1:
        raise AssertionError("Current Base config lacks " + key)
    return updated


def wait_for_text(
    path: Path, needle: str, process: subprocess.Popen, timeout: float, label: str,
) -> str:
    deadline = time.monotonic() + timeout
    latest = ""
    while time.monotonic() < deadline:
        if path.is_file():
            latest = path.read_text(encoding="utf-8", errors="replace")
            if needle in latest:
                return latest
        if process.poll() is not None:
            raise AssertionError(
                f"{label} exited early with {process.returncode}\n{latest}"
            )
        time.sleep(0.2)
    raise AssertionError(f"timed out waiting for {label} marker {needle!r}\n{latest}")


def write_package(root: Path) -> None:
    x, y = 120, 648
    sector_x, sector_y = x // 48, y // 48
    terrain_path = f"terrain/global/lp0/xp{sector_x}-yp{sector_y}.raw"
    placement_path = "placements/global/lp0.json"
    terrain = bytes((0, 1, 8, 0, 0, 0, 0, 0, 0, 0)) * (48 * 48)
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
        "packageId": "current-base.sealed.public-map",
        "packageVersion": "1.0.0",
        "coordinateModel": "signed-layered-v1",
        "storage": {"sectorSize": 48, "presentationChunkSize": 24},
        "worldSpaces": [{"id": "global", "kind": "static"}],
        "levels": [{
            "worldSpace": "global", "level": 0,
            "name": "Current Base public level", "role": "authoring-level",
        }],
        "terrainSectors": [{
            "worldSpace": "global", "level": 0,
            "sectorX": sector_x, "sectorY": sector_y,
            "encoding": "raw-layered-sector-v1", "path": terrain_path,
            "sha256": hashlib.sha256(terrain).hexdigest(),
        }],
        "placementSets": [{
            "id": "current-base-global-lp0", "worldSpace": "global", "level": 0,
            "encoding": "layered-world-placements-v3", "path": placement_path,
            "sha256": hashlib.sha256(placements).hexdigest(),
        }],
    }
    (root / "manifest.json").write_bytes(canonical_json(manifest))


def package_fingerprint(core: Path, package: Path, classes: Path) -> str:
    source = classes / "CurrentBasePackageFingerprint.java"
    source.write_text(
        """
import com.openrsc.server.io.AdaptiveWorldBuilderPackageGuard;
import java.nio.file.Paths;
public final class CurrentBasePackageFingerprint {
  public static void main(String[] args) throws Exception {
    System.out.println(AdaptiveWorldBuilderPackageGuard
      .requireClosedPackage(Paths.get(args[0])).getFingerprint());
  }
}
""".strip() + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["javac", "-source", "8", "-target", "8", "-cp", str(core),
         "-d", str(classes), str(source)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    result = subprocess.run(
        ["java", "-cp", os.pathsep.join((str(core), str(classes))),
         "CurrentBasePackageFingerprint", str(package)],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )
    fingerprint = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise AssertionError("invalid canonical package fingerprint: " + fingerprint)
    return fingerprint


def seed_retro_database(path: Path) -> None:
    with sqlite3.connect(path) as database:
        database.executescript(
            (ROOT / "server/database/sqlite/retro.sqlite").read_text(encoding="utf-8")
        )
        database.execute(
            "INSERT INTO players(id,username,pass,salt,x,y,quest_points,login_date) "
            "VALUES(41,'sealed user','sealedpass','',120,648,2,100)"
        )
        for table in ("curstats", "maxstats", "experience", "capped_experience"):
            database.execute(
                f"INSERT INTO {table}(playerID,praygood,prayevil,goodmagic,"
                "evilmagic,woodcutting) VALUES(41,16,18,17,19,20)"
            )
        database.execute(
            "INSERT INTO itemstatuses(itemID,catalogID,amount,noted,wielded,durability) "
            "VALUES(1001,10,73,0,0,0)"
        )
        database.execute("INSERT INTO invitems(playerID,itemID,slot) VALUES(41,1001,0)")
        database.execute(
            "INSERT INTO itemstatuses(itemID,catalogID,amount,noted,wielded,durability) "
            "VALUES(1002,20,2,0,0,0)"
        )
        database.execute("INSERT INTO bank(playerID,itemID,slot) VALUES(41,1002,0)")
        database.execute("INSERT INTO quests(playerID,id,stage) VALUES(41,1,3)")
        database.execute(
            "INSERT INTO player_cache(playerID,type,`key`,`value`) "
            "VALUES(41,0,'sealed_counter','73')"
        )
        database.execute(
            "INSERT INTO ironman(playerID,iron_man,iron_man_restriction,hc_ironman_death) "
            "VALUES(41,0,1,0)"
        )


class CurrentBaseRuntimeExecutionTest(unittest.TestCase):
    def test_built_pair_logs_in_loads_native_map_and_persists_across_restart(self) -> None:
        if not os.environ.get("DISPLAY"):
            self.fail("Current Base executable client evidence requires DISPLAY")
        subprocess.run(
            ["python3", "scripts/build-current-base.py"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        core = OUTPUT / "server/core.jar"
        plugins = OUTPUT / "server/plugins.jar"
        client_jar = OUTPUT / "client/Open_RSC_Client.jar"
        for artifact in (IDENTITY, core, plugins, client_jar,
                         OUTPUT / "server/content.zip", OUTPUT / "client/content.zip"):
            self.assertTrue(artifact.is_file(), str(artifact))

        with tempfile.TemporaryDirectory(prefix="current-base-runtime-") as temporary:
            fixture = Path(temporary)
            server_root = fixture / "server"
            client_root = fixture / "client"
            server_root.mkdir()
            client_root.mkdir()
            with zipfile.ZipFile(OUTPUT / "server/content.zip") as archive:
                archive.extractall(server_root)
            with zipfile.ZipFile(OUTPUT / "client/content.zip") as archive:
                archive.extractall(client_root)
            shutil.copy2(core, server_root / "core.jar")
            shutil.copy2(plugins, server_root / "plugins.jar")
            shutil.copy2(client_jar, client_root / "Open_RSC_Client.jar")
            (client_root / "Cache/discord_inuse.txt").write_text("1", encoding="ascii")

            source_package = fixture / "package"
            write_package(source_package)
            classes = fixture / "classes"
            classes.mkdir()
            fingerprint = package_fingerprint(core, source_package, classes)
            manifest_hash = hashlib.sha256(
                (source_package / "manifest.json").read_bytes()
            ).hexdigest()
            relative_package = f"world-builder/packages/{fingerprint}/package"
            for runtime_root in (server_root, client_root):
                shutil.copytree(source_package, runtime_root / relative_package)
                profile_root = runtime_root / "world-builder-configs"
                profile_root.mkdir()
                (profile_root / (
                    "installed-server.json" if runtime_root == server_root
                    else "installed-client.json"
                )).write_text(json.dumps({
                    "schemaVersion": 1,
                    "manifestType": (
                        "world-builder-installed-server-profile"
                        if runtime_root == server_root
                        else "world-builder-installed-client-profile"
                    ),
                    "active": True,
                    "packageId": "current-base.sealed.public-map",
                    "packageVersion": "1.0.0",
                    "packageFingerprintSha256": fingerprint,
                    "manifestSha256": manifest_hash,
                    "packageRelativePath": relative_package,
                }, sort_keys=True, indent=2) + "\n", encoding="utf-8")

            source_db = fixture / "preservation-source.db"
            stage_db = server_root / "inc/sqlite/current_base.db"
            stage_db.parent.mkdir(parents=True)
            seed_retro_database(source_db)
            source_before = hashlib.sha256(source_db.read_bytes()).hexdigest()
            migrated = subprocess.run(
                ["java", "-cp", str(core),
                 "com.openrsc.server.database.CurrentBaseStateMigration",
                 "--contract", str(CONTRACT), "--engine", "sqlite",
                 "--source", str(source_db), "--stage", str(stage_db),
                 "--evidence", str(fixture / "migration-evidence.json")],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(0, migrated.returncode, migrated.stdout + migrated.stderr)
            self.assertEqual(source_before, hashlib.sha256(source_db.read_bytes()).hexdigest())

            credential = fixture / "credential.json"
            credential.write_text(json.dumps({
                "username": "sealed_user", "password": "sealedpass"
            }) + "\n", encoding="utf-8")
            port = free_port()
            ws_port = free_port()
            config_path = server_root / "current-base.conf"
            config = config_path.read_text(encoding="utf-8")
            config = replace_config(config, "server_port", str(port))
            config = replace_config(config, "ws_server_port", str(ws_port))
            config_path.write_text(config, encoding="utf-8")

            runtime_profile = json.loads((
                ROOT / "current-platform/runtime/current-base-v1/profile.json"
            ).read_text(encoding="utf-8"))
            advanced_configuration = runtime_profile["advancedExclusions"][
                "configuration"
            ]
            self.assertTrue(advanced_configuration)
            for key, expected in advanced_configuration.items():
                self.assertIs(expected, False)
                matches = re.findall(
                    rf"(?m)^\s*{re.escape(key)}:\s*(\S+)\s*$", config
                )
                self.assertEqual(
                    ["false"], matches,
                    f"launched server config did not exactly disable {key}",
                )

            server_profile = server_root / "world-builder-configs/installed-server.json"
            client_profile = client_root / "world-builder-configs/installed-client.json"
            refused = subprocess.run(
                [
                    "java",
                    f"-Dopenrsc.currentCompositionIdentityFile={IDENTITY}",
                    f"-Dopenrsc.worldBuilderInstalledClientProfile={client_profile}",
                    "-Dopenrsc.currentBaseExecutionEvidence=true",
                    "-Dopenrsc.currentBaseHost=localhost",
                    f"-Dopenrsc.currentBasePort={port}",
                    f"-Dopenrsc.currentBaseCredentialFile={credential}",
                    "-jar", "Open_RSC_Client.jar",
                ],
                cwd=client_root, capture_output=True, text=True,
            )
            self.assertEqual(2, refused.returncode, refused.stdout + refused.stderr)
            self.assertIn(
                "endpoint must be literal loopback 127.0.0.1", refused.stderr
            )
            evidence_runs = []
            for run_number in (1, 2):
                server_log = fixture / f"server-{run_number}.log"
                client_log = fixture / f"client-{run_number}.log"
                runtime_log = fixture / f"client-runtime-{run_number}.log"
                server_command = [
                    "java", "-Xms128m", "-Xmx768m",
                    f"-Dopenrsc.currentCompositionIdentityFile={IDENTITY}",
                    f"-Dopenrsc.worldBuilderInstalledServerProfile={server_profile}",
                    "-cp", os.pathsep.join(("core.jar", "plugins.jar")),
                    "com.openrsc.server.Server", "current-base.conf",
                ]
                with server_log.open("w", encoding="utf-8") as server_output:
                    server = subprocess.Popen(
                        server_command, cwd=server_root, stdout=server_output,
                        stderr=subprocess.STDOUT, text=True,
                    )
                client = None
                try:
                    server_evidence = wait_for_text(
                        server_log, "Game world is now online on", server, 60,
                        f"Current Base server run {run_number}",
                    )
                    self.assertIn("PatchApplier: - Database patches are up to date", server_evidence)
                    self.assertIn("PLAYER_ITEM_ID_AUDIT passed", server_evidence)
                    client_command = [
                        "java", "-Xms256m", "-Xmx1024m",
                        f"-Dopenrsc.currentCompositionIdentityFile={IDENTITY}",
                        f"-Dopenrsc.worldBuilderInstalledClientProfile={client_profile}",
                        "-Dopenrsc.currentBaseExecutionEvidence=true",
                        "-Dopenrsc.currentBaseHost=127.0.0.1",
                        f"-Dopenrsc.currentBasePort={port}",
                        f"-Dopenrsc.currentBaseCredentialFile={credential}",
                        f"-Dspoiledmilk.clientLog={runtime_log}",
                        "-Dsun.java2d.opengl=false", "-jar", "Open_RSC_Client.jar",
                    ]
                    with client_log.open("w", encoding="utf-8") as client_output:
                        client = subprocess.Popen(
                            client_command, cwd=client_root, stdout=client_output,
                            stderr=subprocess.STDOUT, text=True,
                        )
                    try:
                        runtime_evidence = wait_for_text(
                            runtime_log, "CURRENT_BASE_RUNTIME_EXECUTION", client, 90,
                            f"Current Base client run {run_number}",
                        )
                    except AssertionError as failure:
                        client_text = client_log.read_text(
                            encoding="utf-8", errors="replace"
                        ) if client_log.is_file() else "<missing>"
                        server_text = server_log.read_text(
                            encoding="utf-8", errors="replace"
                        ) if server_log.is_file() else "<missing>"
                        raise AssertionError(
                            f"{failure}\nCLIENT LOG:\n{client_text}\n"
                            f"SERVER LOG:\n{server_text}"
                        ) from failure
                    evidence_runs.append(runtime_evidence)
                    self.assertEqual(0, client.wait(timeout=20))
                    server_evidence = wait_for_text(
                        server_log, "Unregistered sealed user from player list.",
                        server, 20, f"Current Base logout run {run_number}",
                    )
                    self.assertIn(
                        "Current composition handshake accepted", server_evidence
                    )
                    self.assertIn("variant=current-base-v1", server_evidence)
                    self.assertIn(
                        "Processed login request for sealed user response: 64",
                        server_evidence,
                    )
                finally:
                    if client is not None and client.poll() is None:
                        client.terminate()
                        client.wait(timeout=10)
                    server.terminate()
                    try:
                        server.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        server.kill()
                        server.wait(timeout=10)

            expected_marker = (
                "CURRENT_BASE_RUNTIME_EXECUTION variant=current-base-v1 "
                "canonicalMap=true initialRegion=true worldX=120 worldY=648 "
                "coins=73 prayer=18 magic=19 woodcut=20 quest1=3 "
                "clientAdvanced=false"
            )
            for evidence in evidence_runs:
                self.assertIn(expected_marker, evidence)
            with sqlite3.connect(stage_db) as database:
                player = database.execute(
                    "SELECT x,y,online,pass FROM players WHERE id=41"
                ).fetchone()
                self.assertEqual((120, 648, 0), player[:3])
                self.assertEqual("sealedpass", player[3])
                self.assertEqual((18, 19, 20), database.execute(
                    "SELECT prayer,magic,woodcut FROM curstats WHERE playerID=41"
                ).fetchone())
                self.assertEqual((10, 73), database.execute(
                    "SELECT catalogID,amount FROM itemstatuses WHERE itemID=1001"
                ).fetchone())
                self.assertEqual((1, 3), database.execute(
                    "SELECT id,stage FROM quests WHERE playerID=41"
                ).fetchone())
                self.assertEqual(("sealed_counter", "73"), database.execute(
                    "SELECT key,value FROM player_cache WHERE playerID=41"
                ).fetchone())
                self.assertEqual(
                    "preservation-retro-to-current-base-v1",
                    database.execute(
                        "SELECT migration_row_id FROM current_base_migrations"
                    ).fetchone()[0],
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
