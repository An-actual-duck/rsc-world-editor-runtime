package com.openrsc.server.net.rsc.parsers.impl;

/** Exact length rules for the private World Builder protocol envelope. */
public final class WorldEditorPacketFraming {
	private static final int[] FIXED_LENGTHS = {13, 15, 19, 22, 29};
	private static final int MAX_TERRAIN_TILES = 64;

	private WorldEditorPacketFraming() {}

	public static boolean acceptsEnvelopeLength(int length) {
		for (int accepted : FIXED_LENGTHS) {
			if (length == accepted) return true;
		}
		return length >= 30 && length <= 286 && (length - 26) % 4 == 0;
	}

	public static boolean acceptsTerrainStroke(int subtype, int length, int count) {
		if (count < 1 || count > MAX_TERRAIN_TILES) return false;
		if (subtype == 6) return length == 26 + count * 4;
		if (subtype == 7) return length == 30 + count * 4;
		return false;
	}

	public static boolean acceptsTerrainLine(int subtype,int length,int brushSize) {
		return subtype==8&&length==38&&(brushSize==1||brushSize==3||brushSize==5||brushSize==7);
	}
}
