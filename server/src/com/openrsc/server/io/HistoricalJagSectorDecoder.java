package com.openrsc.server.io;

import com.openrsc.server.constants.Constants;

/** Pure historical sector decoding; no world, database, configuration, or process startup. */
public final class HistoricalJagSectorDecoder {
	private HistoricalJagSectorDecoder() { }

	public static final class Result {
		private final Sector sector;
		private final byte[] tileDirections;
		private Result(Sector sector, byte[] tileDirections) {
			this.sector = sector; this.tileDirections = tileDirections;
		}
		public Sector sector() { return sector; }
		/** Historical WorldLoader deliberately does not copy this field into Tile. */
		public byte[] discardedTileDirections() { return tileDirections.clone(); }
	}

	public static Result decode(JContent jagArchive, JContent memArchive,
		JContent landJagArchive, JContent landMemArchive,
		int sectionX, int sectionY, int height, boolean memberWorld,
		boolean altFormat, boolean strict) {

		String mapName = "m" + height + sectionX / 10 + sectionX % 10 + sectionY / 10 + sectionY % 10;

		int size = Constants.REGION_SIZE * Constants.REGION_SIZE;
		byte[] terrainHeight = new byte[size];
		byte[] terrainColour = new byte[size];
		byte[] wallsEastWest = new byte[size];
		byte[] wallsNorthSouth = new byte[size];
		int[] wallsDiagonal = new int[size];
		byte[] wallsRoof = new byte[size];
		byte[] tileDecoration = new byte[size];
		byte[] tileDirection = new byte[size];
		int lastVal = 0;

		JContentFile jmFile = jagArchive.unpack(mapName + ".jm");
		JContentFile datFile = jagArchive.unpack(mapName + ".dat");
		JContentFile heiFile = null;
		if (landJagArchive != null)
			heiFile = landJagArchive.unpack(mapName + ".hei");
		JContentFile locFile = jagArchive.unpack(mapName + ".loc");

		if (memArchive != null && memberWorld) {
			JContentFile memberJM = memArchive.unpack(mapName + ".jm");
			JContentFile memberDat = memArchive.unpack(mapName + ".dat");
			JContentFile memberHei = null;
			if (landMemArchive != null)
				memberHei = landMemArchive.unpack(mapName + ".hei");
			if (memberDat != null)
				datFile = memberDat;
			if (memberJM != null)
				jmFile = memberJM;
			if (memberHei != null)
				heiFile = memberHei;
		}

		if (jmFile == null && datFile == null)
			return new Result(null, tileDirection);

		if (datFile != null) {
			if (altFormat) {
				for (int i = 0; i < size; ) {
					int val = datFile.readUnsignedByte();
					if (val < 128) {
						wallsEastWest[i++] = (byte) val;
					} else {
						for (int x = 0; x < val - 128; x++)
							wallsEastWest[i++] = 0;
					}
				}

				for (int i = 0; i < size; ) {
					int val = datFile.readUnsignedByte();
					if (val < 128) {
						wallsNorthSouth[i++] = (byte) val;
					} else {
						for (int x = 0; x < val - 128; x++)
							wallsNorthSouth[i++] = 0;
					}
				}

				for (int i = 0; i < size; ) {
					int val = datFile.readUnsignedByte();
					if (val < 128) {
						wallsDiagonal[i++] = val;
					} else {
						for (int x = 0; x < val - 128; x++)
							wallsDiagonal[i++] = 0;
					}
				}

				for (int i = 0; i < size; ) {
					int val = datFile.readUnsignedByte();
					if (val < 128) {
						wallsDiagonal[i++] = val + 12000;
					} else {
						i += val - 128;
					}
				}

				for (int i = 0; i < size; ) {
					int val = datFile.readUnsignedByte();
					if (val < 128) {
						wallsRoof[i++] = (byte)val;
					} else {
						for (int x = 0; x < val - 128; x++)
							wallsRoof[i++] = 0;
					}
				}

				for (int i = 0; i < size; ) {
					int val = datFile.readUnsignedByte();
					if (val < 128) {
						tileDecoration[i++] = (byte)val;
					} else {
						for (int x = 0; x < val - 128; x++)
							tileDecoration[i++] = 0;
					}
				}

				for (int i = 0; i < size; ) {
					int val = datFile.readUnsignedByte();
					if (val < 128) {
						tileDirection[i++] = (byte)val;
					} else {
						for (int x = 0; x < val - 128; x++)
							tileDirection[i++] = 0;
					}
				}
			} else {
				for (int i = 0; i < size; i++)
					wallsEastWest[i] = datFile.readByte();
				for (int i = 0; i < size; i++)
					wallsNorthSouth[i] = datFile.readByte();
				for (int i = 0; i < size; i++)
					wallsDiagonal[i] = datFile.readUnsignedByte();

				for (int i = 0; i < size; i++) {
					int val = datFile.readUnsignedByte();
					if (val > 0)
						wallsDiagonal[i] = val + 12000;
				}

				for (int tile = 0; tile < 2304; ) {
					int val = datFile.readUnsignedByte();
					if (val < 128) {
						wallsRoof[tile++] = (byte) val;
					} else {
						for (int i = 0; i < val - 128; i++)
							wallsRoof[tile++] = 0;
					}
				}

				lastVal = 0;
				for (int tile = 0; tile < 2304; ) {
					int val = datFile.readUnsignedByte();
					if (val < 128) {
						tileDecoration[tile++] = (byte) val;
						lastVal = val;
					} else {
						for (int i = 0; i < val - 128; i++)
							tileDecoration[tile++] = (byte) lastVal;
					}
				}

				for (int tile = 0; tile < 2304; ) {
					int val = datFile.readUnsignedByte();
					if (val < 128) {
						tileDirection[tile++] = (byte) val;
					} else {
						for (int i = 0; i < val - 128; i++)
							tileDirection[tile++] = 0;
					}
				}
			}
		} else {
			for (int tile = 0; tile < 2304; tile++) {
				wallsNorthSouth[tile] = 0;
				wallsEastWest[tile] = 0;
				wallsDiagonal[tile] = 0;
				wallsRoof[tile] = 0;
				tileDecoration[tile] = 0;
				if (height == 0)
					tileDecoration[tile] = -6;
				if (height == 3)
					tileDecoration[tile] = 8;
				tileDirection[tile] = 0;
			}

			if (locFile != null) {
				for (int tile = 0; tile < size;) {
					int val = locFile.readUnsignedByte();
					if (val < 128) {
						wallsDiagonal[(tile++)] = val + 48000;
					} else {
						tile += val - 128;
					}
				}
			}
		}

		if (heiFile != null) {
			for (int tile = 0; tile < 2304; ) {
				int val = heiFile.readUnsignedByte();
				if (val < 128) {
					terrainHeight[tile++] = (byte) val;
					lastVal = val;
				}
				if (val >= 128) {
					for (int i = 0; i < val - 128; i++)
						terrainHeight[tile++] = (byte) lastVal;
				}
			}

			lastVal = 64;
			for (int tileY = 0; tileY < 48; tileY++) {
				for (int tileX = 0; tileX < 48; tileX++) {
					lastVal = terrainHeight[tileX * 48 + tileY] + lastVal & 0x7f;
					terrainHeight[tileX * 48 + tileY] = (byte) (lastVal * 2);
				}
			}

			lastVal = 0;
			for (int tile = 0; tile < 2304; ) {
				int val = heiFile.readUnsignedByte();
				if (val < 128) {
					terrainColour[tile++] = (byte) val;
					lastVal = val;
				}
				if (val >= 128) {
					for (int i = 0; i < val - 128; i++)
						terrainColour[tile++] = (byte) lastVal;
				}
			}

			lastVal = 35;
			for (int tileY = 0; tileY < 48; tileY++) {
				for (int tileX = 0; tileX < 48; tileX++) {
					lastVal = terrainColour[tileX * 48 + tileY] + lastVal & 0x7f;
					terrainColour[tileX * 48 + tileY] = (byte) (lastVal * 2);
				}

			}
		} else {
			for (int tile = 0; tile < 2304; tile++) {
				terrainHeight[tile] = 0;
				terrainColour[tile] = 0;
			}
		}

		if (jmFile != null)
		{
			int val = 0;
			for (int i = 0; i < size; i++) {
				val = val + jmFile.readUnsignedByte();
				terrainHeight[i] = (byte)val;
			}

			val = 0;
			for (int i = 0; i < size; i++) {
				val = val + jmFile.readUnsignedByte();
				terrainColour[i] = (byte)val;
			}

			for (int i = 0; i < size; i++)
				wallsEastWest[i] = jmFile.readByte();

			for (int i = 0; i < size; i++)
				wallsNorthSouth[i] = jmFile.readByte();

			for (int i = 0; i < size; i++) {
				wallsDiagonal[i] = jmFile.readUnsignedByte() * 256 + jmFile.readUnsignedByte();
			}

			for (int i = 0; i < size; i++)
				wallsRoof[i] = jmFile.readByte();

			for (int i = 0; i < size; i++)
				tileDecoration[i] = jmFile.readByte();

			for (int i = 0; i < size; i++)
				tileDirection[i] = jmFile.readByte();
		}

		Sector s = new Sector();
		for (int x = 0; x < Constants.REGION_SIZE; x++)
		{
			for (int y = 0; y < Constants.REGION_SIZE; y++)
			{
				int index = (x * Constants.REGION_SIZE) + y;

				Tile tile = new Tile();
				tile.groundElevation = terrainHeight[index];
				tile.diagonalWalls = (short)wallsDiagonal[index];
				tile.verticalWall = wallsNorthSouth[index];
				tile.horizontalWall = wallsEastWest[index];
				tile.roofTexture = wallsRoof[index];

				// ??? Not 100% on these
				tile.groundOverlay = tileDecoration[index];
				tile.groundTexture = terrainColour[index];
				s.setTile(index, tile);
			}
		}
		if (strict) {
			if (datFile != null) datFile.requireFullyRead();
			if (heiFile != null) heiFile.requireFullyRead();
			if (jmFile != null) jmFile.requireFullyRead();
			if (datFile == null && locFile != null) locFile.requireFullyRead();
		}
		return new Result(s, tileDirection);
	}

}
