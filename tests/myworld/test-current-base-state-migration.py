#!/usr/bin/env python3
"""Sealed execution proof for the Current Base Preservation migration row."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unittest

import jsonschema


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "current-platform/runtime/current-base-v1/state-migration.json"
SCHEMA = ROOT / "current-platform/schema/current-base-state-migration-v1.schema.json"
SQLITE_SCHEMA = ROOT / "server/database/sqlite/retro.sqlite"
CORE_SQLITE_SCHEMA = ROOT / "server/database/sqlite/core.sqlite"
INITIALIZED_SQLITE = ROOT / "legacy/docs/inherited-openrsc/sqlite-seeds/preservation.db"
MARIA_SCHEMA = ROOT / "server/database/mysql/retro.sql"
CORE = ROOT / "server/core.jar"
MAIN = "com.openrsc.server.database.CurrentBaseStateMigration"
MARIA_IMAGE = (
    "mariadb@sha256:"
    "611a2fcc5fa7c6ceb8644c6f74b25ede004ff6c3a6b38c8f8c23d3bbf6c26430"
)
EVIDENCE_KEYS = {
    "schemaId", "manifestType", "migrationRowId", "engine", "contractSha256",
    "sourceSchemaFingerprint", "sourceStateSha256",
    "stagedSourceProjectionSha256", "sourceBeforeSha256", "sourceAfterSha256",
    "sourceUnchanged", "stageLocation", "rollbackPolicy", "status",
}
CORE_BUILT = False


def build_core() -> None:
    global CORE_BUILT
    if CORE_BUILT:
        return
    build = subprocess.run(
        ["sh", "../tools/vendor/apache-ant-1.10.5/bin/ant", "compile_core"],
        cwd=ROOT / "server", capture_output=True, text=True,
    )
    if build.returncode != 0:
        raise AssertionError(build.stdout + build.stderr)
    CORE_BUILT = True


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def create_sqlite(path: Path, schema: str | None = None) -> None:
    sql = schema if schema is not None else SQLITE_SCHEMA.read_text(encoding="utf-8")
    with sqlite3.connect(path) as database:
        database.executescript(sql)


def seed_sqlite(path: Path) -> None:
    with sqlite3.connect(path) as database:
        database.execute(
            "INSERT INTO players(id,username,pass,salt,x,y) VALUES(?,?,?,?,?,?)",
            (41, "sealed_user", "sealed-test-hash", "", 216, 451),
        )
        for table in ("curstats", "maxstats", "experience", "capped_experience"):
            database.execute(
                f"INSERT INTO {table}(playerID,praygood,prayevil,goodmagic,"
                "evilmagic,woodcutting) VALUES(?,?,?,?,?,?)",
                (41, 16, 18, 17, 19, 20),
            )
        database.execute("INSERT INTO bank(playerID,itemID,slot) VALUES(41,10,0)")
        database.execute("INSERT INTO invitems(playerID,itemID,slot) VALUES(41,20,0)")
        database.execute("INSERT INTO quests(playerID,id,stage) VALUES(41,1,3)")
        database.execute(
            "INSERT INTO player_cache(playerID,type,key,value) "
            "VALUES(41,0,'sealed_key','sealed_value')"
        )


class CurrentBaseStateMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        build_core()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="current-base-migration-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_sqlite(
        self, source: Path, stage: Path, evidence: Path, *extra: str,
        inject: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        command = ["java"]
        if inject:
            command.append("-Dopenrsc.currentBaseMigrationTestFailure=true")
        command.extend([
            "-cp", str(CORE), MAIN, "--contract", str(CONTRACT),
            "--engine", "sqlite", "--source", str(source), "--stage", str(stage),
            "--evidence", str(evidence), *extra,
        ])
        return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)

    def test_contract_is_closed_and_hash_bound_by_platform(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(contract)
        platform = json.loads(
            (ROOT / "current-platform/platform/current-platform-r1.json").read_text()
        )
        record = next(
            row for row in platform["schemaContracts"]
            if row["schemaId"] == "current-base-state-migration-v1"
        )
        self.assertEqual(sha256(SCHEMA), record["sha256"])
        mutated = json.loads(json.dumps(contract))
        mutated["supportedSources"][0]["unexpected"] = True
        self.assertFalse(jsonschema.Draft202012Validator(schema).is_valid(mutated))

    def test_sqlite_migrates_all_rows_without_mutating_source(self) -> None:
        source = self.root / "source.db"
        stage = self.root / "stage.db"
        evidence_path = self.root / "evidence.json"
        create_sqlite(source)
        seed_sqlite(source)
        before = sha256(source)
        result = self.run_sqlite(source, stage, evidence_path)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, sha256(source))
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        self.assertEqual(EVIDENCE_KEYS, set(evidence))
        self.assertTrue(evidence["sourceUnchanged"])
        self.assertEqual("verified", evidence["status"])
        self.assertEqual(sha256(CONTRACT), evidence["contractSha256"])
        self.assertEqual(
            evidence["sourceStateSha256"],
            evidence["stagedSourceProjectionSha256"],
        )
        with sqlite3.connect(stage) as database:
            for table, defaults in (
                ("curstats", (18, 19, 20, 1)),
                ("maxstats", (18, 19, 20, 1)),
                ("experience", (18, 19, 20, 0)),
                ("capped_experience", (18, 19, 20, 0)),
            ):
                row = database.execute(
                    f"SELECT prayer,magic,woodcut,fletching,summoning FROM {table} "
                    "WHERE playerID=41"
                ).fetchone()
                self.assertEqual(defaults + (defaults[-1],), row)
            self.assertEqual((41, 10, 0), database.execute(
                "SELECT playerID,itemID,slot FROM bank WHERE playerID=41"
            ).fetchone())
            self.assertEqual((41, 20, 0), database.execute(
                "SELECT playerID,itemID,slot FROM invitems WHERE playerID=41"
            ).fetchone())
            self.assertEqual((41, 1, 3), database.execute(
                "SELECT playerID,id,stage FROM quests WHERE playerID=41"
            ).fetchone())
            self.assertEqual(("sealed_key", "sealed_value"), database.execute(
                "SELECT key,value FROM player_cache WHERE playerID=41"
            ).fetchone())
            self.assertEqual(4, database.execute(
                "SELECT COUNT(*) FROM db_patches"
            ).fetchone()[0])
            self.assertEqual(0, database.execute(
                "SELECT COUNT(*) FROM equipped"
            ).fetchone()[0])
            self.assertEqual(
                "preservation-retro-sqlite-to-current-base-v1",
                database.execute(
                    "SELECT migration_row_id FROM current_base_migrations"
                ).fetchone()[0],
            )

    def test_sqlite_refuses_custom_schema_and_preserves_preexisting_outputs(self) -> None:
        original = SQLITE_SCHEMA.read_text(encoding="utf-8")
        mutations = {
            "default": original.replace(
                "`slot`     INTEGER NOT NULL DEFAULT 0,",
                "`slot`     INTEGER NOT NULL DEFAULT 1,", 1),
            "check": original.replace(
                "`slot`     INTEGER NOT NULL DEFAULT 0,",
                "`slot`     INTEGER NOT NULL DEFAULT 0 CHECK (`slot` >= 0),", 1),
            "auto-unique": original.replace(
                "PRIMARY KEY (`playerId`, `itemId`, `slot`)",
                "UNIQUE (`playerID`, `itemID`),\n    PRIMARY KEY (`playerId`, `itemId`, `slot`)", 1),
            "generated": original.replace(
                "PRIMARY KEY (`playerId`, `itemId`, `slot`)",
                "`slot_shadow` INTEGER GENERATED ALWAYS AS (`slot`) VIRTUAL,\n    "
                "PRIMARY KEY (`playerId`, `itemId`, `slot`)", 1),
        }
        for label, schema in mutations.items():
            source = self.root / f"custom-{label}.db"
            stage = self.root / f"stage-{label}.db"
            evidence = self.root / f"evidence-{label}.json"
            create_sqlite(source, schema)
            before = sha256(source)
            refused = self.run_sqlite(source, stage, evidence)
            self.assertEqual(2, refused.returncode, label)
            self.assertIn("unsupported or customized sqlite source schema", refused.stderr)
            self.assertEqual(before, sha256(source))
            self.assertFalse(stage.exists())
            self.assertFalse(evidence.exists())

        pristine = self.root / "pristine.db"
        create_sqlite(pristine)
        stage = self.root / "stage.db"
        evidence = self.root / "evidence.json"
        stage.write_bytes(b"pre-existing-stage-sentinel")
        evidence.write_text("pre-existing-evidence-sentinel", encoding="utf-8")
        stage_before = stage.read_bytes()
        evidence_before = evidence.read_bytes()
        refused = self.run_sqlite(pristine, stage, evidence)
        self.assertEqual(2, refused.returncode)
        self.assertEqual(stage_before, stage.read_bytes())
        self.assertEqual(evidence_before, evidence.read_bytes())

    def test_initialized_preservation_row_preserves_populated_state(self) -> None:
        source = self.root / "initialized.db"
        stage = self.root / "stage.db"
        evidence = self.root / "evidence.json"
        shutil.copy2(INITIALIZED_SQLITE, source)
        with sqlite3.connect(source) as database:
            database.execute(
                "INSERT INTO players(id,username,pass,salt,creation_date,creation_ip,"
                "banned,offences,muted,kills,npc_kills,former_name,x,y,email) "
                "VALUES(913,'invented','fixture','',0,'0.0.0.0','0',0,'0',0,0,'',333,444,?)",
                ("invented@example.invalid",),
            )
            database.execute(
                "INSERT INTO curstats(playerID,prayer,magic,woodcut) VALUES(913,31,32,33)"
            )
        before = sha256(source)
        result = self.run_sqlite(source, stage, evidence)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, sha256(source))
        proof = json.loads(evidence.read_text(encoding="utf-8"))
        self.assertEqual(
            "preservation-initialized-sqlite-to-current-base-v1",
            proof["migrationRowId"],
        )
        with sqlite3.connect(stage) as database:
            self.assertEqual((913, "invented", "invented@example.invalid"), database.execute(
                "SELECT id,username,email FROM players WHERE id=913"
            ).fetchone())

    def test_raw_core_row_preserves_existing_skill_values(self) -> None:
        source = self.root / "core.db"
        stage = self.root / "core-stage.db"
        evidence = self.root / "core-evidence.json"
        create_sqlite(source, CORE_SQLITE_SCHEMA.read_text(encoding="utf-8"))
        with sqlite3.connect(source) as database:
            database.execute(
                "INSERT INTO players(id,username,pass,salt,creation_date,creation_ip,"
                "banned,offences,muted,kills,npc_kills,x,y) "
                "VALUES(77,'core_fixture','fixture','',0,'0.0.0','0',0,'0',0,0,222,333)"
            )
            database.execute(
                "INSERT INTO curstats(playerID,prayer,magic,woodcut) VALUES(77,41,42,43)"
            )
        before = sha256(source)
        result = self.run_sqlite(source, stage, evidence)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, sha256(source))
        self.assertEqual(
            "preservation-core-sqlite-to-current-base-v1",
            json.loads(evidence.read_text())["migrationRowId"],
        )
        with sqlite3.connect(stage) as database:
            self.assertEqual((77, "core_fixture", 222, 333), database.execute(
                "SELECT id,username,x,y FROM players WHERE id=77").fetchone())
            self.assertEqual((41, 42, 43, 1), database.execute(
                "SELECT prayer,magic,woodcut,summoning FROM curstats WHERE playerID=77"
            ).fetchone())
            self.assertEqual((31, 32, 33, 1, 1), database.execute(
                "SELECT prayer,magic,woodcut,summoning,blessing FROM curstats "
                "WHERE playerID=913"
            ).fetchone())

    def test_state_hash_frames_null_empty_text_and_binary_delimiters(self) -> None:
        hashes = []
        for index, email in enumerate((None, "", "null", sqlite3.Binary(b";\x00value"))):
            source = self.root / f"framed-{index}.db"
            stage = self.root / f"framed-{index}-stage.db"
            evidence = self.root / f"framed-{index}.json"
            shutil.copy2(INITIALIZED_SQLITE, source)
            with sqlite3.connect(source) as database:
                database.execute(
                    "INSERT INTO players(id,username,pass,salt,creation_date,creation_ip,"
                    "banned,offences,muted,kills,npc_kills,former_name,email) "
                    "VALUES(1,'framed','fixture','',0,'0.0.0','0',0,'0',0,0,'',?)",
                    (email,),
                )
            result = self.run_sqlite(source, stage, evidence)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            hashes.append(json.loads(evidence.read_text())["sourceStateSha256"])
        self.assertEqual(4, len(set(hashes)))

    def test_sqlite_refuses_active_sidecar(self) -> None:
        source = self.root / "sidecar.db"
        create_sqlite(source)
        sidecar = Path(str(source) + "-wal")
        sidecar.write_bytes(b"sealed-active-sidecar")
        result = self.run_sqlite(source, self.root / "stage.db", self.root / "evidence.json")
        self.assertEqual(2, result.returncode)
        self.assertIn("active journal sidecar", result.stderr)
        self.assertFalse((self.root / "stage.db").exists())

    def test_sqlite_rollback_and_closed_cli(self) -> None:
        source = self.root / "source.db"
        stage = self.root / "stage.db"
        evidence = self.root / "evidence.json"
        create_sqlite(source)
        before = sha256(source)
        refused = self.run_sqlite(
            source, stage, evidence, "--fail-after-copy", inject=True,
        )
        self.assertEqual(2, refused.returncode)
        self.assertIn("injected failure", refused.stderr)
        self.assertEqual(before, sha256(source))
        self.assertFalse(stage.exists())
        self.assertFalse(evidence.exists())

        refused = self.run_sqlite(
            source, stage, evidence, "--unknown-option", "value",
        )
        self.assertEqual(2, refused.returncode)
        self.assertIn("closed engine invocation", refused.stderr)
        self.assertFalse(stage.exists())


class CurrentBaseMariaMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        build_core()
        inspected = subprocess.run(
            ["docker", "image", "inspect", MARIA_IMAGE],
            capture_output=True, text=True,
        )
        if inspected.returncode != 0:
            raise AssertionError(
                "sealed MariaDB image is unavailable; expected " + MARIA_IMAGE
            )
        cls.container = f"current-base-migration-{os.getpid()}"
        subprocess.run(
            ["docker", "rm", "-f", cls.container],
            capture_output=True, text=True,
        )
        started = subprocess.run(
            ["docker", "run", "--rm", "-d", "--name", cls.container,
             "-e", "MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1",
             "-p", "127.0.0.1::3306", MARIA_IMAGE],
            capture_output=True, text=True,
        )
        if started.returncode != 0:
            raise AssertionError(started.stdout + started.stderr)
        cls.addClassCleanup(cls.stop_container)
        for _ in range(60):
            ready = subprocess.run(
                ["docker", "exec", cls.container, "mariadb-admin", "-uroot",
                 "ping", "--silent"],
                capture_output=True, text=True,
            )
            logs = subprocess.run(
                ["docker", "logs", cls.container], capture_output=True, text=True,
            )
            # The image first exposes a temporary initialization server.  Wait
            # for the second ready marker so schema import cannot race its stop.
            ready_markers = (logs.stdout + logs.stderr).lower().count(
                "ready for connections"
            )
            if ready.returncode == 0 and ready_markers >= 2:
                break
            time.sleep(1)
        else:
            logs = subprocess.run(
                ["docker", "logs", cls.container], capture_output=True, text=True,
            )
            raise AssertionError("MariaDB did not start:\n" + logs.stdout + logs.stderr)
        port_result = subprocess.run(
            ["docker", "port", cls.container, "3306/tcp"],
            check=True, capture_output=True, text=True,
        )
        cls.port = port_result.stdout.strip().rsplit(":", 1)[1]
        cls.sql(
            "CREATE DATABASE retro_source;"
            "CREATE USER 'migration'@'%' IDENTIFIED BY 'sealed-test-password';"
            "GRANT ALL PRIVILEGES ON *.* TO 'migration'@'%'; FLUSH PRIVILEGES;"
        )
        imported = subprocess.run(
            ["docker", "exec", "-i", cls.container, "mariadb", "-uroot",
             "retro_source"],
            input=MARIA_SCHEMA.read_text(encoding="utf-8"),
            capture_output=True, text=True,
        )
        if imported.returncode != 0:
            raise AssertionError(imported.stdout + imported.stderr)
        cls.sql(
            "USE retro_source;"
            "INSERT INTO players(id,username,pass,salt,x,y) VALUES"
            "(41,'sealed_user','sealed-test-hash','',216,451);"
            "INSERT INTO curstats(playerID,praygood,prayevil,goodmagic,evilmagic,woodcutting)"
            " VALUES(41,16,18,17,19,20);"
            "INSERT INTO maxstats(playerID,praygood,prayevil,goodmagic,evilmagic,woodcutting)"
            " VALUES(41,16,18,17,19,20);"
            "INSERT INTO experience(playerID,praygood,prayevil,goodmagic,evilmagic,woodcutting)"
            " VALUES(41,16,18,17,19,20);"
            "INSERT INTO capped_experience(playerID,praygood,prayevil,goodmagic,evilmagic,woodcutting)"
            " VALUES(41,16,18,17,19,20);"
            "INSERT INTO bank(playerID,itemID,slot) VALUES(41,10,0);"
            "INSERT INTO invitems(playerID,itemID,slot) VALUES(41,20,0);"
            "INSERT INTO quests(playerID,id,stage) VALUES(41,1,3);"
            "INSERT INTO player_cache(playerID,type,`key`,`value`)"
            " VALUES(41,0,'sealed_key','sealed_value');"
            "INSERT INTO db_patches(patch_name,run_date) VALUES"
            "('2021_05_11_add_db_patches.sql','2000-01-01'),"
            "('preservation_extension.sql','2001-02-03');"
        )

    @classmethod
    def stop_container(cls) -> None:
        subprocess.run(
            ["docker", "stop", getattr(cls, "container", "missing")],
            capture_output=True, text=True,
        )

    @classmethod
    def sql(cls, statement: str, database: str | None = None) -> str:
        command = ["docker", "exec", cls.container, "mariadb", "-uroot", "-N"]
        if database:
            command.append(database)
        command.extend(["-e", statement])
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        return result.stdout.strip()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="current-base-maria-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def migrate(
        self, stage: str, evidence: Path, *, inject: bool = False,
        source: str = "retro_source",
    ) -> subprocess.CompletedProcess[str]:
        command = ["java"]
        if inject:
            command.append("-Dopenrsc.currentBaseMigrationTestFailure=true")
        command.extend([
            "-cp", str(CORE), MAIN, "--contract", str(CONTRACT),
            "--engine", "mariadb", "--host", "127.0.0.1", "--port", self.port,
            "--source-schema", source, "--stage-schema", stage,
            "--user-env", "CURRENT_BASE_TEST_DB_USER",
            "--password-env", "CURRENT_BASE_TEST_DB_PASSWORD",
            "--evidence", str(evidence),
        ])
        if inject:
            command.append("--fail-after-copy")
        environment = dict(os.environ)
        environment["CURRENT_BASE_TEST_DB_USER"] = "migration"
        environment["CURRENT_BASE_TEST_DB_PASSWORD"] = "sealed-test-password"
        return subprocess.run(
            command, cwd=ROOT, env=environment, capture_output=True, text=True,
        )

    def test_mariadb_migrates_rows_and_discards_only_owned_failed_stage(self) -> None:
        evidence = self.root / "success.json"
        result = self.migrate("current_stage", evidence)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        row = self.sql(
            "SELECT prayer,magic,woodcut,fletching,summoning FROM curstats "
            "WHERE playerID=41",
            "current_stage",
        )
        self.assertEqual("18\t19\t20\t1\t1", row)
        self.assertEqual("2000-01-01", self.sql(
            "SELECT run_date FROM db_patches WHERE patch_name="
            "'2021_05_11_add_db_patches.sql'", "current_stage",
        ))
        self.assertEqual("2001-02-03", self.sql(
            "SELECT run_date FROM db_patches WHERE patch_name="
            "'preservation_extension.sql'", "current_stage",
        ))
        self.assertEqual("12", self.sql(
            "SELECT COUNT(*) FROM db_patches", "current_stage",
        ))
        self.assertEqual("0", self.sql(
            "SELECT COUNT(*) FROM equipped", "current_stage",
        ))
        self.assertEqual(
            "preservation-retro-mariadb-to-current-base-v1",
            self.sql("SELECT migration_row_id FROM current_base_migrations",
                     "current_stage"),
        )
        migration_evidence = json.loads(evidence.read_text(encoding="utf-8"))
        self.assertEqual(EVIDENCE_KEYS, set(migration_evidence))
        self.assertTrue(migration_evidence["sourceUnchanged"])
        self.assertEqual(
            migration_evidence["sourceStateSha256"],
            migration_evidence["stagedSourceProjectionSha256"],
        )

        failed_evidence = self.root / "failed.json"
        failed = self.migrate("failed_owned_stage", failed_evidence, inject=True)
        self.assertEqual(2, failed.returncode)
        self.assertEqual("0", self.sql(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.SCHEMATA "
            "WHERE SCHEMA_NAME='failed_owned_stage'"
        ))
        self.assertFalse(failed_evidence.exists())

        self.sql("CREATE DATABASE preexisting_stage; CREATE TABLE "
                 "preexisting_stage.sentinel(value INT); INSERT INTO "
                 "preexisting_stage.sentinel VALUES(73)")
        refused = self.migrate("preexisting_stage", self.root / "preexisting.json")
        self.assertEqual(2, refused.returncode)
        self.assertEqual("73", self.sql("SELECT value FROM sentinel", "preexisting_stage"))

    def test_mariadb_refuses_relevant_schema_customization(self) -> None:
        self.sql(
            "ALTER TABLE retro_source.curstats MODIFY praygood "
            "tinyint(3) UNSIGNED NOT NULL DEFAULT 2"
        )
        refused = self.migrate("custom_refused_stage", self.root / "custom.json")
        self.assertEqual(2, refused.returncode)
        self.assertIn("unsupported or customized mariadb source schema", refused.stderr)
        self.assertEqual("0", self.sql(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.SCHEMATA "
            "WHERE SCHEMA_NAME='custom_refused_stage'"
        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
