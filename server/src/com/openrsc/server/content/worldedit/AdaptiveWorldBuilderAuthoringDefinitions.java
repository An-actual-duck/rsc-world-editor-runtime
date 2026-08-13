package com.openrsc.server.content.worldedit;

import com.openrsc.server.ServerConfiguration;
import com.openrsc.server.external.EntityHandler;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

/** Exact authoring inventory from the hash-bound project definition catalog. */
public final class AdaptiveWorldBuilderAuthoringDefinitions {
	private static final String MANIFEST_TYPE =
		"world-builder-definition-catalog";
	private static final long MAX_CATALOG_BYTES = 16L * 1024L * 1024L;
	private static final int MAX_FAMILY_IDS = 65536;

	private AdaptiveWorldBuilderAuthoringDefinitions() {
	}

	public static Result load(
		ServerConfiguration config,
		WorldEditStorageContext storage,
		EntityHandler runtimeDefinitions) throws IOException {
		Path path = storage.validateRuntimeEvidenceFile(
			config.WORLD_BUILDER_DEFINITION_EVIDENCE_PATH,
			"adaptive server definition evidence");
		if (!config.WORLD_BUILDER_DEFINITION_SHA256.equals(
				AdaptiveWorldBuilderRuntimeIdentity.sha256(path))) {
			throw new IOException(
				"Adaptive server definition evidence hash mismatch");
		}
		long size = Files.size(path);
		if (size < 3L || size > MAX_CATALOG_BYTES) {
			throw new IOException(
				"Adaptive authoring definition catalog size is outside its bound");
		}
		byte[] bytes = Files.readAllBytes(path);
		String document = strictUtf8(bytes);
		if (document.indexOf('\r') >= 0 || !document.endsWith("\n")) {
			throw new IOException(
				"Adaptive authoring definition catalog is not canonical UTF-8");
		}
		final JSONObject root;
		try {
			root = new JSONObject(document);
		} catch (RuntimeException failure) {
			throw new IOException(
				"Adaptive authoring definition catalog is invalid JSON", failure);
		}
		requireExactSchema(root, config.WORLD_BUILDER_DEFINITION_ID);
		Set<Integer> tiles = ids(root, "tiles");
		Set<Integer> boundaries = ids(root, "boundaries");
		Set<Integer> scenery = ids(root, "scenery");
		Set<Integer> npcs = ids(root, "npcs");
		Set<Integer> items = ids(root, "groundItems");
		validateRuntimeDefinitions(
			runtimeDefinitions, tiles, boundaries, scenery, npcs, items);
		return new Result(boundaries, scenery, npcs, items);
	}

	private static void requireExactSchema(
		JSONObject root, String expectedCatalogId) throws IOException {
		Set<String> expected = new HashSet<String>(Arrays.asList(
			"schemaVersion", "manifestType", "catalogId", "tiles",
			"boundaries", "scenery", "npcs", "groundItems"));
		if (!root.keySet().equals(expected)) {
			throw new IOException(
				"Adaptive authoring definition catalog fields differ from schema v1");
		}
		Object version = root.opt("schemaVersion");
		if (!(version instanceof Integer) || ((Integer) version).intValue() != 1) {
			throw new IOException(
				"Adaptive authoring definition catalog schemaVersion must be 1");
		}
		if (!MANIFEST_TYPE.equals(root.opt("manifestType"))) {
			throw new IOException(
				"Adaptive authoring definition catalog manifestType is invalid");
		}
		if (expectedCatalogId == null
			|| !expectedCatalogId.equals(root.opt("catalogId"))) {
			throw new IOException(
				"Adaptive authoring definition catalog identity mismatch");
		}
	}

	private static String strictUtf8(byte[] bytes) throws IOException {
		try {
			return StandardCharsets.UTF_8.newDecoder()
				.onMalformedInput(CodingErrorAction.REPORT)
				.onUnmappableCharacter(CodingErrorAction.REPORT)
				.decode(ByteBuffer.wrap(bytes)).toString();
		} catch (CharacterCodingException failure) {
			throw new IOException(
				"Adaptive authoring definition catalog is not UTF-8", failure);
		}
	}

	private static Set<Integer> ids(JSONObject root, String key)
		throws IOException {
		Object raw = root.opt(key);
		if (!(raw instanceof JSONArray)) {
			throw new IOException(
				"Adaptive authoring definition catalog is missing " + key);
		}
		JSONArray array = (JSONArray) raw;
		if (array.length() > MAX_FAMILY_IDS) {
			throw new IOException(
				"Adaptive authoring " + key + " inventory exceeds its bound");
		}
		Set<Integer> result = new TreeSet<Integer>();
		int prior = -1;
		for (int index = 0; index < array.length(); index++) {
			Object value = array.get(index);
			if (!(value instanceof Integer) && !(value instanceof Long)) {
				throw new IOException(
					"Adaptive authoring " + key + " inventory contains a non-integer");
			}
			long longValue = ((Number) value).longValue();
			if (longValue < 0L || longValue > Integer.MAX_VALUE) {
				throw new IOException(
					"Adaptive authoring " + key + " inventory contains an invalid ID");
			}
			int id = (int) longValue;
			if (id <= prior || !result.add(Integer.valueOf(id))) {
				throw new IOException(
					"Adaptive authoring " + key + " inventory is not canonical");
			}
			prior = id;
		}
		return result;
	}

	private static void validateRuntimeDefinitions(
		EntityHandler runtimeDefinitions,
		Set<Integer> tiles,
		Set<Integer> boundaries,
		Set<Integer> scenery,
		Set<Integer> npcs,
		Set<Integer> items) throws IOException {
		if (runtimeDefinitions == null) {
			throw new IOException(
				"Adaptive authoring validation requires runtime definitions");
		}
		for (Integer id : tiles) {
			try {
				if (runtimeDefinitions.getTileDef(id.intValue()) == null) throw new Exception();
			} catch (Exception failure) { throw unavailable("tile", id); }
		}
		for (Integer id : boundaries) {
			try {
				if (runtimeDefinitions.getDoorDef(id.intValue()) == null) throw new Exception();
			} catch (Exception failure) { throw unavailable("boundary", id); }
		}
		for (Integer id : scenery) {
			try {
				if (runtimeDefinitions.getGameObjectDef(id.intValue()) == null) throw new Exception();
			} catch (Exception failure) { throw unavailable("scenery", id); }
		}
		for (Integer id : npcs) {
			try {
				if (runtimeDefinitions.getNpcDef(id.intValue()) == null) throw new Exception();
			} catch (Exception failure) { throw unavailable("NPC", id); }
		}
		for (Integer id : items) {
			try {
				if (runtimeDefinitions.getItemDef(id.intValue()) == null) throw new Exception();
			} catch (Exception failure) { throw unavailable("item", id); }
		}
	}

	private static IOException unavailable(String family, Integer id) {
		return new IOException(
			"Adaptive authoring catalog " + family
				+ " definition is unavailable: " + id);
	}

	private static String csv(Set<Integer> values) {
		StringBuilder result = new StringBuilder();
		for (Integer value : values) {
			if (result.length() > 0) result.append(',');
			result.append(value.intValue());
		}
		return result.toString();
	}

	public static final class Result {
		private final Set<Integer> boundaryIds;
		private final Set<Integer> sceneryIds;
		private final Set<Integer> npcIds;
		private final Set<Integer> itemIds;

		private Result(
			Set<Integer> boundaryIds, Set<Integer> sceneryIds,
			Set<Integer> npcIds, Set<Integer> itemIds) {
			this.boundaryIds = Collections.unmodifiableSet(
				new TreeSet<Integer>(boundaryIds));
			this.sceneryIds = Collections.unmodifiableSet(
				new TreeSet<Integer>(sceneryIds));
			this.npcIds = Collections.unmodifiableSet(
				new TreeSet<Integer>(npcIds));
			this.itemIds = Collections.unmodifiableSet(
				new TreeSet<Integer>(itemIds));
		}

		public String boundaryIdsCsv() { return csv(boundaryIds); }
		public String sceneryIdsCsv() { return csv(sceneryIds); }
		public String npcIdsCsv() { return csv(npcIds); }
		public String itemIdsCsv() { return csv(itemIds); }

		public void requireComposition(
			AdaptiveWorldBuilderDefinitionInventory.Result composition)
			throws IOException {
			requireCsv("boundary", boundaryIds, composition.boundaryIdsCsv());
			requireCsv("scenery", sceneryIds, composition.sceneryIdsCsv());
			requireCsv("NPC", npcIds, composition.npcIdsCsv());
			requireCsv("item", itemIds, composition.itemIdsCsv());
		}

		private static void requireCsv(
			String family, Set<Integer> authorable, String required)
			throws IOException {
			if (required == null || required.isEmpty()) return;
			for (String token : required.split(",", -1)) {
				Integer id = Integer.valueOf(token);
				if (!authorable.contains(id)) {
					throw new IOException(
						"Adaptive effective composition uses " + family
							+ " definition outside its authoring catalog: " + id);
				}
			}
		}
	}
}
