#!/usr/bin/env python3
"""Executable, disposable-only Current Base mutable-state location checks."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import sqlite3
import zipfile
import importlib.util


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/current-platform/current-base-v1"
PROPERTY = "openrsc.currentBaseStateRoot"


class CurrentBaseStateLocationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["python3", "scripts/build-current-base.py", "--test-allow-dirty"],
                       cwd=ROOT, check=True, capture_output=True, text=True)
        cls.shared = tempfile.TemporaryDirectory(prefix="current-state-probe-")
        cls.classes = Path(cls.shared.name)
        source = cls.classes / "StateLocationProbe.java"
        source.write_text('''
import com.openrsc.server.CurrentCompositionIdentity;
import com.openrsc.server.database.impl.sqlite.CurrentBaseStateLocation;
public class StateLocationProbe {
  public static void main(String[] args) throws Exception {
    CurrentCompositionIdentity.initializeFromSystemProperties();
    if (args[0].equals("authoring")) {
      com.openrsc.server.Server server = new com.openrsc.server.Server("authoring.conf");
      com.openrsc.server.database.impl.sqlite.SqliteGameDatabaseConnection database =
        new com.openrsc.server.database.impl.sqlite.SqliteGameDatabaseConnection(server);
      if (!database.open()) throw new AssertionError("authoring SQLite open");
      try (java.sql.ResultSet result = database.getConnection().createStatement().executeQuery("SELECT value FROM state_probe")) {
        if (!result.next() || !"authoring-only".equals(result.getString(1))) throw new AssertionError("wrong database");
      }
      database.close();
      System.out.println("BASE_AUTHORING_STATE_INITIALIZED");
      System.exit(0);
    }
    System.out.println(CurrentBaseStateLocation.resolve(args[0]));
  }
}
''', encoding="utf-8")
        result = subprocess.run(["javac", "-source", "8", "-target", "8", "-cp",
                                 str(OUTPUT / "server/core.jar"), "-d", str(cls.classes),
                                 str(source), str(ROOT / "server/src/com/openrsc/server/database/impl/sqlite/CurrentBaseStateLocation.java")],
                                capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.shared.cleanup()

    def setUp(self):
        self.case = tempfile.TemporaryDirectory(prefix="current-state-location-")
        self.root = Path(self.case.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.state = self.root / "private state #?é"
        self.state.mkdir(mode=0o700)
        self.database = self.state / "current_base.db"
        self.database.write_bytes(b"synthetic-path-only-sentinel")
        self.database.chmod(0o600)

    def tearDown(self):
        self.case.cleanup()

    def probe(self, state=None, name="current_base", bound=True, core=None, authoring=None):
        archive = core or (OUTPUT / "server/core.jar" if bound else ROOT / "server/core.jar")
        command = ["java"]
        if bound:
            command.append(f"-Dopenrsc.currentCompositionIdentityFile={OUTPUT / 'composition-identity.json'}")
        if state is not None:
            command.append(f"-D{PROPERTY}={state}")
        if authoring is not None:
            command.extend([f"-Dopenrsc.currentBaseAuthoringStateRoot={authoring}",
                            f"-Dopenrsc.worldBuilderWorkspaceRoot={self.root}"])
        command.extend(["-cp", os.pathsep.join((str(archive), str(self.classes))),
                        "StateLocationProbe", name])
        return subprocess.run(command, cwd=self.runtime, capture_output=True, text=True, timeout=20)

    def refuse(self, state, expected, **kwargs):
        result = self.probe(state, **kwargs)
        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn(expected, result.stderr)

    def test_private_external_location_is_exact_and_does_not_write(self):
        before = hashlib.sha256(self.database.read_bytes()).hexdigest()
        result = self.probe(self.state)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(str(self.database), result.stdout.strip())
        self.assertEqual(before, hashlib.sha256(self.database.read_bytes()).hexdigest())
        self.assertEqual([self.database], list(self.state.iterdir()))

    def test_actual_base_authoring_initialization_is_isolated_and_guarded(self):
        self.runtime = self.root / "working/runtime/server"
        self.runtime.mkdir(parents=True)
        for relative in ("working/runtime/client", "run"):
            (self.root / relative).mkdir(parents=True)
        with zipfile.ZipFile(OUTPUT / "server/content.zip") as archive:
            archive.extractall(self.runtime)
        authoring = self.root / "working/authoring-state"
        authoring.mkdir(mode=0o700)
        database = authoring / "world_builder.db"
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE state_probe(value TEXT)")
            connection.execute("INSERT INTO state_probe VALUES('authoring-only')")
        database.chmod(0o600)
        spec = importlib.util.spec_from_file_location("adaptive_fixture", ROOT / "tests/myworld/test-adaptive-world-builder-runtime.py")
        adaptive = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adaptive)
        baseline = self.root / "source/layered-baseline/package"
        adaptive.write_package(baseline, empty=True)
        package = self.root / "working/layered-world/package"
        shutil.copytree(baseline, package)
        inventory = hashlib.sha256(b"".join(
            path.relative_to(package).as_posix().encode() + b"\0" + str(path.stat().st_size).encode()
            + b"\0" + hashlib.sha256(path.read_bytes()).hexdigest().encode() + b"\n"
            for path in sorted(package.rglob("*")) if path.is_file())).hexdigest()
        evidence = self.root / "working/provider"
        evidence.mkdir()
        for name in ("server-content.json", "client-content.json"):
            shutil.copyfile(ROOT / "current-platform/runtime/current-base-v1" / name, evidence / name)
        values = {
            "world_builder_mode": "true", "world_builder_adaptive_mode": "true",
            "db_type": "sqlite", "db_name": "world_builder", "db_table_prefix": "",
            "server_bind_address": "127.0.0.1", "max_players": "1", "want_packet_register": "false",
            "allow_in_game_world_editor": "true", "world_builder_layered_review_mode": "true",
            "layered_native_world_runtime_profile": "adaptive-world-builder", "world_builder_project_origin": "standalone-empty",
            "world_builder_definition_id": "test.base", "world_builder_asset_id": "test.base",
            "world_builder_initial_world_space": "global", "world_builder_initial_level": "0",
            "world_builder_initial_x": "0", "world_builder_initial_y": "0", "client_version": "10048",
        }
        for name in ("player_location_authority", "spatial_runtime_authority", "protocol_client_authority",
                     "native_terrain_package", "native_terrain_residency", "native_terrain_readiness",
                     "native_terrain_prediction", "native_terrain_symmetric_residency", "native_terrain_atomic_activation"):
            values["want_layered_" + name] = "true"
        for name in ("world_builder_definition_sha256", "world_builder_asset_sha256",
                     "world_builder_source_baseline_inventory_sha256", "layered_native_terrain_manifest_sha256",
                     "layered_native_terrain_inventory_sha256"):
            values[name] = "1" * 64
        values.update({
            "layered_native_terrain_package_path": str(package),
            "layered_native_terrain_manifest_sha256": hashlib.sha256((package / "manifest.json").read_bytes()).hexdigest(),
            "layered_native_terrain_inventory_sha256": inventory,
            "world_builder_source_baseline_inventory_sha256": inventory,
            "world_builder_definition_evidence_path": str(evidence / "server-content.json"),
            "world_builder_asset_evidence_path": str(evidence / "client-content.json"),
            "world_builder_definition_sha256": hashlib.sha256((evidence / "server-content.json").read_bytes()).hexdigest(),
            "world_builder_asset_sha256": hashlib.sha256((evidence / "client-content.json").read_bytes()).hexdigest(),
        })
        config = self.runtime / "authoring.conf"
        base = "\n".join(line for line in (self.runtime / "current-base.conf").read_text().splitlines()
                         if line.split(":", 1)[0].strip() not in values)
        text = base + "\n" + "\n".join(k + ": " + v for k,v in values.items()) + "\n"
        config.write_text(text)
        before = self.database.read_bytes()
        result = self.probe(name="authoring", authoring=authoring)
        self.assertEqual(0, result.returncode, (result.stdout + result.stderr)[-5000:])
        self.assertIn("BASE_AUTHORING_STATE_INITIALIZED", result.stdout)
        self.assertEqual(before, self.database.read_bytes())
        self.assertFalse((self.runtime / "inc/sqlite/world_builder.db").exists())
        for state, selected, mutation in (
            (self.state, authoring, None), (None, self.state, None),
            (None, authoring, "world_builder_adaptive_mode: false\n"),
            (None, authoring, "server_bind_address: 0.0.0.0\n"),
            (None, authoring, "db_name: current_base\n"),
        ):
            selected_text = text if mutation is None else "\n".join(
                line for line in text.splitlines() if line.split(":", 1)[0] != mutation.split(":", 1)[0]) + "\n" + mutation
            config.write_text(selected_text)
            result = self.probe(state=state, name="authoring", authoring=selected)
            self.assertNotEqual(0, result.returncode, result.stdout)
        config.write_text(text)
        self.refuse(None, "requires validated adaptive", authoring=authoring)

    def test_current_base_never_falls_back_or_creates_missing_state(self):
        fallback = self.runtime / "inc/sqlite/current_base.db"
        fallback.parent.mkdir(parents=True)
        fallback.write_bytes(b"must-not-be-used")
        self.refuse(None, "no in-runtime database fallback")
        self.refuse("", "no in-runtime database fallback")
        self.refuse(self.state, "canonical current_base database name", name="other")
        self.database.unlink()
        self.refuse(self.state, "missing, linked, or has the wrong file type")
        self.assertFalse(self.database.exists())
        self.assertEqual(b"must-not-be-used", fallback.read_bytes())

    def test_non_base_retains_historical_layout_and_rejects_override(self):
        result = self.probe(bound=False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("null", result.stdout.strip())
        self.refuse(self.state, "requires an initialized Current Base composition", bound=False)

    def test_aliases_and_runtime_overlap_are_refused(self):
        self.refuse("../" + self.state.name, "canonical absolute directory")
        self.refuse(str(self.state) + "/../" + self.state.name, "canonical absolute directory")
        alias = self.root / "state-alias"
        alias.symlink_to(self.state, target_is_directory=True)
        self.refuse(alias, "canonical absolute directory")
        parent_alias = self.root / "parent-alias"
        parent_alias.symlink_to(self.root, target_is_directory=True)
        self.refuse(parent_alias / self.state.name, "canonical absolute directory")
        nested = self.runtime / "state"
        nested.mkdir(mode=0o700)
        self.refuse(nested, "disjoint from runtime artifacts and working directory")
        self.runtime.chmod(0o700)
        self.refuse(self.runtime, "disjoint from runtime artifacts and working directory")
        self.refuse(self.root, "disjoint from runtime artifacts and working directory")
        # Prove artifact disjointness independently of the process working directory.
        copied_core = self.state / "core.jar"
        shutil.copy2(OUTPUT / "server/core.jar", copied_core)
        self.refuse(self.state, "disjoint from runtime artifacts and working directory", core=copied_core)

    def test_private_modes_and_file_aliases_are_required(self):
        self.state.chmod(0o755)
        self.refuse(self.state, "directory mode 0700 and file mode 0600")
        self.state.chmod(0o700)
        self.database.chmod(0o644)
        self.refuse(self.state, "directory mode 0700 and file mode 0600")
        self.database.chmod(0o600)
        alias = self.root / "database-hardlink"
        os.link(self.database, alias)
        self.refuse(self.state, "hard-link aliases")
        self.database.unlink()
        self.database.symlink_to(alias)
        self.refuse(self.state, "missing, linked, or has the wrong file type")

    def test_live_recovery_sidecars_must_remain_private_regular_files(self):
        for suffix in ("-journal", "-wal", "-shm"):
            with self.subTest(suffix=suffix):
                sidecar = self.state / ("current_base.db" + suffix)
                sidecar.write_bytes(b"synthetic-sidecar")
                sidecar.chmod(0o600)
                self.assertEqual(0, self.probe(self.state).returncode)
                sidecar.chmod(0o644)
                self.refuse(self.state, "directory mode 0700 and file mode 0600")
                sidecar.unlink()
                sidecar.symlink_to(self.database)
                self.refuse(self.state, "missing, linked, or has the wrong file type")
                sidecar.unlink()


if __name__ == "__main__":
    unittest.main()
