package com.openrsc.server.net.rsc.parsers.impl;

/** Exact length rules for the private World Builder protocol envelope. */
public final class WorldEditorPacketFraming {
	private static final int[] FIXED_LENGTHS = {13, 15, 19, 22, 29, 32, 42, 43};
	private static final int MAX_TERRAIN_TILES = 64;

	private WorldEditorPacketFraming() {}

	public static boolean acceptsEnvelopeLength(int length) {
		for (int accepted : FIXED_LENGTHS) {
			if (length == accepted) return true;
		}
		return (length >= 34 && length <= 290 && (length - 30) % 4 == 0)
			|| (length >= 22 && length <= 1046 && (length - 22) % 4 == 0);
	}

	public static boolean acceptsLockdown(int subtype,int length,int operation,int count){
		if(subtype!=13||operation<0||operation>2||count<0||count>256)return false;
		if(operation==1&&count<1)return false;if(operation!=1&&count!=0)return false;
		return length==22+count*4;
	}

	public static boolean acceptsTerrainStroke(int subtype, int length, int count) {
		if (count < 1 || count > MAX_TERRAIN_TILES) return false;
		if (subtype == 6) return length == 30 + count * 4;
		if (subtype == 7) return length == 34 + count * 4;
		return false;
	}

	public static boolean acceptsTerrainLine(int subtype,int length,int brushSize) {
		return subtype==8&&length==42&&(brushSize==1||brushSize==3||brushSize==5||brushSize==7);
	}

	public static boolean acceptsTerrainRectangle(int subtype,int length,int flags) {
		return subtype==9&&length==43&&(flags&~15)==0&&((flags&12)==0||(flags&2)!=0);
	}
}
