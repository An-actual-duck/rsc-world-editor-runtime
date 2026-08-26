package com.openrsc.interfaces.misc;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Deterministic tile-center interpolation for continuous editor brush drags. */
public final class WorldEditorTerrainBrush {
	private WorldEditorTerrainBrush() {}

	public static final class RectanglePlan {
		private final int[][] tiles;
		private final int[] fieldMasks;

		private RectanglePlan(int[][] tiles, int[] fieldMasks) {
			this.tiles = tiles;
			this.fieldMasks = fieldMasks;
		}

		public int[][] tiles() {
			int[][] copy = new int[tiles.length][2];
			for (int index = 0; index < tiles.length; index++) copy[index] = tiles[index].clone();
			return copy;
		}

		public int[] fieldMasks() {
			return fieldMasks.clone();
		}
	}

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

	public static int[][] rectangleFootprint(
		int startX, int startY, int endX, int endY, boolean fill, int maximumTiles) {
		return rectanglePlan(startX, startY, endX, endY, fill, 1, false, false,
			maximumTiles).tiles();
	}

	public static RectanglePlan rectanglePlan(
		int startX, int startY, int endX, int endY, boolean fill,
		int baseFieldMask, boolean smartWalls, boolean paintSmartWall,
		int maximumTiles) {
		if (maximumTiles < 1 || baseFieldMask < 0 || (baseFieldMask & ~127) != 0) {
			throw new IllegalArgumentException("Terrain rectangle capability is invalid");
		}
		if (smartWalls && (baseFieldMask & 112) != 0) {
			throw new IllegalArgumentException("Smart Walls cannot include raw wall fields");
		}
		if (!smartWalls && paintSmartWall) {
			throw new IllegalArgumentException("Smart wall placement requires Smart Walls");
		}
		if (baseFieldMask == 0 && !paintSmartWall) {
			throw new IllegalArgumentException("Terrain rectangle has no selected fields");
		}
		int minX = Math.min(startX, endX), maxX = Math.max(startX, endX);
		int minY = Math.min(startY, endY), maxY = Math.max(startY, endY);
		long width = (long) maxX - minX + 1L, height = (long) maxY - minY + 1L;
		long footprint = fill ? width * height
			: width == 1L || height == 1L ? width * height : width * 2L + height * 2L - 4L;
		long possible = footprint + (paintSmartWall ? width * 2L + height * 2L : 0L);
		if (footprint < 1L || possible > maximumTiles * 2L + 4L) {
			throw new IllegalArgumentException("Terrain rectangle exceeds the tile limit");
		}
		Map<Long, int[]> tiles = new LinkedHashMap<Long, int[]>();
		Map<Long, Integer> masks = new LinkedHashMap<Long, Integer>();
		if (baseFieldMask != 0) {
			if (fill) {
				for (int x = minX;; x++) {
					for (int y = minY;; y++) {
						addRectangleTile(tiles, masks, x, y, baseFieldMask, maximumTiles);
						if (y == maxY) break;
					}
					if (x == maxX) break;
				}
			} else {
				for (int x = minX;; x++) {
					addRectangleTile(tiles, masks, x, minY, baseFieldMask, maximumTiles);
					if (maxY != minY) addRectangleTile(tiles, masks, x, maxY, baseFieldMask, maximumTiles);
					if (x == maxX) break;
				}
				if (height > 2L) {
					for (int y = minY + 1; y < maxY; y++) {
						addRectangleTile(tiles, masks, minX, y, baseFieldMask, maximumTiles);
						if (maxX != minX) addRectangleTile(tiles, masks, maxX, y, baseFieldMask, maximumTiles);
					}
				}
			}
		}
		if (paintSmartWall) {
			int southY = Math.addExact(maxY, 1), eastX = Math.addExact(maxX, 1);
			for (int x = minX;; x++) {
				addRectangleTile(tiles, masks, x, minY, 32, maximumTiles);
				addRectangleTile(tiles, masks, x, southY, 32, maximumTiles);
				if (x == maxX) break;
			}
			for (int y = minY;; y++) {
				addRectangleTile(tiles, masks, minX, y, 16, maximumTiles);
				addRectangleTile(tiles, masks, eastX, y, 16, maximumTiles);
				if (y == maxY) break;
			}
		}
		int[][] coordinates = tiles.values().toArray(new int[tiles.size()][]);
		int[] fieldMasks = new int[coordinates.length];
		int at = 0;
		for (Integer mask : masks.values()) fieldMasks[at++] = mask.intValue();
		return new RectanglePlan(coordinates, fieldMasks);
	}

	private static void addRectangleTile(
		Map<Long, int[]> tiles, Map<Long, Integer> masks,
		int x, int y, int fieldMask, int maximumTiles) {
		long key = ((long) x << 32) ^ (y & 0xffffffffL);
		Integer previous = masks.get(key);
		if (previous != null) {
			masks.put(key, Integer.valueOf(previous.intValue() | fieldMask));
			return;
		}
		if (tiles.size() >= maximumTiles) {
			throw new IllegalArgumentException("Terrain rectangle exceeds the tile limit");
		}
		tiles.put(key, new int[]{x, y});
		masks.put(key, Integer.valueOf(fieldMask));
	}
}
