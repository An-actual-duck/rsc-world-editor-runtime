package orsc;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.security.SecureRandom;
import java.util.ArrayList;
import java.util.List;

/** Client half of the supervised, project-local Region Paste bridge. */
public final class WorldBuilderRegionPasteClientBridge {
	private static final String WORKSPACE_PROPERTY =
		"openrsc.worldBuilderWorkspaceRoot";
	private static final String PENDING_FILE = ".region-paste.request.pending.json";
	private static final String REQUEST_FILE = "region-paste.request.json";
	private static final String RESPONSE_FILE = "region-paste.response.json";
	private static final long MAX_RESPONSE_BYTES = 16L * 1024L * 1024L;
	private static final long TIMEOUT_NANOS = 60_000_000_000L;
	private final SecureRandom random = new SecureRandom();
	private String requestId;
	private String operation;
	private long submittedNanos;

	public boolean isPending() {
		return requestId != null;
	}

	public void reset() {
		requestId = null;
		operation = null;
		submittedNanos = 0L;
	}

	public void requestLibrary() throws IOException {
		submit("library", "", 0, 0, 0, "", "");
	}

	public void requestPreview(String snapshotId, int level, int x, int y)
		throws IOException {
		requireHash(snapshotId, "snapshot ID");
		submit("preview", snapshotId, level, x, y, "", "");
	}

	public void requestApply(String snapshotId, int level, int x, int y,
		String planHash, boolean overwrite) throws IOException {
		requireHash(snapshotId, "snapshot ID");
		requireHash(planHash, "plan hash");
		submit("apply", snapshotId, level, x, y, planHash,
			(overwrite ? "OVERWRITE " : "PASTE ") + planHash);
	}

	private void submit(String nextOperation, String snapshotId, int level,
		int x, int y, String expectedPlan, String confirmation) throws IOException {
		if (!WorldBuilderClientProfile.current().isAdaptive()) {
			throw new IOException("Region Paste requires an adaptive World Builder project.");
		}
		if (isPending()) throw new IOException("A Region Paste request is already active.");
		Path control = controlDirectory();
		Path pending = control.resolve(PENDING_FILE);
		requireAbsent(pending, "pending Region Paste request");
		requireAbsent(control.resolve(REQUEST_FILE), "Region Paste request");
		requireAbsent(control.resolve(RESPONSE_FILE), "Region Paste response");
		byte[] identity = new byte[16];
		random.nextBytes(identity);
		StringBuilder hex = new StringBuilder(32);
		for (byte value : identity) hex.append(String.format("%02x", value & 0xff));
		String nextRequestId = hex.toString();
		JSONObject root = new JSONObject();
		root.put("schemaVersion", 1);
		root.put("manifestType", "world-builder-region-paste-request");
		root.put("requestId", nextRequestId);
		root.put("operation", nextOperation);
		root.put("snapshotId", snapshotId);
		root.put("level", level);
		root.put("x", x);
		root.put("y", y);
		root.put("expectedPlan", expectedPlan);
		root.put("confirmation", confirmation);
		Files.write(pending, (root.toString(2) + "\n").getBytes(StandardCharsets.UTF_8),
			StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
		try (FileChannel channel = FileChannel.open(pending,
			StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS)) {
			channel.force(true);
		}
		forceDirectory(control);
		requestId = nextRequestId;
		operation = nextOperation;
		submittedNanos = System.nanoTime();
	}

	public Result poll() {
		if (!isPending()) return null;
		try {
			Path response = controlDirectory().resolve(RESPONSE_FILE);
			if (!Files.exists(response, LinkOption.NOFOLLOW_LINKS)) {
				if (System.nanoTime() - submittedNanos > TIMEOUT_NANOS) {
					String timedOut = requestId, timedOperation = operation;
					reset();
					return Result.refused(timedOut, timedOperation, "RECOVERY_REQUIRED",
						"Region Paste did not answer within 60 seconds.",
						"Close and reopen the Builder before retrying.");
				}
				return null;
			}
			if (!Files.isRegularFile(response, LinkOption.NOFOLLOW_LINKS)
				|| Files.isSymbolicLink(response)) {
				throw new IOException("Region Paste response is unsafe.");
			}
			long size = Files.size(response);
			if (size < 2L || size > MAX_RESPONSE_BYTES) {
				throw new IOException("Region Paste response size is invalid.");
			}
			JSONObject root = new JSONObject(new String(
				Files.readAllBytes(response), StandardCharsets.UTF_8));
			if (root.getInt("schemaVersion") != 1
				|| !"world-builder-region-paste-response".equals(
					root.getString("manifestType"))
				|| !requestId.equals(root.getString("requestId"))) {
				throw new IOException("Region Paste response identity does not match the request.");
			}
			String responseOperation = root.optString("operation", operation);
			Result result;
			if ("accepted".equals(root.getString("status"))) {
				JSONObject value = root.getJSONObject("result");
				if ("library".equals(responseOperation)) result = libraryResult(value);
				else if ("preview".equals(responseOperation)) result = previewResult(value);
				else if ("apply".equals(responseOperation)) result = Result.applied(
					requestId, value.getString("snapshotId"),
					value.getString("planFingerprintSha256"));
				else throw new IOException("Region Paste response operation is unsupported.");
			} else {
				result = Result.refused(requestId, responseOperation,
					root.getString("errorCode"), root.getString("message"),
					root.getString("nextStep"));
			}
			Files.delete(response);
			forceDirectory(response.getParent());
			reset();
			return result;
		} catch (Exception failure) {
			String failed = requestId, failedOperation = operation;
			reset();
			String message = failure.getMessage();
			if (message == null || message.isEmpty()) message = failure.getClass().getSimpleName();
			return Result.refused(failed, failedOperation, "UNSUPPORTED_FORMAT", message,
				"Close and reopen the Builder before retrying Region Paste.");
		}
	}

	private Result libraryResult(JSONObject value) {
		JSONArray array = value.getJSONArray("snapshots");
		List<Snapshot> snapshots = new ArrayList<Snapshot>();
		for (int index = 0; index < array.length(); index++) {
			JSONObject record = array.getJSONObject(index);
			snapshots.add(new Snapshot(record.getString("snapshotId"),
				record.getString("name"), record.getInt("tileCount"),
				record.getInt("placementCount"), record.getInt("levelCount")));
		}
		return Result.library(requestId, snapshots);
	}

	private Result previewResult(JSONObject value) {
		JSONObject plan = value.getJSONObject("operationPlan");
		JSONObject footprint = value.getJSONObject("previewFootprint");
		JSONArray markerArray = footprint.getJSONArray("markers");
		int[][] markers = new int[markerArray.length()][2];
		for (int index = 0; index < markerArray.length(); index++) {
			JSONObject marker = markerArray.getJSONObject(index);
			if (marker.getInt("marker") != index + 1) {
				throw new IllegalArgumentException("Region Paste preview marker order is invalid.");
			}
			markers[index][0] = marker.getInt("x");
			markers[index][1] = marker.getInt("y");
		}
		JSONArray collisionArray = plan.getJSONArray("collisions");
		int[][] collisions = new int[collisionArray.length()][3];
		for (int index = 0; index < collisionArray.length(); index++) {
			JSONObject collision = collisionArray.getJSONObject(index);
			collisions[index][0] = collision.getInt("level");
			collisions[index][1] = collision.getInt("x");
			collisions[index][2] = collision.getInt("y");
		}
		return Result.preview(requestId, value.getString("snapshotId"),
			value.getString("name"), value.getInt("tileCount"),
			value.getInt("placementCount"), plan.getString("planFingerprintSha256"),
			plan.getBoolean("blocked"), plan.getBoolean("overwriteRequired"),
			markers, collisions);
	}

	private static void requireHash(String value, String label) throws IOException {
		if (value == null || !value.matches("[0-9a-f]{64}")) {
			throw new IOException("Region Paste " + label + " is invalid.");
		}
	}

	private static Path controlDirectory() throws IOException {
		String configured = System.getProperty(WORKSPACE_PROPERTY, "").trim();
		if (configured.isEmpty()) throw new IOException("World Builder project root is missing.");
		Path workspace = Paths.get(configured).toAbsolutePath().normalize();
		if (!Files.isDirectory(workspace, LinkOption.NOFOLLOW_LINKS)
			|| Files.isSymbolicLink(workspace)) {
			throw new IOException("World Builder project root is unsafe.");
		}
		workspace = workspace.toRealPath();
		Path control = workspace.resolve("run/world-builder").normalize();
		if (!control.startsWith(workspace)
			|| !Files.isDirectory(control, LinkOption.NOFOLLOW_LINKS)
			|| Files.isSymbolicLink(control)
			|| !control.toRealPath().startsWith(workspace)) {
			throw new IOException("World Builder Region Paste control directory is unsafe.");
		}
		return control;
	}

	private static void requireAbsent(Path path, String label) throws IOException {
		if (Files.exists(path, LinkOption.NOFOLLOW_LINKS)) {
			throw new IOException(label + " is already present.");
		}
	}

	private static void forceDirectory(Path directory) throws IOException {
		try (FileChannel channel = FileChannel.open(directory, StandardOpenOption.READ)) {
			channel.force(true);
		} catch (UnsupportedOperationException ignored) {
			// Atomic regular-file publication remains authoritative.
		}
	}

	public static final class Snapshot {
		public final String id;
		public final String name;
		public final int tileCount;
		public final int placementCount;
		public final int levelCount;

		Snapshot(String id, String name, int tileCount, int placementCount, int levelCount) {
			this.id = id;
			this.name = name;
			this.tileCount = tileCount;
			this.placementCount = placementCount;
			this.levelCount = levelCount;
		}
	}

	public static final class Result {
		public final boolean accepted;
		public final String operation;
		public final String requestId;
		public final List<Snapshot> snapshots;
		public final String snapshotId;
		public final String name;
		public final int tileCount;
		public final int placementCount;
		public final String planHash;
		public final boolean blocked;
		public final boolean overwrite;
		public final int[][] markers;
		public final int[][] collisions;
		public final String errorCode;
		public final String message;
		public final String nextStep;

		private Result(boolean accepted, String operation, String requestId,
			List<Snapshot> snapshots, String snapshotId, String name, int tileCount,
			int placementCount, String planHash, boolean blocked, boolean overwrite,
			int[][] markers, int[][] collisions, String errorCode, String message,
			String nextStep) {
			this.accepted = accepted; this.operation = operation; this.requestId = requestId;
			this.snapshots = snapshots; this.snapshotId = snapshotId; this.name = name;
			this.tileCount = tileCount; this.placementCount = placementCount;
			this.planHash = planHash; this.blocked = blocked; this.overwrite = overwrite;
			this.markers = markers; this.collisions = collisions;
			this.errorCode = errorCode; this.message = message; this.nextStep = nextStep;
		}

		static Result library(String id, List<Snapshot> snapshots) {
			return new Result(true, "library", id, snapshots, "", "", 0, 0, "",
				false, false, new int[0][2], new int[0][3], "", "", "");
		}

		static Result preview(String id, String snapshotId, String name, int tiles,
			int placements, String plan, boolean blocked, boolean overwrite,
			int[][] markers, int[][] collisions) {
			return new Result(true, "preview", id, new ArrayList<Snapshot>(), snapshotId,
				name, tiles, placements, plan, blocked, overwrite, markers, collisions,
				"", "", "");
		}

		static Result applied(String id, String snapshotId, String plan) {
			return new Result(true, "apply", id, new ArrayList<Snapshot>(), snapshotId,
				"", 0, 0, plan, false, false, new int[0][2], new int[0][3], "", "", "");
		}

		static Result refused(String id, String operation, String code,
			String message, String nextStep) {
			return new Result(false, operation, id, new ArrayList<Snapshot>(), "", "",
				0, 0, "", false, false, new int[0][2], new int[0][3], code,
				message, nextStep);
		}
	}
}
