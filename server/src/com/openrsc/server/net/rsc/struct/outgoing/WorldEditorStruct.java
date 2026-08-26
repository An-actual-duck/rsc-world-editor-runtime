package com.openrsc.server.net.rsc.struct.outgoing;
import com.openrsc.server.net.rsc.enums.OpcodeOut;
import com.openrsc.server.net.rsc.struct.AbstractStruct;
import java.util.ArrayList;
import java.util.List;
public final class WorldEditorStruct extends AbstractStruct<OpcodeOut> {
	public int type, protocolVersion=2, sequence, x, y, plane, sectorX, sectorY, localX, localY;
	public int elevation, groundTexture, groundOverlay, roofTexture, horizontalWall, verticalWall, diagonal;
	public int traversalMask, fieldMask; public boolean projectileAllowed, copy;
	public int operationTotal, operationOffset;
	public long sessionId; public String message="";
	public final List<TerrainTile> terrainTiles = new ArrayList<TerrainTile>();
	public static final class TerrainTile {
		public int x,y,plane,sectorX,sectorY,localX,localY,elevation,groundTexture,groundOverlay;
		public int roofTexture,horizontalWall,verticalWall,diagonal,traversalMask;
		public boolean projectileAllowed;
	}
}
