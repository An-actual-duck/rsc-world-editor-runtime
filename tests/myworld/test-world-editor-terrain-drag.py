#!/usr/bin/env python3
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRUSH = ROOT / "Client_Base/src/com/openrsc/interfaces/misc/WorldEditorTerrainBrush.java"
FRAMING = ROOT / "server/src/com/openrsc/server/net/rsc/parsers/impl/WorldEditorPacketFraming.java"
STROKE = ROOT / "server/src/com/openrsc/server/content/worldedit/WorldEditorTerrainStroke.java"
SERVER = ROOT / "server/src/com/openrsc/server/Server.java"
UI = ROOT / "Client_Base/src/com/openrsc/interfaces/misc/WorldEditorInterface.java"
CLIENT = ROOT / "Client_Base/src/orsc/mudclient.java"
CLIENT_PACKETS = ROOT / "Client_Base/src/orsc/PacketHandler.java"
HANDLER = ROOT / "server/src/com/openrsc/server/net/rsc/handlers/WorldEditorHandler.java"
GENERATOR = ROOT / "server/src/com/openrsc/server/net/rsc/generators/impl/PayloadCustomGenerator.java"
MANAGER = ROOT / "server/src/com/openrsc/server/content/worldedit/WorldEditorSessionManager.java"
PARSER = ROOT / "server/src/com/openrsc/server/net/rsc/parsers/impl/PayloadCustomParser.java"

HARNESS = r"""
import com.openrsc.interfaces.misc.WorldEditorTerrainBrush;
import com.openrsc.server.net.rsc.parsers.impl.WorldEditorPacketFraming;
import com.openrsc.server.content.worldedit.WorldEditorTerrainStroke;

public final class WorldEditorTerrainDragHarness {
    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
    private static void verifyLine(int x1, int y1, int x2, int y2) {
        int[][] line = WorldEditorTerrainBrush.lineCenters(x1, y1, x2, y2);
        require(line.length >= 1, "line was empty");
        require(line[0][0] == x1 && line[0][1] == y1, "line start changed");
        require(line[line.length - 1][0] == x2 && line[line.length - 1][1] == y2, "line end changed");
        for (int i = 1; i < line.length; i++) {
            int dx = Math.abs(line[i][0] - line[i - 1][0]);
            int dy = Math.abs(line[i][1] - line[i - 1][1]);
            require(dx <= 1 && dy <= 1 && dx + dy > 0, "line contains a gap or duplicate");
        }
    }
    private static void verifyFootprint(int size) {
        int centerX = 100, centerY = 200, radius = size / 2;
        int[][] tiles = WorldEditorTerrainBrush.centeredFootprint(centerX, centerY, size);
        require(tiles.length == size * size, "wrong footprint tile count for " + size);
        require(tiles[0][0] == centerX && tiles[0][1] == centerY,
            "footprint center was not first for " + size);
        java.util.HashSet<String> seen = new java.util.HashSet<String>();
        for (int[] tile : tiles) {
            require(Math.abs(tile[0] - centerX) <= radius, "footprint x exceeded radius");
            require(Math.abs(tile[1] - centerY) <= radius, "footprint y exceeded radius");
            require(seen.add(tile[0] + "," + tile[1]), "footprint contained a duplicate");
        }
        require(seen.contains((centerX - radius) + "," + (centerY - radius)),
            "footprint missed lower corner");
        require(seen.contains((centerX + radius) + "," + (centerY + radius)),
            "footprint missed upper corner");
    }
	private static int maskAt(int[][] tiles,int[] masks,int x,int y) {
		for(int i=0;i<tiles.length;i++)if(tiles[i][0]==x&&tiles[i][1]==y)return masks[i];
		throw new AssertionError("missing rectangle tile "+x+","+y);
	}
	private static void verifyRectangle() {
		int[][] outline=WorldEditorTerrainBrush.rectangleFootprint(10,20,12,22,false,4096);
		require(outline.length==8,"3x3 outline size changed");
		int[][] fill=WorldEditorTerrainBrush.rectangleFootprint(12,22,10,20,true,4096);
		require(fill.length==9,"3x3 fill size changed");
		WorldEditorTerrainBrush.RectanglePlan client=WorldEditorTerrainBrush.rectanglePlan(10,20,12,22,true,4,true,true,4096);
		WorldEditorTerrainStroke.RectanglePlan server=WorldEditorTerrainStroke.rectanglePlan(12,22,10,20,true,4,true,true);
		int[][] clientTiles=client.tiles();int[] clientMasks=client.fieldMasks();
		require(clientTiles.length==15,"smart rectangle unique size changed");
		require(server.coordinates.length==clientTiles.length,"client/server rectangle size differs");
		for(int i=0;i<clientTiles.length;i++)require(clientTiles[i][0]==server.coordinates[i][0]
			&&clientTiles[i][1]==server.coordinates[i][1]&&clientMasks[i]==server.fieldMasks[i],
			"client/server rectangle plan differs at "+i);
		require(maskAt(clientTiles,clientMasks,10,20)==52,"north/east corner ownership changed");
		require(maskAt(clientTiles,clientMasks,11,20)==36,"north edge ownership changed");
		require(maskAt(clientTiles,clientMasks,10,21)==20,"east edge ownership changed");
		require(maskAt(clientTiles,clientMasks,13,21)==16,"far east owner tile changed");
		require(maskAt(clientTiles,clientMasks,11,23)==32,"far north owner tile changed");
		boolean rejected=false;try{WorldEditorTerrainBrush.rectangleFootprint(0,0,64,64,true,4096);}
		catch(IllegalArgumentException expected){rejected=true;}require(rejected,"oversized rectangle was accepted");
	}
    public static void main(String[] args) {
        verifyLine(10, 20, 10, 20);
        verifyLine(10, 20, 18, 20);
        verifyLine(18, 20, 10, 20);
        verifyLine(10, 20, 10, 29);
        verifyLine(10, 20, 18, 29);
        verifyLine(18, 29, 10, 20);
		verifyFootprint(1);
		verifyFootprint(3);
		verifyFootprint(5);
		verifyFootprint(7);
		verifyRectangle();
		require(WorldEditorTerrainBrush.nextSize(1) == 3, "1x1 cycle failed");
		require(WorldEditorTerrainBrush.nextSize(3) == 5, "3x3 cycle failed");
		require(WorldEditorTerrainBrush.nextSize(5) == 7, "5x5 cycle failed");
		require(WorldEditorTerrainBrush.nextSize(7) == 1, "7x7 cycle failed");
		boolean rejected = false;
		try { WorldEditorTerrainBrush.centeredFootprint(0, 0, 2); }
		catch (IllegalArgumentException expected) { rejected = true; }
		require(rejected, "even footprint size was accepted");
		int[][] lineFootprint = WorldEditorTerrainBrush.lineFootprint(10, 20, 14, 20, 3, 64);
		require(lineFootprint.length == 21, "overlapping line footprints were not coalesced");
		require(lineFootprint[0][0] == 10 && lineFootprint[0][1] == 20,
			"line footprint did not retain its anchor first");
		int[][] largeLine = WorldEditorTerrainBrush.lineFootprint(0, 0, 500, 0, 7, 4096);
		require(largeLine.length == 3549, "large 7x7 line footprint changed");
		int[][] serverLargeLine = WorldEditorTerrainStroke.lineFootprint(0, 0, 500, 0, 7);
		require(serverLargeLine.length == largeLine.length, "client/server line size differs");
		for (int i = 0; i < largeLine.length; i++) require(
			largeLine[i][0] == serverLargeLine[i][0] && largeLine[i][1] == serverLargeLine[i][1],
			"client/server line geometry differs at " + i);
		rejected = false;
		try { WorldEditorTerrainBrush.lineFootprint(0, 0, 600, 0, 7, 4096); }
		catch (IllegalArgumentException expected) { rejected = true; }
		require(rejected, "oversized line footprint was accepted");

        require(WorldEditorPacketFraming.acceptsTerrainStroke(6, 282, 64),
            "maximum legacy stroke was rejected");
        require(WorldEditorPacketFraming.acceptsTerrainStroke(7, 286, 64),
            "maximum wide stroke was rejected");
        require(WorldEditorPacketFraming.acceptsEnvelopeLength(286),
            "maximum wide envelope was rejected before parsing");
        require(!WorldEditorPacketFraming.acceptsEnvelopeLength(283),
            "misaligned envelope was accepted");
        require(!WorldEditorPacketFraming.acceptsTerrainStroke(7, 282, 64),
            "wide stroke accepted the legacy length");
        require(!WorldEditorPacketFraming.acceptsTerrainStroke(7, 290, 65),
            "oversized wide stroke was accepted");
		require(WorldEditorPacketFraming.acceptsTerrainLine(8, 38, 7),
			"endpoint-based 7x7 line request was rejected");
		require(!WorldEditorPacketFraming.acceptsTerrainLine(8, 38, 6),
			"even line brush was accepted");
		require(WorldEditorPacketFraming.acceptsTerrainRectangle(9,39,2),"smart rectangle framing was rejected");
		require(WorldEditorPacketFraming.acceptsTerrainRectangle(9,39,7),"filled smart-wall rectangle framing was rejected");
		require(!WorldEditorPacketFraming.acceptsTerrainRectangle(9,39,4),"wall flag without Smart Walls was accepted");
		require(!WorldEditorPacketFraming.acceptsTerrainRectangle(9,39,8),"unknown rectangle flag was accepted");
		require(!WorldEditorPacketFraming.acceptsTerrainRectangle(9,38,2),"short rectangle frame was accepted");
    }
}
"""

with tempfile.TemporaryDirectory(prefix="world-editor-terrain-drag-") as temp:
    temp_path = Path(temp)
    harness = temp_path / "WorldEditorTerrainDragHarness.java"
    harness.write_text(HARNESS, encoding="utf-8")
    subprocess.run(["javac", "-d", temp, str(BRUSH), str(FRAMING), str(STROKE), str(harness)], check=True)
    subprocess.run(["java", "-cp", temp, "WorldEditorTerrainDragHarness"], check=True)

server = SERVER.read_text(encoding="utf-8")
method_start = server.index("private void processWorldBuilderControlPlanePackets()")
method_end = server.index("\n\t}", method_start)
control_plane = server[method_start:method_end]
assert "if (!getConfig().WORLD_BUILDER_MODE)" in control_plane
assert control_plane.index("if (!getConfig().WORLD_BUILDER_MODE)") < control_plane.index(
    "for (final Player player : getWorld().getPlayers())"
)
assert "player.processIncomingPackets()" in control_plane
assert "player.processOutgoingPackets()" in control_plane
assert server.count("processWorldBuilderControlPlanePackets();") == 1
assert "} else {\n\t\t\t\t\tprocessWorldBuilderControlPlanePackets();" in server

ui = UI.read_text(encoding="utf-8")
client = CLIENT.read_text(encoding="utf-8")
client_packets = CLIENT_PACKETS.read_text(encoding="utf-8")
handler = HANDLER.read_text(encoding="utf-8")
generator = GENERATOR.read_text(encoding="utf-8")
manager = MANAGER.read_text(encoding="utf-8")
parser = PARSER.read_text(encoding="utf-8")
assert "TerrainTool terrainTool=TerrainTool.FREEHAND" in ui
assert "lineFootprint(terrainLineAnchorX,terrainLineAnchorY,worldX,worldY" in ui
assert "worldX,worldY,terrainBrushSize,TERRAIN_DRAG_LIMIT" in ui
assert "sendTerrainLine(startX,startY,worldX,worldY)" in ui
assert "sendTerrainRectangle(startX,startY,worldX,worldY)" in ui
assert 'terrainGestureLabel="Rectangle"' in ui and "4096-tile operation limit" in ui
assert 'inspectionStatus="Line cannot cross a legacy wilderness-level boundary."' in ui
assert "terrainLineAnchorX>=0" in ui and '"Rectangle corner":"Line anchor"' in ui
assert "terrainLineAnchorTile()" in ui
assert "worldEditorInterface.terrainPaintActionLabel()" in client
assert "drawWorldEditorTerrainToolPreview(renderer3DFrame)" in client
assert "drawWorldEditorTerrainAnchorMarker" in client
assert "pinY=Math.max(9,Math.min(this.getSurface().height2-10,point[1]-24))" in client
assert "drawBoxAlpha(point[0]-5,point[1]-5,11,11,color,224)" in client and "0xffffff" in client
assert "acceptTerrainLineChunk" in client_packets and "type==8||type==9" in client_packets
assert "paintNativeTerrainOperation" in handler and "paintTerrainOperation" in handler
assert "sendTerrainOperation" in handler and "out.type=9" in handler
assert "editor.type == 8 || editor.type == 9" in generator
assert "acceptsTerrainLine(8,packet.getLength(),editor.brushSize)" in parser
assert "acceptsTerrainRectangle(9,packet.getLength(),editor.rectangleFlags)" in parser
assert "WorldEditorTerrainStroke.rectanglePlan" in handler
assert "paintNativeTerrainPlannedOperation" in handler and "paintTerrainPlannedOperation" in handler
legacy_operation = manager[manager.index("private TerrainStrokeResult paintTerrainTiles("):manager.index("public synchronized NativeTerrainSnapshot inspectNativeTerrain")]
assert legacy_operation.index("projectedOperationDraftSize") < legacy_operation.index("terrainDraft.remove(key)")
native_operation = manager[manager.index("private NativeTerrainStrokeResult paintNativeTerrainTiles("):manager.index("public synchronized NativeLayeredTerrainTile resolveNativeTerrainTile")]
assert native_operation.index("if (projected > TERRAIN_DRAFT_LIMIT)") < native_operation.index("nativeTerrainOverlay.remove(key)")
assert "if(operation)requireNativeOperationCoverage" in native_operation

print("PASS: freehand, line, and smart rectangle tools share bounded authoritative geometry")
