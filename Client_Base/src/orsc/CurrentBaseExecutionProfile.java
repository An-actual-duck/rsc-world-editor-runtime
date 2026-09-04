package orsc;

import org.json.JSONObject;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.Set;
import java.util.TreeSet;

/**
 * Opt-in loopback evidence profile for the built Current Base desktop client.
 *
 * <p>This does not replace normal login or gameplay.  It supplies a sealed
 * disposable account to those paths and exits only after their runtime state
 * is observable.</p>
 */
public final class CurrentBaseExecutionProfile {
	public static final String ENABLED_PROPERTY =
		"openrsc.currentBaseExecutionEvidence";
	private static final Set<String> CREDENTIAL_KEYS = new TreeSet<String>(
		Arrays.asList("username", "password"));
	private static CurrentBaseExecutionProfile current = disabled();

	private final boolean enabled;
	private final String host;
	private final int port;
	private final String username;
	private final String password;

	private CurrentBaseExecutionProfile(boolean enabled, String host, int port,
		String username, String password) {
		this.enabled = enabled;
		this.host = host;
		this.port = port;
		this.username = username;
		this.password = password;
	}

	public static synchronized CurrentBaseExecutionProfile
		initializeFromSystemProperties() {
		String raw = System.getProperty(ENABLED_PROPERTY, "false").trim();
		if (!"true".equals(raw) && !"false".equals(raw)) throw new
			IllegalArgumentException(ENABLED_PROPERTY + " must be true or false");
		if (!Boolean.parseBoolean(raw)) {
			current = disabled();
			return current;
		}
		CurrentCompositionIdentity identity = CurrentCompositionIdentity.current();
		if (!identity.isEnabled()
			|| !"current-base-v1".equals(identity.value("variantId"))) throw new
			IllegalArgumentException("Current Base execution requires its bound composition");
		if (WorldBuilderClientProfile.isEnabled()) throw new IllegalArgumentException(
			"Current Base execution cannot enable World Builder mode");
		if (!WorldBuilderInstalledClientProfile.current().isEnabled()) throw new
			IllegalArgumentException("Current Base execution requires an installed canonical map");
		String host = System.getProperty("openrsc.currentBaseHost", "").trim();
		if (!"127.0.0.1".equals(host)) throw new IllegalArgumentException(
			"Current Base execution endpoint must be literal loopback 127.0.0.1");
		int port = integer("openrsc.currentBasePort", 1, 65535);
		Path credential = Paths.get(System.getProperty(
			"openrsc.currentBaseCredentialFile", "")).toAbsolutePath().normalize();
		if (!Files.isRegularFile(credential, LinkOption.NOFOLLOW_LINKS)
			|| Files.isSymbolicLink(credential)) throw new IllegalArgumentException(
			"Current Base execution credential must be a regular non-link file");
		try {
			if (Files.size(credential) > 4096) throw new IOException(
				"credential exceeds 4096 bytes");
			JSONObject document = new JSONObject(new String(
				Files.readAllBytes(credential), StandardCharsets.UTF_8));
			if (!new TreeSet<String>(document.keySet()).equals(CREDENTIAL_KEYS)) throw new
				IOException("credential fields differ from the closed format");
			String username = document.getString("username");
			String password = document.getString("password");
			if (!username.matches("[A-Za-z0-9_]{1,12}")
				|| password.length() < 5 || password.length() > 20) throw new IOException(
				"credential values are invalid");
			current = new CurrentBaseExecutionProfile(
				true, host, port, username, password);
			return current;
		} catch (IOException | RuntimeException failure) {
			throw new IllegalArgumentException(
				"cannot load Current Base execution credential: " + failure.getMessage(),
				failure);
		}
	}

	public static CurrentBaseExecutionProfile current() {
		return current;
	}

	public boolean isEnabled() {
		return enabled;
	}

	public void applyConnection() {
		if (!enabled) return;
		Config.SERVER_IP = host;
		Config.SERVER_PORT = port;
	}

	public String username() {
		return username;
	}

	public String password() {
		return password;
	}

	private static int integer(String property, int minimum, int maximum) {
		try {
			int value = Integer.parseInt(System.getProperty(property, "").trim());
			if (value < minimum || value > maximum) throw new NumberFormatException();
			return value;
		} catch (NumberFormatException failure) {
			throw new IllegalArgumentException(property + " is invalid");
		}
	}

	private static CurrentBaseExecutionProfile disabled() {
		return new CurrentBaseExecutionProfile(false, "", 0, "", "");
	}
}
