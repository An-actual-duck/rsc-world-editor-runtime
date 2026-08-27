import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "server/core.jar"
CLIENT = ROOT / "Client_Base/Open_RSC_Client.jar"


def raw_tile(elevation, seed, wide):
    elevation_bytes = elevation.to_bytes(2 if wide else 1, "big")
    # texture, overlay, roof, vertical, horizontal, diagonal
    return elevation_bytes + bytes((seed, seed + 1, seed + 2, seed + 3, seed + 4)) + (0x10203040 + seed).to_bytes(4, "big")


def package_at(root, elevations, wide):
    terrain = root / "terrain.raw"
    values = list(elevations)
    records = []
    for index in range(48 * 48):
        records.append(raw_tile(values[index % len(values)], 10 + index % 5, wide))
    terrain.write_bytes(b"".join(records))
    manifest = {
        "schemaVersion": 1,
        "packageType": "layered-world",
        "packageId": "wide-elevation-test",
        "packageVersion": "1.0.0",
        "coordinateModel": "signed-layered-v1",
        "storage": {"sectorSize": 48, "presentationChunkSize": 48},
        "worldSpaces": [{"id": "global", "kind": "static"}],
        "levels": [{"worldSpace": "global", "level": 0, "name": "Test", "role": "surface"}],
        "terrainSectors": [{
            "worldSpace": "global", "level": 0, "sectorX": 0, "sectorY": 0,
            "encoding": "raw-layered-sector-v2-u16" if wide else "raw-layered-sector-v1",
            "path": "terrain.raw", "sha256": hashlib.sha256(terrain.read_bytes()).hexdigest(),
        }],
        "placementSets": [],
    }
    (root / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")


class WideTerrainElevationV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        subprocess.run([str(ROOT / "scripts/build-server.sh")], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
        subprocess.run([str(ROOT / "scripts/build-client.sh")], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)

    def compile_run(self, source, name, classpath, args=()):
        with tempfile.TemporaryDirectory(prefix="wide-elevation-java-") as temp:
            path = Path(temp) / f"{name}.java"
            path.write_text(source, encoding="utf-8")
            subprocess.run(["javac", "-source", "8", "-target", "8", "-cp", str(classpath), "-d", temp, str(path)], check=True)
            return subprocess.run(["java", "-cp", f"{temp}:{classpath}", name, *map(str, args)], text=True, capture_output=True)

    def test_v1_read_and_v2_boundary_decode_preserve_non_elevation_fields(self):
        source = r'''
import com.openrsc.server.io.*;
import com.openrsc.server.model.world.coordinate.*;
import java.nio.file.*;
public final class WideServerProbe {
  static void ok(boolean value,String message){if(!value)throw new AssertionError(message);}
  public static void main(String[] args)throws Exception{
    NativeLayeredWorldPackage world=NativeLayeredWorldPackage.load(Paths.get(args[0]));
    NativeLayeredTerrainSector sector=world.findSector(new WorldMapSectorId(WorldSpaceId.GLOBAL,0,0,0)).get();
    int[] expected={Integer.parseInt(args[1]),Integer.parseInt(args[2]),Integer.parseInt(args[3]),Integer.parseInt(args[4]),Integer.parseInt(args[5])};
    for(int i=0;i<expected.length;i++){
      NativeLayeredTerrainTile tile=sector.getTile(0,i);
      ok(tile.getElevation()==expected[i],"elevation "+i);
      ok(tile.getTexture()==10+i&&tile.getOverlay()==11+i&&tile.getRoof()==12+i,"visual fields "+i);
      ok(tile.getVerticalWall()==13+i&&tile.getHorizontalWall()==14+i,"wall fields "+i);
      ok(tile.getDiagonalWall()==0x10203040+10+i,"diagonal "+i);
    }
    byte[] wire=sector.copyWireBytes();
    ok(wire.length==48*48*Integer.parseInt(args[6]),"wire width");
    if(expected[4]>255){
      boolean refused=false;try{sector.copyToDetachedLegacySector();}catch(IllegalStateException wanted){refused=true;}
      ok(refused,"wide legacy downgrade refusal");
    }
  }
}'''
        with tempfile.TemporaryDirectory(prefix="wide-package-") as temp:
            root = Path(temp)
            package_at(root, [0, 255, 256, 12345, 65535], True)
            result = self.compile_run(source, "WideServerProbe", CORE, (root, 0, 255, 256, 12345, 65535, 11))
            self.assertEqual(0, result.returncode, result.stderr)
            # Repeat the load to prove stable decoding; the built lifecycle test
            # owns the actual author/save/shutdown/reopen persistence claim.
            result = self.compile_run(source, "WideServerProbe", CORE, (root, 0, 255, 256, 12345, 65535, 11))
            self.assertEqual(0, result.returncode, result.stderr)
        with tempfile.TemporaryDirectory(prefix="legacy-package-") as temp:
            root = Path(temp)
            package_at(root, [0, 255], False)
            result = self.compile_run(source, "WideServerProbe", CORE, (root, 0, 255, 0, 255, 0, 10))
            self.assertEqual(0, result.returncode, result.stderr)

    def test_encoding_width_mismatch_fails_closed(self):
        source = r'''
import com.openrsc.server.io.*;import java.nio.file.*;
public final class MismatchProbe {public static void main(String[] a)throws Exception{NativeLayeredWorldPackage.load(Paths.get(a[0]));}}
'''
        with tempfile.TemporaryDirectory(prefix="wide-mismatch-") as temp:
            root = Path(temp)
            package_at(root, [256], True)
            manifest = json.loads((root / "manifest.json").read_text())
            manifest["terrainSectors"][0]["encoding"] = "raw-layered-sector-v1"
            (root / "manifest.json").write_text(json.dumps(manifest) + "\n")
            result = self.compile_run(source, "MismatchProbe", CORE, (root,))
            self.assertNotEqual(0, result.returncode)
            self.assertIn("Raw sector must contain exactly", result.stderr)

    def test_client_v1_and_v2_models_preserve_times_three_elevation_units(self):
        source = r'''
import orsc.NativeLayeredTerrainChunk;import com.openrsc.client.model.Tile;
public final class WideClientProbe {
 static void ok(boolean v,String m){if(!v)throw new AssertionError(m);}
 static byte[] tile(int elevation,boolean wide){byte[] b=new byte[wide?11:10];int p=0;if(wide)b[p++]=(byte)(elevation>>>8);b[p++]=(byte)elevation;b[p++]=10;b[p++]=11;b[p++]=12;b[p++]=13;b[p++]=14;b[p++]=0x10;b[p++]=0x20;b[p++]=0x30;b[p++]=0x40;return b;}
 static void check(int elevation,boolean wide){byte[] one=tile(elevation,wide),all=new byte[48*48*one.length];for(int p=0;p<all.length;p+=one.length)System.arraycopy(one,0,all,p,one.length);NativeLayeredTerrainChunk c=NativeLayeredTerrainChunk.available(48,0,0,0,0,wide?NativeLayeredTerrainChunk.RAW_ENCODING_V2:NativeLayeredTerrainChunk.RAW_ENCODING,"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",all);Tile t=c.createTile(0,0);ok(t.groundElevation==elevation,"model elevation");ok(t.groundElevation*3==elevation*3,"x3 scale");ok((t.groundTexture&255)==10&&(t.groundOverlay&255)==11&&(t.roofTexture&255)==12,"visual preservation");ok((t.verticalWall&255)==13&&(t.horizontalWall&255)==14&&t.diagonalWalls==0x10203040,"structure preservation");}
 public static void main(String[] a){check(255,false);check(0,true);check(256,true);check(12000,true);check(65535,true);}
}'''
        result = self.compile_run(source, "WideClientProbe", CLIENT)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_absolute_raise_lower_and_atomic_bounds(self):
        source = r'''
import com.openrsc.server.content.worldedit.WorldEditorTerrainStroke;
public final class ElevationOperationProbe {static void ok(boolean v,String m){if(!v)throw new AssertionError(m);}public static void main(String[] a){
 int[] set=WorldEditorTerrainStroke.elevationTargets(new int[]{0,255,65535},0,12345,7);ok(set[0]==12345&&set[2]==12345,"absolute");
 int[] raise=WorldEditorTerrainStroke.elevationTargets(new int[]{0,255,256},1,0,17);ok(raise[0]==17&&raise[1]==272&&raise[2]==273,"raise");
 int[] lower=WorldEditorTerrainStroke.elevationTargets(new int[]{17,272},2,0,17);ok(lower[0]==0&&lower[1]==255,"lower");
 boolean overflow=false;try{WorldEditorTerrainStroke.elevationTargets(new int[]{1,65535,2},1,0,1);}catch(IllegalArgumentException e){overflow=e.getMessage().contains("atomically");}ok(overflow,"overflow refusal");
 boolean underflow=false;try{WorldEditorTerrainStroke.elevationTargets(new int[]{1,0,2},2,0,1);}catch(IllegalArgumentException e){underflow=e.getMessage().contains("atomically");}ok(underflow,"underflow refusal");
 }}'''
        result = self.compile_run(source, "ElevationOperationProbe", CORE)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_capability_and_consumers_are_explicit(self):
        capability = json.loads((ROOT / "server/conf/world-builder/adaptive-runtime-capability-v5.json").read_text())
        self.assertEqual(5, capability["schemaVersion"])
        self.assertEqual({"storageEncoding": "unsigned-16", "minimum": 0, "maximum": 65535, "renderScale": 3,
                          "legacyV1Promotion": "unsigned-byte-lossless", "operations": ["absolute", "raise", "lower"],
                          "atomicMultiTileBounds": True}, capability["terrainElevation"])
        client_world = (ROOT / "Client_Base/src/orsc/graphics/three/World.java").read_text()
        for evidence in ("groundElevation * 3", "ROOF_ELEVATION_MARKER", "collectRoofFaceInputs", "getElevation(pixelX, pixelZ)", "NATIVE_MINIMAP"):
            self.assertIn(evidence, client_world)
        handler = (ROOT / "Client_Base/src/orsc/PacketHandler.java").read_text()
        self.assertIn("World Editor operation-history capability mismatch", handler)
        server_tile = (ROOT / "server/src/com/openrsc/server/model/world/region/TileValue.java").read_text()
        self.assertIn("public int elevation", server_tile)


if __name__ == "__main__":
    unittest.main()
