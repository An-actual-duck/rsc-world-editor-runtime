#!/usr/bin/env python3
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class WorldEditorSceneryMoveTests(unittest.TestCase):
    def test_client_exposes_select_preview_commit_and_cancel(self):
        ui = (ROOT / "Client_Base/src/com/openrsc/interfaces/misc/WorldEditorInterface.java").read_text()
        client = (ROOT / "Client_Base/src/orsc/mudclient.java").read_text()
        actions = (ROOT / "Client_Base/src/orsc/enumerations/MenuItemAction.java").read_text()

        self.assertIn("enum SceneryTool { PLACE, MOVE, ROTATE, REMOVE }", ui)
        self.assertIn("selectSceneryMoveSource", ui)
        self.assertIn("sceneryMovePreviewTiles", ui)
        self.assertIn("updateSceneryMovePointer", ui)
        self.assertIn("Scenery move cancelled; the source was not changed.", ui)
        self.assertIn("moveobject ", ui)
        self.assertIn("WORLD_EDITOR_SELECT_SCENERY_MOVE(100)", actions)
        self.assertIn("WORLD_EDITOR_MOVE_SCENERY(100)", actions)
        self.assertIn("drawWorldEditorSceneryMovePreview", client)
        self.assertIn("drawWorldEditorSceneryGhostEdge", client)
        self.assertIn("isSceneryMoveArmed()", client)

    def test_server_uses_one_exact_cross_location_transaction(self):
        sessions = (ROOT / "server/src/com/openrsc/server/content/worldedit/WorldEditorSessionManager.java").read_text()
        world = (ROOT / "server/src/com/openrsc/server/model/world/World.java").read_text()
        regions = (ROOT / "server/src/com/openrsc/server/model/world/region/RegionManager.java").read_text()
        spatial = (ROOT / "server/src/com/openrsc/server/model/world/region/LayeredSpatialEntityIndex.java").read_text()
        commands = (ROOT / "server/plugins/com/openrsc/server/plugins/authentic/commands/Development.java").read_text()

        move_start = sessions.index("public synchronized GameObject moveNativeScenery(")
        move_end = sessions.index("public synchronized Npc placeNativeNpc(", move_start)
        move = sessions[move_start:move_end]
        self.assertIn("moveNativeLayeredGameObject(source, moved)", move)
        self.assertNotIn("unregisterGameObject", move)
        self.assertNotIn("registerGameObject", move)
        self.assertIn("recordNativeScenery(sourceKey, null)", move)
        self.assertIn("recordNativeScenery(destinationKey, movedState)", move)
        self.assertLess(
            move.index("moveNativeLayeredGameObject(source, moved)"),
            move.index("recordNativeScenery(sourceKey, null)"),
        )
        self.assertIn("applyNativeLayeredGameObjectMoveTransaction", world)
        self.assertIn("requireNativeLayeredSceneryMoveDestination", regions)
        self.assertIn("Scenery move destination overlaps another scenery footprint.", regions)
        self.assertIn("checkedOld, checkedMoved, oldIdentity.getLocation()", regions)
        self.assertIn("final WorldLocation targetLocation", spatial)
        self.assertIn('command.equalsIgnoreCase("moveobject")', commands)
        self.assertIn("Layered scenery move refused:", commands)


if __name__ == "__main__":
    unittest.main()
