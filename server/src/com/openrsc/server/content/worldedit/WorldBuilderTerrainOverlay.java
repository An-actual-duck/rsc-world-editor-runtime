package com.openrsc.server.content.worldedit;

/** Product-defined terrain overlay values that do not consume TileDef IDs. */
public final class WorldBuilderTerrainOverlay {
	/** Uses the tile's ground colour while contributing full terrain collision. */
	public static final int BLOCKING_BASE_COLOR = 255;

	private WorldBuilderTerrainOverlay() {
	}

	public static boolean isBlockingBaseColor(int rawOverlay) {
		return rawOverlay == BLOCKING_BASE_COLOR;
	}
}
