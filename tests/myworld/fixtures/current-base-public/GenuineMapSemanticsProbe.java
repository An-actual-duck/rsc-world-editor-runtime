package com.openrsc.server;

import java.io.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import com.openrsc.server.model.entity.npc.Npc;
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
    check(differences == 0, "independent c0102 terrain gameplay comparison failed");
    regions.populateNativeLayeredPlacements();
    check(server.getWorld().getNpcs().size() == 3609, "effective NPC multiplicity changed");
    int voidBounds = 0;
    for (Npc npc : server.getWorld().getNpcs()) {
      check(regions.hasNativeLayeredTerrain(npc.getWorldLocation()), "NPC anchor absent");
      int level = npc.getWorldLocation().getCoordinate().getLevel();
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
      if (crosses) voidBounds++;
    }
    check(voidBounds == 146, "authoritative void-crossing rectangles changed: " + voidBounds);
    check(regions.getNativeLayeredWorldPackage().getTerrainSectorCount() == 352, "population activated void");
    System.out.println("GENUINE_POPULATION npcs=3609 voidBounds=146 sectors=352");
    System.exit(0);
  }
}
