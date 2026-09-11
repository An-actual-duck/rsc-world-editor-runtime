package orsc.graphics.three;

import orsc.util.FastMath;

/** Camera-only editor overlays: no geometry capture, render frame or world-state latch. */
public final class WorldEditorProjection {
	private WorldEditorProjection() { }

	public static boolean project(int x, int y, int z, int offsetX, int offsetY, int offsetZ,
		int rotationX, int rotationY, int rotationZ, int centerX, int centerY,
		int perspectiveShift, int nearPlane, int[] destination) {
		int cameraX = x - offsetX, cameraY = y - offsetY, cameraZ = z - offsetZ;
		int temporary;
		if (rotationZ != 0) {
			int sin = FastMath.trigTable1024[rotationZ], cos = FastMath.trigTable1024[rotationZ + 1024];
			temporary = cameraY * sin + cos * cameraX >> 15;
			cameraY = cameraY * cos - cameraX * sin >> 15;
			cameraX = temporary;
		}
		if (rotationY != 0) {
			int sin = FastMath.trigTable1024[rotationY], cos = FastMath.trigTable1024[rotationY + 1024];
			temporary = cos * cameraX + cameraZ * sin >> 15;
			cameraZ = cos * cameraZ - cameraX * sin >> 15;
			cameraX = temporary;
		}
		if (rotationX != 0) {
			int sin = FastMath.trigTable1024[rotationX], cos = FastMath.trigTable1024[rotationX + 1024];
			temporary = cameraY * cos - sin * cameraZ >> 15;
			cameraZ = sin * cameraY + cos * cameraZ >> 15;
			cameraY = temporary;
		}
		if (cameraZ < Math.max(1, nearPlane)) return false;
		destination[0] = centerX + (cameraX << perspectiveShift) / cameraZ;
		destination[1] = centerY + (cameraY << perspectiveShift) / cameraZ;
		return true;
	}
}
