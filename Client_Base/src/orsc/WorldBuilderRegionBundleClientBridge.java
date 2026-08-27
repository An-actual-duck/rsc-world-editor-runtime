package orsc;

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

/** Client half of the supervised portable Region Import/Export bridge. */
public final class WorldBuilderRegionBundleClientBridge {
	private static final String WORKSPACE_PROPERTY =
		"openrsc.worldBuilderWorkspaceRoot";
	private static final String PENDING_FILE = ".region-bundle.request.pending.json";
	private static final String REQUEST_FILE = "region-bundle.request.json";
	private static final String RESPONSE_FILE = "region-bundle.response.json";
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

	public void requestImport(Path bundle) throws IOException {
		if (bundle == null) throw new IOException("Choose a portable .wbr file first.");
		submit("import", "", bundle.toAbsolutePath().normalize().toString(), "");
	}

	public void requestExport(String snapshotId, Path output) throws IOException {
		requireHash(snapshotId, "snapshot ID");
		if (output == null) throw new IOException("Choose an export destination first.");
		submit("export", snapshotId, "", output.toAbsolutePath().normalize().toString());
	}

	private void submit(String nextOperation, String snapshotId, String bundlePath,
		String outputPath) throws IOException {
		if (!WorldBuilderClientProfile.current().isAdaptive()) {
			throw new IOException("Region sharing requires an adaptive World Builder project.");
		}
		if (isPending()) throw new IOException("A Region Import/Export request is already active.");
		if (bundlePath.length() > 4096 || outputPath.length() > 4096) {
			throw new IOException("The selected Region bundle path is too long.");
		}
		Path control = controlDirectory();
		Path pending = control.resolve(PENDING_FILE);
		requireAbsent(pending, "pending Region bundle request");
		requireAbsent(control.resolve(REQUEST_FILE), "Region bundle request");
		requireAbsent(control.resolve(RESPONSE_FILE), "Region bundle response");
		byte[] identity = new byte[16];
		random.nextBytes(identity);
		StringBuilder hex = new StringBuilder(32);
		for (byte value : identity) hex.append(String.format("%02x", value & 0xff));
		String nextRequestId = hex.toString();
		JSONObject root = new JSONObject();
		root.put("schemaVersion", 1);
		root.put("manifestType", "world-builder-region-bundle-request");
		root.put("requestId", nextRequestId);
		root.put("operation", nextOperation);
		root.put("snapshotId", snapshotId);
		root.put("bundlePath", bundlePath);
		root.put("outputPath", outputPath);
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
						"Region Import/Export did not answer within 60 seconds.",
						"Close and reopen the Builder before retrying.");
				}
				return null;
			}
			if (!Files.isRegularFile(response, LinkOption.NOFOLLOW_LINKS)
				|| Files.isSymbolicLink(response)) {
				throw new IOException("Region bundle response is unsafe.");
			}
			long size = Files.size(response);
			if (size < 2L || size > MAX_RESPONSE_BYTES) {
				throw new IOException("Region bundle response size is invalid.");
			}
			JSONObject root = new JSONObject(new String(
				Files.readAllBytes(response), StandardCharsets.UTF_8));
			if (root.getInt("schemaVersion") != 1
				|| !"world-builder-region-bundle-response".equals(
					root.getString("manifestType"))
				|| !requestId.equals(root.getString("requestId"))) {
				throw new IOException("Region bundle response identity does not match the request.");
			}
			String responseOperation = root.optString("operation", operation);
			Result result;
			if ("accepted".equals(root.getString("status"))) {
				JSONObject value = root.getJSONObject("result");
				if ("import".equals(responseOperation)) {
					JSONObject compatibility = value.getJSONObject("compatibilityReport");
					result = Result.imported(requestId, value.getString("snapshotId"),
						value.getBoolean("libraryEntryCreated"),
						compatibility.getBoolean("compatible"),
						compatibility.getJSONArray("issues").length());
				} else if ("export".equals(responseOperation)) {
					result = Result.exported(requestId, value.getString("snapshotId"),
						value.getString("outputPath"));
				} else {
					throw new IOException("Region bundle response operation is unsupported.");
				}
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
				"Close and reopen the Builder before retrying Region Import/Export.");
		}
	}

	private static void requireHash(String value, String label) throws IOException {
		if (value == null || !value.matches("[0-9a-f]{64}")) {
			throw new IOException("Region Export " + label + " is invalid.");
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
			throw new IOException("World Builder Region bundle control directory is unsafe.");
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

	public static final class Result {
		public final boolean accepted;
		public final String operation;
		public final String requestId;
		public final String snapshotId;
		public final boolean created;
		public final boolean compatible;
		public final int issueCount;
		public final String outputPath;
		public final String errorCode;
		public final String message;
		public final String nextStep;

		private Result(boolean accepted, String operation, String requestId,
			String snapshotId, boolean created, boolean compatible, int issueCount,
			String outputPath, String errorCode, String message, String nextStep) {
			this.accepted = accepted;
			this.operation = operation;
			this.requestId = requestId;
			this.snapshotId = snapshotId;
			this.created = created;
			this.compatible = compatible;
			this.issueCount = issueCount;
			this.outputPath = outputPath;
			this.errorCode = errorCode;
			this.message = message;
			this.nextStep = nextStep;
		}

		static Result imported(String requestId, String snapshotId, boolean created,
			boolean compatible, int issueCount) {
			return new Result(true, "import", requestId, snapshotId, created,
				compatible, issueCount, "", "", "", "");
		}

		static Result exported(String requestId, String snapshotId, String outputPath) {
			return new Result(true, "export", requestId, snapshotId, false,
				true, 0, outputPath, "", "", "");
		}

		static Result refused(String requestId, String operation, String code,
			String message, String nextStep) {
			return new Result(false, operation, requestId, "", false, false, 0,
				"", code, message, nextStep);
		}
	}
}
