package orsc;

import java.awt.FileDialog;
import java.awt.Frame;
import java.awt.GraphicsEnvironment;
import java.io.File;
import java.io.FilenameFilter;
import java.nio.file.Path;
import java.nio.file.Paths;

/** Native file chooser for portable, non-executable World Builder region bundles. */
public final class WorldBuilderRegionBundleFileDialog {
	private static String lastDirectory = System.getProperty("user.home", ".");

	private WorldBuilderRegionBundleFileDialog() {
	}

	public static Path chooseImport() {
		return choose(FileDialog.LOAD, "Import shared World Builder region", null);
	}

	public static Path chooseExport(String snapshotName) {
		return choose(FileDialog.SAVE, "Export World Builder region",
			safeFileName(snapshotName) + ".wbr");
	}

	private static Path choose(int mode, String title, String suggestedName) {
		if (GraphicsEnvironment.isHeadless()) {
			throw new IllegalStateException("A desktop is required to choose a Region bundle.");
		}
		FileDialog dialog = new FileDialog((Frame)null, title, mode);
		dialog.setDirectory(lastDirectory);
		dialog.setMultipleMode(false);
		dialog.setFilenameFilter(new FilenameFilter() {
			@Override
			public boolean accept(File directory, String name) {
				return new File(directory, name).isDirectory()
					|| name.toLowerCase(java.util.Locale.ROOT).endsWith(".wbr");
			}
		});
		if (suggestedName != null) dialog.setFile(suggestedName);
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
}
