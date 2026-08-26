package com.openrsc.interfaces.misc;

/** Mutable rectangle and wall selection state shared by both editor layouts. */
public final class WorldEditorRectangleOptions {
	private boolean fill;
	private boolean smartWalls = true;
	private boolean northWall;
	private boolean eastWall;
	private boolean diagonalWall;

	public boolean isFill() { return fill; }
	public void setFill(boolean selected) { fill = selected; }

	public boolean isSmartWalls() { return smartWalls; }
	public void setSmartWalls(boolean selected) { smartWalls = selected; }
	public void toggleSmartWalls() { smartWalls = !smartWalls; }

	public boolean isNorthWall() { return northWall; }
	public void toggleNorthWall() { northWall = !northWall; }

	public boolean isEastWall() { return eastWall; }
	public void toggleEastWall() { eastWall = !eastWall; }
	public void toggleBothCardinalWalls() {
		boolean selected = !(northWall && eastWall);
		northWall = selected;
		eastWall = selected;
	}

	public boolean isDiagonalWall() { return diagonalWall; }
	public void toggleDiagonalWall() { diagonalWall = !diagonalWall; }

	public boolean isDiagonalPlacementEnabled() { return !smartWalls && diagonalWall; }
	public boolean hasSmartWallSelection() { return smartWalls && (northWall || eastWall); }

	public int rawWallMask() {
		if (smartWalls) return 0;
		return (eastWall ? 16 : 0) | (northWall ? 32 : 0) | (diagonalWall ? 64 : 0);
	}

	public int rectangleFlags() {
		return (fill ? 1 : 0) | (smartWalls ? 2 : 0)
			| (smartWalls && northWall ? 4 : 0)
			| (smartWalls && eastWall ? 8 : 0);
	}
}
