#!/usr/bin/env python3
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TRACKER = ROOT / "Client_Base/src/com/openrsc/interfaces/misc/WorldEditorEntityEditTracker.java"
FRAMING = ROOT / "server/src/com/openrsc/server/net/rsc/parsers/impl/WorldEditorPacketFraming.java"


class WorldEditorEntityAcknowledgementTests(unittest.TestCase):
    def test_tracker_requires_matching_authoritative_sequence_and_operation(self):
        harness = textwrap.dedent(
            """
            package com.openrsc.interfaces.misc;
            import com.openrsc.server.net.rsc.parsers.impl.WorldEditorPacketFraming;
            public final class WorldEditorEntityEditTrackerHarness {
                private static void require(boolean value, String message) {
                    if (!value) throw new AssertionError(message);
                }
                public static void main(String[] args) {
                    require(WorldEditorPacketFraming.acceptsEnvelopeLength(32),
                        "entity-edit envelope was rejected before parsing");
                    require(!WorldEditorPacketFraming.acceptsEnvelopeLength(31),
                        "truncated entity-edit envelope was accepted");
                    require(!WorldEditorPacketFraming.acceptsEnvelopeLength(33),
                        "oversized entity-edit envelope was accepted");
                    WorldEditorEntityEditTracker tracker = new WorldEditorEntityEditTracker();
                    require(tracker.begin(41, 2), "remove did not begin");
                    require(tracker.isPending(), "remove was not pending for immediate Save");
                    tracker.noteSaveQueued();
                    require(!tracker.isQueuedSaveReady(), "Save submitted before remove response");
                    require(!tracker.begin(41, 1), "second mutation bypassed correlation gate");
                    require(!tracker.complete(42, 1), "wrong operation completed removal");
                    require(!tracker.complete(41, 2), "stale sequence completed removal");
                    require(tracker.complete(42, 2), "authoritative removal reply was refused");
                    require(!tracker.isPending(), "authoritative reply did not unblock Save");
                    require(tracker.isQueuedSaveReady(), "matching response did not release queued Save");
                    tracker.clearQueuedSave();
                    require(!tracker.isQueuedSaveReady(), "submitted Save remained queued");
                    System.out.println("entity-edit-correlation-ok");
                }
            }
            """
        )
        with tempfile.TemporaryDirectory(prefix="world-editor-entity-ack-") as temp:
            source = Path(temp) / "WorldEditorEntityEditTrackerHarness.java"
            source.write_text(harness, encoding="utf-8")
            subprocess.run(
                ["javac", "-d", temp, str(TRACKER), str(FRAMING), str(source)],
                check=True,
            )
            result = subprocess.run(
                ["java", "-cp", temp, "com.openrsc.interfaces.misc.WorldEditorEntityEditTrackerHarness"],
                check=True, text=True, capture_output=True,
            )
            self.assertEqual("entity-edit-correlation-ok\n", result.stdout)

    def test_all_builder_entity_edits_use_structured_protocol(self):
        ui = (ROOT / "Client_Base/src/com/openrsc/interfaces/misc/WorldEditorInterface.java").read_text()
        client = (ROOT / "Client_Base/src/orsc/mudclient.java").read_text()
        packets = (ROOT / "Client_Base/src/orsc/PacketHandler.java").read_text()
        parser = (ROOT / "server/src/com/openrsc/server/net/rsc/parsers/impl/PayloadCustomParser.java").read_text()
        handler = (ROOT / "server/src/com/openrsc/server/net/rsc/handlers/WorldEditorHandler.java").read_text()
        generator = (ROOT / "server/src/com/openrsc/server/net/rsc/generators/impl/PayloadCustomGenerator.java").read_text()
        response = (ROOT / "server/src/com/openrsc/server/net/rsc/struct/outgoing/WorldEditorStruct.java").read_text()

        for method in (
            "requestPlaceScenery", "requestRemoveScenery", "requestRotateScenery",
            "requestPlaceNpc", "requestRemoveNpc", "requestPlaceGroundItem",
            "requestRemoveGroundItem",
        ):
            self.assertIn(method, client)
        editor_actions = client.split("case WORLD_EDITOR_PLACE_SCENERY:", 1)[1].split(
            "case WORLD_EDITOR_ADD_REGION_MARKER:", 1
        )[0]
        self.assertNotIn("sendCommandString", editor_actions)
        self.assertIn("requestEntityEdit(4,0,sceneryMoveSourceX", ui)
        self.assertIn("hasPendingAuthoritativeEdits()", ui)
        self.assertIn("entityEditTracker.isPending()", ui)
        self.assertIn("entityEditTracker.noteSaveQueued()", ui)
        self.assertIn("entityEditTracker.clearQueuedSave()", ui)
        self.assertIn("maybeSubmitDeferredSave();", ui.split("acceptEntityEdit", 1)[1])
        self.assertIn("editor.type == 12 ? 32", parser)
        self.assertIn("request.type == 12", handler)
        self.assertIn("out.type=12", handler)
        self.assertIn("editor.type == 12", generator)
        self.assertIn("if(type==12)", packets)
        self.assertIn("version!=5", packets)
        self.assertIn("protocolVersion=5", response)


if __name__ == "__main__":
    unittest.main()
