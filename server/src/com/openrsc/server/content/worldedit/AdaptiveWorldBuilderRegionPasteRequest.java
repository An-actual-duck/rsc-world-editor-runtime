package com.openrsc.server.content.worldedit;

import com.openrsc.server.model.entity.player.Player;
import com.openrsc.server.io.AdaptiveWorldBuilderPackageGuard;
import com.openrsc.server.io.NativeLayeredWorldPackage;
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

/** Publishes a bounded Paste library/preview/apply request after saving live edits. */
public final class AdaptiveWorldBuilderRegionPasteRequest {
	public static final String PENDING_FILE = ".region-paste.request.pending.json";
	public static final String REQUEST_FILE = "region-paste.request.json";
	public static final String RESPONSE_FILE = "region-paste.response.json";
	private static final String RESPONSE_STAGE = ".region-paste.response.runtime.tmp";
	private static final long MAX_REQUEST_BYTES = 256L * 1024L;
	private static final long MAX_RESPONSE_BYTES = 256L * 1024L;
	private static final Pattern REQUEST_ID = Pattern.compile("[0-9a-f]{32}");
	private static final Set<String> REQUEST_KEYS = new HashSet<String>(Arrays.asList(
		"schemaVersion", "manifestType", "requestId", "operation", "snapshotId",
		"level", "x", "y", "expectedPlan", "confirmation"));
	private static final Set<String> RESPONSE_KEYS = new HashSet<String>(Arrays.asList(
		"schemaVersion", "manifestType", "requestId", "operation", "status", "result"));
	private static final Set<String> APPLY_RESULT_KEYS = new HashSet<String>(Arrays.asList(
		"operation", "snapshotId", "planFingerprintSha256", "workingSha256",
		"packageManifestSha256", "packageInventorySha256", "worldModified"));

	private AdaptiveWorldBuilderRegionPasteRequest() {
	}

	public static void submit(Player player) {
		String requestId = "00000000000000000000000000000000";
		Path pending = null;
		try {
			if (player == null || !player.isAdmin()
				|| !AdaptiveWorldBuilderRuntimeIdentity.isAdaptive(player.getConfig())) {
				throw new IOException(
					"Region Paste is restricted to the isolated adaptive World Builder.");
			}
			WorldEditorSessionManager editor =
				player.getWorld().getServer().getWorldEditorSessions();
			if (!editor.ownsActiveSession(player)) {
				throw new IOException("Open and own World Editor mode before using Region Paste.");
			}
			WorldEditStorageContext storage =
				player.getWorld().getServer().getWorldEditStorage();
			Path control = WorldBuilderRuntimeControl.resolveControlDirectory(
				player.getWorld().getServer());
			pending = checked(storage, control.resolve(PENDING_FILE),
				"pending Region Paste request");
			Path request = checked(storage, control.resolve(REQUEST_FILE),
				"Region Paste request");
			Path response = checked(storage, control.resolve(RESPONSE_FILE),
				"Region Paste response");
			if (!Files.isRegularFile(pending, LinkOption.NOFOLLOW_LINKS)
				|| Files.isSymbolicLink(pending)) {
				throw new IOException("The staged Region Paste request is missing or unsafe.");
			}
			long size = Files.size(pending);
			if (size < 2L || size > MAX_REQUEST_BYTES) {
				throw new IOException("The staged Region Paste request has an invalid size.");
			}
			JSONObject document = new JSONObject(new String(
				Files.readAllBytes(pending), StandardCharsets.UTF_8));
			if (!document.keySet().equals(REQUEST_KEYS)
				|| document.getInt("schemaVersion") != 1
				|| !"world-builder-region-paste-request".equals(
					document.getString("manifestType"))) {
				throw new IOException("The staged Region Paste contract is invalid.");
			}
			requestId = document.getString("requestId");
			if (!REQUEST_ID.matcher(requestId).matches()) {
				throw new IOException("The staged Region Paste request ID is invalid.");
			}
			String operation = document.getString("operation");
			if (!("library".equals(operation) || "preview".equals(operation)
				|| "apply".equals(operation) || "undo".equals(operation))) {
				throw new IOException("The staged Region Paste operation is unsupported.");
			}
			if (Files.exists(request, LinkOption.NOFOLLOW_LINKS)
				|| Files.exists(response, LinkOption.NOFOLLOW_LINKS)) {
				throw new IOException("Another Region Paste request is still active.");
			}
			if (!"library".equals(operation) && editor.hasPendingAdaptiveEdits()) {
				editor.saveAdaptivePackage(player);
			}
			try {
				Files.move(pending, request, StandardCopyOption.ATOMIC_MOVE);
			} catch (AtomicMoveNotSupportedException unsupported) {
				Files.move(pending, request);
			}
			forceDirectory(control);
			player.message("[World Editor] Region Paste " + operation
				+ " request queued for exact Editor processing; wait for the separate completed or refused result.");
		} catch (Exception failure) {
			try {
				if (pending != null) Files.deleteIfExists(pending);
				writeRefusal(player, requestId, failure);
			} catch (Exception responseFailure) {
				failure.addSuppressed(responseFailure);
			}
			if (player != null) player.message(
				"[World Editor] Region Paste was refused: " + boundedMessage(failure));
		}
	}

	/** Activates one already-published exact Paste without restarting either process. */
	public static void activate(Player player, String expectedRequestId) {
		Path response = null;
		try {
			if (player == null || !player.isAdmin()
				|| !AdaptiveWorldBuilderRuntimeIdentity.isAdaptive(player.getConfig())) {
				throw new IOException(
					"Live Region Paste is restricted to the isolated adaptive World Builder.");
			}
			if (expectedRequestId == null
				|| !REQUEST_ID.matcher(expectedRequestId).matches()) {
				throw new IOException("Live Region Paste request identity is invalid.");
			}
			WorldEditorSessionManager editor =
				player.getWorld().getServer().getWorldEditorSessions();
			if (!editor.ownsActiveSession(player)) {
				throw new IOException("Open and own World Editor mode before live activation.");
			}
			WorldEditStorageContext storage =
				player.getWorld().getServer().getWorldEditStorage();
			Path control = WorldBuilderRuntimeControl.resolveControlDirectory(
				player.getWorld().getServer());
			response = checked(storage, control.resolve(RESPONSE_FILE),
				"Region Paste response");
			if (!Files.isRegularFile(response, LinkOption.NOFOLLOW_LINKS)
				|| Files.isSymbolicLink(response)
				|| Files.size(response) < 2L
				|| Files.size(response) > MAX_RESPONSE_BYTES) {
				throw new IOException("Live Region Paste response is missing or unsafe.");
			}
			JSONObject root = new JSONObject(new String(
				Files.readAllBytes(response), StandardCharsets.UTF_8));
			if (!root.keySet().equals(RESPONSE_KEYS)
				|| root.getInt("schemaVersion") != 1
				|| !"world-builder-region-paste-response".equals(
					root.getString("manifestType"))
				|| !expectedRequestId.equals(root.getString("requestId"))
				|| !("apply".equals(root.getString("operation"))
					|| "undo".equals(root.getString("operation")))
				|| !"accepted".equals(root.getString("status"))) {
				throw new IOException("Live Region Paste response identity is invalid.");
			}
			JSONObject result = root.getJSONObject("result");
			if (!result.keySet().equals(APPLY_RESULT_KEYS)
				|| !("paste".equals(result.getString("operation"))
					|| "undo".equals(result.getString("operation")))
				|| !result.getBoolean("worldModified")) {
				throw new IOException("Live Region Paste result contract is invalid.");
			}
			String manifestSha256 = result.getString("packageManifestSha256");
			String inventorySha256 = result.getString("packageInventorySha256");
			Path working = storage.layeredWorkingPackage();
			AdaptiveWorldBuilderPackageGuard.Inventory inventory =
				AdaptiveWorldBuilderPackageGuard.requireClosedPackage(working);
			if (!inventorySha256.equals(inventory.getFingerprint())) {
				throw new IOException("Live Region Paste package inventory drifted.");
			}
			NativeLayeredWorldPackage worldPackage =
				NativeLayeredWorldPackage.load(inventory.getRoot());
			if (!manifestSha256.equals(worldPackage.getManifestSha256())) {
				throw new IOException("Live Region Paste package manifest drifted.");
			}
			AdaptiveWorldBuilderDefinitionInventory.validate(
				player.getWorld().getServer().getEntityHandler(), worldPackage);
			editor.adoptPublishedAdaptivePackage(
				player, worldPackage, inventorySha256);
			Files.delete(response);
			forceDirectory(control);
			player.message("undo".equals(result.getString("operation"))
				? "[World Editor] Region Paste Undo activated live; no restart was required."
				: "[World Editor] Region Paste activated live; no restart was required.");
		} catch (Exception failure) {
			try {
				if (response != null) Files.deleteIfExists(response);
			} catch (Exception cleanup) {
				failure.addSuppressed(cleanup);
			}
			if (player != null) player.message(
				"[World Editor] Live Region Paste activation failed: "
					+ boundedMessage(failure)
					+ ". Close and reopen the Builder to load the published world safely.");
		}
	}

	private static void writeRefusal(Player player, String requestId,
		Exception failure) throws IOException {
		if (player == null || !AdaptiveWorldBuilderRuntimeIdentity.isAdaptive(
			player.getConfig())) return;
		WorldEditStorageContext storage =
			player.getWorld().getServer().getWorldEditStorage();
		Path control = WorldBuilderRuntimeControl.resolveControlDirectory(
			player.getWorld().getServer());
		Path response = checked(storage, control.resolve(RESPONSE_FILE),
			"Region Paste response");
		Path stage = checked(storage, control.resolve(RESPONSE_STAGE),
			"staged Region Paste refusal");
		if (Files.exists(response, LinkOption.NOFOLLOW_LINKS)
			|| Files.exists(stage, LinkOption.NOFOLLOW_LINKS)) return;
		JSONObject root = new JSONObject();
		root.put("schemaVersion", 1);
		root.put("manifestType", "world-builder-region-paste-response");
		root.put("requestId", requestId);
		root.put("operation", "unknown");
		root.put("status", "refused");
		root.put("errorCode", "MUTATION_FAILED");
		root.put("message", boundedMessage(failure));
		root.put("nextStep", "Correct the request or save blocker and retry Region Paste.");
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
			// Atomic publication remains authoritative.
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
