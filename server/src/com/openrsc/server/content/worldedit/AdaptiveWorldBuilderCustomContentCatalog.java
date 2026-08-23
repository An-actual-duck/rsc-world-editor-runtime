package com.openrsc.server.content.worldedit;

import com.openrsc.server.ServerConfiguration;

import org.json.JSONArray;
import org.json.JSONObject;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Strict project-local declarative custom-content evidence shared by the
 * adaptive server and client. This parser does not load or execute creator
 * classes, scripts, plug-ins, serialized objects, or configuration behavior.
 */
public final class AdaptiveWorldBuilderCustomContentCatalog {
	public static final String CATALOG_TYPE =
		"world-builder-definition-catalog";
	public static final String ASSET_MANIFEST_TYPE =
		"world-builder-custom-content-assets";
	public static final int CATALOG_SCHEMA = 2;
	public static final int CONTENT_SCHEMA = 1;
	public static final int ASSET_SCHEMA = 1;

	private static final long MAX_CATALOG_BYTES = 16L * 1024L * 1024L;
	private static final long MAX_ASSET_MANIFEST_BYTES = 16L * 1024L * 1024L;
	private static final long MAX_ASSET_BYTES = 64L * 1024L * 1024L;
	private static final long MAX_TOTAL_ASSET_BYTES = 1024L * 1024L * 1024L;
	private static final int MAX_ASSETS = 4096;
	private static final int MAX_IMAGE_DIMENSION = 4096;
	private static final Pattern ID =
		Pattern.compile("[a-z0-9][a-z0-9._-]{0,127}");
	private static final Pattern VERSION =
		Pattern.compile("[0-9]+\\.[0-9]+\\.[0-9]+(?:[-+][A-Za-z0-9._-]+)?");
	private static final Pattern ASSET_KEY =
		Pattern.compile("[a-z0-9][a-z0-9._/-]{0,255}");
	private static final Pattern ASSET_PATH = Pattern.compile(
		"(?:[A-Za-z0-9][A-Za-z0-9._-]{0,127}/){0,15}"
			+ "[A-Za-z0-9][A-Za-z0-9._-]{0,127}");
	private static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}");
	private static final Set<String> ASSET_KINDS = Collections.unmodifiableSet(
		new HashSet<String>(Arrays.asList(
			"texture-png", "npc-animation-png", "item-sprite-png",
			"scenery-model-ob3")));
	private static final Map<String, Set<String>> DEFINITION_KEYS =
		definitionKeys();
	private static final int MAX_DEFINITIONS_PER_FAMILY = 65536;
	private static final int PACKAGED_TEXTURE_COUNT = 55;
	private static final int PACKAGED_ANIMATION_COUNT = 1080;

	private final boolean custom;
	private final JSONObject definitions;
	private final String bundleId;
	private final String bundleVersion;
	private final Map<String, Asset> assets;

	private AdaptiveWorldBuilderCustomContentCatalog(
		boolean custom, JSONObject definitions, String bundleId,
		String bundleVersion, Map<String, Asset> assets) {
		this.custom = custom;
		this.definitions = definitions;
		this.bundleId = bundleId;
		this.bundleVersion = bundleVersion;
		this.assets = Collections.unmodifiableMap(
			new LinkedHashMap<String, Asset>(assets));
	}

	public static AdaptiveWorldBuilderCustomContentCatalog load(
		ServerConfiguration config, WorldEditStorageContext storage)
		throws IOException {
		Path catalogPath = storage.validateRuntimeEvidenceFile(
			config.WORLD_BUILDER_DEFINITION_EVIDENCE_PATH,
			"adaptive custom-content definition catalog");
		if (!config.WORLD_BUILDER_DEFINITION_SHA256.equals(
				AdaptiveWorldBuilderRuntimeIdentity.sha256(catalogPath))) {
			throw new IOException(
				"Adaptive custom-content definition catalog hash mismatch");
		}
		JSONObject root = json(catalogPath, MAX_CATALOG_BYTES,
			"adaptive custom-content definition catalog");
		int schema = integer(root, "schemaVersion",
			"adaptive definition catalog");
		if (schema == 1) {
			return new AdaptiveWorldBuilderCustomContentCatalog(
				false, null, "", "", Collections.<String, Asset>emptyMap());
		}
		if (schema != CATALOG_SCHEMA) {
			throw new IOException(
				"Adaptive definition catalog schema is unsupported");
		}
		requireKeys(root, set(
			"schemaVersion", "manifestType", "catalogId", "tiles",
			"boundaries", "scenery", "npcs", "groundItems",
			"customContent"), "adaptive definition catalog");
		requireText(root, "manifestType", CATALOG_TYPE,
			"adaptive definition catalog");
		requireText(root, "catalogId", config.WORLD_BUILDER_DEFINITION_ID,
			"adaptive definition catalog");
		Object rawContent = root.opt("customContent");
		if (!(rawContent instanceof JSONObject)) {
			throw new IOException(
				"Adaptive definition catalog customContent must be an object");
		}
		JSONObject content = (JSONObject) rawContent;
		requireKeys(content, set(
			"schemaVersion", "bundleId", "bundleVersion",
			"assetManifestId", "textures", "animations", "tiles",
			"boundaries", "scenery", "npcs", "items"),
			"adaptive customContent");
		if (integer(content, "schemaVersion", "adaptive customContent")
			!= CONTENT_SCHEMA) {
			throw new IOException(
				"Adaptive customContent schemaVersion must be 1");
		}
		String bundleId = identifier(content, "bundleId",
			"adaptive customContent");
		String bundleVersion = string(content, "bundleVersion",
			"adaptive customContent");
		if (!VERSION.matcher(bundleVersion).matches()) {
			throw new IOException(
				"Adaptive custom-content bundleVersion is invalid");
		}
		String assetManifestId = identifier(content, "assetManifestId",
			"adaptive customContent");
		if (!assetManifestId.equals(config.WORLD_BUILDER_ASSET_ID)) {
			throw new IOException(
				"Adaptive custom-content asset identity differs from configuration");
		}
		for (String family : Arrays.asList(
			"textures", "animations", "tiles", "boundaries", "scenery",
			"npcs", "items")) {
			if (!(content.opt(family) instanceof JSONArray)) {
				throw new IOException(
					"Adaptive customContent " + family + " must be an array");
			}
		}

		Path manifestPath = storage.validateRuntimeEvidenceFile(
			config.WORLD_BUILDER_ASSET_EVIDENCE_PATH,
			"adaptive custom-content asset manifest");
		if (!config.WORLD_BUILDER_ASSET_SHA256.equals(
				AdaptiveWorldBuilderRuntimeIdentity.sha256(manifestPath))) {
			throw new IOException(
				"Adaptive custom-content asset manifest hash mismatch");
		}
		JSONObject manifest = json(manifestPath, MAX_ASSET_MANIFEST_BYTES,
			"adaptive custom-content asset manifest");
		requireKeys(manifest, set(
			"schemaVersion", "manifestType", "manifestId", "bundleId",
			"bundleVersion", "inventorySha256", "assets"),
			"adaptive asset manifest");
		if (integer(manifest, "schemaVersion", "adaptive asset manifest")
			!= ASSET_SCHEMA) {
			throw new IOException(
				"Adaptive asset manifest schemaVersion must be 1");
		}
		requireText(manifest, "manifestType", ASSET_MANIFEST_TYPE,
			"adaptive asset manifest");
		requireText(manifest, "manifestId", assetManifestId,
			"adaptive asset manifest");
		requireText(manifest, "bundleId", bundleId,
			"adaptive asset manifest");
		requireText(manifest, "bundleVersion", bundleVersion,
			"adaptive asset manifest");
		String expectedInventory = string(
			manifest, "inventorySha256", "adaptive asset manifest");
		if (!SHA256.matcher(expectedInventory).matches()) {
			throw new IOException(
				"Adaptive asset inventory fingerprint is invalid");
		}
		Object rawAssets = manifest.opt("assets");
		if (!(rawAssets instanceof JSONArray)) {
			throw new IOException("Adaptive asset manifest assets must be an array");
		}
		JSONArray entries = (JSONArray) rawAssets;
		if (entries.length() > MAX_ASSETS) {
			throw new IOException("Adaptive asset inventory exceeds its bound");
		}
		Map<String, Asset> assets = new LinkedHashMap<String, Asset>();
		StringBuilder canonical = new StringBuilder();
		String prior = "";
		long total = 0L;
		for (int index = 0; index < entries.length(); index++) {
			Object raw = entries.get(index);
			if (!(raw instanceof JSONObject)) {
				throw new IOException(
					"Adaptive asset inventory contains a non-object");
			}
			JSONObject row = (JSONObject) raw;
			requireKeys(row, set(
				"key", "kind", "path", "size", "sha256", "width",
				"height", "frames"), "adaptive asset row");
			String key = string(row, "key", "adaptive asset row");
			if (!ASSET_KEY.matcher(key).matches() || key.compareTo(prior) <= 0) {
				throw new IOException(
					"Adaptive asset keys are invalid or not canonical");
			}
			prior = key;
			String kind = string(row, "kind", "adaptive asset row");
			if (!ASSET_KINDS.contains(kind)) {
				throw new IOException("Adaptive asset kind is unsupported: " + kind);
			}
			String relative = string(row, "path", "adaptive asset row");
			long size = longInteger(row, "size", "adaptive asset row");
			String hash = string(row, "sha256", "adaptive asset row");
			int width = integer(row, "width", "adaptive asset row");
			int height = integer(row, "height", "adaptive asset row");
			int frames = integer(row, "frames", "adaptive asset row");
			if (size < 1L || size > MAX_ASSET_BYTES
				|| !SHA256.matcher(hash).matches()) {
				throw new IOException("Adaptive asset metadata is outside its bound");
			}
			total += size;
			if (total > MAX_TOTAL_ASSET_BYTES) {
				throw new IOException("Adaptive asset bundle exceeds its total bound");
			}
			Path assetPath = safeAsset(
				storage, manifestPath, relative, size, hash);
			validatePayload(kind, assetPath, width, height, frames);
			Asset asset = new Asset(
				key, kind, relative, assetPath, size, hash, width, height, frames);
			if (assets.put(key, asset) != null) {
				throw new IOException("Adaptive asset key is duplicated: " + key);
			}
			canonical.append(key).append('\t').append(kind).append('\t')
				.append(relative).append('\t').append(size).append('\t')
				.append(hash).append('\t').append(width).append('\t')
				.append(height).append('\t').append(frames).append('\n');
		}
		if (!expectedInventory.equals(sha256(
				canonical.toString().getBytes(StandardCharsets.UTF_8)))) {
			throw new IOException(
				"Adaptive asset inventory fingerprint mismatch");
		}
		validateDefinitions(content, assets);
		validateRendererDependencies(content);
		return new AdaptiveWorldBuilderCustomContentCatalog(
			true, content, bundleId, bundleVersion, assets);
	}

	public boolean hasCustomContent() { return custom; }
	public JSONObject definitions() {
		if (!custom) throw new IllegalStateException("No custom content is bound");
		return definitions;
	}
	public String bundleId() { return bundleId; }
	public String bundleVersion() { return bundleVersion; }
	public Asset asset(String key) { return assets.get(key); }
	public Map<String, Asset> assets() { return assets; }

	private static Map<String, Set<String>> definitionKeys() {
		Map<String, Set<String>> result =
			new LinkedHashMap<String, Set<String>>();
		result.put("textures", set(
			"id", "operation", "dataName", "animationName", "assetKey"));
		result.put("animations", set(
			"id", "operation", "name", "category", "charColour",
			"blueMask", "genderModel", "hasA", "hasF", "assetKey",
			"frameCount"));
		result.put("tiles", set(
			"id", "operation", "colour", "tileValue", "objectType"));
		result.put("boundaries", set(
			"id", "operation", "name", "description", "command1",
			"command2", "doorType", "unknown", "wallHeight",
			"modelVar2", "modelVar3"));
		result.put("scenery", set(
			"id", "operation", "name", "description", "command1",
			"command2", "type", "width", "height", "groundItemVar",
			"modelName", "assetKey"));
		result.put("npcs", set(
			"id", "operation", "name", "description", "command1",
			"command2", "attack", "strength", "hits", "defense",
			"ranged", "projectileRange", "meleeOffense", "rangedOffense",
			"magicOffense", "meleeDefense", "rangedDefense", "magicDefense",
			"combatLevel", "members", "attackable", "aggressive",
			"respawnTime", "sprites", "hairColour", "topColour",
			"bottomColour", "skinColour", "camera1", "camera2",
			"walkModel", "combatModel", "combatSprite", "roundMode"));
		result.put("items", set(
			"id", "operation", "name", "description", "command",
			"isFemaleOnly", "isMembersOnly", "isStackable", "isUntradable",
			"isWearable", "appearanceId", "wearableId", "wearSlot",
			"requiredLevel", "requiredSkillId", "armourBonus",
			"weaponAimBonus", "weaponPowerBonus", "magicBonus", "prayerBonus",
			"basePrice", "isNoteable", "meleeOffense", "rangedOffense",
			"magicOffense", "weaponSpeed", "meleeDefense", "rangedDefense",
			"magicDefense", "spriteId", "spriteLocation", "assetKey"));
		return Collections.unmodifiableMap(result);
	}

	private static void validateDefinitions(
		JSONObject content, Map<String, Asset> assets) throws IOException {
		Set<String> referencedAssets = new HashSet<String>();
		for (Map.Entry<String, Set<String>> family : DEFINITION_KEYS.entrySet()) {
			JSONArray rows = content.getJSONArray(family.getKey());
			if (rows.length() > MAX_DEFINITIONS_PER_FAMILY) {
				throw new IOException(
					"Adaptive " + family.getKey() + " definitions exceed their bound");
			}
			int prior = -1;
			for (int index = 0; index < rows.length(); index++) {
				Object raw = rows.get(index);
				if (!(raw instanceof JSONObject)) {
					throw new IOException(
						"Adaptive " + family.getKey() + " definition is not an object");
				}
				JSONObject row = (JSONObject) raw;
				requireKeys(row, family.getValue(),
					"adaptive " + family.getKey() + " definition");
				int id = integer(row, "id", "adaptive " + family.getKey());
				if (id < 0 || id > 65535 || id <= prior) {
					throw new IOException(
						"Adaptive " + family.getKey() + " IDs are not canonical");
				}
				prior = id;
				String operation = string(
					row, "operation", "adaptive " + family.getKey());
				if (!"add".equals(operation) && !"replace".equals(operation)) {
					throw new IOException(
						"Adaptive definition operation must be add or replace");
				}
				validateDefinitionFields(family.getKey(), row, assets, referencedAssets);
			}
		}
		if (!referencedAssets.equals(assets.keySet())) {
			throw new IOException(
				"Adaptive asset inventory contains missing or unreferenced payloads");
		}
	}

	private static void validateDefinitionFields(
		String family, JSONObject row, Map<String, Asset> assets,
		Set<String> referencedAssets) throws IOException {
		if ("textures".equals(family)) {
			text(row, "dataName", 1, 128, family);
			text(row, "animationName", 0, 128, family);
			requireAsset(row, "assetKey", "texture-png", assets, referencedAssets);
		} else if ("animations".equals(family)) {
			text(row, "name", 1, 128, family);
			text(row, "category", 1, 64, family);
			for (String key : Arrays.asList(
				"charColour", "blueMask", "genderModel")) integer(row, key, family);
			bool(row, "hasA", family); bool(row, "hasF", family);
			Asset asset = requireAsset(
				row, "assetKey", "npc-animation-png", assets, referencedAssets);
			int frames = integer(row, "frameCount", family);
			int requiredFrames = 15
				+ (row.getBoolean("hasA") ? 3 : 0)
				+ (row.getBoolean("hasF") ? 9 : 0);
			if (frames != asset.frames() || frames != requiredFrames) {
				throw new IOException(
					"Adaptive animation frame count differs from its flags or asset");
			}
		} else if ("tiles".equals(family)) {
			integer(row, "colour", family); integer(row, "tileValue", family);
			integer(row, "objectType", family);
		} else if ("boundaries".equals(family)) {
			commonEntity(row, family);
			for (String key : Arrays.asList(
				"doorType", "unknown", "wallHeight", "modelVar2", "modelVar3")) {
				integer(row, key, family);
			}
		} else if ("scenery".equals(family)) {
			commonEntity(row, family);
			for (String key : Arrays.asList(
				"type", "width", "height", "groundItemVar")) integer(row, key, family);
			text(row, "modelName", 1, 128, family);
			requireAsset(row, "assetKey", "scenery-model-ob3", assets, referencedAssets);
		} else if ("npcs".equals(family)) {
			commonEntity(row, family);
			for (String key : Arrays.asList(
				"attack", "strength", "hits", "defense", "projectileRange",
				"meleeOffense", "rangedOffense", "magicOffense", "meleeDefense",
				"rangedDefense", "magicDefense", "combatLevel", "respawnTime",
				"hairColour", "topColour", "bottomColour", "skinColour",
				"camera1", "camera2", "walkModel", "combatModel", "combatSprite",
				"roundMode")) integer(row, key, family);
			bool(row, "ranged", family); bool(row, "members", family);
			bool(row, "attackable", family); bool(row, "aggressive", family);
			Object rawSprites = row.opt("sprites");
			if (!(rawSprites instanceof JSONArray)
				|| ((JSONArray) rawSprites).length() != 12) {
				throw new IOException("Adaptive NPC sprites must contain exactly 12 IDs");
			}
			for (int index = 0; index < 12; index++) {
				Object raw = ((JSONArray) rawSprites).get(index);
				if (!(raw instanceof Integer) && !(raw instanceof Long)) {
					throw new IOException("Adaptive NPC sprite ID is not an integer");
				}
				long value = ((Number) raw).longValue();
				if (value < -1L || value > 65535L) {
					throw new IOException("Adaptive NPC sprite ID is outside its bound");
				}
			}
		} else {
			text(row, "name", 1, 128, family);
			text(row, "description", 0, 512, family);
			text(row, "command", 0, 256, family);
			text(row, "spriteLocation", 0, 256, family);
			for (String key : Arrays.asList(
				"appearanceId", "wearableId", "wearSlot", "requiredLevel",
				"requiredSkillId", "weaponAimBonus", "weaponPowerBonus",
				"magicBonus", "prayerBonus", "basePrice", "meleeOffense",
				"rangedOffense", "magicOffense", "weaponSpeed", "meleeDefense",
				"rangedDefense", "magicDefense", "spriteId")) integer(row, key, family);
			longInteger(row, "armourBonus", family);
			for (String key : Arrays.asList(
				"isFemaleOnly", "isMembersOnly", "isStackable", "isUntradable",
				"isWearable", "isNoteable")) bool(row, key, family);
			requireAsset(row, "assetKey", "item-sprite-png", assets, referencedAssets);
		}
	}

	private static void validateRendererDependencies(JSONObject content)
		throws IOException {
		int textureCount = validateContiguousFamily(
			content.getJSONArray("textures"), PACKAGED_TEXTURE_COUNT, "texture");
		int animationCount = validateContiguousFamily(
			content.getJSONArray("animations"), PACKAGED_ANIMATION_COUNT,
			"animation");
		JSONArray tiles = content.getJSONArray("tiles");
		for (int index = 0; index < tiles.length(); index++) {
			requireRendererResource(
				tiles.getJSONObject(index).getInt("colour"), textureCount,
				"tile colour", "texture");
		}
		JSONArray boundaries = content.getJSONArray("boundaries");
		for (int index = 0; index < boundaries.length(); index++) {
			JSONObject row = boundaries.getJSONObject(index);
			requireRendererResource(
				row.getInt("modelVar2"), textureCount,
				"boundary front texture", "texture");
			requireRendererResource(
				row.getInt("modelVar3"), textureCount,
				"boundary back texture", "texture");
		}
		JSONArray npcs = content.getJSONArray("npcs");
		for (int index = 0; index < npcs.length(); index++) {
			JSONArray sprites = npcs.getJSONObject(index).getJSONArray("sprites");
			for (int layer = 0; layer < sprites.length(); layer++) {
				requireRendererResource(
					sprites.getInt(layer), animationCount,
					"NPC sprite", "animation");
			}
		}
	}

	private static int validateContiguousFamily(
		JSONArray rows, int packagedCount, String family) throws IOException {
		int count = packagedCount;
		for (int index = 0; index < rows.length(); index++) {
			JSONObject row = rows.getJSONObject(index);
			int id = row.getInt("id");
			String operation = row.getString("operation");
			boolean exists = id < count;
			if (("add".equals(operation) && exists)
				|| ("replace".equals(operation) && !exists)) {
				throw new IOException(
					"Adaptive " + family + " " + id
						+ " has an unsafe " + operation + " collision contract");
			}
			if ("add".equals(operation)) {
				if (id != count) {
					throw new IOException(
						"Adaptive " + family + " IDs cannot create a renderer hole");
				}
				count++;
			}
		}
		return count;
	}

	private static void requireRendererResource(
		int id, int count, String label, String family) throws IOException {
		if (id >= count) {
			throw new IOException(
				"Adaptive " + label + " references undefined " + family + " " + id);
		}
	}

	private static void commonEntity(JSONObject row, String label)
		throws IOException {
		text(row, "name", 1, 128, label);
		text(row, "description", 0, 512, label);
		text(row, "command1", 0, 128, label);
		text(row, "command2", 0, 128, label);
	}

	private static String text(
		JSONObject row, String key, int minimum, int maximum, String label)
		throws IOException {
		String result = string(row, key, label);
		if (result.length() < minimum || result.length() > maximum
			|| result.indexOf('\0') >= 0) {
			throw new IOException(label + " " + key + " length is outside its bound");
		}
		return result;
	}

	private static boolean bool(JSONObject row, String key, String label)
		throws IOException {
		Object raw = row.opt(key);
		if (!(raw instanceof Boolean)) {
			throw new IOException(label + " " + key + " must be boolean");
		}
		return ((Boolean) raw).booleanValue();
	}

	private static Asset requireAsset(
		JSONObject row, String field, String expectedKind,
		Map<String, Asset> assets, Set<String> referenced) throws IOException {
		String key = string(row, field, "adaptive definition");
		Asset asset = assets.get(key);
		if (asset == null || !expectedKind.equals(asset.kind())) {
			throw new IOException(
				"Adaptive definition references a missing or wrong-kind asset: " + key);
		}
		referenced.add(key);
		return asset;
	}

	private static Path safeAsset(
		WorldEditStorageContext storage, Path manifestPath, String relative,
		long expectedSize, String expectedHash) throws IOException {
		if (!ASSET_PATH.matcher(relative).matches()
			|| relative.indexOf('\\') >= 0
			|| relative.indexOf('\0') >= 0) {
			throw new IOException("Adaptive asset path is invalid");
		}
		Path raw = Paths.get(relative);
		if (raw.isAbsolute() || !raw.normalize().equals(raw)
			|| relative.startsWith("/") || relative.endsWith("/")) {
			throw new IOException("Adaptive asset path is not canonical");
		}
		Path candidate = manifestPath.getParent().resolve(raw)
			.toAbsolutePath().normalize();
		if (!candidate.startsWith(storage.workingRoot())) {
			throw new IOException(
				"Adaptive asset escapes the isolated project working tree");
		}
		Path current = candidate.getRoot();
		for (Path part : candidate) {
			current = current.resolve(part);
			if (Files.isSymbolicLink(current)) {
				throw new IOException("Adaptive asset path contains a symbolic link");
			}
		}
		if (!Files.isRegularFile(candidate, LinkOption.NOFOLLOW_LINKS)
			|| Files.size(candidate) != expectedSize
			|| !expectedHash.equals(
				AdaptiveWorldBuilderRuntimeIdentity.sha256(candidate))) {
			throw new IOException("Adaptive asset evidence mismatch: " + relative);
		}
		if (!candidate.toRealPath().startsWith(storage.workingRoot())) {
			throw new IOException("Adaptive asset real path escapes the working tree");
		}
		try {
			Object links = Files.getAttribute(
				candidate, "unix:nlink", LinkOption.NOFOLLOW_LINKS);
			if (links instanceof Number && ((Number) links).longValue() != 1L) {
				throw new IOException("Adaptive asset is hard linked");
			}
		} catch (UnsupportedOperationException unsupported) {
			candidate.toRealPath();
		}
		return candidate;
	}

	private static void validatePayload(
		String kind, Path path, int width, int height, int frames)
		throws IOException {
		if (kind.endsWith("-png")) {
			if (width < 1 || width > MAX_IMAGE_DIMENSION
				|| height < 1 || height > MAX_IMAGE_DIMENSION
				|| frames < 1 || frames > 27 || width % frames != 0) {
				throw new IOException("Adaptive PNG dimensions are outside the contract");
			}
			BufferedImage image = ImageIO.read(path.toFile());
			if (image == null || image.getWidth() != width
				|| image.getHeight() != height) {
				throw new IOException("Adaptive PNG payload dimensions differ from evidence");
			}
			if (!"npc-animation-png".equals(kind) && frames != 1) {
				throw new IOException("Only NPC animation assets may declare multiple frames");
			}
			if ("texture-png".equals(kind)
				&& (width != height || (width != 64 && width != 128))) {
				throw new IOException(
					"Adaptive textures must be square 64x64 or 128x128 PNGs");
			}
		} else {
			if (width != 0 || height != 0 || frames != 0) {
				throw new IOException("Adaptive OB3 metadata must use zero dimensions");
			}
			byte[] data = Files.readAllBytes(path);
			validateOb3(data);
		}
	}

	private static void validateOb3(byte[] data) throws IOException {
		if (data.length < 4) throw new IOException("Adaptive OB3 payload is truncated");
		int vertices = unsignedShort(data, 0);
		int faces = unsignedShort(data, 2);
		if (vertices < 1 || vertices > 65535 || faces < 1 || faces > 65535) {
			throw new IOException("Adaptive OB3 counts are outside their bounds");
		}
		long offset = 4L + vertices * 6L + faces * 5L;
		if (offset > data.length) throw new IOException("Adaptive OB3 payload is truncated");
		long indices = 0L;
		int faceCountOffset = 4 + vertices * 6;
		for (int index = 0; index < faces; index++) {
			int count = data[faceCountOffset + index] & 255;
			if (count < 3) throw new IOException("Adaptive OB3 face is invalid");
			indices += count;
		}
		long expected = offset + indices * (vertices < 256 ? 1L : 2L);
		if (expected != data.length) {
			throw new IOException("Adaptive OB3 payload length is not canonical");
		}
	}

	private static int unsignedShort(byte[] bytes, int offset) {
		return ((bytes[offset] & 255) << 8) | (bytes[offset + 1] & 255);
	}

	private static JSONObject json(Path path, long maximum, String label)
		throws IOException {
		long size = Files.size(path);
		if (size < 3L || size > maximum) {
			throw new IOException(label + " size is outside its bound");
		}
		String document = strictUtf8(Files.readAllBytes(path), label);
		if (document.indexOf('\r') >= 0 || !document.endsWith("\n")) {
			throw new IOException(label + " is not canonical UTF-8");
		}
		try {
			return new JSONObject(document);
		} catch (RuntimeException failure) {
			throw new IOException(label + " is invalid JSON", failure);
		}
	}

	private static String strictUtf8(byte[] bytes, String label)
		throws IOException {
		try {
			return StandardCharsets.UTF_8.newDecoder()
				.onMalformedInput(CodingErrorAction.REPORT)
				.onUnmappableCharacter(CodingErrorAction.REPORT)
				.decode(ByteBuffer.wrap(bytes)).toString();
		} catch (CharacterCodingException failure) {
			throw new IOException(label + " is not UTF-8", failure);
		}
	}

	private static Set<String> set(String... values) {
		return new HashSet<String>(Arrays.asList(values));
	}

	private static void requireKeys(
		JSONObject value, Set<String> expected, String label) throws IOException {
		if (!value.keySet().equals(expected)) {
			throw new IOException(label + " fields differ from its schema");
		}
	}

	private static String identifier(
		JSONObject value, String key, String label) throws IOException {
		String result = string(value, key, label);
		if (!ID.matcher(result).matches()) {
			throw new IOException(label + " " + key + " is not a portable identifier");
		}
		return result;
	}

	private static String string(
		JSONObject value, String key, String label) throws IOException {
		Object raw = value.opt(key);
		if (!(raw instanceof String)) {
			throw new IOException(label + " " + key + " must be a string");
		}
		return (String) raw;
	}

	private static void requireText(
		JSONObject value, String key, String expected, String label)
		throws IOException {
		if (!expected.equals(string(value, key, label))) {
			throw new IOException(label + " " + key + " identity mismatch");
		}
	}

	private static int integer(
		JSONObject value, String key, String label) throws IOException {
		long result = longInteger(value, key, label);
		if (result < Integer.MIN_VALUE || result > Integer.MAX_VALUE) {
			throw new IOException(label + " " + key + " is outside integer bounds");
		}
		return (int) result;
	}

	private static long longInteger(
		JSONObject value, String key, String label) throws IOException {
		Object raw = value.opt(key);
		if (!(raw instanceof Integer) && !(raw instanceof Long)) {
			throw new IOException(label + " " + key + " must be an integer");
		}
		return ((Number) raw).longValue();
	}

	private static String sha256(byte[] bytes) throws IOException {
		try {
			byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
			StringBuilder value = new StringBuilder();
			for (byte item : digest) value.append(String.format("%02x", item & 255));
			return value.toString();
		} catch (NoSuchAlgorithmException failure) {
			throw new IOException("SHA-256 is unavailable", failure);
		}
	}

	public static final class Asset {
		private final String key;
		private final String kind;
		private final String relativePath;
		private final Path path;
		private final long size;
		private final String sha256;
		private final int width;
		private final int height;
		private final int frames;

		private Asset(
			String key, String kind, String relativePath, Path path,
			long size, String sha256, int width, int height, int frames) {
			this.key = key;
			this.kind = kind;
			this.relativePath = relativePath;
			this.path = path;
			this.size = size;
			this.sha256 = sha256;
			this.width = width;
			this.height = height;
			this.frames = frames;
		}

		public String key() { return key; }
		public String kind() { return kind; }
		public String relativePath() { return relativePath; }
		public Path path() { return path; }
		public long size() { return size; }
		public String sha256() { return sha256; }
		public int width() { return width; }
		public int height() { return height; }
		public int frames() { return frames; }
	}
}
