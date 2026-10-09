#!/usr/bin/env python3
"""Replay production sender/ACK bodies and serializer against the real decoder.

The facade substitutes transport, Player attributes and immutable sector input,
not queue/ACK control flow, wire layout, residency or decoding. Compiling the
real generator through the server source path also compiles GameStateUpdater.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def method(source, signature):
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 1
    closing = opening + 1
    while depth:
        depth += (source[closing] == "{") - (source[closing] == "}")
        closing += 1
    return source[start:closing]


class StageContextSequencingTest(unittest.TestCase):
    def test_real_sender_wire_decoder_and_delayed_ack_replay(self):
        updater = (ROOT / "server/src/com/openrsc/server/GameStateUpdater.java").read_text()
        constants = updater[updater.index("private static final String NATIVE_TERRAIN_STAGE_SEQUENCE_ATTRIBUTE"):
                            updater.index("private static final long WORLD_TIME_SYNC_INTERVAL_MILLIS")]
        signatures = [
            "public void acceptLayeredTerrainStageReady(",
            "private boolean canActivateNativeTerrainStage(",
            "private void maybeSendNativeTerrainStage(",
            "private void sendNativeTerrainPredictedSymmetricStage(",
            "private void maybeSendNativeTerrainSymmetricResidency(",
            "private static void clearNativeTerrainStage(",
        ]
        template = (ROOT / "tests/myworld/fixtures/orsc/NativeTerrainStageContextReplay.java").read_text()
        facade = template.replace("/* PRODUCTION_METHODS */", constants + "\n" + "\n".join(
            method(updater, signature) for signature in signatures))
        with tempfile.TemporaryDirectory(prefix="stage-context-replay-") as temporary:
            work = Path(temporary)
            harness = work / "NativeTerrainStageContextReplay.java"
            harness.write_text(facade)
            client = ["NativeLayeredTerrainChunk", "NativeLayeredTerrainSnapshot",
                      "NativeLayeredTerrainResidentCache", "NativeLayeredTerrainPacketDecoder",
                      "LayeredSceneContextState"]
            java_home = os.environ.get("JAVA_HOME")
            javac = str(Path(java_home) / "bin/javac") if java_home else "javac"
            java = str(Path(java_home) / "bin/java") if java_home else "java"
            subprocess.run([javac, "-source", "8", "-target", "8", "-encoding", "UTF-8",
                            "-cp", str(ROOT / "server/lib/*"),
                            "-sourcepath", str(ROOT / "server/src"), "-d", str(work),
                            str(harness),
                            str(ROOT / "Client_Base/src/com/openrsc/client/model/Tile.java"),
                            str(ROOT / "tests/myworld/fixtures/orsc/WorldBuilderClientProfile.java"),
                            *[str(ROOT / f"Client_Base/src/orsc/{name}.java") for name in client]],
                           check=True, cwd=ROOT)
            self.assertTrue((work / "com/openrsc/server/GameStateUpdater.class").is_file(),
                            "The changed production updater must compile, not only the facade")
            for encoding in ("legacy", "wide"):
                with self.subTest(encoding=encoding):
                    subprocess.run([java, "-cp", os.pathsep.join([str(work), str(ROOT / "server/lib/*")]),
                                    "orsc.NativeTerrainStageContextReplay", encoding], check=True, cwd=ROOT)


if __name__ == "__main__":
    unittest.main()
