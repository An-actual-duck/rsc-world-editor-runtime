package com.openrsc.server.io;

import com.openrsc.server.ServerConfiguration;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;

/** Loads the World Builder-owned server activation descriptor, when present. */
public final class WorldBuilderInstalledServerProfile {
	public static final String PROFILE_PROPERTY =
		"openrsc.worldBuilderInstalledServerProfile";
	public static final String DEFAULT_PROFILE =
		"world-builder-configs/installed-server.json";
	private static final String MANIFEST_TYPE =
		"world-builder-installed-server-profile";
	private static final Set<String> PROFILE_KEYS = keys(
		"schemaVersion", "manifestType", "active", "packageId",
		"packageVersion", "packageFingerprintSha256", "manifestSha256",
		"packageRelativePath");
	private static final Set<String> PACKAGE_KEYS = keys(
		"schemaVersion", "packageType", "packageId", "packageVersion",
		"coordinateModel", "worldSpaces", "levels", "storage",
		"terrainSectors", "placementSets");
	private static final String SHA256 = "[0-9a-f]{64}";

	private WorldBuilderInstalledServerProfile() {
	}

	public static void apply(final ServerConfiguration configuration)
		throws IOException {
		String configured = System.getProperty(
			PROFILE_PROPERTY, DEFAULT_PROFILE).trim();
		if (configured.isEmpty()) throw new IOException(
			"Installed server profile path is empty");
		Path profile = Paths.get(configured).toAbsolutePath().normalize();
		if (!Files.exists(profile, LinkOption.NOFOLLOW_LINKS)) return;
		requireRegular(profile, "installed server profile");
		Path profileDirectory = profile.getParent();
		if (profileDirectory == null || profileDirectory.getParent() == null) {
			throw new IOException("Installed server profile has no server root");
		}
		Path serverRoot = profileDirectory.getParent().toRealPath();
		JSONObject document = object(profile, "installed server profile");
		requireKeys(document, PROFILE_KEYS, "installed server profile");
		if (exactInt(document, "schemaVersion") != 1
			|| !MANIFEST_TYPE.equals(text(document, "manifestType"))) {
			throw new IOException("Installed server profile identity is unsupported");
		}
		Object rawActive = document.opt("active");
		if (!(rawActive instanceof Boolean)) throw new IOException(
			"Installed server profile active flag is invalid");
		if (!((Boolean)rawActive).booleanValue()) return;
		String packageId = identifier(document, "packageId");
		String packageVersion = identifier(document, "packageVersion");
		String packageFingerprint = hash(document, "packageFingerprintSha256");
		String manifestHash = hash(document, "manifestSha256");
		String relative = text(document, "packageRelativePath");
		Path relativePath = Paths.get(relative).normalize();
		if (relativePath.isAbsolute() || relativePath.getNameCount() < 4
			|| !"world-builder".equals(relativePath.getName(0).toString())
			|| !"packages".equals(relativePath.getName(1).toString())
			|| !packageFingerprint.equals(relativePath.getName(2).toString())
			|| !"package".equals(relativePath.getFileName().toString())
			|| !relativePath.toString().replace('\\', '/').equals(relative)) {
			throw new IOException("Installed server package path is unsafe");
		}
		Path packageRoot = serverRoot.resolve(relativePath).normalize();
		if (!packageRoot.startsWith(serverRoot)
			|| !Files.isDirectory(packageRoot, LinkOption.NOFOLLOW_LINKS)
			|| Files.isSymbolicLink(packageRoot)) {
			throw new IOException("Installed server package root is missing or unsafe");
		}
		Path manifest = packageRoot.resolve("manifest.json").normalize();
		requireRegular(manifest, "installed package manifest");
		if (!manifestHash.equals(sha256(manifest))) throw new IOException(
			"Installed package manifest SHA-256 does not match the server profile");
		JSONObject packageDocument = object(manifest, "installed package manifest");
		requireKeys(packageDocument, PACKAGE_KEYS, "installed package manifest");
		if (exactInt(packageDocument, "schemaVersion") != 1
			|| !"layered-world".equals(text(packageDocument, "packageType"))
			|| !"signed-layered-v1".equals(text(packageDocument, "coordinateModel"))
			|| !packageId.equals(text(packageDocument, "packageId"))
			|| !packageVersion.equals(text(packageDocument, "packageVersion"))) {
			throw new IOException(
				"Installed package identity does not match the server profile");
		}

		configuration.WANT_SYNC_SCENE_BASELINE = true;
		configuration.WANT_LAYERED_PLAYER_LOCATION_AUTHORITY = true;
		configuration.WANT_LAYERED_SPATIAL_RUNTIME_AUTHORITY = true;
		configuration.WANT_LAYERED_PROTOCOL_CLIENT_AUTHORITY = true;
		configuration.WANT_LAYERED_SYNTHETIC_DEEP_FIXTURE = false;
		configuration.WANT_LAYERED_NATIVE_TERRAIN_PACKAGE = true;
		configuration.WANT_LAYERED_NATIVE_TERRAIN_RESIDENCY = true;
		configuration.WANT_LAYERED_NATIVE_TERRAIN_READINESS = true;
		configuration.WANT_LAYERED_NATIVE_TERRAIN_PREDICTION = true;
		configuration.WANT_LAYERED_NATIVE_TERRAIN_SYMMETRIC_RESIDENCY = true;
		configuration.WANT_LAYERED_NATIVE_TERRAIN_ATOMIC_ACTIVATION = true;
		configuration.LAYERED_NATIVE_TERRAIN_PACKAGE_PATH = relative;
		configuration.LAYERED_NATIVE_TERRAIN_MANIFEST_SHA256 = manifestHash;
		configuration.LAYERED_NATIVE_TERRAIN_INVENTORY_SHA256 = "";
		configuration.LAYERED_NATIVE_WORLD_RUNTIME_PROFILE =
			NativeLayeredWorldRuntimeProfile.WORLD_BUILDER_INSTALLED.getId();
	}

	private static JSONObject object(Path path, String label) throws IOException {
		try {
			return new JSONObject(new String(
				Files.readAllBytes(path), StandardCharsets.UTF_8));
		} catch (RuntimeException malformed) {
			throw new IOException(label + " JSON is malformed", malformed);
		}
	}

	private static void requireRegular(Path path, String label) throws IOException {
		if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)
			|| Files.isSymbolicLink(path)) {
			throw new IOException(label + " is missing or unsafe");
		}
	}

	private static void requireKeys(JSONObject value, Set<String> expected, String label)
		throws IOException {
		if (!new TreeSet<String>(value.keySet()).equals(expected)) {
			throw new IOException(label + " fields are not exact");
		}
	}

	private static int exactInt(JSONObject value, String key) throws IOException {
		Object raw = value.opt(key);
		if (!(raw instanceof Number)
			|| ((Number)raw).longValue() != ((Number)raw).doubleValue()
			|| ((Number)raw).longValue() < Integer.MIN_VALUE
			|| ((Number)raw).longValue() > Integer.MAX_VALUE) {
			throw new IOException("Installed server profile " + key + " is invalid");
		}
		return ((Number)raw).intValue();
	}

	private static String identifier(JSONObject value, String key) throws IOException {
		String result = text(value, key);
		if (!result.matches("[a-z0-9][a-z0-9._-]{0,127}")) throw new IOException(
			"Installed server profile " + key + " is invalid");
		return result;
	}

	private static String hash(JSONObject value, String key) throws IOException {
		String result = text(value, key).toLowerCase(Locale.ROOT);
		if (!result.matches(SHA256)) throw new IOException(
			"Installed server profile " + key + " is invalid");
		return result;
	}

	private static String text(JSONObject value, String key) throws IOException {
		Object raw = value.opt(key);
		if (!(raw instanceof String) || ((String)raw).isEmpty()) throw new IOException(
			"Installed server profile " + key + " is invalid");
		return (String)raw;
	}

	private static String sha256(Path path) throws IOException {
		try {
			MessageDigest digest = MessageDigest.getInstance("SHA-256");
			byte[] buffer = new byte[8192];
			try (InputStream input = Files.newInputStream(path)) {
				for (int count; (count = input.read(buffer)) >= 0;) {
					if (count > 0) digest.update(buffer, 0, count);
				}
			}
			StringBuilder value = new StringBuilder();
			for (byte item : digest.digest()) {
				value.append(String.format(Locale.ROOT, "%02x", item & 0xff));
			}
			return value.toString();
		} catch (NoSuchAlgorithmException impossible) {
			throw new IOException("SHA-256 is unavailable", impossible);
		}
	}

	private static Set<String> keys(String... values) {
		return new TreeSet<String>(java.util.Arrays.asList(values));
	}
}
