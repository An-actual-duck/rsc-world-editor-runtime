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

    def test_client_filters_every_adaptive_origin_by_authoring_catalog(self) -> None:
        profile = PROFILE.read_text(encoding="utf-8")
        editor = EDITOR.read_text(encoding="utf-8")
        self.assertIn("hasAuthoringDefinitionBinding()", profile)
        self.assertIn('projectDefinitionIds("scenery")', editor)
        self.assertIn('projectDefinitionIds("npc")', editor)
        self.assertIn('projectDefinitionIds("item")', editor)
        self.assertIn('acceptWallInput(int raw)', editor)
        self.assertIn('steppedWallValue(', editor)

        session = SESSION.read_text(encoding="utf-8")
        self.assertIn("AdaptiveWorldBuilderAuthoringDefinitions.load(", session)
        self.assertIn("authorable.requireComposition(definitions)", session)
        self.assertNotIn("ORIGIN_EMPTY", session)

    def test_compiled_runtime_session_separates_resident_and_authorable_ids(self) -> None:
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
        AdaptiveWorldBuilderRuntimeSession bound = session("target-layered", false);
        allow(bound, "boundary", 1); allow(bound, "boundary", 10);
        allow(bound, "scenery", 0); allow(bound, "scenery", 104);
        allow(bound, "npc", 2); allow(bound, "npc", 30);
        allow(bound, "item", 10); allow(bound, "item", 20);
        refuse(bound, "boundary", 0); refuse(bound, "boundary", 11);
        refuse(bound, "scenery", 1); refuse(bound, "npc", 1);
        refuse(bound, "item", 1); refuse(bound, "item", 100);

        AdaptiveWorldBuilderRuntimeSession fullStandalone =
            session("standalone-empty", false);
        allow(fullStandalone, "boundary", 10);
        allow(fullStandalone, "scenery", 104);
        allow(fullStandalone, "npc", 30);
        allow(fullStandalone, "item", 20);

        AdaptiveWorldBuilderRuntimeSession narrowStandalone =
            session("standalone-empty", true);
        refuse(narrowStandalone, "boundary", 1);
        refuse(narrowStandalone, "scenery", 0);
        refuse(narrowStandalone, "npc", 2);
        refuse(narrowStandalone, "item", 10);
    }

    private static AdaptiveWorldBuilderRuntimeSession session(
            String origin, boolean empty)
            throws Exception {
        Map<String, String> fields = new HashMap<String, String>();
		fields.put("projectOrigin", origin);
        fields.put("requiredBoundaryIds", "1,10");
        fields.put("requiredSceneryIds", "0,104");
        fields.put("requiredNpcIds", "2");
        fields.put("requiredItemIds", "10");
        fields.put("requiredTileIds", "3");
		fields.put("authorableBoundaryIds", empty ? "" : "1,10");
		fields.put("authorableSceneryIds", empty ? "" : "0,104");
		fields.put("authorableNpcIds", empty ? "" : "2,30");
		fields.put("authorableItemIds", empty ? "" : "10,20");
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

    def test_compiled_parser_accepts_real_eight_key_catalog_and_rejects_metadata_drift(self) -> None:
        self.assertTrue(CORE.is_file(), "build the server before running catalog coverage")
        fixture = r'''
import com.openrsc.server.content.worldedit.AdaptiveWorldBuilderAuthoringDefinitions;
import java.io.IOException;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import org.json.JSONObject;

public final class AuthoringDefinitionCatalogSchemaFixture {
    private static final String DOCUMENT =
        "{\n"
        + "  \"schemaVersion\": 1,\n"
        + "  \"manifestType\": \"world-builder-definition-catalog\",\n"
        + "  \"catalogId\": \"fixture-catalog-v1\",\n"
        + "  \"tiles\": [0, 7],\n"
        + "  \"boundaries\": [1, 10],\n"
        + "  \"scenery\": [0, 104],\n"
        + "  \"npcs\": [30, 31],\n"
        + "  \"groundItems\": [10, 20]\n"
        + "}\n";

    public static void main(String[] args) throws Exception {
        Method validate = AdaptiveWorldBuilderAuthoringDefinitions.class
            .getDeclaredMethod("requireExactSchema", JSONObject.class, String.class);
        validate.setAccessible(true);
        JSONObject actual = new JSONObject(DOCUMENT);
        validate.invoke(null, actual, "fixture-catalog-v1");

        reject(validate, changed(actual, "manifestType", "wrong-type"),
            "fixture-catalog-v1");
        reject(validate, removed(actual, "manifestType"), "fixture-catalog-v1");
        reject(validate, changed(actual, "catalogId", "wrong-catalog"),
            "fixture-catalog-v1");
        reject(validate, removed(actual, "catalogId"), "fixture-catalog-v1");
        reject(validate, changed(actual, "extraMetadata", "not-allowed"),
            "fixture-catalog-v1");
        reject(validate, actual, "different-configured-catalog");
    }

    private static JSONObject changed(JSONObject source, String key, Object value) {
        JSONObject result = new JSONObject(source.toString());
        result.put(key, value);
        return result;
    }

    private static JSONObject removed(JSONObject source, String key) {
        JSONObject result = new JSONObject(source.toString());
        result.remove(key);
        return result;
    }

    private static void reject(
            Method validate, JSONObject value, String expectedCatalogId)
            throws Exception {
        try {
            validate.invoke(null, value, expectedCatalogId);
            throw new AssertionError("invalid catalog metadata was accepted");
        } catch (InvocationTargetException expected) {
            if (!(expected.getCause() instanceof IOException)) throw expected;
        }
    }
}
'''
        with tempfile.TemporaryDirectory(prefix="authoring-catalog-schema-") as temporary:
            directory = Path(temporary)
            source = directory / "AuthoringDefinitionCatalogSchemaFixture.java"
            source.write_text(fixture, encoding="utf-8")
            compiled = subprocess.run(
                ["javac", "-source", "8", "-target", "8", "-cp", str(CORE),
                 "-d", str(directory), str(source)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(0, compiled.returncode, compiled.stdout + compiled.stderr)
            executed = subprocess.run(
                ["java", "-cp", f"{directory}:{CORE}",
                 "AuthoringDefinitionCatalogSchemaFixture"],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(0, executed.returncode, executed.stdout + executed.stderr)


if __name__ == "__main__":
    unittest.main()
