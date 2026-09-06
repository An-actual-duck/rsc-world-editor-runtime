package com.openrsc.server;

import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import com.openrsc.server.model.entity.npc.Npc;
import com.openrsc.server.model.entity.player.Player;
import com.openrsc.server.model.entity.GameObject;
import com.openrsc.server.model.Point;
import com.openrsc.server.model.Path;
import com.openrsc.server.model.PathValidation;
import com.openrsc.server.model.AStarPathfinder;
import com.openrsc.server.model.world.coordinate.*;
import com.openrsc.server.model.world.region.*;
import com.openrsc.server.util.rsc.CollisionFlag;

/** Test-only actual packaged runtime probe; expected terrain comes from a separate oracle. */
public final class GenuineMapSemanticsProbe {
  private static WorldLocation at(int x, int y, int level) {
    return new WorldLocation(WorldSpaceId.GLOBAL, new WorldCoordinate(x, y, level));
  }
  private static void check(boolean value, String message) {
    if (!value) throw new AssertionError(message);
  }
  public static void main(String[] args) throws Exception {
    boolean wrongOverlay=Boolean.parseBoolean(args[4]);
    CurrentCompositionIdentity.initializeFromSystemProperties();
    Server server = new Server("current-base.conf");
    server.getEntityHandler().load();
    RegionManager regions = server.getWorld().getRegionManager();
    check(regions.replacesLegacyBasePopulation(), "must replace, not append, legacy population");
    check(regions.getNativeLayeredWorldPackage().getTerrainSectorCount() == 352, "wrong coverage");
    int differences = 0;
    List<String> examples = new ArrayList<>();
    try (DataInputStream input = new DataInputStream(new BufferedInputStream(Files.newInputStream(Paths.get(args[0]))))) {
      int size = input.readInt();
      check(size == 811008, "incomplete independent oracle");
      for (int index = 0; index < size; index++) {
        int x = input.readInt(), y = input.readInt(), level = input.readInt();
        int overlay = input.readInt(), horizontal = input.readInt(), vertical = input.readInt(), diagonal = input.readInt();
        int mask = input.readInt(), projectile = input.readInt(), wallCount = input.readInt(), overlayProjectile = input.readInt();
        WorldLocation location = at(x,y,level);
        check(regions.hasNativeLayeredTerrain(location), "missing canonical tile " + location);
        TileValue tile = regions.getTile(location);
        boolean equal = (tile.overlay & 255) == overlay && (tile.horizontalWallVal & 255) == horizontal
          && (tile.verticalWallVal & 255) == vertical && tile.diagWallVal == diagonal
          && (tile.traversalMask & 255) == mask && tile.projectileAllowed == (projectile != 0)
          && tile.originalProjectileAllowed == (projectile != 0)
          && tile.isTerrainBlocked() == ((mask & 64) != 0)
          && tile.getTerrainWallProjectileCount() == wallCount
          && tile.isTerrainOverlayProjectileBlocked() == (overlayProjectile != 0);
        if (!equal) {
          differences++;
          if (examples.size() < 12) examples.add(location + " expectedMask=" + mask + " actualMask="
            + (tile.traversalMask & 255) + " expectedProjectile=" + projectile + " actualProjectile="
            + tile.projectileAllowed + " expectedWalls=" + wallCount + " actualWalls=" + tile.getTerrainWallProjectileCount());
        }
      }
      check(input.read() == -1, "oracle has trailing records");
    }
    System.out.println("GENUINE_TERRAIN compared=811008 differences=" + differences + " examples=" + examples);
    check(differences == (wrongOverlay?1:0), "independent c0102 terrain gameplay comparison failed");
    regions.populateNativeLayeredPlacements();
    check(server.getWorld().getNpcs().size() == 3609, "effective NPC multiplicity changed");
    check(regions.getNativeLayeredSceneryCount() == 26815 && regions.getNativeLayeredBoundaryCount() == 967,
      "effective object population changed");
    Map<String,String> expectedNpcs = new TreeMap<>(), actualNpcs = new TreeMap<>();
    for (String line : Files.readAllLines(Paths.get(args[1]), StandardCharsets.UTF_8)) {
      String[] columns = line.split("\t",2);
      check(expectedNpcs.put(columns[0],columns[1]) == null,"duplicate expected placement identity");
    }
    int voidBounds = 0;
    for (Npc npc : server.getWorld().getNpcs()) {
      check(regions.hasNativeLayeredTerrain(npc.getWorldLocation()), "NPC anchor absent");
      int level = npc.getWorldLocation().getCoordinate().getLevel();
      String id = npc.getAttribute(RegionManager.NATIVE_LAYERED_PLACEMENT_ID_ATTRIBUTE);
      String value = npc.getID()+"\t"+level+"\t"+npc.getX()+"\t"+npc.getY()+"\t"
        +npc.getLoc().minX()+"\t"+npc.getLoc().minY()+"\t"+npc.getLoc().maxX()+"\t"
        +npc.getLoc().maxY()+"\t"+npc.getAuthoredRespawnSeconds();
      check(id != null && actualNpcs.put(id,value) == null,"duplicate/lost runtime NPC identity");
      boolean crosses = false;
      for (int sx = Math.floorDiv(npc.getLoc().minX(),48); sx <= Math.floorDiv(npc.getLoc().maxX(),48); sx++) {
        for (int sy = Math.floorDiv(npc.getLoc().minY(),48); sy <= Math.floorDiv(npc.getLoc().maxY(),48); sy++) {
          if (!regions.hasNativeLayeredTerrain(at(sx*48,sy*48,level))) {
            crosses = true;
            TileValue missing = regions.getTile(at(sx*48,sy*48,level));
            check(missing.traversalMask == CollisionFlag.FULL_BLOCK && missing.isTerrainBlocked()
              && !missing.projectileAllowed, "roaming void is not fully blocked");
          }
        }
      }
      if (crosses) {
        voidBounds++;
        checkMovementEdge(server,regions,npc,level);
      }
    }
    check(expectedNpcs.equals(actualNpcs), "runtime changed historical NPC IDs, starts, bounds, respawn or multiplicity");
    check(voidBounds == 146, "authoritative void-crossing rectangles changed: " + voidBounds);
    check(regions.getNativeLayeredWorldPackage().getTerrainSectorCount() == 352, "population activated void");
    System.out.println("GENUINE_POPULATION npcs=3609 voidBounds=146 sectors=352");
    int movementDifferences=0, projectileDifferences=0;
    examples.clear();
    try(DataInputStream input=new DataInputStream(new BufferedInputStream(Files.newInputStream(Paths.get(args[2]))))) {
      check(input.readInt()==811008,"incomplete populated oracle");
      for(int index=0;index<811008;index++) {
        int x=input.readInt(),y=input.readInt(),level=input.readInt(),mask=input.readInt(),shot=input.readInt();
        TileValue tile=regions.getTile(at(x,y,level));
        if((tile.traversalMask&255)!=mask)movementDifferences++;
        if(tile.projectileAllowed!=(shot!=0))projectileDifferences++;
        if(((tile.traversalMask&255)!=mask || tile.projectileAllowed!=(shot!=0))&&examples.size()<12)
          examples.add(at(x,y,level)+" expectedMask="+mask+" actualMask="+(tile.traversalMask&255)
            +" expectedProjectile="+shot+" actualProjectile="+tile.projectileAllowed);
      }
      check(input.read()==-1,"populated oracle has trailing records");
    }
    System.out.println("GENUINE_COMPOSED compared=811008 movementDifferences="+movementDifferences
      +" projectileDifferences="+projectileDifferences+" examples="+examples);
    int treeDiagnosticDifferences=0;
    try(DataInputStream input=new DataInputStream(new BufferedInputStream(Files.newInputStream(Paths.get(args[3]))))) {
      check(input.readInt()==811008,"incomplete diagnostic oracle");
      for(int index=0;index<811008;index++) {
        int x=input.readInt(),y=input.readInt(),level=input.readInt();input.readInt();int shot=input.readInt();
        if(regions.getTile(at(x,y,level)).projectileAllowed!=(shot!=0))treeDiagnosticDifferences++;
      }
    }
    System.out.println("GENUINE_DIAGNOSTIC ownerTreeBranchResidualDifferences="+treeDiagnosticDifferences);
    Player observer = new Player(server.getWorld(),12345L);
    observer.setInitialLayeredLocation(at(312,516,-1));
    observer.updateRegion();
    GameObject ladder = regions.findInteractionScenery(Point.location(312,516),observer);
    check(ladder != null && ladder.getID() == 199,"actual historical ladder199 missing");
    TileValue before = regions.getTile(at(312,516,-1));
    check((before.overlay & 255) == (wrongOverlay?8:0) && before.isTerrainBlocked()==wrongOverlay,
      "server overlay correction/control missing");
    check(before.getBlockingSceneryCount() > 0,"ladder does not expose real dynamic collision");
    server.getWorld().unregisterGameObject(ladder);
    TileValue removed = regions.getTile(at(312,516,-1));
    check(removed.isTerrainBlocked()==wrongOverlay && removed.getBlockingSceneryCount() == 0
      && (removed.traversalMask & CollisionFlag.FULL_BLOCK_C) == (wrongOverlay?64:0),
      "ladder removal does not distinguish correction from client-overlay control");
    try { server.getWorld().registerGameObject(ladder); throw new AssertionError("removed instance registered twice"); }
    catch(IllegalStateException expected) { }
    GameObject replacement=new GameObject(server.getWorld(),ladder.getLoc());
    replacement.setInitialWorldLocation(at(312,516,-1));
    server.getWorld().registerGameObject(replacement);
    TileValue restored = regions.getTile(at(312,516,-1));
    check(state(before).equals(state(restored)),"ladder re-add did not restore exact collision/projectile state");
    System.out.println("GENUINE_LADDER before="+state(before)+" removed="+state(removed)+" restored="+state(restored));
    // While present, the ladder masks the wrong overlay's movement difference.
    check(movementDifferences==0&&projectileDifferences==0,"historical composed collision/projectile comparison failed");
    System.exit(0);
  }
  private static String state(TileValue tile) {
    return (tile.traversalMask&255)+":"+tile.getBlockingSceneryCount()+":"+tile.getTerrainCollisionMask()
      +":"+tile.isTerrainBlocked()+":"+tile.getTerrainWallProjectileCount()+":"+tile.getDynamicProjectileCount()
      +":"+tile.isTerrainOverlayProjectileBlocked()+":"+tile.projectileAllowed+":"+tile.getHostileProjectileCollisionMask();
  }
  private static void checkMovementEdge(Server server,RegionManager regions,Npc original,int level) {
    for(int x=original.getLoc().minX();x<=original.getLoc().maxX();x++) {
      for(int y=original.getLoc().minY();y<=original.getLoc().maxY();y++) {
        if(!regions.hasNativeLayeredTerrain(at(x,y,level)))continue;
        for(int dx=-1;dx<=1;dx++)for(int dy=-1;dy<=1;dy++) {
          if(dx==0&&dy==0)continue;
          int tx=x+dx,ty=y+dy;
          if(tx<original.getLoc().minX()||tx>original.getLoc().maxX()
            ||ty<original.getLoc().minY()||ty>original.getLoc().maxY()
            ||regions.hasNativeLayeredTerrain(at(tx,ty,level)))continue;
          Npc probe=new Npc(server.getWorld(),original.getID(),at(x,y,level),2);
          check(!PathValidation.checkAdjacent(probe,x,y,tx,ty),"actual NPC adjacency enters void");
          AStarPathfinder planner=new AStarPathfinder(probe,new Point(x,y),new Point(tx,ty),5);
          planner.feedPath(new Path(probe,Path.PathType.WALK_TO_POINT));
          check(planner.findPath()==null,"actual NPC planner enters void");
          Path forced=new Path(probe,Path.PathType.WALK_TO_POINT);forced.addDirect(tx,ty);
          probe.getWalkingQueue().setPath(forced);probe.getWalkingQueue().processNextMovement();
          check(probe.getX()==x&&probe.getY()==y,"actual NPC walking queue enters void");
          return;
        }
      }
    }
    throw new AssertionError("no actual present/absent boundary tested for NPC "+original.getID());
  }
}
