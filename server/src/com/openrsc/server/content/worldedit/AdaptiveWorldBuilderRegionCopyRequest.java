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

/** Publishes one client-staged Copy/Cut request after saving the live adaptive draft. */
public final class AdaptiveWorldBuilderRegionCopyRequest {
	public static final String PENDING_FILE = ".region-copy.request.pending.json";
	public static final String REQUEST_FILE = "region-copy.request.json";
	public static final String RESPONSE_FILE = "region-copy.response.json";
	private static final String RUNTIME_RESPONSE_STAGE =
		".region-copy.response.runtime.tmp";
	private static final long MAX_REQUEST_BYTES = 256L * 1024L;
	private static final long MAX_RESPONSE_BYTES = 256L * 1024L;
	private static final Pattern REQUEST_ID = Pattern.compile("[0-9a-f]{32}");
	private static final Set<String> REQUEST_KEYS = new HashSet<String>(Arrays.asList(
		"schemaVersion", "manifestType", "requestId", "operation", "name",
		"worldSpace", "markers", "levels", "snapshotId", "expectedPlan",
		"confirmation"));
	private static final Set<String> RESPONSE_KEYS = new HashSet<String>(Arrays.asList(
		"schemaVersion", "manifestType", "requestId", "operation", "status", "result"));
	private static final Set<String> APPLY_RESULT_KEYS = new HashSet<String>(Arrays.asList(
		"operation", "snapshotId", "planFingerprintSha256", "workingSha256",
		"packageManifestSha256", "packageInventorySha256", "worldModified"));

	private AdaptiveWorldBuilderRegionCopyRequest() {
	}

	public static void submit(Player player) {
		String requestId = "00000000000000000000000000000000";
		String operation = "unknown";
		Path pending = null;
		try {
			if (player == null || !player.isAdmin()
				|| !AdaptiveWorldBuilderRuntimeIdentity.isAdaptive(player.getConfig())) {
				throw new IOException(
					"Region Copy is restricted to the isolated adaptive World Builder.");
			}
			WorldEditorSessionManager editor =
				player.getWorld().getServer().getWorldEditorSessions();
			if (!editor.ownsActiveSession(player)) {
				throw new IOException("Open and own World Editor mode before copying a region.");
			}
			WorldEditStorageContext storage =
				player.getWorld().getServer().getWorldEditStorage();
			Path control = WorldBuilderRuntimeControl.resolveControlDirectory(
				player.getWorld().getServer());
			pending = checked(storage, control.resolve(PENDING_FILE),
				"pending Region Copy request");
			Path request = checked(storage, control.resolve(REQUEST_FILE),
				"Region Copy request");
			Path response = checked(storage, control.resolve(RESPONSE_FILE),
				"Region Copy response");
			if (!Files.isRegularFile(pending, LinkOption.NOFOLLOW_LINKS)
				|| Files.isSymbolicLink(pending)) {
				throw new IOException("The staged Region Copy selection is missing or unsafe.");
			}
			long size = Files.size(pending);
			if (size < 2L || size > MAX_REQUEST_BYTES) {
				throw new IOException("The staged Region Copy selection has an invalid size.");
			}
			JSONObject document = new JSONObject(new String(
				Files.readAllBytes(pending), StandardCharsets.UTF_8));
			if (!document.keySet().equals(REQUEST_KEYS)
				|| document.getInt("schemaVersion") != 1
				|| !"world-builder-region-copy-request".equals(
					document.getString("manifestType"))) {
				throw new IOException("The staged Region Copy contract is invalid.");
			}
			requestId = document.getString("requestId");
			if (!REQUEST_ID.matcher(requestId).matches()) {
				throw new IOException("The staged Region Copy request ID is invalid.");
			}
			operation = document.getString("operation");
			if (!("copy".equals(operation) || "cut-preview".equals(operation)
				|| "cut-apply".equals(operation))) {
				throw new IOException("The staged Region Copy/Cut operation is unsupported.");
			}
			if (Files.exists(request, LinkOption.NOFOLLOW_LINKS)
				|| Files.exists(response, LinkOption.NOFOLLOW_LINKS)) {
				throw new IOException("Another Region Copy request is still active.");
			}
			if (editor.hasPendingAdaptiveEdits()) {
				editor.saveAdaptivePackage(player);
			}
			try {
				Files.move(pending, request, StandardCopyOption.ATOMIC_MOVE);
			} catch (AtomicMoveNotSupportedException unsupported) {
				Files.move(pending, request);
			}
			forceDirectory(control);
			player.message("[World Editor] Region " + operation
				+ " request accepted for exact Editor processing.");
		} catch (Exception failure) {
			try {
				if (pending != null) Files.deleteIfExists(pending);
				writeRefusal(player, requestId, operation, failure);
			} catch (Exception responseFailure) {
				failure.addSuppressed(responseFailure);
			}
			player.message("[World Editor] Region Copy/Cut was refused: "
				+ boundedMessage(failure));
		}
	}

	/** Activates one already-published exact Cut without restarting either process. */
	public static void activate(Player player, String expectedRequestId) {
		Path response = null;
		try {
			if (player == null || !player.isAdmin()
				|| !AdaptiveWorldBuilderRuntimeIdentity.isAdaptive(player.getConfig())) {
				throw new IOException(
					"Live Region Cut is restricted to the isolated adaptive World Builder.");
			}
			if (expectedRequestId == null
				|| !REQUEST_ID.matcher(expectedRequestId).matches()) {
				throw new IOException("Live Region Cut request identity is invalid.");
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
				"Region Cut response");
			if (!Files.isRegularFile(response, LinkOption.NOFOLLOW_LINKS)
				|| Files.isSymbolicLink(response)
				|| Files.size(response) < 2L
				|| Files.size(response) > MAX_RESPONSE_BYTES) {
				throw new IOException("Live Region Cut response is missing or unsafe.");
			}
			JSONObject root = new JSONObject(new String(
				Files.readAllBytes(response), StandardCharsets.UTF_8));
			if (!root.keySet().equals(RESPONSE_KEYS)
				|| root.getInt("schemaVersion") != 1
				|| !"world-builder-region-copy-response".equals(
					root.getString("manifestType"))
				|| !expectedRequestId.equals(root.getString("requestId"))
				|| !"cut-apply".equals(root.getString("operation"))
				|| !"accepted".equals(root.getString("status"))) {
				throw new IOException("Live Region Cut response identity is invalid.");
			}
			JSONObject result = root.getJSONObject("result");
			if (!result.keySet().equals(APPLY_RESULT_KEYS)
				|| !"cut".equals(result.getString("operation"))
				|| !result.getBoolean("worldModified")) {
				throw new IOException("Live Region Cut result contract is invalid.");
			}
			String manifestSha256 = result.getString("packageManifestSha256");
			String inventorySha256 = result.getString("packageInventorySha256");
			Path working = storage.layeredWorkingPackage();
			AdaptiveWorldBuilderPackageGuard.Inventory inventory =
				AdaptiveWorldBuilderPackageGuard.requireClosedPackage(working);
			if (!inventorySha256.equals(inventory.getFingerprint())) {
				throw new IOException("Live Region Cut package inventory drifted.");
			}
			NativeLayeredWorldPackage worldPackage =
				NativeLayeredWorldPackage.load(inventory.getRoot());
			if (!manifestSha256.equals(worldPackage.getManifestSha256())) {
				throw new IOException("Live Region Cut package manifest drifted.");
			}
			AdaptiveWorldBuilderDefinitionInventory.validate(
				player.getWorld().getServer().getEntityHandler(), worldPackage);
			editor.adoptPublishedAdaptivePackage(player, worldPackage, inventorySha256);
			Files.delete(response);
			forceDirectory(control);
			player.message("[World Editor] Region Cut activated live; no restart was required.");
		} catch (Exception failure) {
			try {
				if (response != null) Files.deleteIfExists(response);
			} catch (Exception cleanup) {
				failure.addSuppressed(cleanup);
			}
			if (player != null) player.message(
				"[World Editor] Live Region Cut activation failed: "
					+ boundedMessage(failure)
					+ ". Close and reopen the Builder to load the published world safely.");
		}
	}

	private static void writeRefusal(Player player, String requestId, String operation,
		Exception failure) throws IOException {
		if (player == null || !AdaptiveWorldBuilderRuntimeIdentity.isAdaptive(
			player.getConfig())) return;
		WorldEditStorageContext storage =
			player.getWorld().getServer().getWorldEditStorage();
		Path control = WorldBuilderRuntimeControl.resolveControlDirectory(
			player.getWorld().getServer());
		Path response = checked(storage, control.resolve(RESPONSE_FILE),
			"Region Copy response");
		Path stage = checked(storage, control.resolve(RUNTIME_RESPONSE_STAGE),
			"staged Region Copy refusal");
		if (Files.exists(response, LinkOption.NOFOLLOW_LINKS)
			|| Files.exists(stage, LinkOption.NOFOLLOW_LINKS)) return;
		JSONObject root = new JSONObject();
		root.put("schemaVersion", 1);
		root.put("manifestType", "world-builder-region-copy-response");
		root.put("requestId", requestId);
		root.put("operation", operation);
		root.put("status", "refused");
		root.put("errorCode", "MUTATION_FAILED");
		root.put("message", boundedMessage(failure));
		root.put("nextStep", "Correct the selection or save blocker and retry Region Copy/Cut.");
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
			// Atomic publication is still authoritative where directory fsync is unavailable.
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
