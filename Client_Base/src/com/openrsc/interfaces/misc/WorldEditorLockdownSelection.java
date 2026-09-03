package com.openrsc.interfaces.misc;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Deterministic Lockdown geometry: individual tiles, a point, a line, or a polygon. */
public final class WorldEditorLockdownSelection {
	private WorldEditorLockdownSelection() {}

	public static int[][] tiles(int mode, int[][] points, int maximumTiles) {
		if (points == null || points.length < 1 || points.length > 256) {
			throw new IllegalArgumentException("Lockdown requires 1..256 selections.");
		}
		if (mode == 0) return unique(points, maximumTiles);
		if (mode != 1) throw new IllegalArgumentException("Lockdown selection mode is invalid.");
		if (points.length == 1) return unique(points, maximumTiles);
		if (points.length == 2) return line(points[0], points[1], maximumTiles);
		return WorldEditorRegionSelection.ownedTiles(points, maximumTiles);
	}

	private static int[][] unique(int[][] points, int maximumTiles) {
		Map<Long,int[]> result = new LinkedHashMap<Long,int[]>();
		for (int[] point : points) {
			validate(point);
			long key = ((long)point[0] << 32) ^ (point[1] & 0xffffffffL);
			if (!result.containsKey(key)) result.put(key, new int[]{point[0],point[1]});
			if (result.size() > maximumTiles) throw new IllegalArgumentException("Lockdown protects too many tiles.");
		}
		return result.values().toArray(new int[result.size()][2]);
	}

	private static int[][] line(int[] first, int[] second, int maximumTiles) {
		validate(first);validate(second);
		List<int[]> result = new ArrayList<int[]>();
		int x=first[0],y=first[1],targetX=second[0],targetY=second[1];
		int dx=Math.abs(targetX-x),stepX=x<targetX?1:-1;
		int dy=-Math.abs(targetY-y),stepY=y<targetY?1:-1,error=dx+dy;
		while(true){
			if(result.size()>=maximumTiles)throw new IllegalArgumentException("Lockdown line protects too many tiles.");
			result.add(new int[]{x,y});if(x==targetX&&y==targetY)break;
			int doubled=error*2;if(doubled>=dy){error+=dy;x+=stepX;}if(doubled<=dx){error+=dx;y+=stepY;}
		}
		return result.toArray(new int[result.size()][2]);
	}

	private static void validate(int[] point) {
		if(point==null||point.length!=2||point[0]<0||point[0]>32767||point[1]<0||point[1]>32767)
			throw new IllegalArgumentException("Lockdown selection contains an invalid tile.");
	}
}
