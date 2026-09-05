#!/usr/bin/env python3
"""Actual installed role JVMs, persistent leases, closed paths and restartable launch."""
from __future__ import annotations

import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unittest
import uuid
import zipfile
from PIL import ImageGrab, ImageChops

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/current-platform/current-base-v1"
SPEC = importlib.util.spec_from_file_location("installed_execution_fixture",
    ROOT / "tests/myworld/test-current-base-installed-execution.py")
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def binding(path):
    return {"path": str(path), "sha256": FIXTURE.sha256(path)}


def tree_hash(path, package=False):
    digest = hashlib.sha256()
    for entry in sorted(value for value in path.rglob("*") if value.is_file()):
        row = entry.relative_to(path).as_posix() + "\0"
        if package:
            row += str(entry.stat().st_size) + "\0"
        row += FIXTURE.sha256(entry) + ("\n" if package else "\0")
        digest.update(row.encode("utf-8"))
    return digest.hexdigest()


class CurrentBaseInstalledLaunchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(["python3", "scripts/build-current-base.py", "--test-allow-dirty"],
            cwd=ROOT, capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout[-4000:] + result.stderr[-4000:])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="installed-launch-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.anchor = self.root / "installation"
        self.anchor.mkdir(mode=0o700)
        (self.anchor / "sessions").mkdir(mode=0o700)
        self.processes = []
        self.addCleanup(self.stop_processes)
        self.code, self.state, self.working, self.side, self.descriptors = {}, {}, {}, {}, {}
        self.map = self.root / "map"
        FIXTURE.write_package(self.map)
        self.port = FIXTURE.free_port()
        installation_id = str(uuid.uuid4())
        for role, jar in (("server", "core.jar"), ("client", "Open_RSC_Client.jar")):
            self.code[role] = self.root / (role + "-code")
            self.code[role].mkdir()
            with zipfile.ZipFile(OUTPUT / role / "content.zip") as archive:
                archive.extractall(self.code[role])
            shutil.copy2(OUTPUT / role / jar, self.code[role] / jar)
            if role == "server":
                shutil.copy2(OUTPUT / role / "plugins.jar", self.code[role] / "plugins.jar")
            self.state[role] = self.root / (role + "-state")
            self.state[role].mkdir(mode=0o700)
            self.side[role] = self.state[role] / "side"
            self.side[role].mkdir(mode=0o700)
            self.working[role] = self.root / (role + "-work")
            self.working[role].mkdir(mode=0o700)
            (self.anchor / "sessions" / role).mkdir(mode=0o700)
            (self.anchor / (role + ".lock")).touch(mode=0o600)
            profile = self.root / (role + "-map-profile.json")
            fingerprint = tree_hash(self.map, True)
            write_json(profile, {"schemaVersion": 1,
                "manifestType": "world-builder-installed-" + role + "-profile", "active": True,
                "packageId": "current-base.installed-verifier-map", "packageVersion": "1.0.0",
                "packageFingerprintSha256": fingerprint,
                "manifestSha256": FIXTURE.sha256(self.map / "manifest.json"),
                "packageRelativePath": "world-builder/packages/" + fingerprint + "/package"})
            self.descriptors[role] = {"schemaVersion": 1, "manifestType": "current-base-installed-launch",
                "role": role, "installationId": installation_id,
                "compositionIdentity": binding(OUTPUT / "composition-identity.json"),
                "runtimeProfile": binding(OUTPUT / "runtime/profile.json"),
                "installedMapProfile": binding(profile), "mapRoot": str(self.map),
                "mapPackageFingerprintSha256": fingerprint,
                "codeRoot": str(self.code[role]), "codeTreeSha256": tree_hash(self.code[role]),
                "workingRoot": str(self.working[role]), "stateRoot": str(self.state[role]),
                "sideStateRoot": str(self.side[role]), "installationRoot": str(self.anchor),
                "sessionRoot": str(self.anchor / "sessions" / role),
                "configuration": {}, "endpoint": {"host": "127.0.0.1", "gamePort": self.port}}
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:512",
            "-out", str(self.side["server"] / "server.pem")], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", str(self.side["server"] / "server.pem"), "-pubout",
            "-out", str(self.side["server"] / "client.pem")], check=True, capture_output=True)
        shutil.copy2(self.side["server"] / "client.pem", self.side["client"] / "client.pem")
        for role in ("server", "client"):
            self.descriptors[role]["publicKey"] = binding(self.side[role] / "client.pem")
        for name in ("badwords", "goodwords", "alertwords"):
            (self.side["server"] / (name + ".txt")).write_text("inventedword\n")
        config = self.root / "complete-server.conf"
        config.write_text((self.code["server"] / "current-base.conf").read_text().replace(
            "server_port: 43594", "server_port: " + str(self.port)) + "\ndb_type: sqlite\n")
        self.descriptors["server"]["configuration"] = binding(config)
        result = subprocess.run(["java", "-cp", str(self.code["server"] / "core.jar"), FIXTURE.MIGRATION_MAIN,
            "--contract", str(FIXTURE.MIGRATION), "--engine", "sqlite", "--source", str(FIXTURE.INITIALIZED),
            "--stage", str(self.state["server"] / "current_base.db"),
            "--evidence", str(self.root / "migration-evidence.json")], capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        (self.state["server"] / "current_base.db").chmod(0o600)
        with sqlite3.connect(self.state["server"] / "current_base.db") as database:
            database.execute("INSERT INTO players(id,username,pass,salt,x,y,quest_points,login_date) "
                "VALUES(901,'launchtest','launchpass','',120,648,0,100)")
            for table in ("curstats", "maxstats", "experience", "capped_experience"):
                database.execute("INSERT INTO " + table + "(playerID,prayer,magic,woodcut,summoning) VALUES(901,11,16,21,1)")
            database.execute("INSERT INTO itemstatuses(itemID,catalogID,amount,noted,wielded,durability) VALUES(901,10,321,0,0,0)")
            database.execute("INSERT INTO invitems(playerID,itemID,slot) VALUES(901,901,0)")
            database.execute("INSERT INTO quests(playerID,id,stage) VALUES(901,1,3)")
            database.execute("INSERT INTO ironman(playerID,iron_man,iron_man_restriction,hc_ironman_death) VALUES(901,0,1,0)")
        for role in ("server", "client"):
            write_json(self.root / (role + "-launch.json"), self.descriptors[role])
        self.active = {"schemaVersion": 1, "manifestType": "current-base-installed-selection",
            "installationId": installation_id,
            "serverDescriptorSha256": FIXTURE.sha256(self.root / "server-launch.json"),
            "clientDescriptorSha256": FIXTURE.sha256(self.root / "client-launch.json")}
        write_json(self.anchor / "active-launch.json", self.active)

    def stop_processes(self):
        for process, output in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=90)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            output.close()

    def command(self, role, descriptor=None):
        jar = "core.jar" if role == "server" else "Open_RSC_Client.jar"
        main = "com.openrsc.server.CurrentBaseInstalledServer" if role == "server" else "orsc.CurrentBaseInstalledClient"
        classpath = str(self.code[role] / jar)
        if role == "server": classpath += os.pathsep + str(self.code[role] / "plugins.jar")
        return ["java", "-Xms128m", "-Xmx768m", "-cp", classpath, main,
            "--launch", str(descriptor or self.root / (role + "-launch.json"))]

    def start(self, role, descriptor=None):
        before = set((self.anchor / "sessions" / role).iterdir())
        output = tempfile.TemporaryFile(mode="w+")
        process = subprocess.Popen(self.command(role, descriptor), cwd=self.working[role],
            stdout=output, stderr=subprocess.STDOUT, text=True)
        self.processes.append((process, output))
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            sessions = set((self.anchor / "sessions" / role).iterdir()) - before
            ready = [path / "ready.json" for path in sessions if (path / "ready.json").exists()]
            if ready:
                self.assertEqual(1, len(ready))
                return process, ready[0]
            if process.poll() is not None:
                break
            time.sleep(0.05)
        output.seek(0)
        self.fail("Actual installed " + role + " failed readiness: " + output.read()[-7000:])

    def stop(self, process, ready):
        value = json.loads(ready.read_text())
        value["action"] = "shutdown"
        write_json(ready.parent / "shutdown.json", value)
        self.assertEqual(0, process.wait(timeout=90))

    def assert_locked(self, role):
        with (self.anchor / (role + ".lock")).open("r+") as stream:
            with self.assertRaises(BlockingIOError):
                fcntl.lockf(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def log(self, process):
        output = next(output for child, output in self.processes if child is process)
        return os.pread(output.fileno(), 1024 * 1024, 0).decode("utf-8", errors="replace")

    def manual_login(self, server, client):
        self.assertIsNotNone(shutil.which("xdotool"), "Manual UI integration requires xdotool")
        def xdo(*args):
            return subprocess.run(["xdotool", *map(str, args)], capture_output=True, text=True, check=True).stdout
        deadline = time.monotonic() + 30
        while "Got server configs!" not in self.log(client) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertIn("Got server configs!", self.log(client))
        time.sleep(2)
        windows = xdo("search", "--onlyvisible", "--pid", client.pid).split()
        self.assertEqual(1, len(windows), "Only this owned child window is admitted for test input")
        window = windows[0]
        geometry = dict(line.split("=", 1) for line in xdo("getwindowgeometry", "--shell", window).splitlines())
        x, y, width, height = (int(geometry[key]) for key in ("X", "Y", "WIDTH", "HEIGHT"))
        before = ImageGrab.grab(bbox=(x, y, x + width, y + height)).convert("RGB")
        before.save(self.root / "manual-before.png")
        if os.environ.get("CURRENT_BASE_UI_DEBUG_DIR"):
            before.save(Path(os.environ["CURRENT_BASE_UI_DEBUG_DIR"]) / "before.png")
        print("Manual launch geometry", geometry, str(self.root), flush=True)
        xdo("windowfocus", window)
        xdo("mousemove", "--window", window, width // 2 + round(100 * width / 960), height // 2 + round(123 * height / 540))
        xdo("click", "1")
        time.sleep(0.3)
        xdo("type", "--window", window, "--delay", "70", "launchtest")
        xdo("key", "--window", window, "Return")
        ImageGrab.grab(bbox=(x, y, x + width, y + height)).save(self.root / "manual-input.png")
        if os.environ.get("CURRENT_BASE_UI_DEBUG_DIR"):
            ImageGrab.grab(bbox=(x, y, x + width, y + height)).save(Path(os.environ["CURRENT_BASE_UI_DEBUG_DIR"]) / "input.png")
        xdo("type", "--window", window, "--delay", "70", "launchpass")
        xdo("key", "--window", window, "Return")
        deadline = time.monotonic() + 25
        while "Player Loaded: launchtest" not in self.log(server) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertTrue("Player Loaded: launchtest" in self.log(server), self.log(client)[-2500:])
        time.sleep(3)
        after = ImageGrab.grab(bbox=(x, y, x + width, y + height)).convert("RGB")
        difference = ImageChops.difference(before, after)
        changed = sum(pixel != (0, 0, 0) for pixel in difference.getdata())
        self.assertGreater(changed, width * height // 4, "Manual login must render a world, not leave a login/loading window")
        self.assertGreater(len(after.getcolors(width * height)), 100, "Actual map frame must contain rendered content")
        self.assertNotIn("CURRENT_BASE_RUNTIME_EXECUTION", self.log(client), "Normal client must not use credential evidence mode")
        self.assertFalse((self.side["client"] / "credentials.txt").exists())

    def test_normal_pair_uses_persistent_leases_and_restarts_stable_descriptors(self):
        self.assertTrue(os.environ.get("DISPLAY"), "Actual normal client requires a GUI test lane")
        before = {role: tree_hash(self.code[role]) for role in ("server", "client")}
        key_hash = FIXTURE.sha256(self.side["server"] / "server.pem")
        sessions = []
        for iteration in range(2):
            server, server_ready = self.start("server")
            client, client_ready = self.start("client")
            for role in ("server", "client"):
                self.assert_locked(role)
                duplicate = subprocess.run(self.command(role), cwd=self.working[role], capture_output=True, text=True, timeout=20)
                self.assertEqual(2, duplicate.returncode)
            sessions.append((server_ready.parent.name, client_ready.parent.name))
            self.manual_login(server, client)
            self.stop(client, client_ready)
            self.stop(server, server_ready)
            with sqlite3.connect(self.state["server"] / "current_base.db") as database:
                self.assertEqual((120, 648), database.execute("SELECT x,y FROM players WHERE id=901").fetchone())
                self.assertEqual((321,), database.execute("SELECT amount FROM itemstatuses JOIN invitems USING(itemID) WHERE playerID=901 AND catalogID=10").fetchone())
                self.assertEqual((3,), database.execute("SELECT stage FROM quests WHERE playerID=901 AND id=1").fetchone())
            self.assertEqual(before, {role: tree_hash(self.code[role]) for role in ("server", "client")})
            self.assertEqual(key_hash, FIXTURE.sha256(self.side["server"] / "server.pem"))
            for role in ("server", "client"):
                with (self.anchor / (role + ".lock")).open("r+") as stream:
                    fcntl.lockf(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.assertNotEqual(sessions[0], sessions[1])

    def test_hostile_descriptors_refuse_before_session_or_working_mutation(self):
        for mutation in ("unknown-field", "wrong-map", "wrong-code", "extra-classpath", "wrong-cwd", "missing-lock",
                         "missing-selection", "malformed-selection", "retired-descriptor"):
            with self.subTest(mutation=mutation):
                descriptor = copy.deepcopy(self.descriptors["server"])
                if mutation == "unknown-field": descriptor["credential"] = "not-admitted"
                if mutation == "wrong-map": descriptor["mapPackageFingerprintSha256"] = "0" * 64
                if mutation == "wrong-code": descriptor["codeTreeSha256"] = "0" * 64
                changed = self.root / "bad-launch.json"
                write_json(changed, descriptor)
                selected = copy.deepcopy(self.active)
                selected["serverDescriptorSha256"] = FIXTURE.sha256(changed)
                if mutation == "malformed-selection": selected["extra"] = True
                if mutation == "retired-descriptor": selected["serverDescriptorSha256"] = "0" * 64
                write_json(self.anchor / "active-launch.json", selected)
                if mutation == "missing-selection": (self.anchor / "active-launch.json").rename(self.anchor / "saved-selection.json")
                command = self.command("server", changed)
                if mutation == "extra-classpath": command[command.index("-cp") + 1] += os.pathsep + str(self.root)
                lock = self.anchor / "server.lock"
                if mutation == "missing-lock": lock.rename(self.anchor / "saved-server.lock")
                try:
                    result = subprocess.run(command, cwd=self.root if mutation == "wrong-cwd" else self.working["server"],
                        capture_output=True, text=True, timeout=20)
                    self.assertEqual(2, result.returncode, result.stdout + result.stderr)
                    self.assertEqual([], list((self.anchor / "sessions/server").iterdir()))
                    self.assertEqual([], list(self.working["server"].iterdir()))
                finally:
                    if mutation == "missing-lock": (self.anchor / "saved-server.lock").rename(lock)
                    if mutation == "missing-selection": (self.anchor / "saved-selection.json").rename(self.anchor / "active-launch.json")

    def test_bootstrap_implementations_are_identical(self):
        server = (ROOT / "server/src/com/openrsc/server/CurrentInstalledLaunch.java").read_text().split("\n", 1)[1]
        client = (ROOT / "Client_Base/src/orsc/CurrentInstalledLaunch.java").read_text().split("\n", 1)[1]
        self.assertEqual(server, client)

    def test_active_selection_refuses_retired_descriptor_and_accepts_current(self):
        next_descriptor = copy.deepcopy(self.descriptors["server"])
        next_profile = self.root / "next-reviewed-server-profile.json"
        shutil.copy2(Path(next_descriptor["installedMapProfile"]["path"]), next_profile)
        next_descriptor["installedMapProfile"] = binding(next_profile)
        next_path = self.root / "next-server-launch.json"
        write_json(next_path, next_descriptor)
        next_selection = copy.deepcopy(self.active)
        next_selection["serverDescriptorSha256"] = FIXTURE.sha256(next_path)
        write_json(self.anchor / "active-launch.json", next_selection)
        refused = subprocess.run(self.command("server"), cwd=self.working["server"],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(2, refused.returncode)
        self.assertEqual([], list((self.anchor / "sessions/server").iterdir()))
        server, ready = self.start("server", next_path)
        self.assertEqual(FIXTURE.sha256(next_path), json.loads(ready.read_text())["descriptorSha256"])
        self.stop(server, ready)


if __name__ == "__main__":
    unittest.main()
