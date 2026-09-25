#!/usr/bin/env python3
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "server/core.jar"
LIB = ROOT / "server/lib/*"
WALKING = (ROOT / "server/src/com/openrsc/server/model/WalkingQueue.java").read_text()
NPC = (ROOT / "server/src/com/openrsc/server/model/entity/npc/Npc.java").read_text()
HANDLER = (ROOT / "server/src/com/openrsc/server/net/rsc/handlers/WorldEditorHandler.java").read_text()
WORLD = (ROOT / "server/src/com/openrsc/server/model/world/World.java").read_text()
UI = (ROOT / "Client_Base/src/com/openrsc/interfaces/misc/WorldEditorInterface.java").read_text()
HANDLER_COMPACT = re.sub(r"\s+", "", HANDLER)
WORLD_COMPACT = re.sub(r"\s+", "", WORLD)

if not CORE.exists():
    raise SystemExit("Missing server/core.jar; run ./scripts/build-server.sh first")

HARNESS = r"""
import com.openrsc.server.model.PathValidation;
import com.openrsc.server.model.world.region.Region;
import com.openrsc.server.model.world.region.TileValue;
import com.openrsc.server.util.rsc.CollisionFlag;

public final class WorldEditorRegionCollisionHarness {
    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
    public static void main(String[] args) {
        Region region = new Region(null, 0, 0);
        for (int x = 0; x < 48; x++) for (int y = 0; y < 48; y++) {
            TileValue tile = region.getTileValue(x, y);
            tile.initializeTerrainCollision();
            tile.overlay = 10;
            tile.setTerrainBlocked(true);
            tile.addTerrainCollision(CollisionFlag.WALL_NORTH);
            tile.addTerrainWallProjectileBlock();
            tile.addDynamicCollision(CollisionFlag.WALL_EAST);
            tile.addDynamicProjectileBlock();
        }
        region.checkRegionValues();
        require(region.getTileValue(5, 5) == region.getTileValue(6, 5),
            "uniform region fixture did not compress");

        TileValue painted = region.getMutableTileValue(5, 5);
        painted.overlay = 1;
        painted.setTerrainBlocked(false);
        TileValue adjacentVoid = region.getTileValue(6, 5);
        TileValue unrelatedVoid = region.getTileValue(40, 40);
        require(painted != adjacentVoid, "mutable tile still aliases its compressed neighbor");
        require((painted.traversalMask & CollisionFlag.FULL_BLOCK_C) == 0,
            "void-to-walkable paint remained terrain blocked");
        require((adjacentVoid.traversalMask & CollisionFlag.FULL_BLOCK_C) != 0,
            "adjacent untouched void became walkable");
        require((unrelatedVoid.traversalMask & CollisionFlag.FULL_BLOCK_C) != 0,
            "unrelated compressed-region collision changed");
        require((painted.traversalMask & CollisionFlag.WALL_NORTH) != 0 && painted.projectileAllowed,
            "overlay replacement erased terrain wall or projectile collision");
        painted.removeTerrainWallProjectileBlock();
        require(painted.projectileAllowed,
            "compressed-region copy lost dynamic projectile collision ownership");
        painted.removeDynamicCollision(CollisionFlag.WALL_EAST);
        painted.removeDynamicProjectileBlock();
        require((painted.traversalMask & CollisionFlag.WALL_EAST) == 0,
            "mutable tile retained removed dynamic wall collision");
        require(!painted.projectileAllowed,
            "mutable tile retained removed dynamic projectile collision");
        require((adjacentVoid.traversalMask & CollisionFlag.WALL_EAST) != 0 && adjacentVoid.projectileAllowed,
            "mutating copied dynamic collision changed an adjacent tile");
        painted.addTerrainWallProjectileBlock();

        painted.addBlockingScenery();
        painted.addDynamicCollision(CollisionFlag.WALL_EAST);
        painted.addDynamicProjectileBlock();
        painted.removeTerrainCollision(CollisionFlag.WALL_NORTH);
        painted.removeTerrainWallProjectileBlock();
        require((painted.traversalMask & CollisionFlag.FULL_BLOCK_C) != 0,
            "walkable terrain erased blocking scenery");
        require((painted.traversalMask & CollisionFlag.WALL_EAST) != 0 && painted.projectileAllowed,
            "terrain replacement erased dynamic wall or projectile collision");
        painted.removeBlockingScenery();
        require((painted.traversalMask & CollisionFlag.FULL_BLOCK_C) == 0,
            "removed scenery left walkable terrain blocked");
        painted.setTerrainBlocked(true);
        require(PathValidation.isBlocking(painted.traversalMask, (byte)CollisionFlag.WALL_EAST, false),
            "walkable-to-blocked terrain was ignored by authoritative path validation");
        painted.setTerrainBlocked(false);
        require(PathValidation.isBlocking(painted.traversalMask, (byte)CollisionFlag.WALL_EAST, false),
            "dynamic wall was ignored by authoritative path validation");
        require(!PathValidation.isBlocking(painted.traversalMask, (byte)CollisionFlag.WALL_SOUTH, false),
            "unrelated direction became blocked");
    }
}
"""

if "PathValidation.checkAdjacent(mob" not in WALKING:
    raise AssertionError("player/NPC walking queue no longer shares authoritative adjacent validation")
if "return isBlocking(t.traversalMask, (byte) bit);" not in NPC:
    raise AssertionError("NPC roaming no longer derives movement from the tile traversal mask")
if "getMutableTile(x,y)" not in HANDLER_COMPACT or "getMutableTile(finalintx,finalinty)" not in WORLD_COMPACT:
    raise AssertionError("post-load terrain or entity collision mutation bypasses region copy-on-write")
if re.search(r"getTile\([^;\n]+\)\.(?:add|remove|set|initialize)", WORLD):
    raise AssertionError("world entity collision mutation bypasses region copy-on-write")
if re.search(r"getTile\([^;\n]+\)\.traversalMask\s*[|&^]?=", WORLD):
    raise AssertionError("world collision mask is mutated outside authoritative ownership")
if "paintFloorColor?6:0" not in UI or "terrainStrokeTexture=paintFloorColor?resolvedFloorOverlay():0" not in UI:
    raise AssertionError("unified Floor no longer applies color and resolved collision overlay atomically")

tile_defs = ET.parse(ROOT / "server/conf/server/defs/TileDef.xml").getroot().findall("TileDef")
if int(tile_defs[0].findtext("objectType")) != 0:
    raise AssertionError("raw Floor Texture 1 is no longer walkable")
if int(tile_defs[9].findtext("objectType")) == 0:
    raise AssertionError("raw Floor Texture 10 is no longer blocking void")

with tempfile.TemporaryDirectory(prefix="world-editor-region-collision-") as temp:
    source = Path(temp) / "WorldEditorRegionCollisionHarness.java"
    source.write_text(HARNESS, encoding="utf-8")
    classpath = f"{CORE}:{LIB}"
    subprocess.run(["javac", "-cp", classpath, "-d", temp, str(source)], check=True)
    subprocess.run(["java", "-cp", f"{temp}:{classpath}", "WorldEditorRegionCollisionHarness"], check=True)

print("PASS: compressed-region copy-on-write and authoritative collision isolation validated")
