package com.openrsc.client.entityhandling.defs;

public class TileDef {
	public int colour;
	private int tileValue;
	private int objectType;
	private String worldBuilderMaterial;
	private int worldBuilderSourceOverlay;

	public TileDef(int colour, int tileValue, int objectType) {
		this.colour = colour;
		this.tileValue = tileValue;
		this.objectType = objectType;
	}

	public TileDef(int colour, int tileValue, int objectType, String material, int sourceOverlay) {
		this(colour, tileValue, objectType);
		worldBuilderMaterial = material;
		worldBuilderSourceOverlay = sourceOverlay;
	}

	public boolean blocksLegacyProjectiles(int rawOverlay) {
		return (rawOverlay == 2 || rawOverlay == 11) && getWorldBuilderMaterial().isEmpty()
			&& worldBuilderSourceOverlay == 0;
	}

	public boolean usesExplicitBaseColor() { return "base-color-v1".equals(worldBuilderMaterial); }
	public int getWorldBuilderSourceOverlay() { return worldBuilderSourceOverlay; }
	public String getWorldBuilderMaterial() { return worldBuilderMaterial == null ? "" : worldBuilderMaterial; }

	public static void validateWorldBuilderDefinitions(java.util.List<TileDef> definitions) {
		for (int index = 0; index < definitions.size(); index++) {
			TileDef value = definitions.get(index);
			String material = value.getWorldBuilderMaterial();
			if (!material.isEmpty() && !value.usesExplicitBaseColor())
				throw new IllegalArgumentException("Unsupported World Builder floor material at " + (index + 1));
			if (value.usesExplicitBaseColor() && (index + 1 >= 250 || value.colour != 0 || value.tileValue != 0
				|| value.worldBuilderSourceOverlay != 0 || value.objectType < 0 || value.objectType > 1))
				throw new IllegalArgumentException("Invalid explicit base-color floor at " + (index + 1));
			int source = value.worldBuilderSourceOverlay;
			if (source != 0) {
				if (source < 1 || source > index || source == 250 || index + 1 >= 250)
					throw new IllegalArgumentException("Invalid source floor at " + (index + 1));
				TileDef original = definitions.get(source - 1);
				if (!original.getWorldBuilderMaterial().isEmpty() || original.worldBuilderSourceOverlay != 0
					|| original.colour != value.colour || original.tileValue != value.tileValue
					|| value.objectType < 0 || value.objectType > 1 || original.objectType < 0 || original.objectType > 1)
					throw new IllegalArgumentException("Floor partner does not match its original at " + (index + 1));
			}
		}
	}

	public int getColour() {
		return colour;
	}

	public int getTileValue() {
		return tileValue;
	}

	public int getObjectType() {
		return objectType;
	}
}
