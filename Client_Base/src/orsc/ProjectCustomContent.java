package orsc;

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
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/** Strict, data-only custom content bound to one isolated Builder project. */
public final class ProjectCustomContent {
	private static final String CATALOG_TYPE =
		"world-builder-definition-catalog";
	private static final String ASSET_TYPE =
		"world-builder-custom-content-assets";
	private static final long MAX_MANIFEST_BYTES = 16L * 1024L * 1024L;
	private static final long MAX_ASSET_BYTES = 64L * 1024L * 1024L;
	private static final long MAX_TOTAL_BYTES = 1024L * 1024L * 1024L;
	private static final int MAX_ASSETS = 4096;
	private static final Pattern ID =
		Pattern.compile("[a-z0-9][a-z0-9._-]{0,127}");
	private static final Pattern VERSION =
		Pattern.compile("[0-9]+\\.[0-9]+\\.[0-9]+(?:[-+][A-Za-z0-9._-]+)?");
	private static final Pattern KEY =
		Pattern.compile("[a-z0-9][a-z0-9._/-]{0,255}");
	private static final Pattern ASSET_PATH = Pattern.compile(
		"(?:[A-Za-z0-9][A-Za-z0-9._-]{0,127}/){0,15}"
			+ "[A-Za-z0-9][A-Za-z0-9._-]{0,127}");
	private static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}");
	private static final Set<String> KINDS = Collections.unmodifiableSet(
		new HashSet<String>(Arrays.asList(
			"texture-png", "npc-animation-png", "item-sprite-png",
			"scenery-model-ob3")));
	private static final Map<String, Set<String>> DEFINITION_KEYS = keys();
	private static final ProjectCustomContent EMPTY = new ProjectCustomContent();

	private final boolean custom;
	private final JSONObject definitions;
	private final String bundleId;
	private final String bundleVersion;
	private final Map<String, Asset> assets;
	private final Map<Integer, Asset> textures;
	private final Map<Integer, AnimationAsset> animations;
	private final Map<Integer, Asset> items;
	private final Map<String, Asset> models;

	private ProjectCustomContent() {
		this.custom = false;
		this.definitions = null;
		this.bundleId = "";
		this.bundleVersion = "";
		this.assets = Collections.emptyMap();
		this.textures = Collections.emptyMap();
		this.animations = Collections.emptyMap();
		this.items = Collections.emptyMap();
		this.models = Collections.emptyMap();
	}

	private ProjectCustomContent(
		JSONObject definitions, String bundleId, String bundleVersion,
		Map<String, Asset> assets, Map<Integer, Asset> textures,
		Map<Integer, AnimationAsset> animations, Map<Integer, Asset> items,
		Map<String, Asset> models) {
		this.custom = true;
		this.definitions = definitions;
		this.bundleId = bundleId;
		this.bundleVersion = bundleVersion;
		this.assets = Collections.unmodifiableMap(assets);
		this.textures = Collections.unmodifiableMap(textures);
		this.animations = Collections.unmodifiableMap(animations);
		this.items = Collections.unmodifiableMap(items);
		this.models = Collections.unmodifiableMap(models);
	}

	public static ProjectCustomContent empty() { return EMPTY; }

	public static ProjectCustomContent load(
		Path workspaceRoot, Path catalogPath, Path manifestPath,
		String expectedCatalogId, String expectedManifestId) throws IOException {
		JSONObject root = json(catalogPath, "definition catalog");
		int schema = integer(root, "schemaVersion", "definition catalog");
		if (schema == 1) return EMPTY;
		if (schema != 2) throw new IOException("Unsupported definition catalog schema");
		requireKeys(root, set(
			"schemaVersion", "manifestType", "catalogId", "tiles",
			"boundaries", "scenery", "npcs", "groundItems", "customContent"),
			"definition catalog");
		expect(root, "manifestType", CATALOG_TYPE, "definition catalog");
		expect(root, "catalogId", expectedCatalogId, "definition catalog");
		Object raw = root.opt("customContent");
		if (!(raw instanceof JSONObject)) {
			throw new IOException("Definition catalog customContent must be an object");
		}
		JSONObject content = (JSONObject) raw;
		requireKeys(content, set(
			"schemaVersion", "bundleId", "bundleVersion", "assetManifestId",
			"textures", "animations", "tiles", "boundaries", "scenery",
			"npcs", "items"), "customContent");
		if (integer(content, "schemaVersion", "customContent") != 1) {
			throw new IOException("customContent schemaVersion must be 1");
		}
		String bundleId = identifier(content, "bundleId", "customContent");
		String bundleVersion = string(content, "bundleVersion", "customContent");
		if (!VERSION.matcher(bundleVersion).matches()) {
			throw new IOException("customContent bundleVersion is invalid");
		}
		expect(content, "assetManifestId", expectedManifestId, "customContent");

		JSONObject manifest = json(manifestPath, "asset manifest");
		requireKeys(manifest, set(
			"schemaVersion", "manifestType", "manifestId", "bundleId",
			"bundleVersion", "inventorySha256", "assets"), "asset manifest");
		if (integer(manifest, "schemaVersion", "asset manifest") != 1) {
			throw new IOException("asset manifest schemaVersion must be 1");
		}
		expect(manifest, "manifestType", ASSET_TYPE, "asset manifest");
		expect(manifest, "manifestId", expectedManifestId, "asset manifest");
		expect(manifest, "bundleId", bundleId, "asset manifest");
		expect(manifest, "bundleVersion", bundleVersion, "asset manifest");
		String inventory = string(manifest, "inventorySha256", "asset manifest");
		if (!SHA256.matcher(inventory).matches()) {
			throw new IOException("asset inventory fingerprint is invalid");
		}
		Object rawAssets = manifest.opt("assets");
		if (!(rawAssets instanceof JSONArray)) {
			throw new IOException("asset manifest assets must be an array");
		}
		JSONArray rows = (JSONArray) rawAssets;
		if (rows.length() > MAX_ASSETS) {
			throw new IOException("asset inventory exceeds its bound");
		}
		Map<String, Asset> assets = new LinkedHashMap<String, Asset>();
		String prior = "";
		StringBuilder canonical = new StringBuilder();
		long total = 0L;
		for (int index = 0; index < rows.length(); index++) {
			Object rowRaw = rows.get(index);
			if (!(rowRaw instanceof JSONObject)) {
				throw new IOException("asset inventory row is not an object");
			}
			JSONObject row = (JSONObject) rowRaw;
			requireKeys(row, set(
				"key", "kind", "path", "size", "sha256", "width",
				"height", "frames"), "asset row");
			String key = string(row, "key", "asset row");
			if (!KEY.matcher(key).matches() || key.compareTo(prior) <= 0) {
				throw new IOException("asset keys are invalid or not canonical");
			}
			prior = key;
			String kind = string(row, "kind", "asset row");
			if (!KINDS.contains(kind)) throw new IOException("unsupported asset kind");
			String relative = string(row, "path", "asset row");
			long size = longInteger(row, "size", "asset row");
			String hash = string(row, "sha256", "asset row");
			int width = integer(row, "width", "asset row");
			int height = integer(row, "height", "asset row");
			int frames = integer(row, "frames", "asset row");
			if (size < 1 || size > MAX_ASSET_BYTES || !SHA256.matcher(hash).matches()) {
				throw new IOException("asset metadata is outside its bound");
			}
			total += size;
			if (total > MAX_TOTAL_BYTES) throw new IOException("asset bundle is too large");
			Path path = safeAsset(
				workspaceRoot, manifestPath, relative, size, hash);
			validatePayload(kind, path, width, height, frames);
			Asset asset = new Asset(key, kind, path, width, height, frames);
			if (assets.put(key, asset) != null) throw new IOException("duplicate asset key");
			canonical.append(key).append('\t').append(kind).append('\t')
				.append(relative).append('\t').append(size).append('\t').append(hash)
				.append('\t').append(width).append('\t').append(height).append('\t')
				.append(frames).append('\n');
		}
		if (!inventory.equals(sha256(
				canonical.toString().getBytes(StandardCharsets.UTF_8)))) {
			throw new IOException("asset inventory fingerprint mismatch");
		}
		validateDefinitionSchema(content, assets);

		Map<Integer, Asset> textures = new HashMap<Integer, Asset>();
		Map<Integer, AnimationAsset> animations =
			new HashMap<Integer, AnimationAsset>();
		Map<Integer, Asset> items = new HashMap<Integer, Asset>();
		Map<String, Asset> models = new HashMap<String, Asset>();
		for (Object value : content.getJSONArray("textures")) {
			JSONObject row = (JSONObject) value;
			textures.put(row.getInt("id"), assets.get(row.getString("assetKey")));
		}
		for (Object value : content.getJSONArray("animations")) {
			JSONObject row = (JSONObject) value;
			animations.put(row.getInt("id"), new AnimationAsset(
				assets.get(row.getString("assetKey")), row.getInt("frameCount")));
		}
		for (Object value : content.getJSONArray("items")) {
			JSONObject row = (JSONObject) value;
			String key = row.getString("assetKey");
			if (!key.isEmpty()) items.put(row.getInt("id"), assets.get(key));
		}
		for (Object value : content.getJSONArray("scenery")) {
			JSONObject row = (JSONObject) value;
			String key = row.getString("assetKey");
			if (!key.isEmpty()) models.put(row.getString("modelName"), assets.get(key));
		}
		return new ProjectCustomContent(
			content, bundleId, bundleVersion, assets, textures, animations,
			items, models);
	}

	public boolean isPresent() { return custom; }
	public JSONObject definitions() {
		if (!custom) throw new IllegalStateException("No project custom content");
		return definitions;
	}
	public String bundleId() { return bundleId; }
	public String bundleVersion() { return bundleVersion; }
	public Asset texture(int id) { return textures.get(id); }
	public AnimationAsset animation(int id) { return animations.get(id); }
	public Asset item(int id) { return items.get(id); }
	public Asset model(String name) { return models.get(name); }
	public int assetCount() { return assets.size(); }

	private static Map<String, Set<String>> keys() {
		Map<String, Set<String>> result = new LinkedHashMap<String, Set<String>>();
		result.put("textures", set(
			"id", "operation", "dataName", "animationName", "assetKey"));
		result.put("animations", set(
			"id", "operation", "name", "category", "charColour", "blueMask",
			"genderModel", "hasA", "hasF", "assetKey", "frameCount"));
		result.put("tiles", set(
			"id", "operation", "colour", "tileValue", "objectType"));
		result.put("boundaries", set(
			"id", "operation", "name", "description", "command1", "command2",
			"doorType", "unknown", "wallHeight", "modelVar2", "modelVar3"));
		result.put("scenery", set(
			"id", "operation", "name", "description", "command1", "command2",
			"type", "width", "height", "groundItemVar", "modelName", "assetKey"));
		result.put("npcs", set(
			"id", "operation", "name", "description", "command1", "command2",
			"attack", "strength", "hits", "defense", "ranged", "projectileRange",
			"meleeOffense", "rangedOffense", "magicOffense", "meleeDefense",
			"rangedDefense", "magicDefense", "combatLevel", "members", "attackable",
			"aggressive", "respawnTime", "sprites", "hairColour", "topColour",
			"bottomColour", "skinColour", "camera1", "camera2", "walkModel",
			"combatModel", "combatSprite", "roundMode"));
		result.put("items", set(
			"id", "operation", "name", "description", "command", "isFemaleOnly",
			"isMembersOnly", "isStackable", "isUntradable", "isWearable",
			"appearanceId", "wearableId", "wearSlot", "requiredLevel",
			"requiredSkillId", "armourBonus", "weaponAimBonus", "weaponPowerBonus",
			"magicBonus", "prayerBonus", "basePrice", "isNoteable", "meleeOffense",
			"rangedOffense", "magicOffense", "weaponSpeed", "meleeDefense",
			"rangedDefense", "magicDefense", "spriteId", "spriteLocation", "assetKey"));
		return Collections.unmodifiableMap(result);
	}

	private static void validateDefinitionSchema(
		JSONObject content, Map<String, Asset> assets) throws IOException {
		Set<String> referenced = new HashSet<String>();
		for (Map.Entry<String, Set<String>> family : DEFINITION_KEYS.entrySet()) {
			Object raw = content.opt(family.getKey());
			if (!(raw instanceof JSONArray)) throw new IOException("definition family is not an array");
			JSONArray rows = (JSONArray) raw;
			if (rows.length() > 65536) throw new IOException("definition family exceeds its bound");
			int prior = -1;
			for (int index = 0; index < rows.length(); index++) {
				Object value = rows.get(index);
				if (!(value instanceof JSONObject)) throw new IOException("definition row is not an object");
				JSONObject row = (JSONObject) value;
				requireKeys(row, family.getValue(), family.getKey() + " definition");
				int id = integer(row, "id", family.getKey());
				if (id < 0 || id > 65535 || id <= prior) throw new IOException("definition IDs are not canonical");
				prior = id;
				String operation = string(row, "operation", family.getKey());
				if (!"add".equals(operation) && !"replace".equals(operation)) {
					throw new IOException("definition operation is invalid");
				}
				validateRow(family.getKey(), row, assets, referenced);
			}
		}
		if (!referenced.equals(assets.keySet())) {
			throw new IOException("asset inventory has missing or unreferenced entries");
		}
	}

	private static void validateRow(
		String family, JSONObject row, Map<String, Asset> assets,
		Set<String> referenced) throws IOException {
		if ("textures".equals(family)) {
			text(row, "dataName", 1, 128, family); text(row, "animationName", 0, 128, family);
			requireAsset(row, "texture-png", assets, referenced);
		} else if ("animations".equals(family)) {
			text(row, "name", 1, 128, family); text(row, "category", 1, 64, family);
			integer(row, "charColour", family); integer(row, "blueMask", family);
			integer(row, "genderModel", family); bool(row, "hasA", family); bool(row, "hasF", family);
			Asset asset = requireAsset(row, "npc-animation-png", assets, referenced);
			int frames = integer(row, "frameCount", family);
			int requiredFrames = 15
				+ (row.getBoolean("hasA") ? 3 : 0)
				+ (row.getBoolean("hasF") ? 9 : 0);
			if (frames != asset.frames || frames != requiredFrames) {
				throw new IOException("animation frame count differs from flags or asset");
			}
		} else if ("tiles".equals(family)) {
			integer(row, "colour", family); integer(row, "tileValue", family); integer(row, "objectType", family);
		} else if ("boundaries".equals(family)) {
			entity(row, family);
			for (String key : Arrays.asList("doorType", "unknown", "wallHeight", "modelVar2", "modelVar3")) integer(row, key, family);
		} else if ("scenery".equals(family)) {
			entity(row, family);
			for (String key : Arrays.asList("type", "width", "height", "groundItemVar")) integer(row, key, family);
			text(row, "modelName", 1, 128, family);
			requireAsset(row, "scenery-model-ob3", assets, referenced);
		} else if ("npcs".equals(family)) {
			entity(row, family);
			for (String key : Arrays.asList(
				"attack", "strength", "hits", "defense", "projectileRange", "meleeOffense",
				"rangedOffense", "magicOffense", "meleeDefense", "rangedDefense", "magicDefense",
				"combatLevel", "respawnTime", "hairColour", "topColour", "bottomColour",
				"skinColour", "camera1", "camera2", "walkModel", "combatModel", "combatSprite", "roundMode")) integer(row, key, family);
			for (String key : Arrays.asList("ranged", "members", "attackable", "aggressive")) bool(row, key, family);
			Object sprites = row.opt("sprites");
			if (!(sprites instanceof JSONArray) || ((JSONArray) sprites).length() != 12) throw new IOException("NPC sprites must have 12 IDs");
			for (Object sprite : (JSONArray) sprites) {
				if (!(sprite instanceof Integer) && !(sprite instanceof Long)) throw new IOException("NPC sprite ID is not integer");
				long id = ((Number) sprite).longValue();
				if (id < -1 || id > 65535) throw new IOException("NPC sprite ID is outside its bound");
			}
		} else {
			text(row, "name", 1, 128, family); text(row, "description", 0, 512, family);
			text(row, "command", 0, 256, family); text(row, "spriteLocation", 0, 256, family);
			for (String key : Arrays.asList(
				"appearanceId", "wearableId", "wearSlot", "requiredLevel", "requiredSkillId",
				"weaponAimBonus", "weaponPowerBonus", "magicBonus", "prayerBonus", "basePrice",
				"meleeOffense", "rangedOffense", "magicOffense", "weaponSpeed", "meleeDefense",
				"rangedDefense", "magicDefense", "spriteId")) integer(row, key, family);
			longInteger(row, "armourBonus", family);
			for (String key : Arrays.asList("isFemaleOnly", "isMembersOnly", "isStackable", "isUntradable", "isWearable", "isNoteable")) bool(row, key, family);
			requireAsset(row, "item-sprite-png", assets, referenced);
		}
	}

	private static void entity(JSONObject row, String label) throws IOException {
		text(row, "name", 1, 128, label); text(row, "description", 0, 512, label);
		text(row, "command1", 0, 128, label); text(row, "command2", 0, 128, label);
	}

	private static Asset requireAsset(
		JSONObject row, String kind, Map<String, Asset> assets, Set<String> referenced)
		throws IOException {
		String key = string(row, "assetKey", "definition");
		Asset asset = assets.get(key);
		if (asset == null || !kind.equals(asset.kind)) throw new IOException("missing or wrong-kind definition asset");
		referenced.add(key);
		return asset;
	}

	private static Path safeAsset(
		Path workspaceRoot, Path manifestPath, String relative,
		long size, String hash) throws IOException {
		if (!ASSET_PATH.matcher(relative).matches()
			|| relative.indexOf('\\') >= 0 || relative.indexOf('\0') >= 0) throw new IOException("invalid asset path");
		Path raw = Paths.get(relative);
		if (raw.isAbsolute() || !raw.normalize().equals(raw) || relative.startsWith("/") || relative.endsWith("/")) throw new IOException("noncanonical asset path");
		Path working = workspaceRoot.resolve("working").toRealPath();
		Path candidate = manifestPath.getParent().resolve(raw).toAbsolutePath().normalize();
		if (!candidate.startsWith(working)) throw new IOException("asset escapes project working tree");
		Path current = candidate.getRoot();
		for (Path part : candidate) {
			current = current.resolve(part);
			if (Files.isSymbolicLink(current)) throw new IOException("asset path contains symbolic link");
		}
		if (!Files.isRegularFile(candidate, LinkOption.NOFOLLOW_LINKS) || Files.size(candidate) != size || !hash.equals(sha256(candidate))) throw new IOException("asset evidence mismatch");
		if (!candidate.toRealPath().startsWith(working)) throw new IOException("asset real path escapes project");
		try {
			Object links = Files.getAttribute(candidate, "unix:nlink", LinkOption.NOFOLLOW_LINKS);
			if (links instanceof Number && ((Number) links).longValue() != 1) throw new IOException("asset is hard linked");
		} catch (UnsupportedOperationException ignored) { candidate.toRealPath(); }
		return candidate;
	}

	private static void validatePayload(String kind, Path path, int width, int height, int frames) throws IOException {
		if (kind.endsWith("-png")) {
			if (width < 1 || width > 4096 || height < 1 || height > 4096 || frames < 1 || frames > 27 || width % frames != 0) throw new IOException("PNG dimensions outside contract");
			BufferedImage image = ImageIO.read(path.toFile());
			if (image == null || image.getWidth() != width || image.getHeight() != height) throw new IOException("PNG dimensions differ from evidence");
			if (!"npc-animation-png".equals(kind) && frames != 1) throw new IOException("only animations may have multiple frames");
			if ("texture-png".equals(kind)
				&& (width != height || (width != 64 && width != 128))) {
				throw new IOException("textures must be square 64x64 or 128x128 PNGs");
			}
		} else {
			if (width != 0 || height != 0 || frames != 0) throw new IOException("OB3 dimensions must be zero");
			validateOb3(Files.readAllBytes(path));
		}
	}

	private static void validateOb3(byte[] data) throws IOException {
		if (data.length < 4) throw new IOException("truncated OB3");
		int vertices = ((data[0] & 255) << 8) | (data[1] & 255);
		int faces = ((data[2] & 255) << 8) | (data[3] & 255);
		if (vertices < 1 || faces < 1) throw new IOException("invalid OB3 counts");
		long offset = 4L + vertices * 6L + faces * 5L;
		if (offset > data.length) throw new IOException("truncated OB3");
		long indices = 0;
		int faceOffset = 4 + vertices * 6;
		for (int index = 0; index < faces; index++) {
			int count = data[faceOffset + index] & 255;
			if (count < 3) throw new IOException("invalid OB3 face");
			indices += count;
		}
		if (offset + indices * (vertices < 256 ? 1L : 2L) != data.length) throw new IOException("noncanonical OB3 length");
	}

	private static JSONObject json(Path path, String label) throws IOException {
		long size = Files.size(path);
		if (size < 3 || size > MAX_MANIFEST_BYTES) throw new IOException(label + " size outside bound");
		String value = strictUtf8(Files.readAllBytes(path), label);
		if (value.indexOf('\r') >= 0 || !value.endsWith("\n")) throw new IOException(label + " is not canonical UTF-8");
		try { return new JSONObject(value); }
		catch (RuntimeException failure) { throw new IOException(label + " is invalid JSON", failure); }
	}

	private static String strictUtf8(byte[] bytes, String label) throws IOException {
		try {
			return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
				.onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
		} catch (CharacterCodingException failure) { throw new IOException(label + " is not UTF-8", failure); }
	}

	private static Set<String> set(String... values) { return new HashSet<String>(Arrays.asList(values)); }
	private static void requireKeys(JSONObject value, Set<String> expected, String label) throws IOException {
		if (!value.keySet().equals(expected)) throw new IOException(label + " fields differ from schema");
	}
	private static String string(JSONObject value, String key, String label) throws IOException {
		Object raw = value.opt(key); if (!(raw instanceof String)) throw new IOException(label + " " + key + " must be string"); return (String) raw;
	}
	private static String identifier(JSONObject value, String key, String label) throws IOException {
		String result = string(value, key, label); if (!ID.matcher(result).matches()) throw new IOException(label + " " + key + " invalid"); return result;
	}
	private static void expect(JSONObject value, String key, String expected, String label) throws IOException {
		if (!expected.equals(string(value, key, label))) throw new IOException(label + " " + key + " mismatch");
	}
	private static long longInteger(JSONObject value, String key, String label) throws IOException {
		Object raw = value.opt(key); if (!(raw instanceof Integer) && !(raw instanceof Long)) throw new IOException(label + " " + key + " must be integer"); return ((Number) raw).longValue();
	}
	private static int integer(JSONObject value, String key, String label) throws IOException {
		long result = longInteger(value, key, label); if (result < Integer.MIN_VALUE || result > Integer.MAX_VALUE) throw new IOException(label + " " + key + " outside bounds"); return (int) result;
	}
	private static boolean bool(JSONObject value, String key, String label) throws IOException {
		Object raw = value.opt(key); if (!(raw instanceof Boolean)) throw new IOException(label + " " + key + " must be boolean"); return (Boolean) raw;
	}
	private static String text(JSONObject value, String key, int minimum, int maximum, String label) throws IOException {
		String result = string(value, key, label); if (result.length() < minimum || result.length() > maximum || result.indexOf('\0') >= 0) throw new IOException(label + " " + key + " length outside bound"); return result;
	}
	private static String sha256(Path path) throws IOException { return sha256(Files.readAllBytes(path)); }
	private static String sha256(byte[] bytes) throws IOException {
		try {
			byte[] digest = MessageDigest.getInstance("SHA-256").digest(bytes);
			StringBuilder result = new StringBuilder(); for (byte value : digest) result.append(String.format("%02x", value & 255)); return result.toString();
		} catch (NoSuchAlgorithmException failure) { throw new IOException("SHA-256 unavailable", failure); }
	}

	public static final class Asset {
		private final String key;
		private final String kind;
		private final Path path;
		private final int width;
		private final int height;
		private final int frames;
		private Asset(String key, String kind, Path path, int width, int height, int frames) {
			this.key = key; this.kind = kind; this.path = path; this.width = width; this.height = height; this.frames = frames;
		}
		public String key() { return key; }
		public String kind() { return kind; }
		public Path path() { return path; }
		public int width() { return width; }
		public int height() { return height; }
		public int frames() { return frames; }
	}

	public static final class AnimationAsset {
		private final Asset asset;
		private final int frameCount;
		private AnimationAsset(Asset asset, int frameCount) {
			this.asset = asset; this.frameCount = frameCount;
		}
		public Asset asset() { return asset; }
		public int frameCount() { return frameCount; }
	}
}
