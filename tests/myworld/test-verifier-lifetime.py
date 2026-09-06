#!/usr/bin/env python3
"""Actual JVM leases, hard-killed supervisor, suspended real child entrypoints and recovery refusals."""
from pathlib import Path
import fcntl
import hashlib
import importlib.util
import json
import os
import select
import socket
import struct
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("installed_fixture", ROOT / "tests/myworld/test-current-base-installed-execution.py")
FIXTURE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(FIXTURE)


class VerifierLifetimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes_temp = tempfile.TemporaryDirectory(prefix="verifier-lifetime-classes-")
        cls.classes = Path(cls.classes_temp.name)
        cls.addClassCleanup(cls.classes_temp.cleanup)
        # Real lifetime/entrypoint sources, with game class initializers as a
        # deterministic mutation sentinel. The separate pair test runs real gameplay.
        sources = {
            "Probe.java": '''
import com.openrsc.server.VerifierLifetime;
import java.nio.file.*;
import java.util.*;
import org.json.*;
public class Probe {
  public static void main(String[] args) throws Exception {
    try {
      if (args[0].equals("recover")) {
        VerifierLifetime owner = VerifierLifetime.recovery(Paths.get(args[1]), args[2], Paths.get(args[3]));
        owner.recover(Paths.get(args[4])); return;
      }
      JSONObject input = new JSONObject(new String(Files.readAllBytes(Paths.get(args[1])), "UTF-8"));
      Map<String,String> options = new TreeMap<>();
      for (String key : input.keySet()) options.put(key, input.getString(key));
      VerifierLifetime owner = VerifierLifetime.supervisor(options);
      if (args[0].equals("retry")) {
        try { owner.finish(); throw new AssertionError("expected external client lease"); }
        catch (VerifierLifetime.Busy expected) { }
        try { VerifierLifetime.supervisor(options); throw new AssertionError("overlapping owner admitted"); }
        catch (VerifierLifetime.Busy expected) { }
        try { owner.finish(); throw new AssertionError("expected second external client lease"); }
        catch (VerifierLifetime.Busy expected) { }
        System.out.println("RETRY_HELD"); System.out.flush();
        System.in.read(); owner.finish(); return;
      }
      if (!args[0].equals("empty")) {
        Files.createDirectories(Paths.get(options.get("workspace"), "execution/server"));
        Files.createDirectories(Paths.get(options.get("workspace"), "execution/client"));
        owner.credential("invented-private-credential".getBytes("UTF-8"));
      }
      System.out.println("OWNED"); System.out.flush();
      if (System.in.read() == 'f') owner.finish();
    } catch (VerifierLifetime.Busy busy) { System.exit(3); }
      catch (Exception failure) { System.err.println(failure.getMessage()); System.exit(2); }
  }
}''',
            "Server.java": '''package com.openrsc.server;
public class Server {
  static { try { java.nio.file.Files.createFile(java.nio.file.Paths.get("GAME_EFFECT")); }
    catch (Exception failure) { throw new RuntimeException(failure); } }
  public static void main(String[] args) throws Exception { System.out.println("GAME_EFFECT"); Thread.sleep(60000); }
}''',
            "OpenRSC.java": '''package orsc;
public class OpenRSC {
  static { try { java.nio.file.Files.createFile(java.nio.file.Paths.get("GAME_EFFECT")); }
    catch (Exception failure) { throw new RuntimeException(failure); } }
  public static void main(String[] args) throws Exception { System.out.println("GAME_EFFECT"); Thread.sleep(60000); }
}'''}
        paths = []
        for name, text in sources.items():
            path = cls.classes / name
            path.write_text(text)
            paths.append(str(path))
        paths += [str(ROOT / path) for path in (
            "server/src/com/openrsc/server/VerifierLifetime.java",
            "server/src/com/openrsc/server/CurrentBaseVerifierServer.java",
            "Client_Base/src/orsc/VerifierLifetime.java", "PC_Client/src/orsc/CurrentBaseVerifierClient.java")]
        cls.classpath = os.pathsep.join((str(cls.classes), str(ROOT / "server/lib/json-20190722.jar")))
        subprocess.run(["javac", "-source", "8", "-target", "8", "-cp", cls.classpath,
            "-d", str(cls.classes), *paths], capture_output=True, check=True)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="verifier-lifetime-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.processes = []
        self.addCleanup(self.stop_owned)
        self.workspace = self.root / "workspace"
        names = ("contract", "composition-identity", "runtime-profile", "installed-server-root", "installed-client-root",
            "server-config", "server-profile", "client-profile", "map-package", "state-db")
        command = ["java", "--unused-probe"]
        for name in names:
            path = self.root / name
            path.write_text("invented-input")
            command += ["--" + name, str(path)]
        command += ["--workspace", str(self.workspace), "--evidence", str(self.root / "evidence.json"),
            "--server-port", "43594", "--websocket-port", "43595"]
        self.command = FIXTURE.with_supervision(command)
        first = self.command.index("--contract")
        self.options = {self.command[i][2:]: self.command[i + 1] for i in range(first, len(self.command), 2)}
        self.control = Path(self.options["supervision"]).parent
        self.options_file = self.root / "options.json"
        self.options_file.write_text(json.dumps(self.options))

    def spawn(self, command, cwd=None):
        process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True)
        self.processes.append(process)
        return process

    def stop_owned(self):
        for process in reversed(self.processes):
            if process.poll() is None:
                process.kill()  # Only disposable test-owned JVM handles.
            process.wait(timeout=10)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream and not stream.closed: stream.close()

    def supervisor(self, empty=False):
        process = self.spawn(["java", "-cp", self.classpath, "Probe", "empty" if empty else "open", str(self.options_file)])
        self.assertTrue(select.select([process.stdout], [], [], 10)[0], "Supervisor did not acquire lease")
        self.assertEqual("OWNED", process.stdout.readline().strip(), process.stderr.read() if process.poll() is not None else "")
        return process

    def recovery(self, name="recovery.json"):
        return subprocess.run(["java", "-cp", self.classpath, "Probe", "recover", self.options["supervision"],
            self.options["supervision-sha256"], self.options["contract"], str(self.root / name)],
            capture_output=True, text=True, timeout=10)

    def child(self, role, suspended=False):
        command = ["java"]
        port = FIXTURE.free_port()
        if suspended:
            command += [f"-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:{port}"]
        command += ["-cp", self.classpath,
            "com.openrsc.server.CurrentBaseVerifierServer" if role == "server" else "orsc.CurrentBaseVerifierClient",
            "--supervision", self.options["supervision"], "--supervision-sha256", self.options["supervision-sha256"],
            "--intent-sha256", FIXTURE.sha256(self.control / "intent.json")]
        process = self.spawn(command, self.workspace / "execution" / role)
        self.assertTrue(select.select([process.stdout], [], [], 10)[0], "Child did not reach controlled startup")
        line = process.stdout.readline().strip()
        self.assertIn("Listening for transport dt_socket" if suspended else "GAME_EFFECT", line)
        return process, port

    def resume(self, port):
        # JDWP suspension occurs before Java main: no production delay flags or
        # alternate launcher are added to the provider contract.
        with socket.create_connection(("127.0.0.1", port), timeout=5) as connection:
            connection.sendall(b"JDWP-Handshake")
            self.assertEqual(b"JDWP-Handshake", connection.recv(14))
            connection.sendall(struct.pack(">IIBBB", 11, 1, 0, 1, 9))
            time.sleep(0.05)

    def test_actual_jvm_lease_busy_until_exit_and_success_recovery_idempotent(self):
        supervisor = self.supervisor()
        self.assertEqual(3, self.recovery().returncode)
        supervisor.stdin.write("f"); supervisor.stdin.flush()
        self.assertEqual(0, supervisor.wait(timeout=10))
        self.assertFalse((self.workspace / "execution/credential.json").exists())
        for name in ("recovered.json", "recovered-again.json"):
            result = self.recovery(name)
            self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue((self.control / "revocation.json").is_file())

    def test_hard_kill_then_revoke_blocks_both_prelease_suspended_child_entrypoints(self):
        supervisor = self.supervisor()
        children = [self.child(role, suspended=True) for role in ("server", "client")]
        supervisor.kill(); supervisor.wait(timeout=10)
        result = self.recovery()
        self.assertEqual(0, result.returncode, result.stderr)
        for child, port in children:
            self.resume(port)
            self.assertEqual(2, child.wait(timeout=10))
        for role in ("server", "client"):
            self.assertFalse((self.workspace / "execution" / role / "GAME_EFFECT").exists())

    def test_hard_killed_supervisor_does_not_make_live_child_safe_to_clean(self):
        supervisor = self.supervisor()
        child, _ = self.child("server")
        supervisor.kill(); supervisor.wait(timeout=10)
        self.assertEqual(3, self.recovery().returncode)
        self.assertFalse((self.control / "revocation.json").exists())
        self.assertTrue((self.workspace / "execution/credential.json").exists())
        child.stdin.close()
        self.assertEqual(2, child.wait(timeout=10))
        self.assertEqual(0, self.recovery().returncode)

    def test_empty_intent_revocation_refuses_delayed_supervisor(self):
        self.assertEqual(0, self.recovery().returncode)
        delayed = self.spawn(["java", "-cp", self.classpath, "Probe", "open", str(self.options_file)])
        self.assertEqual(2, delayed.wait(timeout=10))
        self.assertFalse(self.workspace.exists())

    def test_replaced_anchor_or_intent_inode_refuses(self):
        for name in ("supervisor.lock", "server.lock", "client.lock", "intent.json"):
            with self.subTest(name=name):
                original = self.control / name
                saved = self.control / (name + ".saved")
                original.rename(saved)
                original.touch(mode=0o600)
                result = self.recovery()
                self.assertEqual(2, result.returncode)
                self.assertFalse((self.control / "revocation.json").exists())
                original.unlink(); saved.rename(original)

    def test_partial_intent_and_foreign_credential_are_retained(self):
        supervisor = self.supervisor()
        supervisor.kill(); supervisor.wait(timeout=10)
        intent = self.control / "intent.json"
        original = intent.read_bytes()
        intent.write_bytes(b'{"schemaVersion":')
        self.assertEqual(2, self.recovery().returncode)
        self.assertTrue((self.workspace / "execution/credential.json").exists())
        intent.write_bytes(original)
        credential = self.workspace / "execution/credential.json"
        saved = credential.with_suffix(".saved")
        credential.rename(saved)
        credential.write_bytes(saved.read_bytes()); credential.chmod(0o600)
        self.assertEqual(2, self.recovery().returncode)
        self.assertTrue(credential.exists())
        self.assertTrue((self.control / "revocation.json").is_file(),
            "Foreign credential refuses deletion but delayed execution must already be revoked")

    def test_partial_acquisition_retry_and_overlapping_owner_preserve_process_locks(self):
        with (self.control / "client.lock").open("r+b") as client_lock:
            fcntl.lockf(client_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            process = self.spawn(["java", "-cp", self.classpath, "Probe", "retry", str(self.options_file)])
            self.assertTrue(select.select([process.stdout], [], [], 10)[0])
            self.assertEqual("RETRY_HELD", process.stdout.readline().strip())
            # These contenders are separate processes, so Java's overlapping-lock
            # bookkeeping cannot disguise a dropped kernel lease.
            for role in ("supervisor", "server"):
                contender = subprocess.run(["python3", "-c",
                    "import fcntl,sys; f=open(sys.argv[1],'r+b'); "
                    "fcntl.lockf(f,fcntl.LOCK_EX|fcntl.LOCK_NB)", str(self.control / (role + ".lock"))],
                    capture_output=True, timeout=10)
                self.assertNotEqual(0, contender.returncode, role + " lease was dropped by retry/overlap")
            fcntl.lockf(client_lock, fcntl.LOCK_UN)
            process.stdin.write("f"); process.stdin.flush()
            self.assertEqual(0, process.wait(timeout=10))
        self.assertEqual(0, self.recovery().returncode)

    def test_evidence_overlap_and_symlink_parent_refused_without_revocation(self):
        for name in ("workspace/evidence.json", self.control.name + "/evidence.json", "contract"):
            self.assertEqual(2, self.recovery(name).returncode)
            self.assertFalse((self.control / "revocation.json").exists())
        (self.root / "alias").symlink_to(self.root, target_is_directory=True)
        self.assertEqual(2, self.recovery("alias/evidence.json").returncode)
        self.assertFalse((self.control / "revocation.json").exists())

    def test_bootstrap_parity(self):
        server = (ROOT / "server/src/com/openrsc/server/VerifierLifetime.java").read_text().split("\n", 1)[1]
        client = (ROOT / "Client_Base/src/orsc/VerifierLifetime.java").read_text().split("\n", 1)[1]
        self.assertEqual(server, client)


if __name__ == "__main__":
    unittest.main()
