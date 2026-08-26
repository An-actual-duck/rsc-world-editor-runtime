package com.openrsc.interfaces.misc;

import java.util.ArrayList;
import java.util.List;

/** Runtime preview geometry matching the Editor's authoritative integer polygon contract. */
public final class WorldEditorRegionSelection {
	private WorldEditorRegionSelection() {
	}

	public static int[][] ownedTiles(int[][] markers, int maximumTiles) {
		Geometry geometry = Geometry.create(markers);
		List<int[]> result = new ArrayList<int[]>();
		for (long x = geometry.minimumX; x <= (long)geometry.maximumX; x++) {
			for (long y = geometry.minimumY; y <= (long)geometry.maximumY; y++) {
				if (!geometry.owns((int)x, (int)y)) continue;
				if (result.size() >= maximumTiles) {
					throw new IllegalArgumentException("Selection owns too many preview tiles.");
				}
				result.add(new int[] {(int)x, (int)y});
			}
		}
		if (result.isEmpty()) {
			throw new IllegalArgumentException("Selection owns no tile centers.");
		}
		return result.toArray(new int[result.size()][2]);
	}

	public static void validateClosed(int[][] markers) {
		Geometry.create(markers);
	}

	private static final class Geometry {
		final Point[] points;
		final int minimumX, maximumX, minimumY, maximumY;

		private Geometry(Point[] points, int minimumX, int maximumX,
			int minimumY, int maximumY) {
			this.points = points;
			this.minimumX = minimumX;
			this.maximumX = maximumX;
			this.minimumY = minimumY;
			this.maximumY = maximumY;
		}

		static Geometry create(int[][] markers) {
			if (markers == null || markers.length < 3 || markers.length > 256) {
				throw new IllegalArgumentException("Selection requires 3..256 markers.");
			}
			Point[] points = new Point[markers.length];
			int minX = Integer.MAX_VALUE, maxX = Integer.MIN_VALUE;
			int minY = Integer.MAX_VALUE, maxY = Integer.MIN_VALUE;
			for (int index = 0; index < markers.length; index++) {
				if (markers[index] == null || markers[index].length != 2) {
					throw new IllegalArgumentException("Selection marker is invalid.");
				}
				Point point = new Point(markers[index][0], markers[index][1]);
				for (int prior = 0; prior < index; prior++) {
					if (points[prior].x == point.x && points[prior].y == point.y) {
						throw new IllegalArgumentException("Selection marker coordinate is repeated.");
					}
				}
				points[index] = point;
				minX = Math.min(minX, point.x); maxX = Math.max(maxX, point.x);
				minY = Math.min(minY, point.y); maxY = Math.max(maxY, point.y);
			}
			if ((long)maxX - minX > 4096L || (long)maxY - minY > 4096L) {
				throw new IllegalArgumentException("Selection exceeds 4,096 tiles per axis.");
			}
			long area = 0L;
			for (int index = 0; index < points.length; index++) {
				Point a = points[index], b = points[(index + 1) % points.length];
				area += ((long)a.x - minX) * ((long)b.y - minY)
					- ((long)b.x - minX) * ((long)a.y - minY);
			}
			if (area == 0L) throw new IllegalArgumentException("Selection is degenerate.");
			for (int first = 0; first < points.length; first++) {
				int firstNext = (first + 1) % points.length;
				for (int second = first + 1; second < points.length; second++) {
					int secondNext = (second + 1) % points.length;
					if (first == second || firstNext == second || secondNext == first) continue;
					if (segmentsIntersect(points[first], points[firstNext],
						points[second], points[secondNext])) {
						throw new IllegalArgumentException("Selection self-intersects.");
					}
				}
			}
			return new Geometry(points, minX, maxX, minY, maxY);
		}

		boolean owns(int x, int y) {
			long px = 2L * x + 1L, py = 2L * y + 1L;
			boolean inside = false;
			for (int index = 0, previous = points.length - 1;
				index < points.length; previous = index++) {
				long ax = 2L * points[previous].x + 1L;
				long ay = 2L * points[previous].y + 1L;
				long bx = 2L * points[index].x + 1L;
				long by = 2L * points[index].y + 1L;
				if (onSegment(ax, ay, bx, by, px, py)) return true;
				if ((ay > py) != (by > py)) {
					long left = (px - ax) * (by - ay);
					long right = (bx - ax) * (py - ay);
					if (by > ay ? left < right : left > right) inside = !inside;
				}
			}
			return inside;
		}

		private static boolean segmentsIntersect(Point a, Point b, Point c, Point d) {
			long o1 = orient(a, b, c), o2 = orient(a, b, d);
			long o3 = orient(c, d, a), o4 = orient(c, d, b);
			if (o1 == 0 && between(a, b, c) || o2 == 0 && between(a, b, d)
				|| o3 == 0 && between(c, d, a) || o4 == 0 && between(c, d, b)) return true;
			return (o1 < 0) != (o2 < 0) && (o3 < 0) != (o4 < 0);
		}

		private static long orient(Point a, Point b, Point c) {
			return ((long)b.x - a.x) * ((long)c.y - a.y)
				- ((long)b.y - a.y) * ((long)c.x - a.x);
		}

		private static boolean between(Point a, Point b, Point p) {
			return p.x >= Math.min(a.x, b.x) && p.x <= Math.max(a.x, b.x)
				&& p.y >= Math.min(a.y, b.y) && p.y <= Math.max(a.y, b.y);
		}

		private static boolean onSegment(long ax, long ay, long bx, long by,
			long px, long py) {
			return (bx - ax) * (py - ay) == (by - ay) * (px - ax)
				&& px >= Math.min(ax, bx) && px <= Math.max(ax, bx)
				&& py >= Math.min(ay, by) && py <= Math.max(ay, by);
		}
	}

	private static final class Point {
		final int x, y;
		Point(int x, int y) { this.x = x; this.y = y; }
	}
}
