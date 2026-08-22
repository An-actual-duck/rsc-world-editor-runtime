#!/usr/bin/env python3
"""Guards nearest-visible terrain priority for movement and authoring picks."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCENE = ROOT / "Client_Base/src/orsc/graphics/three/Scene.java"
CLIENT = ROOT / "Client_Base/src/orsc/mudclient.java"


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def main() -> None:
    scene = SCENE.read_text(encoding="utf-8")
    client = CLIENT.read_text(encoding="utf-8")
    start = scene.index("public int[] projectScreenToTerrainTile(")
    end = scene.index("private int[] projectScreenToTerrainTileIterative(", start)
    projection = scene[start:end]

    iterative = projection.index(
        "int[] fixedPointHit = projectScreenToTerrainTileIterative("
    )
    horizontal = projection.index("double horizontalLength =", iterative)
    march = projection.index("for (double t = 0.0D; t <= maxT; t += stepT)")
    foreground_hit = projection.index("this.terrainProjectionResult = 5;", march)
    iterative_fallback = projection.index("if (fixedPointHit != null) {", march)

    require(
        iterative < march < foreground_hit < iterative_fallback,
        "terrain projection must march near-to-far before accepting the iterative fallback",
    )
    require(
        "this.terrainProjectionIterativeT + stepT" in projection
        and "maxT = Math.min(" in projection,
        "the fast iterative candidate must bound, not bypass, foreground scanning",
    )
    require(
        "return fixedPointHit;" not in projection[iterative:horizontal],
        "a non-vertical iterative hit can still bypass foreground terrain",
    )
    require(
        "break;" in projection[march:iterative_fallback],
        "leaving the resident field must preserve a validated bounded fallback",
    )
    require(
        "scene.projectScreenToTerrainTile(" in client
        and "int[] local=projectScreenToCurrentTerrainTile();" in client,
        "movement, placement, and drag authoring must share the corrected picker",
    )

    print("PASS: terrain picking prioritizes the nearest visible valid surface")


if __name__ == "__main__":
    main()
