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

assert "nativeTerrainHistory.record" in manager
assert "undoNativeTerrain" in manager and "redoNativeTerrain" in manager
assert "Editor state changed outside this history" in HISTORY.read_text()
assert "request.type == 10" in handler and "request.type == 11" in handler
assert "editor.historyToken=packet.readInt()" in parser
assert "editor.type == 8 || editor.type == 9 || editor.type == 10" in generator
assert "acceptTerrainHistoryChunk" in client and "requestTerrainHistory" in client
assert "Ctrl+Z" in client and "Ctrl+Y" in client
assert "type==8||type==9||type==10" in packets

print("PASS: bounded authoritative terrain operation history")
