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
import java.util.HashSet;
import java.util.Set;

/** Client half of the supervised, project-local Region Copy bridge. */
public final class WorldBuilderRegionCopyClientBridge {
	private static final String WORKSPACE_PROPERTY =
		"openrsc.worldBuilderWorkspaceRoot";
	private static final String PENDING_FILE =
		".region-copy.request.pending.json";
	private static final String REQUEST_FILE = "region-copy.request.json";
	private static final String RESPONSE_FILE = "region-copy.response.json";
	private static final long MAX_RESPONSE_BYTES = 16L * 1024L * 1024L;
	private static final long TIMEOUT_NANOS = 60_000_000_000L;
	private final SecureRandom random = new SecureRandom();
	private String requestId;
	private long submittedNanos;

	public boolean isPending() {
		return requestId != null;
	}

	public void reset() {
		requestId = null;
		submittedNanos = 0L;
	}

	public void submit(String name, int level, int[][] markers) throws IOException {
		if (!WorldBuilderClientProfile.current().isAdaptive()) {
			throw new IOException("Region Copy requires an adaptive World Builder project.");
		}
		if (isPending()) throw new IOException("A Region Copy request is already active.");
		if (name == null || name.trim().isEmpty() || name.length() > 128) {
			throw new IOException("Snapshot name must contain 1..128 characters.");
		}
		if (markers == null || markers.length < 3 || markers.length > 256) {
			throw new IOException("Close a selection containing 3..256 ordered markers.");
		}
		Set<String> seen = new HashSet<String>();
		JSONArray markerArray = new JSONArray();
		for (int index = 0; index < markers.length; index++) {
			if (markers[index] == null || markers[index].length != 2
				|| !seen.add(markers[index][0] + ":" + markers[index][1])) {
				throw new IOException("Selection markers must use unique tile coordinates.");
			}
			JSONObject marker = new JSONObject();
			marker.put("marker", index + 1);
			marker.put("x", markers[index][0]);
			marker.put("y", markers[index][1]);
			markerArray.put(marker);
		}
		Path control = controlDirectory();
		Path pending = control.resolve(PENDING_FILE);
		Path request = control.resolve(REQUEST_FILE);
		Path response = control.resolve(RESPONSE_FILE);
		requireAbsent(pending, "pending Region Copy request");
		requireAbsent(request, "Region Copy request");
		requireAbsent(response, "Region Copy response");

		byte[] identity = new byte[16];
		random.nextBytes(identity);
		StringBuilder hex = new StringBuilder(32);
		for (byte value : identity) hex.append(String.format("%02x", value & 0xff));
		String nextRequestId = hex.toString();
		JSONObject root = new JSONObject();
		root.put("schemaVersion", 1);
		root.put("manifestType", "world-builder-region-copy-request");
		root.put("requestId", nextRequestId);
		root.put("name", name.trim());
		root.put("worldSpace", "global");
		root.put("markers", markerArray);
		root.put("levels", new JSONArray().put(level));
		Files.write(pending, (root.toString(2) + "\n").getBytes(StandardCharsets.UTF_8),
			StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
		try (FileChannel channel = FileChannel.open(pending,
			StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS)) {
			channel.force(true);
		}
		forceDirectory(control);
		requestId = nextRequestId;
		submittedNanos = System.nanoTime();
	}

	public Result poll() {
		if (!isPending()) return null;
		try {
			Path response = controlDirectory().resolve(RESPONSE_FILE);
			if (!Files.exists(response, LinkOption.NOFOLLOW_LINKS)) {
				if (System.nanoTime() - submittedNanos > TIMEOUT_NANOS) {
					String timedOut = requestId;
					reset();
					return Result.refused(timedOut, "RECOVERY_REQUIRED",
						"Region Copy did not answer within 60 seconds.",
						"Close and reopen the Builder before retrying.");
				}
				return null;
			}
			if (!Files.isRegularFile(response, LinkOption.NOFOLLOW_LINKS)
				|| Files.isSymbolicLink(response)) {
				throw new IOException("Region Copy response is unsafe.");
			}
			long size = Files.size(response);
			if (size < 2L || size > MAX_RESPONSE_BYTES) {
				throw new IOException("Region Copy response size is invalid.");
			}
			JSONObject root = new JSONObject(new String(
				Files.readAllBytes(response), StandardCharsets.UTF_8));
			if (root.getInt("schemaVersion") != 1
				|| !"world-builder-region-copy-response".equals(
					root.getString("manifestType"))
				|| !requestId.equals(root.getString("requestId"))) {
				throw new IOException("Region Copy response identity does not match the request.");
			}
			Result result;
			if ("accepted".equals(root.getString("status"))) {
				JSONObject value = root.getJSONObject("result");
				result = Result.accepted(requestId, value.getString("snapshotId"),
					value.optString("name", "Region snapshot"),
					value.getInt("tileCount"), value.getInt("placementCount"),
					value.getJSONArray("footprintBoundaryReports").length(),
					value.getBoolean("libraryEntryCreated"));
			} else {
				result = Result.refused(requestId, root.getString("errorCode"),
					root.getString("message"), root.getString("nextStep"));
			}
			Files.delete(response);
			forceDirectory(response.getParent());
			reset();
			return result;
		} catch (Exception failure) {
			String failed = requestId;
			reset();
			String message = failure.getMessage();
			if (message == null || message.isEmpty()) message = failure.getClass().getSimpleName();
			return Result.refused(failed, "UNSUPPORTED_FORMAT", message,
				"Close and reopen the Builder before retrying Region Copy.");
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
			throw new IOException("World Builder Region Copy control directory is unsafe.");
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
			// The atomic regular-file publication remains authoritative.
		}
	}

	public static final class Result {
		public final boolean accepted;
		public final String requestId;
		public final String snapshotId;
		public final String name;
		public final int tileCount;
		public final int placementCount;
		public final int crossingReportCount;
		public final boolean created;
		public final String errorCode;
		public final String message;
		public final String nextStep;

		private Result(boolean accepted, String requestId, String snapshotId,
			String name, int tileCount, int placementCount, int crossingReportCount,
			boolean created, String errorCode, String message, String nextStep) {
			this.accepted = accepted;
			this.requestId = requestId;
			this.snapshotId = snapshotId;
			this.name = name;
			this.tileCount = tileCount;
			this.placementCount = placementCount;
			this.crossingReportCount = crossingReportCount;
			this.created = created;
			this.errorCode = errorCode;
			this.message = message;
			this.nextStep = nextStep;
		}

		static Result accepted(String requestId, String snapshotId, String name,
			int tileCount, int placementCount, int crossingReportCount,
			boolean created) {
			return new Result(true, requestId, snapshotId, name, tileCount,
				placementCount, crossingReportCount, created, "", "", "");
		}

		static Result refused(String requestId, String code, String message,
			String nextStep) {
			return new Result(false, requestId, "", "", 0, 0, 0, false,
				code, message, nextStep);
		}
	}
}
