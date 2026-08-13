#!/usr/bin/env python3
"""Exact authenticated definition boundaries for Builder placement paths."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "server/core.jar"
SESSION = ROOT / "server/src/com/openrsc/server/content/worldedit/AdaptiveWorldBuilderRuntimeSession.java"
PLAYER_SESSION = ROOT / "server/src/com/openrsc/server/content/worldedit/WorldBuilderPlayerSession.java"
MANAGER = ROOT / "server/src/com/openrsc/server/content/worldedit/WorldEditorSessionManager.java"
HANDLER = ROOT / "server/src/com/openrsc/server/net/rsc/handlers/WorldEditorHandler.java"
PROFILE = ROOT / "Client_Base/src/orsc/WorldBuilderClientProfile.java"
EDITOR = ROOT / "Client_Base/src/com/openrsc/interfaces/misc/WorldEditorInterface.java"


class ProjectBoundPlacementDefinitionsTest(unittest.TestCase):
    def test_every_server_mutation_path_uses_authenticated_exact_binding(self) -> None:
        player_session = PLAYER_SESSION.read_text(encoding="utf-8")
        manager = MANAGER.read_text(encoding="utf-8")
        handler = HANDLER.read_text(encoding="utf-8")

        self.assertIn("BINDING_COMPLETE_ATTRIBUTE", player_session)
        self.assertIn("requireProjectDefinition(", player_session)
        self.assertIn("session.requireDefinition(family, id)", player_session)
        self.assertEqual(6, manager.count("requireClientPlacementDefinition("))
        self.assertIn("requireClientBoundaryPlacementDefinitions(", manager)
        self.assertIn("player.getClientLimitations().maxBoundaryId", manager)
        self.assertIn(
            'WorldBuilderPlayerSession.requireProjectDefinition(p,"boundary",raw-1)',
            handler,
        )

        scenery = manager.index("public synchronized GameObject placeNativeScenery(")
        scenery_check = manager.index("requireClientPlacementDefinition(", scenery)
        scenery_mutation = manager.index("placeNativeSceneryAt(", scenery_check)
        self.assertLess(scenery_check, scenery_mutation)

        npc = manager.index("public synchronized Npc placeNativeNpc(")
        npc_check = manager.index("requireClientPlacementDefinition(", npc)
        npc_mutation = manager.index("player.getWorld().registerNpc(npc)", npc_check)
        self.assertLess(npc_check, npc_mutation)

        item = manager.index("public synchronized GroundItem placeNativeGroundItem(")
        item_check = manager.index("requireClientPlacementDefinition(", item)
        item_mutation = manager.index("registerNativeLayeredGroundItem(placement)", item_check)
        self.assertLess(item_check, item_mutation)

        terrain = manager.index("public synchronized NativeTerrainStrokeResult paintNativeTerrainStroke(")
        boundary_check = manager.index("requireClientBoundaryPlacementDefinitions(", terrain)
        boundary_mutation = manager.index("nativeTerrainOverlay.put(key, painted)", boundary_check)
        self.assertLess(boundary_check, boundary_mutation)

    def test_client_filters_only_project_bound_sessions(self) -> None:
        profile = PROFILE.read_text(encoding="utf-8")
        editor = EDITOR.read_text(encoding="utf-8")
        self.assertIn("hasProjectDefinitionRestrictions()", profile)
        self.assertIn('projectDefinitionIds("scenery")', editor)
        self.assertIn('projectDefinitionIds("npc")', editor)
        self.assertIn('projectDefinitionIds("item")', editor)
        self.assertIn('acceptWallInput(int raw)', editor)
        self.assertIn('steppedWallValue(', editor)

    def test_compiled_runtime_session_accepts_exact_ids_and_preserves_standalone(self) -> None:
        self.assertTrue(CORE.is_file(), "build the server before running binding coverage")
        fixture = r"""
import com.openrsc.server.content.worldedit.AdaptiveWorldBuilderRuntimeSession;
import java.lang.reflect.Constructor;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashMap;
import java.util.Map;

public final class ProjectBoundDefinitionFixture {
    public static void main(String[] args) throws Exception {
        AdaptiveWorldBuilderRuntimeSession bound = session("target-layered");
        allow(bound, "boundary", 1); allow(bound, "boundary", 10);
        allow(bound, "scenery", 0); allow(bound, "scenery", 104);
        allow(bound, "npc", 2); allow(bound, "item", 10);
        refuse(bound, "boundary", 0); refuse(bound, "boundary", 11);
        refuse(bound, "scenery", 1); refuse(bound, "npc", 1);
        refuse(bound, "item", 1); refuse(bound, "item", 100);

        AdaptiveWorldBuilderRuntimeSession standalone = session("standalone-empty");
        allow(standalone, "boundary", 37); allow(standalone, "scenery", 401);
        allow(standalone, "npc", 77); allow(standalone, "item", 999);
    }

    private static AdaptiveWorldBuilderRuntimeSession session(String origin)
            throws Exception {
        Map<String, String> fields = new HashMap<String, String>();
        fields.put("projectOrigin", origin);
        fields.put("requiredBoundaryIds", "1,10");
        fields.put("requiredSceneryIds", "0,104");
        fields.put("requiredNpcIds", "2");
        fields.put("requiredItemIds", "10");
        fields.put("requiredTileIds", "3");
        Constructor<AdaptiveWorldBuilderRuntimeSession> constructor =
            AdaptiveWorldBuilderRuntimeSession.class.getDeclaredConstructor(
                String.class, Path.class, Path.class, Map.class);
        constructor.setAccessible(true);
        return constructor.newInstance(
            "token", Paths.get("binding"), Paths.get("composition"), fields);
    }

    private static void allow(
            AdaptiveWorldBuilderRuntimeSession session, String family, int id) {
        session.requireDefinition(family, id);
    }

    private static void refuse(
            AdaptiveWorldBuilderRuntimeSession session, String family, int id) {
        try {
            session.requireDefinition(family, id);
            throw new AssertionError("accepted unbound " + family + " " + id);
        } catch (IllegalArgumentException expected) {
            if (!expected.getMessage().contains("does not permit")) throw expected;
        }
    }
}
"""
        with tempfile.TemporaryDirectory(prefix="project-bound-definitions-") as temporary:
            directory = Path(temporary)
            source = directory / "ProjectBoundDefinitionFixture.java"
            source.write_text(fixture, encoding="utf-8")
            compiled = subprocess.run(
                ["javac", "-source", "8", "-target", "8", "-cp", str(CORE),
                 "-d", str(directory), str(source)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(0, compiled.returncode, compiled.stdout + compiled.stderr)
            executed = subprocess.run(
                ["java", "-cp", f"{directory}:{CORE}", "ProjectBoundDefinitionFixture"],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(0, executed.returncode, executed.stdout + executed.stderr)


if __name__ == "__main__":
    unittest.main()
