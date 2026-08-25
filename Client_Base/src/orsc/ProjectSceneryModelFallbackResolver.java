package orsc;

import com.openrsc.data.DataOperations;

public final class ProjectSceneryModelFallbackResolver {
	private ProjectSceneryModelFallbackResolver() {}

	public static String resolve(byte[] models, String requested, String packagedFallback) {
		if (models == null || !usable(requested)
			|| !usable(packagedFallback) || requested.equalsIgnoreCase(packagedFallback)) {
			return requested;
		}
		if (contains(models, requested) || !contains(models, packagedFallback)) {
			return requested;
		}
		return packagedFallback;
	}

	private static boolean usable(String name) {
		return name != null && !name.trim().isEmpty() && !"na".equalsIgnoreCase(name.trim());
	}

	private static boolean contains(byte[] models, String name) {
		return DataOperations.getDataFileOffset(name + ".ob3", models) != 0;
	}
}
