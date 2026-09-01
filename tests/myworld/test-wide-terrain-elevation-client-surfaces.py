#!/usr/bin/env python3
"""Guards live wide-elevation scenery and editor mouse projection."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORLD = ROOT / "Client_Base/src/orsc/graphics/three/World.java"
CLIENT = ROOT / "Client_Base/src/orsc/mudclient.java"
NATIVE_CHUNK = ROOT / "Client_Base/src/orsc/NativeLayeredTerrainChunk.java"
NATIVE_SNAPSHOT = ROOT / "Client_Base/src/orsc/NativeLayeredTerrainSnapshot.java"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> None:
    world = WORLD.read_text(encoding="utf-8")
    client = CLIENT.read_text(encoding="utf-8")
    native_chunk = NATIVE_CHUNK.read_text(encoding="utf-8")
    native_snapshot = NATIVE_SNAPSHOT.read_text(encoding="utf-8")

    require(
        "if (isLocalTile(localTileX, localTileZ))" in world
        and "loaded != null && loaded.isLoaded()" in world
        and ".groundElevation * 3;" in world,
        "presentation elevation must prefer the live loaded editor sector",
    )
    require(
        "this.world.getPresentationTerrainElevation(x, z);" in client
        and "model.setTranslate(x, -elevation, z);" in client,
        "scenery materialization must use the live presentation surface",
    )
    require(
        "int[] local=projectScreenToCurrentTerrainTile();" in client,
        "editor drag must intersect the actual terrain surface",
    )
    require(
        "scene.projectScreenToGroundTile(mouseX,mouseY,tileSize" not in client
        and "getClickTeleportGroundPlaneY" not in client,
        "editor input must not retain the flat ground-plane projection",
    )
    require(
        "scene.projectScreenToTerrainTile(" in client,
        "navigation and editor input must share height-aware terrain projection",
    )
    require(
        ": tileBytes[offset++] & 0xff;" in native_chunk
        and "tile.groundElevation = tileBytes[offset++];" not in native_chunk,
        "legacy native chunk elevations must remain unsigned during Tile materialization",
    )
    require(
        "tile.groundElevation = elevation;" in native_snapshot
        and "tile.groundElevation = (byte) elevation;" not in native_snapshot,
        "uniform native elevations must remain int-valued during Tile materialization",
    )

    print("PASS: wide terrain scenery and editor input use the live surface")


if __name__ == "__main__":
    main()
