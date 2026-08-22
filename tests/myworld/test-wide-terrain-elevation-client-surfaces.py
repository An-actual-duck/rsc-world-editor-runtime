#!/usr/bin/env python3
"""Guards live wide-elevation scenery and editor mouse projection."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORLD = ROOT / "Client_Base/src/orsc/graphics/three/World.java"
CLIENT = ROOT / "Client_Base/src/orsc/mudclient.java"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> None:
    world = WORLD.read_text(encoding="utf-8")
    client = CLIENT.read_text(encoding="utf-8")

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

    print("PASS: wide terrain scenery and editor input use the live surface")


if __name__ == "__main__":
    main()
