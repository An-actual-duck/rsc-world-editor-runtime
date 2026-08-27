package com.openrsc.server.net.rsc.struct.incoming;
import com.openrsc.server.net.rsc.enums.OpcodeIn;
import com.openrsc.server.net.rsc.struct.AbstractStruct;
public final class WorldEditorRequestStruct extends AbstractStruct<OpcodeIn> {
	public int type, sequence, x, y, plane, entityId, direction, objectType;
	public int brushSize, endX, endY;
	/** Positive client operation identity; drag batches share one token. */
	public int historyToken;
	/** Rectangle flags: bit 0 fill, bit 1 Smart Walls, bit 2 place selected smart wall. */
	public int rectangleFlags, smartWall;
	public int fieldMask, elevation, groundTexture, groundOverlay;
	/** 0 absolute, 1 raise, 2 lower; elevationStep is used by relative operations. */
	public int elevationOperation, elevationStep;
	public int roofTexture, horizontalWall, verticalWall, diagonal;
	public int[][] terrainTiles;
	public long sessionId;
}
