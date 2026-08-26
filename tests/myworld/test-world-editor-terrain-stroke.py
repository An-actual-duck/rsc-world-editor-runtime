#!/usr/bin/env python3
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STROKE = ROOT / "server/src/com/openrsc/server/content/worldedit/WorldEditorTerrainStroke.java"

HARNESS = r"""
import com.openrsc.server.content.worldedit.WorldEditorTerrainStroke;
import java.util.HashSet;
import java.util.Set;

public final class WorldEditorTerrainStrokeHarness {
    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
    private static void rejects(Runnable action, String message) {
        try { action.run(); } catch (IllegalArgumentException expected) { return; }
        throw new AssertionError(message);
    }
    public static void main(String[] args) {
        int[][] one = WorldEditorTerrainStroke.coordinates(100, 200, 1, 2);
        require(one.length == 1 && one[0][0] == 100 && one[0][1] == 200, "1x1 footprint changed");

        int[][] nine = WorldEditorTerrainStroke.coordinates(100, 200, 3, 8);
        require(nine.length == 9 && nine[0][0] == 100 && nine[0][1] == 200, "3x3 center/order changed");
        Set<String> unique = new HashSet<String>();
        for (int[] tile : nine) unique.add(tile[0] + ":" + tile[1]);
        require(unique.size() == 9, "3x3 contains duplicate tiles");
        for (int dx = -1; dx <= 1; dx++) for (int dy = -1; dy <= 1; dy++)
            require(unique.contains((100 + dx) + ":" + (200 + dy)), "3x3 is not centered and complete");

        rejects(() -> WorldEditorTerrainStroke.coordinates(0, 0, 2, 2), "unsupported brush was accepted");
        require(WorldEditorTerrainStroke.coordinates(0, 0, 3, 16).length == 9,
            "3x3 wall stroke was rejected");

        boolean[] before = {false, true, false, true};
        boolean[] after = {true, false, true, true};
        require(WorldEditorTerrainStroke.projectedDraftSize(10, before, after) == 11, "draft delta accounting changed");
        rejects(() -> WorldEditorTerrainStroke.projectedDraftSize(0, new boolean[]{true}, new boolean[]{false}), "draft underflow was accepted");
        int[][] sixtyFour = new int[64][2];
        for (int i = 0; i < sixtyFour.length; i++) { sixtyFour[i][0] = i; sixtyFour[i][1] = 500; }
        int[][] accepted = WorldEditorTerrainStroke.validateTiles(sixtyFour);
        require(accepted.length == 64, "64-tile stroke was rejected");
        sixtyFour[0][0] = 999;
        require(accepted[0][0] == 0, "validated coordinates were not defensively copied");
        rejects(() -> WorldEditorTerrainStroke.validateTiles(new int[65][2]), "oversized coordinate batch was accepted");
		int[][] operation = new int[4096][2];
		for (int i = 0; i < operation.length; i++) { operation[i][0] = i; operation[i][1] = 700; }
		require(WorldEditorTerrainStroke.validateOperationTiles(operation).length == 4096,
			"4096-tile operation was rejected");
		rejects(() -> WorldEditorTerrainStroke.validateOperationTiles(new int[4097][2]),
			"oversized terrain operation was accepted");
		require(WorldEditorTerrainStroke.projectedOperationDraftSize(0,new boolean[4096],new boolean[4096]) == 0,
			"large operation draft accounting changed");
        rejects(() -> WorldEditorTerrainStroke.validateTiles(new int[][]{{1, 2}, {1, 2}}), "duplicate coordinates were accepted");
        rejects(() -> WorldEditorTerrainStroke.projectedDraftSize(0, new boolean[65], new boolean[65]), "oversized stroke accounting was accepted");
    }
}
"""

with tempfile.TemporaryDirectory(prefix="world-editor-stroke-") as temp:
    temp_path = Path(temp)
    harness = temp_path / "WorldEditorTerrainStrokeHarness.java"
    harness.write_text(HARNESS, encoding="utf-8")
    subprocess.run(["javac", "-d", temp, str(STROKE), str(harness)], check=True)
    subprocess.run(["java", "-cp", temp, "WorldEditorTerrainStrokeHarness"], check=True)

print("PASS: terrain strokes are centered, bounded, and correctly accounted")
