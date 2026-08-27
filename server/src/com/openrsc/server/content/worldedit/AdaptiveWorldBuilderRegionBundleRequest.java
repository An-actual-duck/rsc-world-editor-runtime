package com.openrsc.server.content.worldedit;

import com.openrsc.server.model.entity.player.Player;
import org.json.JSONObject;

import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.regex.Pattern;

/** Authenticates and publishes one client-staged portable Region Import/Export request. */
public final class AdaptiveWorldBuilderRegionBundleRequest {
	public static final String PENDING_FILE = ".region-bundle.request.pending.json";
	public static final String REQUEST_FILE = "region-bundle.request.json";
	public static final String RESPONSE_FILE = "region-bundle.response.json";
	private static final String RESPONSE_STAGE = ".region-bundle.response.runtime.tmp";
	private static final long MAX_REQUEST_BYTES = 256L * 1024L;
	private static final Pattern REQUEST_ID = Pattern.compile("[0-9a-f]{32}");
	private static final Pattern SNAPSHOT_ID = Pattern.compile("[0-9a-f]{64}");
	private static final Set<String> REQUEST_KEYS = new HashSet<String>(Arrays.asList(
		"schemaVersion", "manifestType", "requestId", "operation", "snapshotId",
		"bundlePath", "outputPath"));

	private AdaptiveWorldBuilderRegionBundleRequest() {
	}

	public static void submit(Player player) {
		String requestId = "00000000000000000000000000000000";
		String operation = "unknown";
		Path pending = null;
		try {
			if (player == null || !player.isAdmin()
				|| !AdaptiveWorldBuilderRuntimeIdentity.isAdaptive(player.getConfig())) {
				throw new IOException(
					"Region sharing is restricted to the isolated adaptive World Builder.");
			}
			WorldEditorSessionManager editor =
				player.getWorld().getServer().getWorldEditorSessions();
			if (!editor.ownsActiveSession(player)) {
				throw new IOException("Open and own World Editor mode before sharing a region.");
			}
			WorldEditStorageContext storage =
				player.getWorld().getServer().getWorldEditStorage();
			Path control = WorldBuilderRuntimeControl.resolveControlDirectory(
				player.getWorld().getServer());
			pending = checked(storage, control.resolve(PENDING_FILE),
				"pending Region bundle request");
			Path request = checked(storage, control.resolve(REQUEST_FILE),
				"Region bundle request");
			Path response = checked(storage, control.resolve(RESPONSE_FILE),
				"Region bundle response");
			if (!Files.isRegularFile(pending, LinkOption.NOFOLLOW_LINKS)
				|| Files.isSymbolicLink(pending)) {
				throw new IOException("The staged Region bundle request is missing or unsafe.");
			}
			long size = Files.size(pending);
			if (size < 2L || size > MAX_REQUEST_BYTES) {
				throw new IOException("The staged Region bundle request has an invalid size.");
			}
			JSONObject document = new JSONObject(new String(
				Files.readAllBytes(pending), StandardCharsets.UTF_8));
			if (!document.keySet().equals(REQUEST_KEYS)
				|| document.getInt("schemaVersion") != 1
				|| !"world-builder-region-bundle-request".equals(
					document.getString("manifestType"))) {
				throw new IOException("The staged Region bundle contract is invalid.");
			}
			requestId = document.getString("requestId");
			if (!REQUEST_ID.matcher(requestId).matches()) {
				throw new IOException("The staged Region bundle request ID is invalid.");
			}
			operation = document.getString("operation");
			String snapshotId = document.getString("snapshotId");
			String bundlePath = document.getString("bundlePath");
			String outputPath = document.getString("outputPath");
			if (bundlePath.length() > 4096 || outputPath.length() > 4096) {
				throw new IOException("The staged Region bundle path is too long.");
			}
			if ("import".equals(operation)) {
				if (!snapshotId.isEmpty() || bundlePath.isEmpty() || !outputPath.isEmpty()) {
					throw new IOException("The staged Region Import fields are invalid.");
				}
			} else if ("export".equals(operation)) {
				if (!SNAPSHOT_ID.matcher(snapshotId).matches()
					|| !bundlePath.isEmpty() || outputPath.isEmpty()) {
					throw new IOException("The staged Region Export fields are invalid.");
				}
			} else {
				throw new IOException("The staged Region bundle operation is unsupported.");
			}
			if (Files.exists(request, LinkOption.NOFOLLOW_LINKS)
				|| Files.exists(response, LinkOption.NOFOLLOW_LINKS)) {
				throw new IOException("Another Region Import/Export request is still active.");
			}
			try {
				Files.move(pending, request, StandardCopyOption.ATOMIC_MOVE);
			} catch (AtomicMoveNotSupportedException unsupported) {
				Files.move(pending, request);
			}
			forceDirectory(control);
			player.message("[World Editor] Region "
				+ ("import".equals(operation) ? "Import" : "Export")
				+ " request accepted for exact Editor processing.");
		} catch (Exception failure) {
			try {
				if (pending != null) Files.deleteIfExists(pending);
				writeRefusal(player, requestId, operation, failure);
			} catch (Exception responseFailure) {
				failure.addSuppressed(responseFailure);
			}
			if (player != null) player.message(
				"[World Editor] Region sharing was refused: " + boundedMessage(failure));
		}
	}

	private static void writeRefusal(Player player, String requestId,
		String operation, Exception failure) throws IOException {
		if (player == null || !AdaptiveWorldBuilderRuntimeIdentity.isAdaptive(
			player.getConfig())) return;
		WorldEditStorageContext storage =
			player.getWorld().getServer().getWorldEditStorage();
		Path control = WorldBuilderRuntimeControl.resolveControlDirectory(
			player.getWorld().getServer());
		Path response = checked(storage, control.resolve(RESPONSE_FILE),
			"Region bundle response");
		Path stage = checked(storage, control.resolve(RESPONSE_STAGE),
			"staged Region bundle refusal");
		if (Files.exists(response, LinkOption.NOFOLLOW_LINKS)
			|| Files.exists(stage, LinkOption.NOFOLLOW_LINKS)) return;
		JSONObject root = new JSONObject();
		root.put("schemaVersion", 1);
		root.put("manifestType", "world-builder-region-bundle-response");
		root.put("requestId", requestId);
		root.put("operation", operation);
		root.put("status", "refused");
		root.put("errorCode", "MUTATION_FAILED");
		root.put("message", boundedMessage(failure));
		root.put("nextStep", "Correct the portable Region request and retry.");
		Files.write(stage, (root.toString(2) + "\n").getBytes(StandardCharsets.UTF_8),
			StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
		try (FileChannel channel = FileChannel.open(stage,
			StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS)) {
			channel.force(true);
		}
		try {
			Files.move(stage, response, StandardCopyOption.ATOMIC_MOVE);
		} catch (AtomicMoveNotSupportedException unsupported) {
			Files.move(stage, response);
		}
		forceDirectory(control);
	}

	private static Path checked(WorldEditStorageContext storage, Path path,
		String label) throws IOException {
		return storage.validateGeneratedPath(path, label);
	}

	private static void forceDirectory(Path directory) throws IOException {
		try (FileChannel channel = FileChannel.open(directory, StandardOpenOption.READ)) {
			channel.force(true);
		} catch (UnsupportedOperationException ignored) {
			// Atomic publication remains authoritative where directory fsync is unavailable.
		}
	}

	private static String boundedMessage(Exception failure) {
		String message = failure.getMessage();
		if (message == null || message.trim().isEmpty()) {
			message = failure.getClass().getSimpleName();
		}
		return message.length() <= 512 ? message : message.substring(0, 512);
	}
}
