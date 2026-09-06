package orsc;

import java.nio.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.lang.reflect.*;
import java.util.*;
import org.json.*;
import orsc.graphics.three.World;
import com.openrsc.client.model.Sector;
import com.openrsc.client.model.Tile;

/** Actual packaged CPU window consumer, not a GUI/login or packet-authentication proof. */
public final class GenuineMapClientWindowProbe {
  private static String key(int level,int x,int y) {return level+":"+x+":"+y;}
  private static void check(boolean value,String label) {if(!value)throw new AssertionError(label);}
  public static void main(String[] args) throws Exception {
    CurrentCompositionIdentity.initializeFromSystemProperties();
    check(WorldBuilderInstalledClientProfile.current().isEnabled(),"normal installed bootstrap not selected");
    Path packageRoot=WorldBuilderInstalledClientProfile.current().packageRoot();
    com.openrsc.server.io.NativeLayeredWorldPackage serverPackage=
      com.openrsc.server.io.NativeLayeredWorldPackage.load(packageRoot);
    JSONObject manifest=new JSONObject(new String(Files.readAllBytes(packageRoot.resolve("manifest.json")),StandardCharsets.UTF_8));
    Map<String,JSONObject> declarations=new LinkedHashMap<>();Map<String,byte[]> payloads=new HashMap<>();
    JSONArray sectors=manifest.getJSONArray("terrainSectors");
    for(int index=0;index<sectors.length();index++) {
      JSONObject row=sectors.getJSONObject(index);String key=key(row.getInt("level"),row.getInt("sectorX"),row.getInt("sectorY"));
      check(declarations.put(key,row)==null,"duplicate sector");
      payloads.put(key,Files.readAllBytes(packageRoot.resolve(row.getString("path"))));
    }
    check(declarations.size()==352,"client-only terrain activated");
    Method reads=World.class.getDeclaredMethod("legacyLandscapeReadAttemptCount");reads.setAccessible(true);
    World world=new World(null,null);
    check(((Long)reads.invoke(null))==0L,"native constructor read historical archive");
    Field snapshotField=World.class.getDeclaredField("nativeLayeredTerrainSnapshot");snapshotField.setAccessible(true);
    Method build=World.class.getDeclaredMethod("buildCpuSectionWindow",int.class,int.class,int.class);build.setAccessible(true);
    long presentTiles=0,voidTiles=0;
    for(JSONObject center:declarations.values()) {
      int level=center.getInt("level"),sx=center.getInt("sectorX"),sy=center.getInt("sectorY");
      NativeLayeredTerrainChunk[] chunks=new NativeLayeredTerrainChunk[9];int index=0;
      for(int dx=-1;dx<=1;dx++)for(int dy=-1;dy<=1;dy++) {
        int x=sx+dx,y=sy+dy;String key=key(level,x,y);JSONObject row=declarations.get(key);
        chunks[index++]=row==null?NativeLayeredTerrainChunk.voidChunk(48,x,y):NativeLayeredTerrainChunk.available(
          48,x,y,x,y,row.getString("encoding"),row.getString("sha256"),wire(serverPackage,level,x,y));
      }
      NativeLayeredTerrainSnapshot snapshot=new NativeLayeredTerrainSnapshot(
        NativeLayeredTerrainSnapshot.ATOMIC_ACTIVATION_PROTOCOL_VERSION,manifest.getString("packageId"),
        manifest.getString("packageVersion"),WorldBuilderInstalledClientProfile.current().mapIdentity(),48,
        "global",level,sx,sy,1,chunks);
      // Isolate the real CPU consumer from renderer/GUI scheduling. These are
      // local fixture snapshots, not claims of an authenticated network session.
      snapshotField.set(world,snapshot);
      Object window=build.invoke(world,level==-1?3:level,sx,sy);
      Field data=window.getClass().getDeclaredField("sectors");data.setAccessible(true);
      Sector[] actual=(Sector[])data.get(window);
      for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++) {
        byte[] expected=payloads.get(key(level,sx+dx,sy+dy));
        ByteBuffer raw=expected==null?null:ByteBuffer.wrap(expected);
        Sector sector=actual[(dy+1)*3+dx+1];
        for(int x=0;x<48;x++)for(int y=0;y<48;y++) {
          Tile tile=sector.getTile(x,y);
          if(raw==null) {
            check((tile.groundOverlay&255)==8 && (tile.groundTexture&255)==1 && tile.groundElevation==0
              && tile.roofTexture==0 && tile.horizontalWall==0 && tile.verticalWall==0 && tile.diagonalWalls==0,
              "missing native cell borrowed legacy/presentation data");voidTiles++;
          } else {
            check(tile.groundElevation==(raw.getShort()&65535) && (tile.groundTexture&255)==(raw.get()&255)
              && (tile.groundOverlay&255)==(raw.get()&255) && (tile.roofTexture&255)==(raw.get()&255)
              && (tile.horizontalWall&255)==(raw.get()&255) && (tile.verticalWall&255)==(raw.get()&255)
              && tile.diagonalWalls==raw.getInt(),"CPU window changed canonical presentation/gameplay fields");presentTiles++;
          }
        }
      }
    }
    check(voidTiles>0 && presentTiles>=811008,"incomplete boundary window coverage");
    check(((Long)reads.invoke(null))==0L,"CPU windows attempted legacy archive access");
    System.out.println("GENUINE_CLIENT_CPU windows=352 presentTileVisits="+presentTiles+" voidTileVisits="+voidTiles+" legacyReads=0");
  }
  private static byte[] wire(com.openrsc.server.io.NativeLayeredWorldPackage source,int level,int sx,int sy) {
    // Reuse the actual packaged server wire encoder, not raw storage bytes:
    // storage and wire deliberately order the two wall fields differently.
    byte[] result=new byte[48*48*11];
    for(int cx=0;cx<2;cx++)for(int cy=0;cy<2;cy++) {
      byte[] chunk=source.findPresentationChunk(com.openrsc.server.model.world.coordinate.WorldSpaceId.GLOBAL,
        level,sx*2+cx,sy*2+cy).get().copyWireBytes();
      for(int x=0;x<24;x++)for(int y=0;y<24;y++)
        System.arraycopy(chunk,(x*24+y)*11,result,((cx*24+x)*48+cy*24+y)*11,11);
    }
    return result;
  }
}
