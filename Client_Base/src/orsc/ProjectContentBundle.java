package orsc;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
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
import java.util.regex.Pattern;

/** Client-side verifier and path router for project-content-bundle-v1. */
public final class ProjectContentBundle {
	public static final String CAPABILITY_ID = "project-local-custom-content-v1";
	private static final String MANIFEST_TYPE = "world-builder-project-content-bundle";
	private static final String ZERO_HASH =
		"0000000000000000000000000000000000000000000000000000000000000000";
	private static final Pattern SHA = Pattern.compile("[0-9a-f]{64}");
	private static final long MAX_FILE = 256L * 1024L * 1024L;
	private static final List<Spec> SPECS = specs();
	private static final ProjectContentBundle EMPTY =
		new ProjectContentBundle(null, null, Collections.<String, Path>emptyMap());

	private final Path root;
	private final JSONObject catalog;
	private final Map<String, Path> paths;

	private ProjectContentBundle(Path root, JSONObject catalog,
		Map<String, Path> paths) {
		this.root = root;
		this.catalog = catalog;
		this.paths = Collections.unmodifiableMap(
			new LinkedHashMap<String, Path>(paths));
	}

	public static ProjectContentBundle empty() { return EMPTY; }

	public static ProjectContentBundle load(
		Path workspaceRoot, String requestedPath, String capability,
		String expectedBundle, String expectedDefinitions, String expectedAssets)
		throws IOException {
		String requested = trim(requestedPath);
		if (requested.isEmpty()) {
			if (!trim(capability).isEmpty() || !trim(expectedBundle).isEmpty()
				|| !trim(expectedDefinitions).isEmpty() || !trim(expectedAssets).isEmpty()) {
				throw new IOException("Content identities require a bundle path");
			}
			return EMPTY;
		}
		if (!CAPABILITY_ID.equals(capability) || !SHA.matcher(expectedBundle).matches()
			|| !SHA.matcher(expectedDefinitions).matches()
			|| !SHA.matcher(expectedAssets).matches()) {
			throw new IOException("Project content launch identities are invalid");
		}
		Path expected = workspaceRoot.resolve("working/content-bundle")
			.toAbsolutePath().normalize();
		Path root = java.nio.file.Paths.get(requested);
		if (!root.isAbsolute()) root = workspaceRoot.resolve(root);
		root = root.toAbsolutePath().normalize();
		if (!root.equals(expected) || !Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)
			|| Files.isSymbolicLink(root)) {
			throw new IOException("Project content must be working/content-bundle");
		}
		root = root.toRealPath();
		Path manifestPath = safeFile(root.resolve("manifest.json"), 16L * 1024L * 1024L);
		JSONObject manifest = new JSONObject(new String(
			Files.readAllBytes(manifestPath), StandardCharsets.UTF_8));
		requireKeys(manifest, set(
			"schemaVersion", "manifestType", "capabilityId", "sourceKind",
			"definitionCatalog", "familyBindings", "files",
			"definitionFingerprintSha256", "assetFingerprintSha256",
			"bundleFingerprintSha256"));
		expectInt(manifest, "schemaVersion", 1);
		expect(manifest, "manifestType", MANIFEST_TYPE);
		expect(manifest, "capabilityId", CAPABILITY_ID);
		expect(manifest, "sourceKind", "target-adopted");
		JSONObject catalog = manifest.getJSONObject("definitionCatalog");
		validateCatalog(catalog);
		validateBindings(manifest.getJSONArray("familyBindings"));

		JSONArray rows = manifest.getJSONArray("files");
		if (rows.length() != SPECS.size()) throw new IOException("Content inventory is incomplete");
		Map<String, Path> paths = new LinkedHashMap<String, Path>();
		List<JSONObject> records = new ArrayList<JSONObject>();
		long total = 0L;
		for (int index = 0; index < SPECS.size(); index++) {
			Spec spec = SPECS.get(index); JSONObject row = rows.getJSONObject(index);
			requireKeys(row, set("role", "bundleRelativePath", "runtimeRelativePath",
				"mediaType", "size", "sha256"));
			expect(row, "role", spec.role); expect(row, "runtimeRelativePath", spec.path);
			expect(row, "bundleRelativePath", "files/" + spec.path);
			expect(row, "mediaType", spec.media);
			long size = row.getLong("size"); String hash = row.getString("sha256");
			if (size < 1L || size > MAX_FILE || !SHA.matcher(hash).matches()) {
				throw new IOException("Content file metadata is outside its bound");
			}
			total += size; if (total > 1024L * 1024L * 1024L) throw new IOException("Content bundle is too large");
			Path path = safeFile(root.resolve("files").resolve(spec.path), MAX_FILE);
			if (Files.size(path) != size || !hash.equals(sha256(path))) {
				throw new IOException("Content file fingerprint mismatch: " + spec.role);
			}
			paths.put(spec.role, path); records.add(row);
		}
		Set<Path> actual = new HashSet<Path>();
		try (java.util.stream.Stream<Path> stream = Files.walk(root)) {
			stream.forEach(path -> {
				if (Files.isSymbolicLink(path)) throw new UnsafeBundle("Content bundle contains a link");
				if (Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) actual.add(path.toAbsolutePath().normalize());
			});
		} catch (UnsafeBundle failure) { throw new IOException(failure.getMessage()); }
		Set<Path> expectedFiles = new HashSet<Path>(paths.values()); expectedFiles.add(manifestPath);
		if (!actual.equals(expectedFiles)) throw new IOException("Content bundle contains extra files");

		String definition = fingerprint("world-builder-project-content-definitions-v1\n",
			records, true, catalog.getString("catalogSha256"));
		String assets = fingerprint("world-builder-project-content-assets-v1\n",
			records, false, "");
		if (!definition.equals(manifest.getString("definitionFingerprintSha256"))
			|| !assets.equals(manifest.getString("assetFingerprintSha256"))) {
			throw new IOException("Content domain fingerprint mismatch");
		}
		JSONObject zero = new JSONObject(manifest.toString());
		zero.put("bundleFingerprintSha256", ZERO_HASH);
		String bundle = sha256(("world-builder-project-content-bundle-v1\n"
			+ canonical(zero)).getBytes(StandardCharsets.UTF_8));
		if (!bundle.equals(manifest.getString("bundleFingerprintSha256"))
			|| !bundle.equals(expectedBundle) || !definition.equals(expectedDefinitions)
			|| !assets.equals(expectedAssets)) {
			throw new IOException("Content identity differs between client and server");
		}
		return new ProjectContentBundle(root, catalog, paths);
	}

	public boolean isPresent() { return root != null; }
	public JSONObject catalog() { return catalog; }
	public Path path(String role) {
		Path path = paths.get(role);
		if (path == null) throw new IllegalArgumentException("Unknown project content role: " + role);
		return path;
	}
	public Path assetForRuntimePath(String runtimePath) {
		for (Spec spec : SPECS) if (!spec.definition && spec.path.equals(runtimePath)) return path(spec.role);
		return null;
	}

	private static void validateCatalog(JSONObject catalog) throws IOException {
		requireKeys(catalog, set("schemaVersion", "manifestType", "catalogId", "tiles",
			"boundaries", "scenery", "npcs", "groundItems", "catalogSha256"));
		expectInt(catalog, "schemaVersion", 1);
		expect(catalog, "manifestType", "world-builder-definition-catalog");
		for (String family : Arrays.asList("tiles", "boundaries", "scenery", "npcs", "groundItems")) {
			JSONArray ids = catalog.getJSONArray(family); int previous = -1;
			if (ids.length() < 1 || ids.length() > 65536) throw new IOException("Catalog family is outside its bound");
			for (int index = 0; index < ids.length(); index++) {
				int id = ids.getInt(index);
				if (id < 0 || id > 65535 || id <= previous
					|| ((family.equals("tiles") || family.equals("boundaries") || family.equals("scenery")) && id != index)) {
					throw new IOException("Catalog IDs are not canonical");
				}
				previous = id;
			}
		}
		JSONObject zero = new JSONObject(catalog.toString()); zero.put("catalogSha256", ZERO_HASH);
		if (!catalog.getString("catalogSha256").equals(
				sha256(canonical(zero).getBytes(StandardCharsets.UTF_8)))) {
			throw new IOException("Catalog self fingerprint mismatch");
		}
	}

	private static void validateBindings(JSONArray bindings) throws IOException {
		String expected = "[{\"assetRoles\":[\"asset.sprite.custom\"],\"definitionRoles\":[\"definition.tile\"],\"family\":\"floor\"},{\"assetRoles\":[\"asset.library\",\"asset.sprite.authentic\",\"asset.sprite.custom\",\"asset.spritepack\"],\"definitionRoles\":[\"definition.item.base\",\"definition.item.custom\",\"definition.item.patch\",\"definition.item.world\"],\"family\":\"ground-item\"},{\"assetRoles\":[\"asset.library\",\"asset.sprite.authentic\",\"asset.sprite.custom\",\"asset.spritepack\"],\"definitionRoles\":[\"definition.npc.base\",\"definition.npc.custom\",\"definition.npc.patch\",\"definition.npc.world\"],\"family\":\"npc\"},{\"assetRoles\":[\"asset.library\",\"asset.model\",\"asset.sprite.custom\"],\"definitionRoles\":[\"definition.scenery\"],\"family\":\"scenery\"},{\"assetRoles\":[\"asset.sprite.custom\"],\"definitionRoles\":[\"definition.boundary\"],\"family\":\"wall\"}]";
		if (!expected.equals(canonical(bindings))) throw new IOException("Family bindings differ from v1");
	}

	private static String fingerprint(String domain, List<JSONObject> rows,
		boolean definitions, String catalogHash) throws IOException {
		MessageDigest digest = digest(); digest.update(domain.getBytes(StandardCharsets.UTF_8));
		for (int index = 0; index < SPECS.size(); index++) {
			Spec spec = SPECS.get(index); if (spec.definition != definitions) continue;
			JSONObject row = rows.get(index);
			digest.update((spec.role + "\0" + spec.path + "\0" + row.getLong("size")
				+ "\0" + row.getString("sha256") + "\n").getBytes(StandardCharsets.UTF_8));
		}
		if (!catalogHash.isEmpty()) digest.update(catalogHash.getBytes(StandardCharsets.US_ASCII));
		return hex(digest.digest());
	}

	private static Path safeFile(Path path, long maximum) throws IOException {
		Path result = path.toAbsolutePath().normalize();
		if (!Files.isRegularFile(result, LinkOption.NOFOLLOW_LINKS) || Files.isSymbolicLink(result)
			|| Files.size(result) < 1L || Files.size(result) > maximum) throw new IOException("Content file is missing or unsafe");
		try {
			Object links = Files.getAttribute(
				result, "unix:nlink", LinkOption.NOFOLLOW_LINKS);
			if (links instanceof Number && ((Number) links).longValue() != 1L) {
				throw new IOException("Content file is hard linked");
			}
		} catch (UnsupportedOperationException unsupported) {
			result.toRealPath();
		}
		return result.toRealPath();
	}
	private static void requireKeys(JSONObject value, Set<String> keys) throws IOException {
		if (!value.keySet().equals(keys)) throw new IOException("Content JSON contains unknown or missing keys");
	}
	private static void expect(JSONObject value, String key, String expected) throws IOException {
		if (!(value.opt(key) instanceof String) || !expected.equals(value.optString(key))) throw new IOException("Content " + key + " differs from v1");
	}
	private static void expectInt(JSONObject value, String key, int expected) throws IOException {
		if (!(value.opt(key) instanceof Number) || value.getInt(key) != expected) throw new IOException("Content " + key + " differs from v1");
	}
	private static Set<String> set(String... values) { return new HashSet<String>(Arrays.asList(values)); }
	private static String trim(String value) { return value == null ? "" : value.trim(); }
	private static String canonical(Object value) throws IOException {
		if (value == null || value == JSONObject.NULL) return "null";
		if (value instanceof JSONObject) {
			JSONObject object = (JSONObject) value; List<String> keys = new ArrayList<String>(object.keySet()); Collections.sort(keys);
			StringBuilder out = new StringBuilder("{");
			for (int i = 0; i < keys.size(); i++) { if (i > 0) out.append(','); String key = keys.get(i); out.append(JSONObject.quote(key)).append(':').append(canonical(object.get(key))); }
			return out.append('}').toString();
		}
		if (value instanceof JSONArray) {
			JSONArray array = (JSONArray) value; StringBuilder out = new StringBuilder("[");
			for (int i = 0; i < array.length(); i++) { if (i > 0) out.append(','); out.append(canonical(array.get(i))); }
			return out.append(']').toString();
		}
		if (value instanceof String) return JSONObject.quote((String) value);
		if (value instanceof Boolean || value instanceof Number) return value.toString();
		throw new IOException("Unsupported content JSON value");
	}
	private static String sha256(Path path) throws IOException {
		MessageDigest digest = digest(); byte[] buffer = new byte[8192];
		try (java.io.InputStream input = Files.newInputStream(path)) { for (int read; (read = input.read(buffer)) >= 0;) if (read > 0) digest.update(buffer, 0, read); }
		return hex(digest.digest());
	}
	private static String sha256(byte[] bytes) { return hex(digest().digest(bytes)); }
	private static MessageDigest digest() { try { return MessageDigest.getInstance("SHA-256"); } catch (NoSuchAlgorithmException e) { throw new IllegalStateException(e); } }
	private static String hex(byte[] bytes) { StringBuilder out = new StringBuilder(); for (byte value : bytes) out.append(String.format("%02x", value & 0xff)); return out.toString(); }

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
		Collections.sort(values, new Comparator<Spec>() { public int compare(Spec a, Spec b) { return a.path.compareTo(b.path); } });
		return Collections.unmodifiableList(values);
	}
	private static final class Spec {
		final String role, path, media; final boolean definition;
		Spec(String role, String path, String media, boolean definition) { this.role = role; this.path = path; this.media = media; this.definition = definition; }
	}
	private static final class UnsafeBundle extends RuntimeException { UnsafeBundle(String message) { super(message); } }
}
