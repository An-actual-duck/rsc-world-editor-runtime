#!/usr/bin/env python3
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BRUSH = ROOT / "Client_Base/src/com/openrsc/interfaces/misc/WorldEditorTerrainBrush.java"
FRAMING = ROOT / "server/src/com/openrsc/server/net/rsc/parsers/impl/WorldEditorPacketFraming.java"
SERVER = ROOT / "server/src/com/openrsc/server/Server.java"

HARNESS = r"""
import com.openrsc.interfaces.misc.WorldEditorTerrainBrush;
import com.openrsc.server.net.rsc.parsers.impl.WorldEditorPacketFraming;

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
    public static void main(String[] args) {
        verifyLine(10, 20, 10, 20);
        verifyLine(10, 20, 18, 20);
        verifyLine(18, 20, 10, 20);
        verifyLine(10, 20, 10, 29);
        verifyLine(10, 20, 18, 29);
        verifyLine(18, 29, 10, 20);

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
    }
}
"""

with tempfile.TemporaryDirectory(prefix="world-editor-terrain-drag-") as temp:
    temp_path = Path(temp)
    harness = temp_path / "WorldEditorTerrainDragHarness.java"
    harness.write_text(HARNESS, encoding="utf-8")
    subprocess.run(["javac", "-d", temp, str(BRUSH), str(FRAMING), str(harness)], check=True)
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

print("PASS: terrain drags interpolate, accept wide batches, and use Builder-only low-latency control")
