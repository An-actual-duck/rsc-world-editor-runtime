#!/usr/bin/env python3
"""Execute real Current Base NPC population, tile lookup, A*, and WalkingQueue."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/current-platform/current-base-v1"
spec = importlib.util.spec_from_file_location("roam_fixture", Path(__file__).with_name("test-native-blocked-void-npc-roam.py"))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)

HARNESS = r'''
package com.openrsc.server;
import com.openrsc.server.model.*;
import com.openrsc.server.model.Path.PathType;
import com.openrsc.server.model.entity.npc.Npc;
import com.openrsc.server.model.entity.player.Player;
import com.openrsc.server.content.worldedit.WorldEditorSessionManager;
import com.openrsc.server.model.world.coordinate.*;
import com.openrsc.server.model.world.region.*;
import com.openrsc.server.model.world.World;
import com.openrsc.server.util.rsc.CollisionFlag;

public final class BlockedVoidMovementHarness {
  static void check(boolean condition, String message) {
    if (!condition) throw new AssertionError(message);
  }
  static WorldLocation at(int x, int y) {
    return new WorldLocation(WorldSpaceId.GLOBAL, new WorldCoordinate(x, y, 0));
  }
  static Path plan(Npc npc, int x, int y) {
    AStarPathfinder planner = new AStarPathfinder(npc, new Point(npc.getX(), npc.getY()), new Point(x, y), 5);
    planner.feedPath(new Path(npc, PathType.WALK_TO_POINT));
    return planner.findPath();
  }
  static void edge(World world, int x, int y, int dx, int dy) {
    Npc npc = new Npc(world, 11, at(x, y), 2);
    check(world.getRegionManager().hasNativeLayeredTerrain(npc.getWorldLocation()), "edge anchor absent");
    int targetX=x+dx, targetY=y+dy;
    check(!world.getRegionManager().hasNativeLayeredTerrain(at(targetX,targetY)), "edge target not absent");
    check(npc.getTileAtCurrentLevel(targetX,targetY).traversalMask==CollisionFlag.FULL_BLOCK,
      "cardinal/corner void not FULL_BLOCK");
    check(!PathValidation.checkAdjacent(npc,x,y,targetX,targetY), "cardinal/corner movement allowed");
    check(plan(npc,targetX,targetY)==null, "cardinal/corner A* allowed");
    Path forced=new Path(npc,PathType.WALK_TO_POINT);
    forced.addDirect(targetX,targetY);
    npc.getWalkingQueue().setPath(forced);
    npc.getWalkingQueue().processNextMovement();
    check(npc.getX()==x && npc.getY()==y, "cardinal/corner queue entered void");
  }
  public static void main(String[] args) throws Exception {
    CurrentCompositionIdentity.initializeFromSystemProperties();
    Server server = new Server("current-base.conf");
    server.getEntityHandler().load();
    RegionManager regions = server.getWorld().getRegionManager();
    regions.populateNativeLayeredPlacements();
    if (!args[0].equals("edges")) {
      Npc corner = new Npc(server.getWorld(),11,at(47,47),3);
      check(regions.hasNativeLayeredTerrain(at(48,48)), "corner destination must be present");
      check(!regions.hasNativeLayeredTerrain(at(48,47)), "missing corner side activated");
      Path route=plan(corner,48,48);
      if(args[0].equals("detour")) {
        check(route!=null, "planner failed to route around void on present terrain");
        check(route.size()>=2, "A* did not route around the missing side");
        corner.getWalkingQueue().setPath(route);
        for(int tick=0;tick<5 && !corner.getWalkingQueue().finished();tick++) {
          corner.getWalkingQueue().processNextMovement();
          check(regions.hasNativeLayeredTerrain(corner.getWorldLocation()), "detour entered void");
        }
        check(corner.getX()==48 && corner.getY()==48, "detour did not reach destination");
      } else {
        check(!PathValidation.checkAdjacent(corner,47,47,48,48), "diagonal entered a disconnected island");
        check(route==null, "A* crossed void into a disconnected present island");
      }
      check(!regions.hasNativeLayeredTerrain(at(48,47)), "planner allocated corner side");
      System.out.println("blocked-void-movement: verified");
      System.exit(0);
    }
    Npc npc = server.getWorld().getNpcs().iterator().next();
    check(npc.getX() == 47 && npc.getY() == 24, "native anchor changed");
    check(npc.getLoc().minX() == 46 && npc.getLoc().maxX() == 50
      && npc.getLoc().minY() == 22 && npc.getLoc().maxY() == 26, "authoritative bounds changed");
    check(regions.getNativeLayeredWorldPackage().getTerrainSectorCount() == 1, "terrain grew");
    Player editor = new Player(server.getWorld(),12345L);
    editor.setInitialLayeredLocation(at(47,24));
    WorldEditorSessionManager sessions=new WorldEditorSessionManager();
    java.lang.reflect.Method coverage=sessions.getClass().getDeclaredMethod(
      "requireNativeNpcTerrainCoverage",Player.class,WorldLocation.class,
      int.class,int.class,int.class,int.class);
    coverage.setAccessible(true);
    coverage.invoke(sessions,editor,at(47,24),46,22,50,26);
    for(int[] invalid:new int[][]{{48,24,46,22,50,26},{47,24,46,22,175,26},{47,24,48,22,50,26}}) {
      try {
        coverage.invoke(sessions,editor,at(invalid[0],invalid[1]),invalid[2],invalid[3],invalid[4],invalid[5]);
        throw new AssertionError("live NPC coverage guard accepted invalid start/bounds");
      } catch(java.lang.reflect.InvocationTargetException rejected) {
        check(rejected.getCause() instanceof IllegalArgumentException,"unexpected live guard failure");
      }
    }
    for (int dy = -1; dy <= 1; dy++) {
      WorldLocation missing = at(48, 24 + dy);
      check(!regions.hasNativeLayeredTerrain(missing), "absent sector activated");
      TileValue tile = regions.getTile(missing);
      check(tile.traversalMask == CollisionFlag.FULL_BLOCK && tile.isTerrainBlocked()
        && tile.getHostileProjectileCollisionMask() == CollisionFlag.FULL_BLOCK && !tile.projectileAllowed,
        "absent region lookup not blocked: mask="+tile.traversalMask+" terrain="+tile.isTerrainBlocked()
        +" overlayProjectile="+tile.isTerrainOverlayProjectileBlocked()+" projectileAllowed="+tile.projectileAllowed);
      check(npc.getTileAtCurrentLevel(48, 24 + dy).traversalMask == CollisionFlag.FULL_BLOCK,
        "mob supplied null/unblocked planner cell");
      check(!PathValidation.checkAdjacent(npc, 47, 24, 48, 24 + dy), "adjacent void entry allowed");
      check(plan(npc, 48, 24 + dy) == null, "A* planned into absent terrain");
      Path forced = new Path(npc, PathType.WALK_TO_POINT);
      forced.addDirect(48, 24 + dy);
      npc.getWalkingQueue().setPath(forced);
      npc.getWalkingQueue().processNextMovement();
      check(npc.getX() == 47 && npc.getY() == 24, "WalkingQueue entered absent terrain");
    }
    check(PathValidation.checkAdjacent(npc, 47, 24, 47, 23), "present neighbor rejected");
    Path walkable = plan(npc, 47, 23);
    check(walkable != null, "A* rejected present terrain");
    npc.getWalkingQueue().setPath(walkable);
    for (int tick = 0; tick < 3 && !npc.getWalkingQueue().finished(); tick++)
      npc.getWalkingQueue().processNextMovement();
    check(npc.getX() == 47 && npc.getY() == 23, "positive real movement failed");
    check(npc.getLoc().maxX() == 50, "movement clamped roam bounds");
    check(!regions.hasNativeLayeredTerrain(at(48, 24)), "movement allocated void");
    edge(server.getWorld(),0,24,-1,0);
    edge(server.getWorld(),24,0,0,-1);
    edge(server.getWorld(),24,47,0,1);
    edge(server.getWorld(),0,0,-1,-1);
    edge(server.getWorld(),47,47,1,1);
    edge(server.getWorld(),0,47,-1,1);
    edge(server.getWorld(),47,0,1,-1);
    System.out.println("blocked-void-movement: verified");
    System.exit(0);
  }
}
'''


class BlockedVoidMovementTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build = subprocess.run(["python3", "scripts/build-current-base.py", "--test-allow-dirty"],
                               cwd=ROOT, capture_output=True, text=True)
        if build.returncode:
            raise RuntimeError((build.stdout + build.stderr)[-12000:])

    def test_packaged_npc_movement_and_astar_refuse_absent_sector(self):
        self.run_case("edges")

    def test_astar_routes_around_void_and_rejects_disconnected_present_island(self):
        self.run_case("detour")
        self.run_case("island")

    def run_case(self, mode):
        with tempfile.TemporaryDirectory(prefix="blocked-void-real-movement-") as temporary:
            root = Path(temporary)
            package = root / "package"
            fixture.package(package)
            if mode != "edges":
                manifest = json.loads((package / "manifest.json").read_text())
                for x, y in ([(0, 1), (1, 1)] if mode == "detour" else [(1, 1)]):
                    path = f"terrain-{x}-{y}.raw"
                    (package / path).write_bytes((package / "terrain.raw").read_bytes())
                    manifest["terrainSectors"].append(dict(manifest["terrainSectors"][0],
                                                          sectorX=x, sectorY=y, path=path))
                fixture.write_json(package / "manifest.json", manifest)
            runtime = root / "runtime"
            runtime.mkdir()
            with zipfile.ZipFile(OUTPUT / "server/content.zip") as archive:
                archive.extractall(runtime)
            (runtime / "plugins.jar").write_bytes((OUTPUT / "server/plugins.jar").read_bytes())
            config = runtime / "current-base.conf"
            config.write_text(config.read_text() + "\n" + "\n".join((
                "want_layered_player_location_authority: true",
                "want_layered_spatial_runtime_authority: true",
                "want_layered_protocol_client_authority: true",
                "want_layered_native_terrain_package: true",
                "layered_native_world_runtime_profile: world-builder-installed",
                "layered_native_terrain_package_path: " + str(package),
                "layered_native_terrain_manifest_sha256: " + hashlib.sha256((package / "manifest.json").read_bytes()).hexdigest(),
            )) + "\n")
            source = root / "BlockedVoidMovementHarness.java"
            source.write_text(HARNESS)
            classpath = os.pathsep.join((str(root), str(OUTPUT / "server/core.jar"), str(OUTPUT / "server/plugins.jar")))
            compiled = subprocess.run(["javac", "-source", "8", "-target", "8", "-cp", classpath,
                                       "-d", str(root), str(source)], capture_output=True, text=True)
            self.assertEqual(0, compiled.returncode, compiled.stdout + compiled.stderr)
            executed = subprocess.run(["java", "-Xmx512m", "-Dopenrsc.currentCompositionIdentityFile="
                                       + str(OUTPUT / "composition-identity.json"), "-cp", classpath,
                                       "com.openrsc.server.BlockedVoidMovementHarness", mode],
                                      cwd=runtime, capture_output=True, text=True, timeout=60)
            self.assertEqual(0, executed.returncode, (executed.stdout + executed.stderr)[-14000:])
            self.assertIn("blocked-void-movement: verified", executed.stdout)


if __name__ == "__main__":
    unittest.main()
