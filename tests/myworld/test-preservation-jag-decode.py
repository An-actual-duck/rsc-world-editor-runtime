#!/usr/bin/env python3
"""Pure historical r64 decoding, bounded input refusals, and complete public-map comparison."""

import bz2
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
import zipfile

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "output/current-platform/current-base-v1/server/core.jar"
CONTRACT = ROOT / "current-platform/input-adapters/preservation-r64-sqlite-v1.json"
SCHEMA = ROOT / "current-platform/schema/current-preservation-r64-input-adapter-v1.schema.json"
ARCHIVES = [ROOT / "server/conf/server/data/maps" / name
            for name in ("maps64.jag", "maps64.mem", "land64.jag", "land64.mem")]
CLIENT = ROOT / "Client_Base/Cache/video/Authentic_Landscape.orsc"
FROZEN_RUNTIME = "3999e021325fe3953787e3d278852d4858a91140"
MAIN = "com.openrsc.server.io.PreservationJagDecode"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def u24(value):
    return value.to_bytes(3, "big")


def name_hash(name):
    value = 0
    for character in name.upper():
        value = (61 * value + ord(character) - 32) & 0xffffffff
    return value


def jag(entries, compressed=True, compress_entries=False):
    table, payload = bytearray(), bytearray()
    for name, data in entries:
        packed = bz2.compress(data, compresslevel=1)[4:] if compress_entries else data
        table.extend(struct.pack(">I", name_hash(name)) + u24(len(data)) + u24(len(packed)))
        payload.extend(packed)
    data = struct.pack(">H", len(entries)) + table + payload
    packed = bz2.compress(data, compresslevel=1)[4:] if compressed else data
    return u24(len(data)) + u24(len(packed)) + packed


class PreservationJagDecodeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run(["python3", "scripts/build-current-base.py", "--test-allow-dirty"],
                       cwd=ROOT, check=True, capture_output=True, text=True)
        cls.temporary = tempfile.TemporaryDirectory(prefix="preservation-jag-tests-")
        cls.root = Path(cls.temporary.name)
        original = subprocess.run(["git", "show", FROZEN_RUNTIME +
            ":server/src/com/openrsc/server/io/WorldLoader.java"], cwd=ROOT,
            check=True, capture_output=True, text=True).stdout
        method = re.search(r"(\tprivate Sector loadJAGSector\(.*?)(?=\n\tprivate boolean loadSection)",
                           original, re.S).group(1)
        if digest(method.encode()) != "12d9989f1f1b48ee186b74a179354faa3413484ab3d40f72b1d13be61c62a82a":
            raise AssertionError("Frozen historical oracle method changed")
        method = method.replace("getWorld().getServer().getConfig().MEMBER_WORLD", "true")
        source = cls.root / "JagOracle.java"
        source.write_text("""package com.openrsc.server.io;
import com.openrsc.server.constants.Constants;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
public final class JagOracle {
 private JContent jagArchive, memArchive, landJagArchive, landMemArchive;
""" + method + """
 private static String hash(byte[] data) throws Exception {
  StringBuilder result = new StringBuilder();
  for (byte b : MessageDigest.getInstance("SHA-256").digest(data)) result.append(String.format("%02x", b & 255));
  return result.toString();
 }
 private static final class MemoryArchive extends JContent {
  final Map<String, byte[]> files = new HashMap<String, byte[]>();
  @Override public JContentFile unpack(String name) {
   return files.containsKey(name) ? new JContentFile(files.get(name)) : null;
  }
 }
 private static void check(boolean value) { if (!value) throw new AssertionError("synthetic decoder contract"); }
 private static void refused(Runnable action) {
  try { action.run(); } catch (RuntimeException expected) { return; }
  throw new AssertionError("malformed stream accepted");
 }
 private static void synthetic() throws Exception {
  MemoryArchive free = new MemoryArchive(), members = new MemoryArchive(), land = new MemoryArchive();
  check(HistoricalJagSectorDecoder.decode(free, members, land, land, 48,37,0,true,false,true).sector() == null);
  byte[] base = new byte[2304*9], member = base.clone();
  base[0] = 1; member[0] = 5;
  member[4*2304] = (byte)255; member[4*2304+1] = (byte)255;
  member[7*2304] = (byte)250; member[8*2304] = 7;
  free.files.put("m04837.jm", base); members.files.put("m04837.jm", member);
  members.files.put("m04837.loc", new byte[]{127}); // Never consumed: historical loc is free-map only.
  HistoricalJagSectorDecoder.Result result = HistoricalJagSectorDecoder.decode(free,members,land,land,48,37,0,true,false,true);
  check(result.sector().getTile(0).getGroundElevation() == 5);
  check(result.sector().getTile(0).getDiagonalWalls() == -1);
  check(result.sector().getTile(0).getGroundOverlay() == 250);
  check(result.discardedTileDirections()[0] == 7);
  check(result.sector().pack().array().length == 23040);
  check(HistoricalJagSectorDecoder.decode(free,members,land,land,48,37,0,false,false,true)
    .sector().getTile(0).getGroundElevation() == 1);
  members.files.put("m04837.jm", Arrays.copyOf(member, member.length + 1));
  refused(() -> HistoricalJagSectorDecoder.decode(free,members,land,land,48,37,0,true,false,true));
  members.files.put("m04837.jm", new byte[1]);
  refused(() -> HistoricalJagSectorDecoder.decode(free,members,land,land,48,37,0,true,false,true));
  members.files.clear(); free.files.clear();
  byte[] badDat = new byte[4*2304+19]; Arrays.fill(badDat,4*2304,badDat.length,(byte)255);
  free.files.put("m04837.dat", badDat);
  refused(() -> HistoricalJagSectorDecoder.decode(free,members,land,land,48,37,0,true,false,true));
  byte[] nonProgressing = new byte[65536]; Arrays.fill(nonProgressing,(byte)128);
  free.files.put("m04837.dat", nonProgressing);
  refused(() -> HistoricalJagSectorDecoder.decode(free,members,land,land,48,37,0,true,true,true));
  byte[] runs = new byte[19]; Arrays.fill(runs,(byte)255); runs[18]=(byte)146;
  byte[] dat = new byte[4*2304+58];
  System.arraycopy(runs,0,dat,4*2304,19);
  dat[4*2304+19]=3; Arrays.fill(dat,4*2304+20,4*2304+38,(byte)255); dat[4*2304+38]=(byte)145;
  System.arraycopy(runs,0,dat,4*2304+39,19);
  byte[] hei = new byte[38]; System.arraycopy(runs,0,hei,0,19); System.arraycopy(runs,0,hei,19,19);
  free.files.put("m04837.dat",dat); land.files.put("m04837.hei",hei);
  JagOracle original = new JagOracle(); original.jagArchive=free; original.memArchive=members;
  original.landJagArchive=land; original.landMemArchive=land;
  result=HistoricalJagSectorDecoder.decode(free,members,land,land,48,37,0,true,false,true);
  check(result.sector().getTile(0).getGroundElevation()==134); // HEI's initial repeat retains DAT decoration carry.
  check(Arrays.equals(original.loadJAGSector(48,37,0,false).pack().array(),result.sector().pack().array()));
  byte[] alt = new byte[7*19]; for(int i=0;i<7;i++) System.arraycopy(runs,0,alt,i*19,19);
  free.files.put("m04837.dat",alt);
  result=HistoricalJagSectorDecoder.decode(free,members,land,land,48,37,0,true,true,true);
  check(Arrays.equals(original.loadJAGSector(48,37,0,true).pack().array(),result.sector().pack().array()));
  System.out.println("synthetic strict decoding verified");
 }
 public static void main(String[] args) throws Exception {
  if (args[0].equals("archive")) { System.out.println(new BoundedJagArchive(Files.readAllBytes(Paths.get(args[1]))).entryCount()); return; }
  if (args[0].equals("synthetic")) { synthetic(); return; }
  JagOracle oracle = new JagOracle();
  JContent[] old = new JContent[4]; BoundedJagArchive[] bounded = new BoundedJagArchive[4];
  for (int i=0;i<4;i++) { old[i] = new JContent(); check(old[i].open(args[i+1], true)); bounded[i] = new BoundedJagArchive(Files.readAllBytes(Paths.get(args[i+1]))); }
  oracle.jagArchive=old[0]; oracle.memArchive=old[1]; oracle.landJagArchive=old[2]; oracle.landMemArchive=old[3];
  for (int p=0;p<4;p++) for(int x=48;x<=68;x++) for(int y=37;y<=56;y++) {
   Sector expected=oracle.loadJAGSector(x,y,p,false);
   Sector actual=HistoricalJagSectorDecoder.decode(bounded[0],bounded[1],bounded[2],bounded[3],x,y,p,true,false,true).sector();
   check((expected == null) == (actual == null));
   if(expected != null) {
    byte[] bytes=expected.pack().array(); check(Arrays.equals(bytes,actual.pack().array()));
    System.out.println("h"+p+"x"+x+"y"+y+" "+hash(bytes));
   }
  }
 }
}
""", encoding="utf-8")
        subprocess.run(["javac", "-source", "8", "-target", "8", "-cp", str(CORE),
                        "-d", str(cls.root), str(source)], check=True, capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def harness(self, *arguments):
        return subprocess.run(["java", "-Xmx256m", "-cp", os.pathsep.join((str(self.root), str(CORE))),
            "com.openrsc.server.io.JagOracle", *map(str, arguments)], cwd=ROOT,
            capture_output=True, text=True, timeout=30)

    def command(self, directory):
        result = ["java", "-Xmx256m", "-cp", str(CORE), MAIN, "--contract", str(CONTRACT)]
        for role, archive in zip(("maps-free", "maps-members", "land-free", "land-members"), ARCHIVES):
            result.extend(["--" + role, str(archive)])
        return result + ["--output", str(directory / "sectors"), "--evidence", str(directory / "evidence.json")]

    def test_complete_reviewed_inventory_historical_parity_and_client_comparison(self):
        with tempfile.TemporaryDirectory(prefix="jag-parity-#é-") as temporary:
            root = Path(temporary)
            command = self.command(root)
            before = [digest(path.read_bytes()) for path in [CONTRACT, *ARCHIVES, CLIENT]]
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(0, completed.returncode, completed.stderr)
            evidence_bytes = (root / "evidence.json").read_bytes()
            evidence = json.loads(evidence_bytes)
            schema = json.loads(SCHEMA.read_text())
            jsonschema.Draft202012Validator({"$ref": "#/$defs/jagDecodeEvidence", "$defs": schema["$defs"]}).validate(evidence)
            self.assertLessEqual(len(evidence_bytes), 2097152)
            self.assertEqual(digest(canonical(evidence["inventory"])), evidence["inventorySha256"])
            self.assertEqual("68776ead9a4487320840c1f88f054b46f342a5b115b05de93d9eace511ff6310",
                             evidence["inventorySha256"])
            self.assertEqual({"probeCount":1680,"presentSectorCount":352,"absentSectorCount":1328,
                              "discardedNonzeroDirectionTiles":15468,"overlay250Tiles":0,
                              "signedNegativeDiagonalTiles":0}, evidence["summary"])
            self.assertEqual(1680, len({(row["plane"], row["archiveX"], row["archiveY"])
                                        for row in evidence["inventory"]}))
            oracle = self.harness("oracle", *ARCHIVES)
            self.assertEqual(0, oracle.returncode, oracle.stderr)
            expected = dict(line.split() for line in oracle.stdout.splitlines())
            present = [row for row in evidence["inventory"] if row["present"]]
            self.assertEqual(352, len(expected))
            with zipfile.ZipFile(CLIENT) as client:
                self.assertEqual("48ed0e1634b870888f96c0bc3e31cbaf152570b913140fdfd3596897a3eb29fa",
                                 digest(CLIENT.read_bytes()))
                self.assertEqual(1764, len(client.infolist()))
                self.assertEqual(1764, len(set(client.namelist())))
                client_data = {name: client.read(name) for name in client.namelist()}
                self.assertTrue(all(len(data) == 23040 for data in client_data.values()))
                same, different, server_only = [], [], []
                fields = ("height", "colour", "overlay", "roof", "horizontalWall", "verticalWall", "diagonal")
                differences = dict.fromkeys(fields, 0)
                for row in present:
                    path = root / "sectors" / row["relativePath"]
                    data = path.read_bytes()
                    name = path.stem
                    self.assertEqual(23040, len(data))
                    self.assertEqual(expected[name], digest(data))
                    self.assertEqual(row["sha256"], digest(data))
                    if name not in client.namelist():
                        server_only.append(name)
                    elif data == client_data[name]:
                        same.append(name)
                    else:
                        different.append(name)
                        other = client_data[name]
                        for tile in range(2304):
                            for offset, field in enumerate(fields):
                                start = tile * 10 + offset
                                end = start + (4 if field == "diagonal" else 1)
                                if data[start:end] != other[start:end]:
                                    differences[field] += 1
                client_only = sorted(set(client.namelist()) - set(expected))
                comparison = {"serverPresent":len(present),"byteIdentical":len(same),
                              "different":len(different),"serverOnly":len(server_only),
                              "clientOnly":len(client_only)}
                print("Complete reviewed JAG/client ZIP comparison: " + json.dumps(comparison, sort_keys=True))
                print("Differing native tile fields: " + json.dumps(differences, sort_keys=True))
                self.assertEqual({"height":162324,"colour":1,"overlay":1,"roof":1,
                                  "horizontalWall":0,"verticalWall":0,"diagonal":291}, differences)
                self.assertEqual({"serverPresent":352,"byteIdentical":276,"different":76,
                                  "serverOnly":0,"clientOnly":1412}, comparison)
                probed = {f'h{row["plane"]}x{row["archiveX"]}y{row["archiveY"]}' for row in evidence["inventory"]}
                self.assertEqual(1328, len(set(client_only) & probed))
                self.assertEqual(84, len(set(client_only) - probed))
            again = root / "again"; again.mkdir()
            repeated = subprocess.run(self.command(again), cwd=ROOT, capture_output=True, text=True, timeout=30)
            self.assertEqual(0, repeated.returncode, repeated.stderr)
            self.assertEqual(evidence_bytes, (again / "evidence.json").read_bytes())
            self.assertEqual(before, [digest(path.read_bytes()) for path in [CONTRACT, *ARCHIVES, CLIENT]])
            self.assertEqual(352, len(list((root / "sectors").iterdir())))

    def test_synthetic_precedence_signed_diagonals_directions_and_malformed_streams(self):
        result = self.harness("synthetic")
        self.assertEqual(0, result.returncode, result.stderr)

    def test_bounded_archive_framing_entries_and_compression(self):
        with tempfile.TemporaryDirectory(prefix="jag-framing-") as temporary:
            path = Path(temporary) / "archive.jag"
            for compressed, entries in ((False,False),(True,False),(False,True),(True,True)):
                with self.subTest(valid_compression=(compressed,entries)):
                    path.write_bytes(jag([("m04837.jm", bytes(20736))], compressed, entries))
                    accepted = self.harness("archive", path)
                    self.assertEqual(0, accepted.returncode, accepted.stderr)
                    self.assertEqual("1", accepted.stdout.strip())
            valid = jag([("m04837.jm", bytes(20736))])
            corrupt = bytearray(valid); corrupt[len(corrupt)//2] ^= 32
            malformed = {
                "short": b"short", "header-length": valid[:-1],
                "oversized-expanded": u24(16777215) + valid[3:],
                "corrupt-compressed": bytes(corrupt),
                "trailing-compressed": valid[:3] + u24(len(valid)-5) + valid[6:] + b"x",
                "duplicate-hash": jag([("m04837.jm",b"x"),("m04837.jm",b"y")]),
                "oversized-entry": jag([("m04837.jm",bytes(65537))]),
                "table-overrun": u24(2)+u24(2)+b"\xff\xff",
                "entry-truncation": jag([("m04837.jm",b"x")],False)[:-1],
            }
            for label, data in malformed.items():
                with self.subTest(malformed=label):
                    path.write_bytes(data)
                    self.assertNotEqual(0, self.harness("archive",path).returncode)

    def test_cli_refuses_drift_aliases_overlap_and_existing_outputs(self):
        with tempfile.TemporaryDirectory(prefix="jag-refusals-") as temporary:
            root = Path(temporary)
            changed = root / "changed.jag"; changed.write_bytes(ARCHIVES[0].read_bytes() + b"drift")
            alias = root / "alias.jag"; alias.symlink_to(ARCHIVES[0])
            copies = root / "copies"; copies.mkdir()
            copied = copies / "maps.jag"; shutil.copy2(ARCHIVES[0],copied)
            hard = root / "hard.jag"; os.link(copied, hard)
            existing = root / "existing"; existing.mkdir()
            sentinel = existing / "sentinel"; sentinel.write_text("preserve")
            for label, flag, value in (("drift","--maps-free",changed),
                                      ("symlink","--maps-free",alias),
                                      ("hardlink","--maps-free",hard),
                                      ("existing","--output",existing),
                                      ("existing-evidence","--evidence",sentinel),
                                      ("same-output-evidence","--output",root/"evidence.json"),
                                      ("overlap","--output",ARCHIVES[0]),
                                      ("relative","--output",Path("relative-output")),
                                      ("contract","--contract",changed)):
                with self.subTest(refusal=label):
                    command = self.command(root)
                    command[command.index(flag)+1] = str(value)
                    result = subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=30)
                    self.assertEqual(2,result.returncode,result.stderr)
                    self.assertFalse((root/"evidence.json").exists())
                    self.assertFalse((root/"sectors").exists())
                    self.assertEqual("preserve",sentinel.read_text())


if __name__ == "__main__":
    unittest.main()
