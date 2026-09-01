#!/usr/bin/env python3
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORY = ROOT / "server/src/com/openrsc/server/content/worldedit/WorldEditorOperationHistory.java"

HARNESS = r"""
import com.openrsc.server.content.worldedit.WorldEditorOperationHistory;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.Map;

public final class WorldEditorOperationHistoryHarness {
    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
    private static WorldEditorOperationHistory.Change<String,Integer> change(
            String key, int before, int after) {
        return WorldEditorOperationHistory.Change.of(key, before, after);
    }
    public static void main(String[] args) {
        WorldEditorOperationHistory<String,Integer> history =
            new WorldEditorOperationHistory<String,Integer>();
        history.record(1, "Brush", Arrays.asList(change("a", 0, 1), change("b", 0, 1)));
        history.record(1, "Brush", Arrays.asList(change("a", 1, 2), change("c", 0, 1)));
        require(history.canUndo() && !history.canRedo(), "coalesced history availability changed");

        Map<String,Integer> current = new LinkedHashMap<String,Integer>();
        current.put("a", 2); current.put("b", 1); current.put("c", 1);
        WorldEditorOperationHistory.Action<String,Integer> undo = history.undo(current);
        require(undo.changes.size() == 3, "drag batches were not coalesced");
        for (WorldEditorOperationHistory.Change<String,Integer> value : undo.changes)
            current.put(value.key, value.after);
        require(current.get("a") == 0 && current.get("b") == 0 && current.get("c") == 0,
            "undo did not restore the first before-state");
        require(!undo.canUndo && undo.canRedo, "undo availability changed");

        WorldEditorOperationHistory.Action<String,Integer> redo = history.redo(current);
        for (WorldEditorOperationHistory.Change<String,Integer> value : redo.changes)
            current.put(value.key, value.after);
        require(current.get("a") == 2 && current.get("b") == 1 && current.get("c") == 1,
            "redo did not restore the final after-state");

        history.undo(current);
		history.record(2, "No-op", Arrays.asList(change("a", 0, 0)));
		require(history.canRedo(), "no-op operation cleared redo");
        history.record(2, "Line", Arrays.asList(change("d", 0, 4)));
        require(!history.canRedo(), "new operation did not clear redo");

        current.clear(); current.put("d", 9);
        boolean refused = false;
        try { history.undo(current); }
        catch (IllegalStateException expected) { refused = true; }
        require(refused && history.canUndo(), "drift did not refuse without consuming history");

        history.clear();
        require(!history.canUndo() && !history.canRedo(), "clear retained history");

		history.record(2L, "Terrain", Arrays.asList(change("terrain:1,1", 0, 7)));
		history.record(3L, "Scenery Place", Arrays.asList(change("scenery:2,2", 0, 42)));
		history.record(5L, "NPC Place", Arrays.asList(change("npc:3,3", 0, 84)));
		current.clear();current.put("terrain:1,1",7);current.put("scenery:2,2",42);current.put("npc:3,3",84);
		undo=history.undo(current);
		require("NPC Place".equals(undo.label),"mixed history did not undo newest placement first");
		for(WorldEditorOperationHistory.Change<String,Integer> value:undo.changes)current.put(value.key,value.after);
		undo=history.undo(current);
		require("Scenery Place".equals(undo.label),"mixed history lost placement ordering");
		for(WorldEditorOperationHistory.Change<String,Integer> value:undo.changes)current.put(value.key,value.after);
		undo=history.undo(current);
		require("Terrain".equals(undo.label),"mixed history did not reach terrain in edit order");
		for(WorldEditorOperationHistory.Change<String,Integer> value:undo.changes)current.put(value.key,value.after);
		redo=history.redo(current);
		require("Terrain".equals(redo.label),"mixed history redo order changed");
    }
}
"""

with tempfile.TemporaryDirectory(prefix="world-editor-operation-history-") as temp:
    harness = Path(temp) / "WorldEditorOperationHistoryHarness.java"
    harness.write_text(HARNESS, encoding="utf-8")
    subprocess.run(["javac", "-d", temp, str(HISTORY), str(harness)], check=True)
    subprocess.run(["java", "-cp", temp, "WorldEditorOperationHistoryHarness"], check=True)

manager = (ROOT / "server/src/com/openrsc/server/content/worldedit/WorldEditorSessionManager.java").read_text()
handler = (ROOT / "server/src/com/openrsc/server/net/rsc/handlers/WorldEditorHandler.java").read_text()
parser = (ROOT / "server/src/com/openrsc/server/net/rsc/parsers/impl/PayloadCustomParser.java").read_text()
generator = (ROOT / "server/src/com/openrsc/server/net/rsc/generators/impl/PayloadCustomGenerator.java").read_text()
client = (ROOT / "Client_Base/src/com/openrsc/interfaces/misc/WorldEditorInterface.java").read_text()
packets = (ROOT / "Client_Base/src/orsc/PacketHandler.java").read_text()

assert "nativeOperationHistory.record" in manager
assert "undoNativeOperation" in manager and "redoNativeOperation" in manager
for label in ("Scenery Place", "Scenery Remove", "Scenery Rotate", "Scenery Move",
              "NPC Place", "NPC Remove", "Ground Item Place", "Ground Item Remove"):
    assert f'"{label}"' in manager
assert "changes.add(placementHistoryChange(sourceKey,current,null))" in manager
assert "changes.add(placementHistoryChange(destinationKey,null,movedState))" in manager
assert "Editor state changed outside this history" in HISTORY.read_text()
assert "request.type == 10" in handler and "request.type == 11" in handler
assert "editor.historyToken=packet.readInt()" in parser
assert "editor.type == 8 || editor.type == 9 || editor.type == 10" in generator
assert "editor.type == 11" in generator
assert "acceptTerrainHistoryChunk" in client and "requestTerrainHistory" in client
assert "acceptPlacementHistory" in client
assert "acceptEntityEdit" in client
assert "terrainHistoryCanUndo=canUndo;terrainHistoryCanRedo=canRedo" in client
assert "Ctrl+Z" in client and "Ctrl+Y" in client
assert "Availability is presentation state, not authority" in client
assert "if(redo?!terrainHistoryCanRedo:!terrainHistoryCanUndo)" not in client
assert "type==8||type==9||type==10" in packets
assert "type==11" in packets

print("PASS: bounded authoritative mixed Builder operation history")
