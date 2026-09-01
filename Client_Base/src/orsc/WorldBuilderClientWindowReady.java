package orsc;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;

/** Signals that the dedicated World Builder client window has actually been shown. */
final class WorldBuilderClientWindowReady {
	static final String READY_FILE_PROPERTY = "openrsc.worldBuilderClientReadyFile";
	private static boolean signalled;

	private WorldBuilderClientWindowReady() {
	}

	static synchronized void signalWindowShown() {
		if (signalled) {
			return;
		}
		String configured = System.getProperty(READY_FILE_PROPERTY, "").trim();
		if (configured.isEmpty()) {
			return;
		}
		Path ready = Paths.get(configured).toAbsolutePath().normalize();
		String workspaceValue = System.getProperty(
			"openrsc.worldBuilderWorkspaceRoot", "").trim();
		if (!workspaceValue.isEmpty()) {
			Path expected = Paths.get(workspaceValue).toAbsolutePath().normalize()
				.resolve("run/client.ready");
			if (!ready.equals(expected)) {
				System.err.println(
					"World Builder client readiness path is outside its workspace: " + ready);
				return;
			}
		}
		Path parent = ready.getParent();
		if (parent == null || !Files.isDirectory(parent, LinkOption.NOFOLLOW_LINKS)
			|| Files.isSymbolicLink(parent)
			|| Files.exists(ready, LinkOption.NOFOLLOW_LINKS)
				&& Files.isSymbolicLink(ready)) {
			System.err.println("World Builder client readiness path is unsafe: " + ready);
			return;
		}
		Path staged = null;
		try {
			staged = Files.createTempFile(parent, ".client-ready-", ".tmp");
			Files.write(staged, "visible\n".getBytes(StandardCharsets.US_ASCII));
			try {
				Files.move(staged, ready, StandardCopyOption.ATOMIC_MOVE,
					StandardCopyOption.REPLACE_EXISTING);
			} catch (AtomicMoveNotSupportedException ignored) {
				Files.move(staged, ready, StandardCopyOption.REPLACE_EXISTING);
			}
			signalled = true;
		} catch (IOException failure) {
			System.err.println("World Builder client could not signal that its window opened: "
				+ failure.getMessage());
			try {
				if (staged != null) Files.deleteIfExists(staged);
			} catch (IOException ignored) {
			}
		}
	}
}
