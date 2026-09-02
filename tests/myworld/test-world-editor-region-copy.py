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
assert '"Regions"' in ui
assert "MODE_REGION" in ui and "MODE_REGION_COPY" in ui and "MODE_REGION_CUT" in ui and "MODE_REGION_PASTE" in ui
assert "drawModeIcon(WorldEditorIconRegistry.Key.MODE_REGION" in ui
assert "drawRegionToolIcon(WorldEditorIconRegistry.Key.MODE_REGION_COPY" in ui
assert "drawRegionToolIcon(WorldEditorIconRegistry.Key.MODE_REGION_CUT" in ui
assert "drawRegionToolIcon(WorldEditorIconRegistry.Key.MODE_REGION_PASTE" in ui
assert "mode==Mode.REGION&&dockHit(rx,ry,1,0)" in ui
assert "mode==Mode.REGION&&dockHit(rx,ry,1,1)" in ui
assert "mode==Mode.REGION&&dockHit(rx,ry,1,2)" in ui
assert "drawRegionModeIcon" not in ui
assert "drawContextActionIcon(WorldEditorIconRegistry.Key.MODE_REGION_COPY" not in ui
assert "drawContextActionIcon(WorldEditorIconRegistry.Key.MODE_REGION_PASTE" not in ui
assert "addRegionMarker" in ui and "closeRegionSelection" in ui
assert "removeLastRegionMarker" in ui and "cancelRegionSelection" in ui
assert "advanceRegionSelectionState" in ui and '"Start":"Stop"' in ui
assert "requestRegionCopy" in ui and 'mc.sendCommandString("copyregion")' in ui
assert "drawWorldEditorRegionSelectionPreview" in client
assert "drawWorldEditorRegionMarker" in client
assert "WORLD_EDITOR_ADD_REGION_MARKER" in client
assert '"world-builder-region-copy-request"' in bridge
assert "StandardOpenOption.CREATE_NEW" in bridge
assert 'command.equalsIgnoreCase("copyregion")' in commands
assert 'command.equalsIgnoreCase("cutregion")' in commands
assert server.index("editor.saveAdaptivePackage(player)") < server.index("Files.move(pending, request")
assert "ownsActiveSession(player)" in server
assert '"world-builder-region-copy-response"' in server
assert "wait for the separate completed or refused result before changing tools" in server
assert "RegionTool { COPY, CUT, PASTE }" in ui
assert "requestRegionCut" in ui and "requestCutPreview" in ui
assert "requestCutApply" in ui and 'mc.sendCommandString("cutregion")' in ui
assert 'mc.sendCommandString("activateregioncut "+result.requestId)' in ui
assert 'command.equalsIgnoreCase("activateregioncut")' in commands
assert '"cut-preview".equals(operation)' in server
assert '"cut-apply".equals(operation)' in server
assert "adoptPublishedAdaptivePackage" in server
assert "setRegionPasteDestination" in ui and "requestRegionPasteApply" in ui
assert "regionPasteOverwritePrompted" in ui and "regionPasteOverwriteArmed" in ui
assert 'return "Overwrite?"' in ui and 'return "Confirm"' in ui
assert '"There is nothing copied to clipboard"' in ui
assert "regionLibraryPreferredSnapshotId=regionClipboardSnapshotId" in ui
assert "selected.isEmpty()&&regionLibrary.size()==1" in ui
assert "selectRegionLibrarySnapshot(result.activeSnapshotId)" in ui
assert "snapshot library has multiple entries but no active clipboard selection" in ui
assert "Paste selected. There is nothing copied to clipboard" not in ui
assert "rememberCapturedRegionSnapshot(result)" in ui
assert "new WorldBuilderRegionPasteClientBridge.Snapshot(result.snapshotId,result.name,result.tileCount,result.placementCount,1)" in ui
assert 'inspectionStatus="Region Copy queued; waiting for the completed Editor result..."' in ui
assert 'inspectionStatus="Region Copy completed:' in ui
assert "mc.showWorldEditorStatus(inspectionStatus)" in ui
assert "lastRegionCopyFailure=inspectionStatus" in ui
assert "emptyRegionClipboardStatus()" in ui
assert 'lastRegionCopyFailure+" No clipboard snapshot was created."' in ui
assert "if(selectRegionLibrarySnapshot(regionClipboardSnapshotId))" in ui
assert "else requestRegionLibrary()" in ui
assert "public Snapshot(String id, String name" in paste_bridge
assert 'value.optString("activeSnapshotId", "")' in paste_bridge
assert "Region Paste active clipboard is absent from the snapshot library" in paste_bridge
assert "c!='\\uffff'&&!Character.isSurrogate(c)" in ui
assert "drawWorldEditorRegionPastePreview" in client
assert "WORLD_EDITOR_SET_REGION_PASTE_DESTINATION" in client
assert '"world-builder-region-paste-request"' in paste_bridge
assert '"OVERWRITE " : "PASTE "' in paste_bridge
assert "requestUndo" in paste_bridge and 'submit("undo"' in paste_bridge
assert 'command.equalsIgnoreCase("pasteregion")' in commands
assert 'command.equalsIgnoreCase("activateregionpaste")' in commands
assert "editor.saveAdaptivePackage(player)" in paste_server
assert '"world-builder-region-paste-response"' in paste_server
assert "wait for the separate completed or refused result" in paste_server
assert '"undo".equals(operation)' in paste_server
assert "adoptPublishedAdaptivePackage" in paste_server
assert 'inspectionStatus="Region Paste refused [' in ui
assert '"Paste preview ready:' in ui
assert 'mc.sendCommandString("activateregionpaste "+result.requestId)' in ui
assert "restartWorldBuilderAfterRegionPaste" not in client
assert "activateregionpaste" in ui
assert "sameCenterTerrainContentRefresh" in packet_handler
assert "clearWorldEditorTerrainPatchesForAuthoritativeReload" in client
assert "worldEditorTerrainPatches.clear()" in (ROOT / "Client_Base/src/orsc/graphics/three/World.java").read_text(encoding="utf-8")
assert packet_handler.index("mc.clearWorldEditorTerrainPatchesForAuthoritativeReload()") < packet_handler.index(
    "mc.reloadWorldEditorTerrain()"
)
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
assert '"Import .wbr"' in ui and '"Export"' in ui
assert "requestRegionImport" in ui and "requestRegionExport" in ui
assert "pollRegionBundleDialog" in ui
assert 'mc.sendCommandString("shareregion")' in ui
assert 'command.equalsIgnoreCase("shareregion")' in commands
assert '"world-builder-region-bundle-request"' in bundle_server
assert "ownsActiveSession(player)" in bundle_server
assert "Files.move(pending, request" in bundle_server
assert "saveAdaptivePackage" not in bundle_server

print("PASS: ordered Region Copy/Cut, exact Paste, and portable sharing UI bridges validated")
