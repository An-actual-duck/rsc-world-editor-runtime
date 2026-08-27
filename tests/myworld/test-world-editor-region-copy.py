#!/usr/bin/env python3
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GEOMETRY = ROOT / "Client_Base/src/com/openrsc/interfaces/misc/WorldEditorRegionSelection.java"
UI = ROOT / "Client_Base/src/com/openrsc/interfaces/misc/WorldEditorInterface.java"
CLIENT = ROOT / "Client_Base/src/orsc/mudclient.java"
PACKET_HANDLER = ROOT / "Client_Base/src/orsc/PacketHandler.java"
BRIDGE = ROOT / "Client_Base/src/orsc/WorldBuilderRegionCopyClientBridge.java"
SERVER = ROOT / "server/src/com/openrsc/server/content/worldedit/AdaptiveWorldBuilderRegionCopyRequest.java"
PASTE_BRIDGE = ROOT / "Client_Base/src/orsc/WorldBuilderRegionPasteClientBridge.java"
BUNDLE_BRIDGE = ROOT / "Client_Base/src/orsc/WorldBuilderRegionBundleClientBridge.java"
BUNDLE_DIALOG = ROOT / "Client_Base/src/orsc/WorldBuilderRegionBundleFileDialog.java"
BUNDLE_SERVER = ROOT / "server/src/com/openrsc/server/content/worldedit/AdaptiveWorldBuilderRegionBundleRequest.java"
PASTE_SERVER = ROOT / "server/src/com/openrsc/server/content/worldedit/AdaptiveWorldBuilderRegionPasteRequest.java"
COMMANDS = ROOT / "server/plugins/com/openrsc/server/plugins/authentic/commands/Development.java"

HARNESS = r"""
import com.openrsc.interfaces.misc.WorldEditorRegionSelection;

public final class WorldEditorRegionSelectionHarness {
    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
    private static void refused(int[][] markers, String label) {
        boolean refused = false;
        try { WorldEditorRegionSelection.validateClosed(markers); }
        catch (IllegalArgumentException expected) { refused = true; }
        require(refused, label);
    }
    public static void main(String[] args) {
        int[][] square = {{10,20},{12,20},{12,22},{10,22}};
        int[][] reversed = {{10,22},{12,22},{12,20},{10,20}};
        require(WorldEditorRegionSelection.ownedTiles(square, 9).length == 9,
            "inclusive square ownership changed");
        require(WorldEditorRegionSelection.ownedTiles(reversed, 9).length == 9,
            "marker winding changed ownership");
        boolean bounded = false;
        try { WorldEditorRegionSelection.ownedTiles(square, 8); }
        catch (IllegalArgumentException expected) { bounded = true; }
        require(bounded, "preview inventory limit was ignored");
        refused(new int[][] {{0,0},{2,2},{0,2},{2,0}},
            "self-intersection was accepted");
        refused(new int[][] {{0,0},{2,0},{0,0}},
            "duplicate marker was accepted");
        refused(new int[][] {{0,0},{1,1},{2,2}},
            "degenerate polygon was accepted");
        int[][] extreme = {{Integer.MAX_VALUE - 1,0},{Integer.MAX_VALUE,0},
            {Integer.MAX_VALUE,1}};
        require(WorldEditorRegionSelection.ownedTiles(extreme, 3).length == 3,
            "extreme coordinate iteration overflowed");
    }
}
"""

with tempfile.TemporaryDirectory(prefix="world-editor-region-copy-") as temp:
    harness = Path(temp) / "WorldEditorRegionSelectionHarness.java"
    harness.write_text(HARNESS, encoding="utf-8")
    subprocess.run(["javac", "-d", temp, str(GEOMETRY), str(harness)], check=True)
    completed = subprocess.run(
        ["java", "-cp", temp, "WorldEditorRegionSelectionHarness"],
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stdout + completed.stderr)

ui = UI.read_text(encoding="utf-8")
client = CLIENT.read_text(encoding="utf-8")
packet_handler = PACKET_HANDLER.read_text(encoding="utf-8")
bridge = BRIDGE.read_text(encoding="utf-8")
server = SERVER.read_text(encoding="utf-8")
paste_bridge = PASTE_BRIDGE.read_text(encoding="utf-8")
bundle_bridge = BUNDLE_BRIDGE.read_text(encoding="utf-8")
bundle_dialog = BUNDLE_DIALOG.read_text(encoding="utf-8")
bundle_server = BUNDLE_SERVER.read_text(encoding="utf-8")
paste_server = PASTE_SERVER.read_text(encoding="utf-8")
commands = COMMANDS.read_text(encoding="utf-8")

assert "Mode { NAVIGATE, INSPECT, TERRAIN, SCENERY, NPC, ITEMS, REGION }" in ui
assert '"Copy/Paste"' in ui
assert "addRegionMarker" in ui and "closeRegionSelection" in ui
assert "removeLastRegionMarker" in ui and "cancelRegionSelection" in ui
assert "requestRegionCopy" in ui and 'mc.sendCommandString("copyregion")' in ui
assert "drawWorldEditorRegionSelectionPreview" in client
assert "drawWorldEditorRegionMarker" in client
assert "WORLD_EDITOR_ADD_REGION_MARKER" in client
assert '"world-builder-region-copy-request"' in bridge
assert "StandardOpenOption.CREATE_NEW" in bridge
assert 'command.equalsIgnoreCase("copyregion")' in commands
assert server.index("editor.saveAdaptivePackage(player)") < server.index("Files.move(pending, request")
assert "ownsActiveSession(player)" in server
assert '"world-builder-region-copy-response"' in server
assert "RegionTool { COPY, PASTE }" in ui
assert "setRegionPasteDestination" in ui and "requestRegionPasteApply" in ui
assert "regionPasteOverwriteArmed" in ui
assert "c!='\\uffff'&&!Character.isSurrogate(c)" in ui
assert "drawWorldEditorRegionPastePreview" in client
assert "WORLD_EDITOR_SET_REGION_PASTE_DESTINATION" in client
assert '"world-builder-region-paste-request"' in paste_bridge
assert '"OVERWRITE " : "PASTE "' in paste_bridge
assert 'command.equalsIgnoreCase("pasteregion")' in commands
assert 'command.equalsIgnoreCase("activateregionpaste")' in commands
assert "editor.saveAdaptivePackage(player)" in paste_server
assert '"world-builder-region-paste-response"' in paste_server
assert "adoptPublishedAdaptivePackage" in paste_server
assert 'mc.sendCommandString("activateregionpaste "+result.requestId)' in ui
assert "restartWorldBuilderAfterRegionPaste" not in client
assert "activates live without restarting" in ui
assert "sameCenterTerrainContentRefresh" in packet_handler
assert "mc.reloadWorldEditorTerrain()" in packet_handler
assert packet_handler.index("mc.beginLayeredSceneActivation(") < packet_handler.index(
    "mc.reloadWorldEditorTerrain()"
)
assert '"world-builder-region-bundle-request"' in bundle_bridge
assert "requestImport" in bundle_bridge and "requestExport" in bundle_bridge
assert "libraryEntryCreated" in bundle_bridge and "compatibilityReport" in bundle_bridge
assert "FileDialog.LOAD" in bundle_dialog and "FileDialog.SAVE" in bundle_dialog
assert "chooser.setDaemon(true)" in bundle_dialog
assert "dialog.setAlwaysOnTop(true)" in bundle_dialog
assert "EventQueue.invokeLater" in bundle_dialog
assert "windowOpened" in bundle_dialog and "dialog.toFront()" in bundle_dialog
assert '"Import .wbr"' in ui and '"Export selected"' in ui
assert "requestRegionImport" in ui and "requestRegionExport" in ui
assert "pollRegionBundleDialog" in ui
assert 'mc.sendCommandString("shareregion")' in ui
assert 'command.equalsIgnoreCase("shareregion")' in commands
assert '"world-builder-region-bundle-request"' in bundle_server
assert "ownsActiveSession(player)" in bundle_server
assert "Files.move(pending, request" in bundle_server
assert "saveAdaptivePackage" not in bundle_server

print("PASS: ordered Region Copy, exact Paste, and portable sharing UI bridges validated")
