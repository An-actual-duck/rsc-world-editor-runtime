package com.openrsc.server.content.worldedit;

import com.openrsc.server.ServerConfiguration;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.regex.Pattern;

/**
 * Strict consumer for the Editor-owned project-content-bundle-v1 contract.
 * The bundle contains captured declarative definitions and existing client
 * archives only. It never discovers or executes target classes, scripts, or
 * plug-ins.
 */
public final class AdaptiveWorldBuilderProjectContentBundle {
	public static final String CAPABILITY_ID = "project-local-custom-content-v1";
	public static final String MANIFEST_TYPE =
		"world-builder-project-content-bundle";
	private static final String CATALOG_TYPE =
		"world-builder-definition-catalog";
	private static final String ZERO_HASH = repeat('0', 64);
	private static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}");
	private static final long MAX_MANIFEST_BYTES = 16L * 1024L * 1024L;
	private static final long MAX_FILE_BYTES = 256L * 1024L * 1024L;
	private static final long MAX_TOTAL_BYTES = 1024L * 1024L * 1024L;
	private static final Set<String> ROOT_KEYS = set(
		"schemaVersion", "manifestType", "capabilityId", "sourceKind",
		"definitionCatalog", "familyBindings", "files",
		"definitionFingerprintSha256", "assetFingerprintSha256",
		"bundleFingerprintSha256");
	private static final Set<String> CATALOG_KEYS = set(
		"schemaVersion", "manifestType", "catalogId", "tiles",
		"boundaries", "scenery", "npcs", "groundItems", "catalogSha256");
	private static final Set<String> FILE_KEYS = set(
		"role", "bundleRelativePath", "runtimeRelativePath", "mediaType",
		"size", "sha256");
	private static final Set<String> BINDING_KEYS = set(
		"family", "definitionRoles", "assetRoles");

	private static final List<Spec> SPECS = specs();
	private static final List<Binding> BINDINGS = bindings();
	private static final AdaptiveWorldBuilderProjectContentBundle EMPTY =
		new AdaptiveWorldBuilderProjectContentBundle(
			null, null, Collections.<String, Path>emptyMap(), "", "", "", "");

	private final Path root;
	private final JSONObject catalog;
	private final Map<String, Path> paths;
	private final String catalogId;
	private final String bundleSha256;
	private final String definitionSha256;
	private final String assetSha256;

	private AdaptiveWorldBuilderProjectContentBundle(
		Path root, JSONObject catalog, Map<String, Path> paths,
		String catalogId, String bundleSha256, String definitionSha256,
		String assetSha256) {
		this.root = root;
		this.catalog = catalog;
		this.paths = Collections.unmodifiableMap(
			new LinkedHashMap<String, Path>(paths));
		this.catalogId = catalogId;
		this.bundleSha256 = bundleSha256;
		this.definitionSha256 = definitionSha256;
		this.assetSha256 = assetSha256;
	}

	public static AdaptiveWorldBuilderProjectContentBundle load(
		ServerConfiguration config, WorldEditStorageContext storage)
		throws IOException {
		String configured = trim(config.WORLD_BUILDER_CONTENT_BUNDLE_PATH);
		if (configured.isEmpty()) {
			requireEmpty(config.WORLD_BUILDER_CONTENT_CAPABILITY_ID,
				"content capability");
			requireEmpty(config.WORLD_BUILDER_CONTENT_BUNDLE_SHA256,
				"content bundle fingerprint");
			requireEmpty(config.WORLD_BUILDER_CONTENT_DEFINITION_SHA256,
				"content definition fingerprint");
			requireEmpty(config.WORLD_BUILDER_CONTENT_ASSET_SHA256,
				"content asset fingerprint");
			return EMPTY;
		}
		if (!CAPABILITY_ID.equals(
				trim(config.WORLD_BUILDER_CONTENT_CAPABILITY_ID))) {
			throw new IOException("Project content capability identity is unsupported");
		}
		requireSha(config.WORLD_BUILDER_CONTENT_BUNDLE_SHA256,
			"content bundle fingerprint");
		requireSha(config.WORLD_BUILDER_CONTENT_DEFINITION_SHA256,
			"content definition fingerprint");
		requireSha(config.WORLD_BUILDER_CONTENT_ASSET_SHA256,
			"content asset fingerprint");

		Path expected = storage.workingRoot().resolve("content-bundle")
			.toAbsolutePath().normalize();
		Path requested = java.nio.file.Paths.get(configured);
		if (!requested.isAbsolute()) {
			requested = storage.workingRoot().resolve(requested);
		}
		requested = requested.toAbsolutePath().normalize();
		if (!requested.equals(expected)) {
			throw new IOException(
				"Project content bundle must be working/content-bundle");
		}
		Path root = safeDirectory(requested, "project content bundle");
		Path manifestPath = safeFile(root.resolve("manifest.json"),
			MAX_MANIFEST_BYTES, "project content manifest");
		String document = new String(Files.readAllBytes(manifestPath),
			StandardCharsets.UTF_8);
		StrictJsonScanner.validate(document);
		JSONObject manifest;
		try {
			manifest = new JSONObject(document);
		} catch (RuntimeException failure) {
			throw new IOException("Project content manifest is invalid JSON", failure);
		}
		requireKeys(manifest, ROOT_KEYS, "project content manifest");
		requireInteger(manifest, "schemaVersion", 1, "project content manifest");
		requireText(manifest, "manifestType", MANIFEST_TYPE,
			"project content manifest");
		requireText(manifest, "capabilityId", CAPABILITY_ID,
			"project content manifest");
		requireText(manifest, "sourceKind", "target-adopted",
			"project content manifest");

		JSONObject catalog = object(manifest, "definitionCatalog",
			"project content manifest");
		validateCatalog(catalog);
		validateBindings(array(manifest, "familyBindings",
			"project content manifest"));
		JSONArray rows = array(manifest, "files", "project content manifest");
		if (rows.length() != SPECS.size()) {
			throw new IOException("Project content inventory must contain exactly "
				+ SPECS.size() + " files");
		}

		Map<String, Path> paths = new LinkedHashMap<String, Path>();
		List<JSONObject> records = new ArrayList<JSONObject>();
		long total = 0L;
		for (int index = 0; index < SPECS.size(); index++) {
			Spec spec = SPECS.get(index);
			Object raw = rows.get(index);
			if (!(raw instanceof JSONObject)) {
				throw new IOException("Project content file row is not an object");
			}
			JSONObject row = (JSONObject) raw;
			requireKeys(row, FILE_KEYS, "project content file row");
			requireText(row, "role", spec.role, "project content file row");
			requireText(row, "runtimeRelativePath", spec.runtimePath,
				"project content file row");
			requireText(row, "bundleRelativePath", "files/" + spec.runtimePath,
				"project content file row");
			requireText(row, "mediaType", spec.mediaType,
				"project content file row");
			long size = exactLong(row, "size", "project content file row");
			String hash = text(row, "sha256", "project content file row");
			if (size < 1L || size > MAX_FILE_BYTES || !SHA256.matcher(hash).matches()) {
				throw new IOException("Project content file metadata is outside its bound");
			}
			total += size;
			if (total > MAX_TOTAL_BYTES) {
				throw new IOException("Project content bundle exceeds its total bound");
			}
			Path path = safeFile(root.resolve("files").resolve(spec.runtimePath),
				MAX_FILE_BYTES, "project content file " + spec.role);
			if (Files.size(path) != size || !hash.equals(sha256(path))) {
				throw new IOException("Project content file fingerprint mismatch: "
					+ spec.role);
			}
			paths.put(spec.role, path);
			records.add(row);
		}
		validateExactTree(root, paths.values());

		String catalogHash = text(catalog, "catalogSha256",
			"definition catalog");
		String expectedDefinition = recordFingerprint(
			"world-builder-project-content-definitions-v1\n", records, true,
			catalogHash);
		String expectedAssets = recordFingerprint(
			"world-builder-project-content-assets-v1\n", records, false, "");
		String definition = text(manifest, "definitionFingerprintSha256",
			"project content manifest");
		String assets = text(manifest, "assetFingerprintSha256",
			"project content manifest");
		if (!definition.equals(expectedDefinition)
			|| !assets.equals(expectedAssets)) {
			throw new IOException("Project content domain fingerprint mismatch");
		}
		String bundle = text(manifest, "bundleFingerprintSha256",
			"project content manifest");
		JSONObject zeroed = new JSONObject(manifest.toString());
		zeroed.put("bundleFingerprintSha256", ZERO_HASH);
		String calculatedBundle = sha256((
			"world-builder-project-content-bundle-v1\n" + canonical(zeroed))
			.getBytes(StandardCharsets.UTF_8));
		if (!bundle.equals(calculatedBundle)) {
			throw new IOException("Project content bundle fingerprint mismatch");
		}
		if (!bundle.equals(config.WORLD_BUILDER_CONTENT_BUNDLE_SHA256)
			|| !definition.equals(config.WORLD_BUILDER_CONTENT_DEFINITION_SHA256)
			|| !assets.equals(config.WORLD_BUILDER_CONTENT_ASSET_SHA256)) {
			throw new IOException(
				"Project content manifest differs from the launched identity");
		}
		return new AdaptiveWorldBuilderProjectContentBundle(
			root, catalog, paths, text(catalog, "catalogId", "definition catalog"),
			bundle, definition, assets);
	}

	public boolean isPresent() { return root != null; }
	public Path root() { return root; }
	public Path path(String role) {
		Path result = paths.get(role);
		if (result == null) throw new IllegalArgumentException("Unknown content role: " + role);
		return result;
	}
	public JSONObject catalog() { return catalog; }
	public String catalogId() { return catalogId; }
	public String bundleSha256() { return bundleSha256; }
	public String definitionSha256() { return definitionSha256; }
	public String assetSha256() { return assetSha256; }

	private static void validateCatalog(JSONObject catalog) throws IOException {
		requireKeys(catalog, CATALOG_KEYS, "definition catalog");
		requireInteger(catalog, "schemaVersion", 1, "definition catalog");
		requireText(catalog, "manifestType", CATALOG_TYPE, "definition catalog");
		String catalogId = text(catalog, "catalogId", "definition catalog");
		if (!catalogId.matches("[a-z0-9][a-z0-9._-]{0,127}")) {
			throw new IOException("Definition catalog identity is invalid");
		}
		validateIds(catalog, "tiles", true);
		validateIds(catalog, "boundaries", true);
		validateIds(catalog, "scenery", true);
		validateIds(catalog, "npcs", false);
		validateIds(catalog, "groundItems", false);
		String hash = text(catalog, "catalogSha256", "definition catalog");
		JSONObject zeroed = new JSONObject(catalog.toString());
		zeroed.put("catalogSha256", ZERO_HASH);
		if (!SHA256.matcher(hash).matches()
			|| !hash.equals(sha256(canonical(zeroed).getBytes(StandardCharsets.UTF_8)))) {
			throw new IOException("Definition catalog self fingerprint mismatch");
		}
	}

	private static void validateIds(JSONObject catalog, String key, boolean dense)
		throws IOException {
		JSONArray values = array(catalog, key, "definition catalog");
		if (values.length() < 1 || values.length() > 65536) {
			throw new IOException("Definition catalog " + key + " is outside its bound");
		}
		int previous = -1;
		for (int index = 0; index < values.length(); index++) {
			Object raw = values.get(index);
			if (!(raw instanceof Number)) {
				throw new IOException("Definition catalog ID is not an integer");
			}
			int value = ((Number) raw).intValue();
			if (((Number) raw).longValue() != value || value < 0 || value > 65535
				|| value <= previous || (dense && value != index)) {
				throw new IOException("Definition catalog " + key
					+ " has holes, duplicates, or noncanonical IDs");
			}
			previous = value;
		}
	}

	private static void validateBindings(JSONArray rows) throws IOException {
		if (rows.length() != BINDINGS.size()) {
			throw new IOException("Project content family bindings are incomplete");
		}
		for (int index = 0; index < BINDINGS.size(); index++) {
			Object raw = rows.get(index);
			if (!(raw instanceof JSONObject)) {
				throw new IOException("Project content family binding is not an object");
			}
			JSONObject row = (JSONObject) raw;
			requireKeys(row, BINDING_KEYS, "project content family binding");
			Binding expected = BINDINGS.get(index);
			requireText(row, "family", expected.family,
				"project content family binding");
			if (!strings(array(row, "definitionRoles", "family binding"))
				.equals(expected.definitionRoles)
				|| !strings(array(row, "assetRoles", "family binding"))
				.equals(expected.assetRoles)) {
				throw new IOException("Project content family binding differs from v1");
			}
		}
	}

	private static String recordFingerprint(
		String domain, List<JSONObject> rows, boolean definitions,
		String catalogHash) throws IOException {
		MessageDigest digest = digest();
		digest.update(domain.getBytes(StandardCharsets.UTF_8));
		for (int index = 0; index < SPECS.size(); index++) {
			Spec spec = SPECS.get(index);
			if (spec.definition != definitions) continue;
			JSONObject row = rows.get(index);
			String record = spec.role + "\0" + spec.runtimePath + "\0"
				+ exactLong(row, "size", "content row") + "\0"
				+ text(row, "sha256", "content row") + "\n";
			digest.update(record.getBytes(StandardCharsets.UTF_8));
		}
		if (!catalogHash.isEmpty()) {
			digest.update(catalogHash.getBytes(StandardCharsets.US_ASCII));
		}
		return hex(digest.digest());
	}

	private static void validateExactTree(Path root, Iterable<Path> expected)
		throws IOException {
		final Set<Path> allowed = new HashSet<Path>();
		allowed.add(root.resolve("manifest.json").toRealPath());
		for (Path path : expected) allowed.add(path.toRealPath());
		final Set<String> portable = new HashSet<String>();
		Files.walkFileTree(root, new SimpleFileVisitor<Path>() {
			@Override
			public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs)
				throws IOException {
				if (Files.isSymbolicLink(dir)) {
					throw new IOException("Project content bundle contains a directory link");
				}
				return FileVisitResult.CONTINUE;
			}
			@Override
			public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
				throws IOException {
				if (!attrs.isRegularFile() || Files.isSymbolicLink(file)
					|| !allowed.contains(file.toRealPath())) {
					throw new IOException("Project content bundle contains an unexpected entry");
				}
				String folded = root.relativize(file).toString().replace('\\', '/')
					.toLowerCase(java.util.Locale.ROOT);
				if (!portable.add(folded)) {
					throw new IOException("Project content bundle has a portable-name collision");
				}
				requireSingleLink(file, "project content file");
				return FileVisitResult.CONTINUE;
			}
		});
		if (allowed.size() != 1 + SPECS.size()) {
			throw new IOException("Project content inventory is incomplete");
		}
	}

	private static Path safeDirectory(Path path, String label) throws IOException {
		Path normalized = path.toAbsolutePath().normalize();
		if (!Files.isDirectory(normalized, LinkOption.NOFOLLOW_LINKS)
			|| Files.isSymbolicLink(normalized)) {
			throw new IOException(label + " is missing or unsafe");
		}
		return normalized.toRealPath();
	}

	private static Path safeFile(Path path, long maximum, String label)
		throws IOException {
		Path normalized = path.toAbsolutePath().normalize();
		if (!Files.isRegularFile(normalized, LinkOption.NOFOLLOW_LINKS)
			|| Files.isSymbolicLink(normalized)) {
			throw new IOException(label + " is missing or unsafe");
		}
		long size = Files.size(normalized);
		if (size < 1L || size > maximum) {
			throw new IOException(label + " is outside its size bound");
		}
		requireSingleLink(normalized, label);
		return normalized.toRealPath();
	}

	private static void requireSingleLink(Path path, String label) throws IOException {
		try {
			Object links = Files.getAttribute(path, "unix:nlink", LinkOption.NOFOLLOW_LINKS);
			if (links instanceof Number && ((Number) links).longValue() != 1L) {
				throw new IOException(label + " is hard linked");
			}
		} catch (UnsupportedOperationException unsupported) {
			path.toRealPath();
		}
	}

	private static void requireKeys(JSONObject value, Set<String> expected,
		String label) throws IOException {
		if (!expected.equals(value.keySet())) {
			throw new IOException(label + " contains unknown or missing keys");
		}
	}

	private static JSONObject object(JSONObject value, String key, String label)
		throws IOException {
		Object raw = value.opt(key);
		if (!(raw instanceof JSONObject)) throw new IOException(label + " " + key + " is not an object");
		return (JSONObject) raw;
	}

	private static JSONArray array(JSONObject value, String key, String label)
		throws IOException {
		Object raw = value.opt(key);
		if (!(raw instanceof JSONArray)) throw new IOException(label + " " + key + " is not an array");
		return (JSONArray) raw;
	}

	private static String text(JSONObject value, String key, String label)
		throws IOException {
		Object raw = value.opt(key);
		if (!(raw instanceof String)) throw new IOException(label + " " + key + " is not text");
		return (String) raw;
	}

	private static long exactLong(JSONObject value, String key, String label)
		throws IOException {
		Object raw = value.opt(key);
		if (!(raw instanceof Number)) throw new IOException(label + " " + key + " is not an integer");
		long result = ((Number) raw).longValue();
		if (raw instanceof Double || raw instanceof Float
			|| new BigDecimal(raw.toString()).compareTo(BigDecimal.valueOf(result)) != 0) {
			throw new IOException(label + " " + key + " is not an exact integer");
		}
		return result;
	}

	private static void requireInteger(JSONObject value, String key, int expected,
		String label) throws IOException {
		if (exactLong(value, key, label) != expected) {
			throw new IOException(label + " " + key + " is unsupported");
		}
	}

	private static void requireText(JSONObject value, String key, String expected,
		String label) throws IOException {
		if (!expected.equals(text(value, key, label))) {
			throw new IOException(label + " " + key + " differs from v1");
		}
	}

	private static List<String> strings(JSONArray values) throws IOException {
		List<String> result = new ArrayList<String>();
		for (Object value : values) {
			if (!(value instanceof String)) throw new IOException("Family binding role is not text");
			result.add((String) value);
		}
		return result;
	}

	private static String canonical(Object value) throws IOException {
		if (value == null || value == JSONObject.NULL) return "null";
		if (value instanceof JSONObject) {
			JSONObject object = (JSONObject) value;
			List<String> keys = new ArrayList<String>(object.keySet());
			Collections.sort(keys);
			StringBuilder out = new StringBuilder("{");
			for (int index = 0; index < keys.size(); index++) {
				if (index > 0) out.append(',');
				String key = keys.get(index);
				out.append(JSONObject.quote(key)).append(':')
					.append(canonical(object.get(key)));
			}
			return out.append('}').toString();
		}
		if (value instanceof JSONArray) {
			JSONArray array = (JSONArray) value;
			StringBuilder out = new StringBuilder("[");
			for (int index = 0; index < array.length(); index++) {
				if (index > 0) out.append(',');
				out.append(canonical(array.get(index)));
			}
			return out.append(']').toString();
		}
		if (value instanceof String) return JSONObject.quote((String) value);
		if (value instanceof Boolean) return value.toString();
		if (value instanceof Number) {
			String number = JSONObject.numberToString((Number) value);
			if (number.indexOf('.') >= 0 || number.indexOf('e') >= 0
				|| number.indexOf('E') >= 0) {
				throw new IOException("Project content manifest numbers must be integers");
			}
			return number;
		}
		throw new IOException("Project content manifest contains an unsupported value");
	}

	private static String sha256(Path path) throws IOException {
		MessageDigest digest = digest();
		byte[] buffer = new byte[8192];
		try (java.io.InputStream input = Files.newInputStream(path)) {
			for (int read; (read = input.read(buffer)) >= 0;) {
				if (read > 0) digest.update(buffer, 0, read);
			}
		}
		return hex(digest.digest());
	}

	private static String sha256(byte[] bytes) {
		MessageDigest digest = digest();
		return hex(digest.digest(bytes));
	}

	private static MessageDigest digest() {
		try { return MessageDigest.getInstance("SHA-256"); }
		catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
	}

	private static String hex(byte[] bytes) {
		StringBuilder out = new StringBuilder(bytes.length * 2);
		for (byte value : bytes) out.append(String.format("%02x", value & 0xff));
		return out.toString();
	}

	private static String trim(String value) { return value == null ? "" : value.trim(); }
	private static void requireEmpty(String value, String label) throws IOException {
		if (!trim(value).isEmpty()) throw new IOException(label + " requires a content bundle path");
	}
	private static void requireSha(String value, String label) throws IOException {
		if (!SHA256.matcher(trim(value)).matches()) throw new IOException(label + " is invalid");
	}
	private static String repeat(char value, int count) {
		char[] chars = new char[count]; Arrays.fill(chars, value); return new String(chars);
	}
	private static Set<String> set(String... values) {
		return Collections.unmodifiableSet(new HashSet<String>(Arrays.asList(values)));
	}

	private static List<Spec> specs() {
		List<Spec> values = Arrays.asList(
			new Spec("asset.sprite.authentic", "client/Cache/video/Authentic_Sprites.orsc", "application/vnd.openrsc.archive", false),
			new Spec("asset.sprite.custom", "client/Cache/video/Custom_Sprites.osar", "application/gzip", false),
			new Spec("asset.library", "client/Cache/video/library.orsc", "application/vnd.openrsc.archive", false),
			new Spec("asset.model", "client/Cache/video/models.orsc", "application/vnd.openrsc.archive", false),
			new Spec("asset.spritepack", "client/Cache/video/spritepacks/Menus.osar", "application/gzip", false),
			new Spec("definition.boundary", "server/conf/server/defs/DoorDef.xml", "application/xml", true),
			new Spec("definition.scenery", "server/conf/server/defs/GameObjectDef.xml", "application/xml", true),
			new Spec("definition.item.base", "server/conf/server/defs/ItemDefs.json", "application/json", true),
			new Spec("definition.item.custom", "server/conf/server/defs/ItemDefsCustom.json", "application/json", true),
			new Spec("definition.item.world", "server/conf/server/defs/ItemDefsMyWorld.json", "application/json", true),
			new Spec("definition.item.patch", "server/conf/server/defs/ItemDefsPatch18.json", "application/json", true),
			new Spec("definition.npc.base", "server/conf/server/defs/NpcDefs.json", "application/json", true),
			new Spec("definition.npc.custom", "server/conf/server/defs/NpcDefsCustom.json", "application/json", true),
			new Spec("definition.npc.world", "server/conf/server/defs/NpcDefsMyWorld.json", "application/json", true),
			new Spec("definition.npc.patch", "server/conf/server/defs/NpcDefsPatch18.json", "application/json", true),
			new Spec("definition.tile", "server/conf/server/defs/TileDef.xml", "application/xml", true));
		Collections.sort(values, new Comparator<Spec>() {
			public int compare(Spec left, Spec right) { return left.runtimePath.compareTo(right.runtimePath); }
		});
		return Collections.unmodifiableList(values);
	}

	private static List<Binding> bindings() {
		return Collections.unmodifiableList(Arrays.asList(
			new Binding("floor", Arrays.asList("definition.tile"), Arrays.asList("asset.sprite.custom")),
			new Binding("ground-item", Arrays.asList("definition.item.base", "definition.item.custom", "definition.item.patch", "definition.item.world"), Arrays.asList("asset.library", "asset.sprite.authentic", "asset.sprite.custom", "asset.spritepack")),
			new Binding("npc", Arrays.asList("definition.npc.base", "definition.npc.custom", "definition.npc.patch", "definition.npc.world"), Arrays.asList("asset.library", "asset.sprite.authentic", "asset.sprite.custom", "asset.spritepack")),
			new Binding("scenery", Arrays.asList("definition.scenery"), Arrays.asList("asset.library", "asset.model", "asset.sprite.custom")),
			new Binding("wall", Arrays.asList("definition.boundary"), Arrays.asList("asset.sprite.custom"))));
	}

	private static final class Spec {
		final String role, runtimePath, mediaType; final boolean definition;
		Spec(String role, String runtimePath, String mediaType, boolean definition) {
			this.role = role; this.runtimePath = runtimePath; this.mediaType = mediaType; this.definition = definition;
		}
	}
	private static final class Binding {
		final String family; final List<String> definitionRoles, assetRoles;
		Binding(String family, List<String> definitionRoles, List<String> assetRoles) {
			this.family = family; this.definitionRoles = definitionRoles; this.assetRoles = assetRoles;
		}
	}

	/** Minimal strict scanner used before org.json so duplicate keys fail closed. */
	private static final class StrictJsonScanner {
		private final String text; private int at;
		private StrictJsonScanner(String text) { this.text = text; }
		static void validate(String text) throws IOException {
			StrictJsonScanner scanner = new StrictJsonScanner(text);
			scanner.ws(); scanner.value(); scanner.ws();
			if (scanner.at != text.length()) scanner.fail("trailing content");
		}
		private void value() throws IOException {
			if (at >= text.length()) fail("missing value");
			char c = text.charAt(at);
			if (c == '{') object(); else if (c == '[') array(); else if (c == '"') string();
			else if (c == '-' || Character.isDigit(c)) number();
			else if (text.startsWith("true", at)) at += 4;
			else if (text.startsWith("false", at)) at += 5;
			else if (text.startsWith("null", at)) at += 4;
			else fail("invalid value");
		}
		private void object() throws IOException {
			at++; ws(); Set<String> keys = new HashSet<String>();
			if (take('}')) return;
			while (true) {
				if (at >= text.length() || text.charAt(at) != '"') fail("object key must be text");
				String key = string(); if (!keys.add(key)) fail("duplicate object key");
				ws(); expect(':'); ws(); value(); ws();
				if (take('}')) return; expect(','); ws();
			}
		}
		private void array() throws IOException {
			at++; ws(); if (take(']')) return;
			while (true) { value(); ws(); if (take(']')) return; expect(','); ws(); }
		}
		private String string() throws IOException {
			StringBuilder out = new StringBuilder(); expect('"');
			while (at < text.length()) {
				char c = text.charAt(at++); if (c == '"') return out.toString();
				if (c < 0x20) fail("control character in string");
				if (c != '\\') { out.append(c); continue; }
				if (at >= text.length()) fail("truncated escape");
				char escaped = text.charAt(at++);
				if (escaped == 'u') {
					if (at + 4 > text.length()) fail("truncated unicode escape");
					try { out.append((char) Integer.parseInt(text.substring(at, at + 4), 16)); }
					catch (NumberFormatException failure) { fail("invalid unicode escape"); }
					at += 4;
				} else {
					int pos = "\"\\/bfnrt".indexOf(escaped); if (pos < 0) fail("invalid escape");
					out.append(pos < 3 ? escaped : "\b\f\n\r\t".charAt(pos - 3));
				}
			}
			fail("unterminated string"); return "";
		}
		private void number() throws IOException {
			int start = at; if (take('-') && at >= text.length()) fail("invalid number");
			if (take('0')) { if (at < text.length() && Character.isDigit(text.charAt(at))) fail("leading zero"); }
			else { if (at >= text.length() || !Character.isDigit(text.charAt(at))) fail("invalid number"); while (at < text.length() && Character.isDigit(text.charAt(at))) at++; }
			if (at < text.length() && (text.charAt(at) == '.' || text.charAt(at) == 'e' || text.charAt(at) == 'E')) fail("manifest numbers must be integers");
			try { Long.parseLong(text.substring(start, at)); } catch (NumberFormatException failure) { fail("integer outside bound"); }
		}
		private void ws() { while (at < text.length() && " \t\r\n".indexOf(text.charAt(at)) >= 0) at++; }
		private boolean take(char c) { if (at < text.length() && text.charAt(at) == c) { at++; return true; } return false; }
		private void expect(char c) throws IOException { if (!take(c)) fail("expected " + c); }
		private void fail(String message) throws IOException { throw new IOException("Project content manifest " + message + " at byte " + at); }
	}
}
