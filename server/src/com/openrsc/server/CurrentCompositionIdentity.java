package com.openrsc.server;

import com.openrsc.server.net.Packet;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Properties;
import java.util.Set;
import java.util.regex.Pattern;

/** Runtime authority for a provider-bound current server composition. */
public final class CurrentCompositionIdentity {
	public static final String IDENTITY_FILE_PROPERTY =
		"openrsc.currentCompositionIdentityFile";
	public static final String HANDSHAKE_ID = "current-composition-handshake-v1";
	public static final int HANDSHAKE_OPCODE = 18;
	private static final String MARKER_RESOURCE =
		"/META-INF/rsc-current-composition.properties";
	private static final String ARTIFACT_CONTRACT =
		"current-platform-runtime-artifact-v1";
	private static final Pattern ID =
		Pattern.compile("[a-z][a-z0-9]*(?:-[a-z0-9]+)*");
	private static final Pattern SHA256 = Pattern.compile("[0-9a-f]{64}");
	private static final Set<String> DOCUMENT_KEYS = Collections.unmodifiableSet(
		new LinkedHashSet<String>(Arrays.asList(
			"schemaId", "manifestType", "platformReleaseId",
			"platformManifestHash", "schemaSetHash", "variantId",
			"variantManifestHash", "moduleSetHash", "bundleInventoryHash",
			"moduleSet", "bundleInventory", "bundleSpecId", "bundleSpecHash",
			"inputAdapterContractId", "installable")));
	private static final String[] IDENTITY_FIELDS = {
		"platformReleaseId", "platformManifestHash", "variantId",
		"variantManifestHash", "moduleSetHash", "bundleInventoryHash"
	};
	private static final Set<String> MARKER_KEYS = Collections.unmodifiableSet(
		new LinkedHashSet<String>(Arrays.asList(
			"artifactContract", "handshakeId", "moduleSetHash",
			"platformManifestHash", "platformReleaseId", "variantId",
			"variantManifestHash")));
	private static volatile CurrentCompositionIdentity current = disabled();

	private final boolean enabled;
	private final Map<String, String> fields;

	private CurrentCompositionIdentity(boolean enabled, Map<String, String> fields) {
		this.enabled = enabled;
		this.fields = Collections.unmodifiableMap(
			new LinkedHashMap<String, String>(fields));
	}

	public static synchronized CurrentCompositionIdentity initializeFromSystemProperties() {
		InputStream marker = CurrentCompositionIdentity.class.getResourceAsStream(
			MARKER_RESOURCE);
		String configured = System.getProperty(IDENTITY_FILE_PROPERTY, "").trim();
		if (marker == null) {
			if (!configured.isEmpty()) {
				throw new IllegalArgumentException(
					"composition identity was supplied to an unbound server artifact");
			}
			current = disabled();
			return current;
		}
		if (configured.isEmpty()) {
			closeQuietly(marker);
			throw new IllegalArgumentException(
				IDENTITY_FILE_PROPERTY + " is required by this server artifact");
		}
		try {
			CurrentCompositionIdentity loaded = load(Paths.get(configured));
			loaded.requireArtifactMarker(marker);
			current = loaded;
			return current;
		} catch (IOException exception) {
			throw new IllegalArgumentException(
				"cannot load current server composition identity: "
					+ exception.getMessage(), exception);
		}
	}

	public static CurrentCompositionIdentity current() {
		return current;
	}

	public boolean isEnabled() {
		return enabled;
	}

	public String value(String field) {
		String value = fields.get(field);
		if (value == null) {
			throw new IllegalArgumentException("unknown composition identity field: " + field);
		}
		return value;
	}

	public void requireClientHandshake(Packet packet) {
		if (!enabled) {
			throw new IllegalArgumentException(
				"composition handshake sent to an unbound server");
		}
		try {
			String handshake = packet.readString();
			if (!HANDSHAKE_ID.equals(handshake)) {
				throw new IllegalArgumentException("client composition handshake id differs");
			}
			for (String field : IDENTITY_FIELDS) {
				String supplied = packet.readString();
				if (!value(field).equals(supplied)) {
					throw new IllegalArgumentException(
						"client composition differs at " + field);
				}
			}
			if (packet.getBuffer().isReadable()) {
				throw new IllegalArgumentException(
					"client composition handshake has trailing data");
			}
		} catch (IndexOutOfBoundsException exception) {
			throw new IllegalArgumentException(
				"client composition handshake is truncated", exception);
		}
	}

	public static String[] identityFields() {
		return IDENTITY_FIELDS.clone();
	}

	private static CurrentCompositionIdentity load(Path configured) throws IOException {
		Path path = configured.toAbsolutePath().normalize();
		if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
			throw new IOException("identity path is not a regular file: " + path);
		}
		JSONObject document = new JSONObject(new String(
			Files.readAllBytes(path), StandardCharsets.UTF_8));
		if (!document.keySet().equals(DOCUMENT_KEYS)) {
			throw new IOException("identity document keys differ from the closed contract");
		}
		if (!"current-composition-identity-v1".equals(document.optString("schemaId"))
			|| !"current-platform-composition-identity".equals(
				document.optString("manifestType"))) {
			throw new IOException("identity document has wrong contract type");
		}
		Map<String, String> fields = new LinkedHashMap<String, String>();
		for (String field : IDENTITY_FIELDS) {
			Object raw = document.get(field);
			if (!(raw instanceof String)) {
				throw new IOException("identity field is not a string: " + field);
			}
			String value = (String)raw;
			Pattern pattern = field.endsWith("Hash") ? SHA256 : ID;
			if (!pattern.matcher(value).matches()) {
				throw new IOException("identity field is malformed: " + field);
			}
			fields.put(field, value);
		}
		return new CurrentCompositionIdentity(true, fields);
	}

	private void requireArtifactMarker(InputStream input) throws IOException {
		Properties marker = new Properties();
		try {
			marker.load(input);
		} finally {
			input.close();
		}
		if (!marker.stringPropertyNames().equals(MARKER_KEYS)) {
			throw new IOException("server artifact marker keys differ from the contract");
		}
		if (!ARTIFACT_CONTRACT.equals(marker.getProperty("artifactContract"))
			|| !HANDSHAKE_ID.equals(marker.getProperty("handshakeId"))) {
			throw new IOException("server artifact marker has wrong contract identity");
		}
		for (String field : IDENTITY_FIELDS) {
			if ("bundleInventoryHash".equals(field)) {
				continue;
			}
			if (!value(field).equals(marker.getProperty(field))) {
				throw new IOException("server artifact differs at " + field);
			}
		}
	}

	private static CurrentCompositionIdentity disabled() {
		return new CurrentCompositionIdentity(false,
			Collections.<String, String>emptyMap());
	}

	private static void closeQuietly(InputStream input) {
		try {
			input.close();
		} catch (IOException ignored) {
		}
	}

	public static void main(String[] args) {
		try {
			CurrentCompositionIdentity identity = initializeFromSystemProperties();
			if (!identity.isEnabled()) {
				throw new IllegalArgumentException("server artifact is not composition-bound");
			}
			System.out.println("Current server composition accepted: "
				+ identity.value("variantId"));
		} catch (IllegalArgumentException exception) {
			System.err.println("Current server startup refused: " + exception.getMessage());
			System.exit(2);
		}
	}
}
