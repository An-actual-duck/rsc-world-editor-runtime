package com.openrsc.interfaces.misc;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Deterministic tile-center interpolation for continuous editor brush drags. */
public final class WorldEditorTerrainBrush {
	private WorldEditorTerrainBrush() {}

	public static int[][] centeredFootprint(int centerX, int centerY, int size) {
		if (size < 1 || size > 7 || (size & 1) == 0) {
			throw new IllegalArgumentException("Terrain brush size must be one of 1, 3, 5, or 7");
		}
		int[][] tiles = new int[size * size][2];
		tiles[0][0] = centerX;
		tiles[0][1] = centerY;
		int radius = size / 2;
		int at = 1;
		for (int dx = -radius; dx <= radius; dx++) {
			for (int dy = -radius; dy <= radius; dy++) {
				if (dx == 0 && dy == 0) continue;
				tiles[at][0] = centerX + dx;
				tiles[at++][1] = centerY + dy;
			}
		}
		return tiles;
	}

	public static int nextSize(int size) {
		switch (size) {
			case 1: return 3;
			case 3: return 5;
			case 5: return 7;
			default: return 1;
		}
	}

	public static int[][] lineFootprint(
		int startX, int startY, int endX, int endY, int size, int maximumTiles) {
		if (maximumTiles < 1) {
			throw new IllegalArgumentException("Terrain line tile limit must be positive");
		}
		Map<Long, int[]> unique = new LinkedHashMap<Long, int[]>();
		for (int[] center : lineCenters(startX, startY, endX, endY)) {
			for (int[] tile : centeredFootprint(center[0], center[1], size)) {
				long key = ((long) tile[0] << 32) ^ (tile[1] & 0xffffffffL);
				if (unique.containsKey(key)) continue;
				if (unique.size() >= maximumTiles) {
					throw new IllegalArgumentException("Terrain line exceeds the tile limit");
				}
				unique.put(key, tile);
			}
		}
		return unique.values().toArray(new int[unique.size()][]);
	}

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
