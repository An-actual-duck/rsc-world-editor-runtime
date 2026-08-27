package orsc;

import java.awt.EventQueue;
import java.awt.FileDialog;
import java.awt.Frame;
import java.awt.GraphicsEnvironment;
import java.awt.event.WindowAdapter;
import java.awt.event.WindowEvent;
import java.io.File;
import java.io.FilenameFilter;
import java.nio.file.Path;
import java.nio.file.Paths;

/** Non-blocking native file chooser for portable World Builder region bundles. */
public final class WorldBuilderRegionBundleFileDialog {
	private static volatile String lastDirectory = System.getProperty("user.home", ".");
	private final Object lock = new Object();
	private long generation;
	private boolean pending;
	private Selection completed;
	private FileDialog activeDialog;

	public boolean isPending() {
		synchronized (lock) {
			return pending;
		}
	}

	public void openImport() {
		start("import", "", FileDialog.LOAD,
			"Import shared World Builder region", null);
	}

	public void openExport(String snapshotId, String snapshotName) {
		start("export", snapshotId, FileDialog.SAVE,
			"Export World Builder region", safeFileName(snapshotName) + ".wbr");
	}

	public Selection poll() {
		synchronized (lock) {
			Selection result = completed;
			completed = null;
			return result;
		}
	}

	public void reset() {
		FileDialog dialog;
		synchronized (lock) {
			generation++;
			pending = false;
			completed = null;
			dialog = activeDialog;
			activeDialog = null;
		}
		if (dialog != null) {
			final FileDialog closing = dialog;
			EventQueue.invokeLater(new Runnable() {
				@Override public void run() {
					closing.setVisible(false);
					closing.dispose();
				}
			});
		}
	}

	private void start(final String operation, final String snapshotId,
		final int mode, final String title, final String suggestedName) {
		final long ticket;
		synchronized (lock) {
			if (pending) throw new IllegalStateException(
				"A Region Import/Export file chooser is already open.");
			pending = true;
			completed = null;
			ticket = ++generation;
		}
		Thread chooser = new Thread(new Runnable() {
			@Override public void run() {
				Selection result;
				try {
					Path selected = choose(ticket, mode, title, suggestedName);
					result = selected == null
						? Selection.cancelled(operation, snapshotId)
						: Selection.selected(operation, snapshotId, selected);
				} catch (Exception failure) {
					String message = failure.getMessage();
					if (message == null || message.trim().isEmpty()) {
						message = failure.getClass().getSimpleName();
					}
					result = Selection.failed(operation, snapshotId, message);
				}
				synchronized (lock) {
					if (generation == ticket) {
						completed = result;
						pending = false;
					}
				}
			}
		}, "World Builder Region " + (mode == FileDialog.LOAD ? "Import" : "Export")
			+ " chooser");
		chooser.setDaemon(true);
		chooser.start();
	}

	private Path choose(long ticket, int mode, String title, String suggestedName) {
		if (GraphicsEnvironment.isHeadless()) {
			throw new IllegalStateException("A desktop is required to choose a Region bundle.");
		}
		final FileDialog dialog = new FileDialog((Frame)null, title, mode);
		dialog.setDirectory(lastDirectory);
		dialog.setMultipleMode(false);
		dialog.setFilenameFilter(new FilenameFilter() {
			@Override public boolean accept(File directory, String name) {
				return new File(directory, name).isDirectory()
					|| name.toLowerCase(java.util.Locale.ROOT).endsWith(".wbr");
			}
		});
		if (suggestedName != null) dialog.setFile(suggestedName);
		try {
			dialog.setAlwaysOnTop(true);
		} catch (SecurityException ignored) {
			// The native dialog still remains usable on desktops that forbid this hint.
		}
		dialog.addWindowListener(new WindowAdapter() {
			@Override public void windowOpened(WindowEvent event) {
				dialog.toFront();
				dialog.requestFocus();
			}
		});
		synchronized (lock) {
			if (generation != ticket) {
				dialog.dispose();
				return null;
			}
			activeDialog = dialog;
		}
		try {
			dialog.setVisible(true);
			String directory = dialog.getDirectory();
			String file = dialog.getFile();
			if (directory == null || file == null) return null;
			if (mode == FileDialog.SAVE
				&& !file.toLowerCase(java.util.Locale.ROOT).endsWith(".wbr")) {
				file += ".wbr";
			}
			Path selected = Paths.get(directory, file).toAbsolutePath().normalize();
			Path parent = selected.getParent();
			if (parent != null) lastDirectory = parent.toString();
			return selected;
		} finally {
			synchronized (lock) {
				if (activeDialog == dialog) activeDialog = null;
			}
			dialog.dispose();
		}
	}

	private static String safeFileName(String value) {
		String normalized = value == null ? "" : value.trim()
			.replaceAll("[^A-Za-z0-9._ -]+", "-")
			.replaceAll("[. ]+$", "");
		if (normalized.isEmpty()) normalized = "shared-region";
		return normalized.length() > 96 ? normalized.substring(0, 96) : normalized;
	}

	public static final class Selection {
		public final String operation;
		public final String snapshotId;
		public final Path path;
		public final boolean cancelled;
		public final String error;

		private Selection(String operation, String snapshotId, Path path,
			boolean cancelled, String error) {
			this.operation = operation;
			this.snapshotId = snapshotId;
			this.path = path;
			this.cancelled = cancelled;
			this.error = error;
		}

		private static Selection selected(String operation, String snapshotId,
			Path path) {
			return new Selection(operation, snapshotId, path, false, "");
		}

		private static Selection cancelled(String operation, String snapshotId) {
			return new Selection(operation, snapshotId, null, true, "");
		}

		private static Selection failed(String operation, String snapshotId,
			String error) {
			return new Selection(operation, snapshotId, null, false, error);
		}
	}
}
