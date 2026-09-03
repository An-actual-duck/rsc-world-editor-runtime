#!/usr/bin/env python3
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLIENT_SELECTION = ROOT / "Client_Base/src/com/openrsc/interfaces/misc/WorldEditorLockdownSelection.java"
REGION_SELECTION = ROOT / "Client_Base/src/com/openrsc/interfaces/misc/WorldEditorRegionSelection.java"
SERVER_SELECTION = ROOT / "server/src/com/openrsc/server/content/worldedit/WorldEditorLockdownSelection.java"
UI = (ROOT / "Client_Base/src/com/openrsc/interfaces/misc/WorldEditorInterface.java").read_text(encoding="utf-8")
CLIENT = (ROOT / "Client_Base/src/orsc/mudclient.java").read_text(encoding="utf-8")
PACKETS = (ROOT / "server/src/com/openrsc/server/net/rsc/parsers/impl/PayloadCustomParser.java").read_text(encoding="utf-8")
HANDLER = (ROOT / "server/src/com/openrsc/server/net/rsc/handlers/WorldEditorHandler.java").read_text(encoding="utf-8")
SESSION = (ROOT / "server/src/com/openrsc/server/content/worldedit/WorldEditorSessionManager.java").read_text(encoding="utf-8")

HARNESS = r"""
import com.openrsc.interfaces.misc.WorldEditorLockdownSelection;
public final class LockdownHarness {
  private static void require(boolean value,String message){if(!value)throw new AssertionError(message);}
  public static void main(String[] args){
    require(WorldEditorLockdownSelection.tiles(0,new int[][]{{7,8}},16).length==1,"single tile failed");
    int[][] line=WorldEditorLockdownSelection.tiles(1,new int[][]{{2,3},{5,3}},16);
    require(line.length==4&&line[0][0]==2&&line[3][0]==5,"straight line failed");
    require(WorldEditorLockdownSelection.tiles(1,new int[][]{{10,20},{12,20},{12,22},{10,22}},9).length==9,"polygon failed");
    require(com.openrsc.server.content.worldedit.WorldEditorLockdownSelection.tiles(1,new int[][]{{2,3},{5,3}},16).length==4,"server line failed");
	boolean crossed=false;try{com.openrsc.server.content.worldedit.WorldEditorLockdownSelection.tiles(1,new int[][]{{0,0},{2,2},{0,2},{2,0}},16);}catch(IllegalArgumentException expected){crossed=true;}require(crossed,"server accepted crossing polygon");
  }
}
"""
with tempfile.TemporaryDirectory(prefix="world-editor-lockdown-") as temp:
    harness = Path(temp) / "LockdownHarness.java"
    harness.write_text(HARNESS, encoding="utf-8")
    subprocess.run(["javac", "-d", temp, str(REGION_SELECTION), str(CLIENT_SELECTION), str(SERVER_SELECTION), str(harness)], check=True)
    subprocess.run(["java", "-cp", temp, "LockdownHarness"], check=True)

assert "TerrainTool { FREEHAND, LINE, RECTANGLE, LOCKDOWN }" in UI
assert "LockdownMode { TILES, MARKERS }" in UI
assert "advanceLockdown" in UI and 'lockdownDone?"Reset":"Done"' in UI
assert "toggleLockdown" in UI and "click==2" in UI
assert "unlockedTiles" in UI and "lockdownOverlaps(regionPastePreviewTiles" in UI
assert "isLockdownSelecting" in CLIENT and "drawWorldEditorLockdownPreview" in CLIENT
assert "editor.type==13" in PACKETS and "acceptsLockdown" in PACKETS
assert "editLockdown" in HANDLER and "configureLockdown" in HANDLER
assert "filterLockdown" in SESSION and "requireUnlocked" in SESSION
assert "clearLockdown();" in SESSION
print("PASS: session-authoritative Lockdown selection and edit guards validated")
