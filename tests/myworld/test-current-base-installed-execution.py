#!/usr/bin/env python3
"""Execute the closed installed Current Base verifier against copied artifacts."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile

import jsonschema


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/current-platform/current-base-v1"
IDENTITY = OUTPUT / "composition-identity.json"
MIGRATION = ROOT / "current-platform/runtime/current-base-v1/state-migration.json"
VERIFIER = ROOT / "current-platform/runtime/current-base-v1/installed-execution-verifier.json"
EVIDENCE_SCHEMA = ROOT / "current-platform/schema/current-base-installed-execution-evidence-v1.schema.json"
INITIALIZED = ROOT / "legacy/docs/inherited-openrsc/sqlite-seeds/preservation.db"
MIGRATION_MAIN = "com.openrsc.server.database.CurrentBaseStateMigration"
VERIFIER_MAIN = "com.openrsc.server.database.CurrentBaseInstalledExecutionVerifier"


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def option(command: list[str], name: str, value: Path | str) -> list[str]:
    changed = list(command)
    index = changed.index(name)
    changed[index + 1] = str(value)
    return changed


def run_supervised(command: list[str], timeout: int = 240) -> subprocess.CompletedProcess:
    # communicate() would close stdin before waiting and therefore cancel the verifier.
    with tempfile.TemporaryFile(mode="w+") as stdout, tempfile.TemporaryFile(mode="w+") as stderr:
        process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.PIPE,
                                   stdout=stdout, stderr=stderr, text=True)
        try:
            process.wait(timeout=timeout)
        finally:
            process.stdin.close()
            process.wait(timeout=90)
        stdout.seek(0)
        stderr.seek(0)
        return subprocess.CompletedProcess(command, process.returncode,
                                           stdout.read(), stderr.read())


def process_running(pid: int) -> bool:
    try:
        return Path(f"/proc/{pid}/stat").read_text().split(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


def direct_children(pid: int) -> list[int]:
    # These are the actual children of this test's verifier, never guessed game PIDs.
    try:
        return sorted({int(value) for task in Path(f"/proc/{pid}/task").glob("*/children")
                       for value in task.read_text().split()})
    except FileNotFoundError:
        return []


def await_condition(condition, seconds: int, label: str) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for {label}")


def write_package(root: Path) -> None:
    sector_x, sector_y = 2, 13
    terrain_path = "terrain/global/lp0/xp2-yp13.raw"
    placement_path = "placements/global/lp0.json"
    terrain = bytes((0, 1, 8, 0, 0, 0, 0, 0, 0, 0)) * (48 * 48)
    placements = canonical_json({
        "schemaVersion": 3, "encoding": "layered-world-placements-v3",
        "worldSpace": "global", "level": 0, "npcs": [], "groundItems": [],
        "scenery": [], "boundaries": [],
    })
    (root / terrain_path).parent.mkdir(parents=True)
    (root / placement_path).parent.mkdir(parents=True)
    (root / terrain_path).write_bytes(terrain)
    (root / placement_path).write_bytes(placements)
    (root / "manifest.json").write_bytes(canonical_json({
        "schemaVersion": 1, "packageType": "layered-world",
        "packageId": "current-base.installed-verifier-map", "packageVersion": "1.0.0",
        "coordinateModel": "signed-layered-v1",
        "storage": {"sectorSize": 48, "presentationChunkSize": 24},
        "worldSpaces": [{"id": "global", "kind": "static"}],
        "levels": [{"worldSpace": "global", "level": 0,
                    "name": "Verifier public level", "role": "authoring-level"}],
        "terrainSectors": [{"worldSpace": "global", "level": 0,
                            "sectorX": sector_x, "sectorY": sector_y,
                            "encoding": "raw-layered-sector-v1", "path": terrain_path,
                            "sha256": hashlib.sha256(terrain).hexdigest()}],
        "placementSets": [{"id": "verifier-global-lp0", "worldSpace": "global",
                           "level": 0, "encoding": "layered-world-placements-v3",
                           "path": placement_path,
                           "sha256": hashlib.sha256(placements).hexdigest()}],
    }))


def package_fingerprint(core: Path, package: Path, classes: Path) -> str:
    source = classes / "InstalledVerifierPackageFingerprint.java"
    source.write_text("""
import com.openrsc.server.io.AdaptiveWorldBuilderPackageGuard;
import java.nio.file.Paths;
public final class InstalledVerifierPackageFingerprint {
  public static void main(String[] args) throws Exception {
    System.out.println(AdaptiveWorldBuilderPackageGuard
      .requireClosedPackage(Paths.get(args[0])).getFingerprint());
  }
}
""".strip() + "\n", encoding="utf-8")
    subprocess.run(["javac", "-source", "8", "-target", "8", "-cp", str(core),
                    "-d", str(classes), str(source)], check=True,
                   capture_output=True, text=True)
    completed = subprocess.run(
        ["java", "-cp", os.pathsep.join((str(core), str(classes))),
         "InstalledVerifierPackageFingerprint", str(package)],
        check=True, capture_output=True, text=True,
    )
    return completed.stdout.strip()


class CurrentBaseInstalledExecutionTest(unittest.TestCase):
    def test_closed_verifier_uses_disposable_account_and_preserves_all_inputs(self) -> None:
        if not os.environ.get("DISPLAY"):
            self.fail("Current Base installed execution requires a non-headless GUI test lane")
        subprocess.run(
            ["python3", "scripts/build-current-base.py", "--test-allow-dirty"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        core = OUTPUT / "server/core.jar"
        with tempfile.TemporaryDirectory(prefix="current-base-installed-") as temporary:
            root = Path(temporary)
            server = root / "installed-server"
            client = root / "installed-client"
            server.mkdir()
            client.mkdir()
            with zipfile.ZipFile(OUTPUT / "server/content.zip") as archive:
                archive.extractall(server)
            with zipfile.ZipFile(OUTPUT / "client/content.zip") as archive:
                archive.extractall(client)
            shutil.copy2(core, server / "core.jar")
            shutil.copy2(OUTPUT / "server/plugins.jar", server / "plugins.jar")
            shutil.copy2(OUTPUT / "client/Open_RSC_Client.jar",
                         client / "Open_RSC_Client.jar")
            (client / "Cache/discord_inuse.txt").write_text("1", encoding="ascii")

            package = root / "canonical-map"
            write_package(package)
            classes = root / "classes"
            classes.mkdir()
            fingerprint = package_fingerprint(core, package, classes)
            manifest_hash = sha256(package / "manifest.json")
            relative = f"world-builder/packages/{fingerprint}/package"
            profiles = []
            for role in ("server", "client"):
                path = root / f"installed-{role}-profile.json"
                path.write_text(json.dumps({
                    "schemaVersion": 1,
                    "manifestType": f"world-builder-installed-{role}-profile",
                    "active": True, "packageId": "current-base.installed-verifier-map",
                    "packageVersion": "1.0.0",
                    "packageFingerprintSha256": fingerprint,
                    "manifestSha256": manifest_hash, "packageRelativePath": relative,
                }, sort_keys=True, indent=2) + "\n", encoding="utf-8")
                profiles.append(path)

            source = root / "populated-preservation.db"
            shutil.copy2(INITIALIZED, source)
            with sqlite3.connect(source) as database:
                database.execute(
                    "INSERT INTO players(id,username,pass,salt,creation_date,creation_ip,"
                    "banned,offences,muted,kills,npc_kills,former_name,x,y) "
                    "VALUES(913,'existing','not-a-real-password','',0,'0.0.0.0','0',0,'0',0,0,'',120,648)"
                )
            source_hash = sha256(source)
            staged = root / "staged-current-base.db"
            migration_evidence = root / "migration-evidence.json"
            migrated = subprocess.run([
                "java", "-cp", str(core), MIGRATION_MAIN,
                "--contract", str(MIGRATION), "--engine", "sqlite",
                "--source", str(source), "--stage", str(staged),
                "--evidence", str(migration_evidence),
            ], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(0, migrated.returncode, migrated.stdout + migrated.stderr)
            self.assertEqual(source_hash, sha256(source))
            self.assertEqual(
                "preservation-initialized-sqlite-to-current-base-v1",
                json.loads(migration_evidence.read_text())["migrationRowId"],
            )

            inputs = [IDENTITY, OUTPUT / "runtime/profile.json", server,
                      client, server / "current-base.conf", *profiles, package, staged]
            before = {str(path): sha256(path) for path in inputs if path.is_file()}
            before.update({str(server): tree_hash(server), str(client): tree_hash(client),
                           str(package): tree_hash(package)})
            workspace = root / "verification workspace #?é"
            evidence_path = root / "installed-evidence.json"
            command = [
                "java", "-cp", str(core), VERIFIER_MAIN,
                "--contract", str(VERIFIER), "--composition-identity", str(IDENTITY),
                "--runtime-profile", str(OUTPUT / "runtime/profile.json"),
                "--installed-server-root", str(server),
                "--installed-client-root", str(client),
                "--server-config", str(server / "current-base.conf"),
                "--server-profile", str(profiles[0]), "--client-profile", str(profiles[1]),
                "--map-package", str(package), "--state-db", str(staged),
                "--workspace", str(workspace), "--server-port", str(free_port()),
                "--websocket-port", str(free_port()), "--evidence", str(evidence_path),
            ]
            verified = run_supervised(command)
            failure_logs = ""
            if verified.returncode:
                for log in sorted(workspace.glob("logs/client-*.log")):
                    failure_logs += "\n" + log.name + "\n" + log.read_text(encoding="utf-8", errors="replace")[-12000:]
            self.assertEqual(0, verified.returncode, verified.stdout + verified.stderr + failure_logs)
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            jsonschema.Draft202012Validator(
                json.loads(EVIDENCE_SCHEMA.read_text())
            ).validate(evidence)
            self.assertGreater(evidence["execution"]["disposableAccountId"], 913)
            self.assertNotEqual(evidence["execution"]["workingStateSeededSha256"],
                                evidence["execution"]["workingStateFinalSha256"])
            self.assertEqual([1, 2], [row["run"] for row in evidence["runs"]])
            self.assertTrue(evidence["execution"]["stateOutsideRuntimeRoots"])
            self.assertTrue(evidence["execution"]["mapOutsideRuntimeRoots"])
            self.assertTrue(evidence["execution"]["mapUnchanged"])
            self.assertEqual(tree_hash(package), tree_hash(workspace / "maps/package"))
            self.assertFalse((workspace / "execution/server" / relative).exists())
            self.assertFalse((workspace / "execution/client" / relative).exists())
            self.assertFalse((workspace / "execution/server/inc/sqlite/current_base.db").exists())
            self.assertNotIn("existing", evidence_path.read_text(encoding="utf-8"))
            self.assertFalse((workspace / "execution/credential.json").exists())
            with sqlite3.connect(workspace / "state/current_base.db") as db:
                self.assertEqual((913, "existing"), db.execute(
                    "SELECT id,username FROM players WHERE id=913").fetchone())
            after = {str(path): sha256(path) for path in inputs if path.is_file()}
            after.update({str(server): tree_hash(server), str(client): tree_hash(client),
                          str(package): tree_hash(package)})
            self.assertEqual(before, after)

            for mode, child_count in (("eof", 1), ("data", 2), ("term", 2),
                                      ("parent-loss", 1), ("parent-loss", 2)):
                with self.subTest(supervision=mode, active_children=child_count):
                    self.assert_supervised_cancellation(
                        command, root, mode, child_count)
                    after_cancel = {str(path): sha256(path) for path in inputs if path.is_file()}
                    after_cancel.update({str(server): tree_hash(server),
                                         str(client): tree_hash(client),
                                         str(package): tree_hash(package)})
                    self.assertEqual(before, after_cancel)

            closed_workspace = root / "closed-pipe-workspace"
            closed_evidence = root / "closed-pipe-evidence.json"
            closed = subprocess.run(
                option(option(command, "--workspace", closed_workspace),
                       "--evidence", closed_evidence),
                cwd=ROOT, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                timeout=90,
            )
            self.assertEqual(2, closed.returncode)
            self.assertFalse(closed_evidence.exists())
            self.assertFalse((closed_workspace / "execution/credential.json").exists())

            changed_contract = json.loads(VERIFIER.read_text())
            changed_contract["supervisionPolicy"]["stdin"] = "unreviewed-no-supervisor"
            changed_contract_path = root / "unreviewed-supervision.json"
            changed_contract_path.write_text(json.dumps(changed_contract), encoding="utf-8")
            policy_workspace = root / "unreviewed-policy-workspace"
            policy_evidence = root / "unreviewed-policy-evidence.json"
            refused = run_supervised(option(option(option(command,
                "--contract", changed_contract_path), "--workspace", policy_workspace),
                "--evidence", policy_evidence), timeout=30)
            self.assertEqual(2, refused.returncode)
            self.assertIn("compiled reviewed contract", refused.stderr)
            self.assertFalse(policy_workspace.exists())
            self.assertFalse(policy_evidence.exists())

            alias = root / "server-alias"
            alias.symlink_to(server, target_is_directory=True)
            aliased_workspace = alias / "must-not-be-created"
            aliased_evidence = root / "aliased-refusal.json"
            refused = run_supervised(
                option(option(command, "--workspace", aliased_workspace),
                       "--evidence", aliased_evidence),
                timeout=30,
            )
            self.assertEqual(2, refused.returncode)
            self.assertIn("disjoint from every supplied input", refused.stderr)
            self.assertFalse(aliased_workspace.exists())
            self.assertFalse(aliased_evidence.exists())

            with (client / "Open_RSC_Client.jar").open("ab") as stream:
                stream.write(b"sealed-binary-mismatch")
            mismatch_workspace = root / "mismatch-workspace"
            mismatch_evidence = root / "mismatch-evidence.json"
            refused = run_supervised(
                option(option(command, "--workspace", mismatch_workspace),
                       "--evidence", mismatch_evidence),
                timeout=30,
            )
            self.assertEqual(2, refused.returncode)
            self.assertIn("installed artifact hash differs for role client-runtime",
                          refused.stderr)
            self.assertFalse(mismatch_workspace.exists())
            self.assertFalse(mismatch_evidence.exists())

    def assert_supervised_cancellation(self, command: list[str], root: Path,
                                      mode: str, child_count: int) -> None:
        self.assertTrue(Path("/proc/self/task").is_dir(),
                        "Cancellation process-evidence lane requires Linux /proc")
        workspace = root / f"cancel-{mode}-{child_count}"
        evidence = root / f"cancel-{mode}-{child_count}.json"
        selected = option(option(command, "--workspace", workspace), "--evidence", evidence)
        selected = option(option(selected, "--server-port", str(free_port())),
                          "--websocket-port", str(free_port()))
        with tempfile.TemporaryFile(mode="w+") as output:
            if mode == "parent-loss":
                # Only this parent owns the write end. Its hard exit must produce EOF in
                # the still-running verifier without killing the verifier itself.
                parent_source = (
                    "import subprocess,sys,time\n"
                    "child=subprocess.Popen(sys.argv[1:],stdin=subprocess.PIPE,"
                    "stdout=sys.stderr,stderr=sys.stderr,close_fds=True)\n"
                    "print(child.pid,flush=True)\n"
                    "time.sleep(240)\n"
                )
                process = subprocess.Popen([sys.executable, "-c", parent_source, *selected],
                                           cwd=ROOT, stdout=subprocess.PIPE, stderr=output,
                                           text=True)
                verifier_pid = int(process.stdout.readline().strip())
            else:
                process = subprocess.Popen(selected, cwd=ROOT, stdin=subprocess.PIPE,
                                           stdout=output, stderr=output, text=True)
                verifier_pid = process.pid
            observed_children: list[int] = []
            try:
                def ready() -> bool:
                    if not process_running(verifier_pid):
                        output.seek(0)
                        self.fail("Verifier exited before cancellation probe: " + output.read())
                    observed_children[:] = direct_children(verifier_pid)
                    return len(observed_children) >= child_count and all(
                        process_running(pid) for pid in observed_children)
                await_condition(ready, 90, "owned active server/client processes")
                self.assertTrue((workspace / "execution/credential.json").exists())
                if mode == "parent-loss":
                    process.kill()
                    process.wait(timeout=10)
                elif mode == "term":
                    process.terminate()
                elif mode == "data":
                    process.stdin.write("unexpected\n")
                    process.stdin.flush()
                else:
                    process.stdin.close()
                await_condition(lambda: not process_running(verifier_pid), 90,
                                "verifier cancellation cleanup and exit")
                if mode != "parent-loss":
                    process.wait(timeout=5)
                    self.assertNotEqual(0, process.returncode)
                    if mode != "term":
                        self.assertEqual(2, process.returncode)
                self.assertTrue(all(not process_running(pid) for pid in observed_children))
                self.assertFalse((workspace / "execution/credential.json").exists())
                self.assertFalse(evidence.exists())
                self.assertTrue((workspace / "logs/server-1.log").is_file())
                if child_count == 2:
                    self.assertTrue((workspace / "logs/client-1.log").is_file())
                for log in (workspace / "logs").glob("*.log"):
                    self.assertLessEqual(log.stat().st_size, 1048576)
            finally:
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()
                if mode == "parent-loss" and process.poll() is None:
                    process.kill()
                process.wait(timeout=90)
                if process.stdout:
                    process.stdout.close()
                await_condition(lambda: not process_running(verifier_pid), 90,
                                "final verifier cleanup")


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(sha256(path).encode("ascii") + b"\0")
    return digest.hexdigest()


if __name__ == "__main__":
    unittest.main()
