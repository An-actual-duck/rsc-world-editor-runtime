#!/usr/bin/env python3
"""Executable, disposable-only Current Base mutable-state location checks."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


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

    def probe(self, state=None, name="current_base", bound=True, core=None):
        archive = core or (OUTPUT / "server/core.jar" if bound else ROOT / "server/core.jar")
        command = ["java"]
        if bound:
            command.append(f"-Dopenrsc.currentCompositionIdentityFile={OUTPUT / 'composition-identity.json'}")
        if state is not None:
            command.append(f"-D{PROPERTY}={state}")
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
