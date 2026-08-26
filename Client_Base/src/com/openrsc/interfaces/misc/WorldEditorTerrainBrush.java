package com.openrsc.interfaces.misc;

import java.util.ArrayList;
import java.util.List;

/** Deterministic tile-center interpolation for continuous editor brush drags. */
public final class WorldEditorTerrainBrush {
	private WorldEditorTerrainBrush() {}

	public static int[][] lineCenters(int startX, int startY, int endX, int endY) {
		List<int[]> centers = new ArrayList<int[]>();
		int x = startX, y = startY;
		int dx = Math.abs(endX - startX), sx = startX < endX ? 1 : -1;
		int dy = -Math.abs(endY - startY), sy = startY < endY ? 1 : -1;
		int error = dx + dy;
		while (true) {
			centers.add(new int[]{x, y});
			if (x == endX && y == endY) break;
			int doubled = error * 2;
			if (doubled >= dy) { error += dy; x += sx; }
			if (doubled <= dx) { error += dx; y += sy; }
		}
		return centers.toArray(new int[centers.size()][]);
	}
}
