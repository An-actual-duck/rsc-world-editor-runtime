package com.openrsc.server.net.rsc.struct.incoming;
import com.openrsc.server.net.rsc.enums.OpcodeIn;
import com.openrsc.server.net.rsc.struct.AbstractStruct;
public final class WorldEditorRequestStruct extends AbstractStruct<OpcodeIn> {
	public int type, sequence, x, y, plane, entityId, direction, objectType;
	public int fieldMask, elevation, groundTexture, groundOverlay;
	/** 0 absolute, 1 raise, 2 lower; elevationStep is used by relative operations. */
	public int elevationOperation, elevationStep;
	public int roofTexture, horizontalWall, verticalWall, diagonal;
	public int[][] terrainTiles;
	public long sessionId;
}
