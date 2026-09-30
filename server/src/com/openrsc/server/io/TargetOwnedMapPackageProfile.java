package com.openrsc.server.io;

import com.openrsc.server.model.world.coordinate.WorldSpaceId;
import java.util.HashSet;
import java.util.Set;

/** Map-only package validation; target content identities remain opaque IDs. */
public final class TargetOwnedMapPackageProfile {
    private TargetOwnedMapPackageProfile() { }
	public static void validate(
		final NativeLayeredWorldPackageCatalog catalog,
		final String profileId) {
		if (catalog.size() != 1) {
			throw new IllegalStateException(
				"The " + profileId + " profile requires exactly one package");
		}
		final NativeLayeredWorldPackage loaded = catalog.getPrimaryPackage();
		if (loaded.getWorldSpaceCount() != 1
			|| !"static".equals(loaded.getWorldSpaceKinds().get("global"))) {
			throw new IllegalStateException(
				"The " + profileId + " profile requires one static global world space");
		}
		if (loaded.getLevelCount() < 1
			|| loaded.getLevelCount() > 64
			|| loaded.getTerrainSectorCount() < 1
			|| loaded.getTerrainSectorCount() > 8192
			|| loaded.getPlacementSetCount() != loaded.getLevelCount()) {
			throw new IllegalStateException(
				"The " + profileId + " package exceeds its bounded level, "
					+ "terrain, or placement-set contract");
		}
		long placementCount = (long) loaded.getNpcPlacementCount()
			+ loaded.getGroundItemPlacementCount()
			+ loaded.getSceneryPlacementCount()
			+ loaded.getBoundaryPlacementCount();
		if (placementCount > 100000) {
			throw new IllegalStateException(
				"The " + profileId + " package exceeds "
					+ 100000 + " placements");
		}
		Set<Integer> declaredLevels = new HashSet<Integer>();
		for (NativeLayeredWorldPackage.LevelDeclaration level
			: loaded.getLevelDeclarations()) {
			if (!WorldSpaceId.GLOBAL.equals(level.getWorldSpace())
				|| !declaredLevels.add(Integer.valueOf(level.getLevel()))) {
				throw new IllegalStateException(
					"The " + profileId + " package has ambiguous level ownership");
			}
			boolean hasTerrain = false;
			for (com.openrsc.server.model.world.coordinate.WorldMapSectorId sector
				: loaded.getTerrainSectors().keySet()) {
				if (WorldSpaceId.GLOBAL.equals(sector.getWorldSpace())
					&& sector.getLevel() == level.getLevel()) {
					hasTerrain = true;
					break;
				}
			}
			if (!hasTerrain) {
				throw new IllegalStateException(
					"The " + profileId + " package has a level without terrain: "
						+ level.getLevel());
			}
		}
		Set<Integer> placementLevels = new HashSet<Integer>();
		String placementEncoding = null;
		for (NativeLayeredPlacementSet set : loaded.getPlacementSets().values()) {
			String sourceEncoding = set.getSourceEncoding();
			if (!WorldSpaceId.GLOBAL.equals(set.getWorldSpace())
				|| (!NativeLayeredWorldPackage.WORLD_PLACEMENT_ENCODING_V3.equals(
					sourceEncoding)
					&& !NativeLayeredWorldPackage.WORLD_PLACEMENT_ENCODING_V4.equals(
						sourceEncoding)
					&& !NativeLayeredWorldPackage.WORLD_PLACEMENT_ENCODING_V5.equals(
						sourceEncoding))
				|| (placementEncoding != null
					&& !placementEncoding.equals(sourceEncoding))
				|| !placementLevels.add(Integer.valueOf(set.getLevel()))) {
				throw new IllegalStateException(
					"The " + profileId + " profile requires one consistently encoded global "
						+ "placement set per level");
			}
			placementEncoding = sourceEncoding;
		}
		if (!declaredLevels.equals(placementLevels)) {
			throw new IllegalStateException(
				"The " + profileId + " placement levels are incomplete");
		}
	}

}
