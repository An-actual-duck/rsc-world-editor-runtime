#!/usr/bin/env python3
"""Execute retained public transition consumers against the converted full baseline.

This is server/plugin integration evidence, not client login or promotion approval.
The actual Player and RegionManager execute every destination; no coordinate stub
or replacement teleport implementation participates in the fixture.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "output/current-platform/current-base-v1"
BASELINE = "tools/layered-maps/baselines/rsc-remastered-preservation-r64-v1.json"
BASELINE_COMMIT = "19d819b3649dfb8401836d649d7f218c8d347577"


def frozen_map_input(root):
    """Materialize only the twelve sealed provider-owned baseline inputs."""
    manifest_bytes = (ROOT / BASELINE).read_bytes()
    manifest = json.loads(manifest_bytes)
    for record in manifest["files"]:
        payload = (ROOT / record["path"]).read_bytes()
        if hashlib.sha256(payload).hexdigest() != record["sha256"]:
            payload = subprocess.check_output(
                ["git", "show", BASELINE_COMMIT + ":" + record["path"]], cwd=ROOT,
            )
        if len(payload) != record["size"] or hashlib.sha256(payload).hexdigest() != record["sha256"]:
            raise AssertionError("provider history does not reproduce frozen baseline: " + record["path"])
        destination = root / record["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    destination = root / BASELINE
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(manifest_bytes)

HARNESS = r"""
package com.openrsc.server;

import com.openrsc.server.io.NativeLayeredWorldRuntimeProfile;
import com.openrsc.server.model.Point;
import com.openrsc.server.model.TelePoint;
import com.openrsc.server.model.entity.GameObject;
import com.openrsc.server.model.entity.player.Player;
import com.openrsc.server.model.world.coordinate.LegacyPackedPointAdapter;
import com.openrsc.server.model.world.coordinate.WorldLocation;
import com.openrsc.server.plugins.authentic.defaults.Ladders;
import com.openrsc.server.plugins.authentic.misc.MagicGuildPortals;
import com.openrsc.server.net.rsc.handlers.GameObjectWallAction;

public final class PreservationTransitionExecution {
  private static Server server;
  private static Player player;

  public static void main(String[] args) throws Exception {
    CurrentCompositionIdentity.initializeFromSystemProperties();
    server = new Server("current-base.conf");
    server.getEntityHandler().load();
    player = new Player(server.getWorld(), 12345L);
    player.setClientVersion(server.getConfig().CLIENT_VERSION);
    player.setInitialLayeredLocation(LegacyPackedPointAdapter.fromPackedValues(120, 648));
    player.updateRegion();
    check(server.getWorld().getRegionManager().hasNativeLayeredTerrain(
      LegacyPackedPointAdapter.fromPackedValues(212, 695)), "native surface");
    check(server.getWorld().getRegionManager().hasNativeLayeredTerrain(
      LegacyPackedPointAdapter.fromPackedValues(212, 2583)), "native overlapping upper floor");

    // Frozen BoundaryLocs has ID147 at (602,2642), the Magic Guild's top floor.
    GameObject portal = object(147, 602, 2642, 0, 1);
    move(602, 2642);
    WorldLocation ambiguous = server.getWorld().getRegionManager()
      .fromRuntimeCompatibilityPoint(Point.location(212, 695), player.getLayeredLocation(), true);
    check(ambiguous.getCoordinate().getLevel() == 2,
      "fixture must reproduce the old two-int teleport ambiguity");
    new MagicGuildPortals().onOpBound(player, portal, 0);
    destination(212, 695, "Magic Guild upper-to-surface portal");
    move(602, 2642);
    new MagicGuildPortals().onOpBound(player, portal, 1);
    destination(602, 2642, "portal examine must not teleport");

    Ladders ladders = new Ladders();
    // Ordinary one-tile ladder keeps geographic position and changes signed level.
    move(120, 648);
    ladders.onObjectAction(object(5, 120, 648, 0, 0), "climb-up", player);
    destination(120, 1592, "generic ladder up");
    ladders.onObjectAction(object(6, 120, 1592, 0, 0), "climb-down", player);
    destination(120, 648, "generic ladder down");

    // Historical special stairs must match their packed source even in native mode.
    move(368, 438);
    ladders.onObjectAction(object(42, 368, 438, 0, 0), "climb-down", player);
    destination(371, 3266, "Heroes Guild basement");
    ladders.onObjectAction(object(41, 370, 3264, 0, 0), "climb-up", player);
    destination(369, 437, "Heroes Guild surface return");
    move(148, 1507);
    ladders.onObjectAction(object(6, 148, 1507, 0, 0), "climb-down", player);
    destination(148, 563, "historical upper-floor special ladder");

    // Exercise the actual Ladders data lookup path in both directions.
    move(223, 110);
    ladders.onObjectAction(object(223, 223, 110, 0, 0), "climb-down", player);
    destination(446, 3368, "explicit object edge down");
    ladders.onObjectAction(object(5, 446, 3367, 0, 0), "climb-up", player);
    destination(223, 109, "explicit object edge surface return");

    // All 18 reviewed public edges must resolve from signed source coordinates with their
    // original command and decode into package-owned destinations.
    javax.xml.parsers.DocumentBuilderFactory factory = javax.xml.parsers.DocumentBuilderFactory.newInstance();
    factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
    org.w3c.dom.NodeList edges = factory.newDocumentBuilder().parse(
      new java.io.File("conf/server/defs/extras/ObjectTelePoints.xml")).getElementsByTagName("entry");
    check(edges.getLength() == 18, "exact reviewed public edge count");
    for (int index = 0; index < edges.getLength(); index++) {
      org.w3c.dom.Element entry = (org.w3c.dom.Element)edges.item(index);
      org.w3c.dom.Element origin = (org.w3c.dom.Element)entry.getElementsByTagName("Point").item(0);
      org.w3c.dom.Element target = (org.w3c.dom.Element)entry.getElementsByTagName("TelePoint").item(0);
      int x = Integer.parseInt(origin.getElementsByTagName("x").item(0).getTextContent());
      int y = Integer.parseInt(origin.getElementsByTagName("y").item(0).getTextContent());
      String command = target.getElementsByTagName("command").item(0).getTextContent();
      TelePoint edge = server.getEntityHandler().getObjectTelePoint(
        LegacyPackedPointAdapter.fromPackedValues(x, y), command);
      check(edge != null, "explicit edge " + index + " lookup");
      move(x, y);
      player.teleportLegacyPacked(edge.getX(), edge.getY(), false);
      destination(Integer.parseInt(target.getElementsByTagName("x").item(0).getTextContent()),
        Integer.parseInt(target.getElementsByTagName("y").item(0).getTextContent()), "explicit edge " + index);
    }
    // The owner's two added transitions must not leak into the public composition.
    check(server.getEntityHandler().getObjectTelePoint(
      LegacyPackedPointAdapter.fromPackedValues(499, 469), "Go down") == null,
      "owner-only downward edge excluded from Base");
    check(server.getEntityHandler().getObjectTelePoint(
      LegacyPackedPointAdapter.fromPackedValues(498, 3296), "Go up") == null,
      "owner-only upward edge excluded from Base");
    // Individual wall edge: Melzar's maze floor1, long-distance floor1 destination.
    WorldLocation wallSource = LegacyPackedPointAdapter.fromPackedValues(414, 1107);
    TelePoint wall = server.getEntityHandler().getObjectTelePoint(wallSource, "walk through");
    check(wall != null, "explicit boundary telepoint source survives signed projection");
    move(414, 1107);
    java.lang.reflect.Method wallAction = GameObjectWallAction.class.getDeclaredMethod(
      "applyConfiguredTransition", Player.class, GameObject.class, String.class);
    wallAction.setAccessible(true);
    GameObject wallObject = object(1, 414, 1107, 0, 1);
    check((Boolean)wallAction.invoke(null, player, wallObject, "walk through"), "actual boundary default action");
    destination(700, 1395, "explicit boundary destination");
    check(!(Boolean)wallAction.invoke(null, player, wallObject, "wrong command"), "explicit edge command gate");
    destination(700, 1395, "wrong command must not move player");
    check(NativeLayeredWorldRuntimeProfile.PRESERVATION_R64_REPLACEMENT
      .replacesLegacyBasePopulation(), "complete package replaces old population");
    System.out.println("preservation-transition-execution: verified");
    System.exit(0);
  }

  private static GameObject object(int id, int x, int packedY, int direction, int type) {
    GameObject object = new GameObject(server.getWorld(), Point.location(x, packedY), id, direction, type);
    object.setInitialWorldLocation(LegacyPackedPointAdapter.fromPackedValues(x, packedY));
    return object;
  }
  private static void move(int x, int packedY) {
    player.teleportLegacyPacked(x, packedY, false);
  }
  private static void destination(int x, int packedY, String label) {
    WorldLocation expected = LegacyPackedPointAdapter.fromPackedValues(x, packedY);
    check(expected.equals(player.getLayeredLocation()), label + ": " + player.getLayeredLocation());
    check(expected.equals(player.getWorldLocation()), label + " spatial authority");
    check(server.getWorld().getRegionManager().hasNativeLayeredTerrain(expected), label + " package ownership");
    check(server.getWorld().getRegionManager().findNativeLayeredWorldPackage(expected).get()
      .getPackageId().equals(NativeLayeredWorldRuntimeProfile.PRESERVATION_PACKAGE_ID), label + " exact package");
  }
  private static void check(boolean value, String label) {
    if (!value) throw new AssertionError(label);
  }
}
"""


class PreservationTransitionExecutionTest(unittest.TestCase):
    def test_actual_player_and_plugins_use_signed_destinations_in_full_public_map(self):
        build = subprocess.run(
            ["python3", "scripts/build-current-base.py", "--test-allow-dirty"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(0, build.returncode, build.stdout + build.stderr)
        with tempfile.TemporaryDirectory(prefix="preservation-transitions-exec-") as tmp:
            root = Path(tmp)
            baseline_root = root / "frozen-input"
            frozen_map_input(baseline_root)
            tool_classes = root / "tool-classes"
            tool_classes.mkdir()
            tool_build = subprocess.run(
                ["javac", "-source", "8", "-target", "8", "-d", str(tool_classes),
                 *map(str, sorted((ROOT / "tools/layered-maps/src").rglob("*.java")))],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(0, tool_build.returncode, tool_build.stdout + tool_build.stderr)
            generated = subprocess.run(
                ["java", "-cp", str(tool_classes), "com.openrsc.layeredmaps.LayeredMapsCli",
                 "preservation-package", "--root", str(baseline_root), "--workspace", str(root / "map")],
                cwd=ROOT,
                capture_output=True, text=True,
            )
            self.assertEqual(0, generated.returncode, generated.stdout + generated.stderr)
            report = json.loads((root / "map/generation-report.json").read_text())
            self.assertEqual(1764, report["terrainSectorCount"])
            self.assertFalse(report["runtimePromotionApproved"])
            runtime = root / "runtime"
            runtime.mkdir()
            with zipfile.ZipFile(OUTPUT / "server/content.zip") as archive:
                archive.extractall(runtime)
            (runtime / "plugins.jar").write_bytes((OUTPUT / "server/plugins.jar").read_bytes())
            config = runtime / "current-base.conf"
            config.write_text(config.read_text() + "\n" + "\n".join((
                "want_layered_player_location_authority: true",
                "want_layered_spatial_runtime_authority: true",
                "want_layered_protocol_client_authority: true",
                "want_layered_native_terrain_package: true",
                "layered_native_world_runtime_profile: preservation-r64-replacement",
                "layered_native_terrain_package_path: " + str(root / "map/package"),
            )) + "\n")
            source = root / "PreservationTransitionExecution.java"
            source.write_text(HARNESS)
            classpath = os.pathsep.join((str(OUTPUT / "server/core.jar"), str(OUTPUT / "server/plugins.jar"), str(root)))
            compiled = subprocess.run(
                ["javac", "-source", "8", "-target", "8", "-cp", classpath,
                 "-d", str(root), str(source)], cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(0, compiled.returncode, compiled.stdout + compiled.stderr)
            executed = subprocess.run(
                ["java", "-Xmx1536m", "-Dopenrsc.currentCompositionIdentityFile="
                 + str(OUTPUT / "composition-identity.json"), "-cp", classpath,
                 "com.openrsc.server.PreservationTransitionExecution"],
                cwd=runtime, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(0, executed.returncode, (executed.stdout + executed.stderr)[-18000:])
            self.assertIn("preservation-transition-execution: verified", executed.stdout)


if __name__ == "__main__":
    unittest.main()
