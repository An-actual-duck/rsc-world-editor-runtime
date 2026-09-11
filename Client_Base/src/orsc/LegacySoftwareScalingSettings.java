package orsc;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Properties;

/**
 * Owns active software-presenter scaling compatibility state.
 *
 * <p>This is not an OpenGL render-surface or presentation setting. Keep it
 * available while {@link ScaledWindow} remains the maintained fallback.</p>
 */
final class LegacySoftwareScalingSettings {

	interface SettingsStore {
		Properties load();

		void save(Properties properties);
	}

	static final String SCALING_TYPE_KEY = "scaling_type";
	static final String UI_SCALE_KEY = "ui_scale";
	static final String LEGACY_SCALAR_KEY = "scaling_scalar";
	static final float MIN_SCALAR = 1.0f;
	static final float MAX_INTEGER_SCALAR = 2.0f;
	static final float MAX_INTERPOLATION_SCALAR = 2.0f;

	private static volatile ScaledWindow.ScalingAlgorithm scalingAlgorithm =
		ScaledWindow.ScalingAlgorithm.INTEGER_SCALING;
	private static volatile float renderingScalar = MIN_SCALAR;
	private static volatile float pendingRenderingScalar = MIN_SCALAR;
	private static volatile boolean loginRedrawPending;
	private static volatile List<Float> integerScalars =
		createScalarSequence(2, 1.0f, MAX_INTEGER_SCALAR);
	private static volatile List<Float> interpolationScalars =
		createScalarSequence(2, 0.5f, MAX_INTERPOLATION_SCALAR);

	private LegacySoftwareScalingSettings() {
	}

	static ScaledWindow.ScalingAlgorithm getScalingAlgorithm() {
		return scalingAlgorithm;
	}

	static float getRenderingScalar() {
		return renderingScalar;
	}

	static float getPendingRenderingScalar() {
		return pendingRenderingScalar;
	}

	static boolean hasPendingScalarChange() {
		return Float.compare(pendingRenderingScalar, renderingScalar) != 0;
	}

	static synchronized float applyPendingScalar(float appliedScalar) {
		renderingScalar = normalizeScalar(appliedScalar, getAllowedScalars());
		return renderingScalar;
	}

	static boolean isLoginRedrawPending() {
		return loginRedrawPending;
	}

	static void markLoginRedrawPending() {
		loginRedrawPending = true;
	}

	static void clearLoginRedrawPending() {
		loginRedrawPending = false;
	}

	static List<Float> getAllowedScalars() {
		return scalingAlgorithm == ScaledWindow.ScalingAlgorithm.INTEGER_SCALING
			? integerScalars : interpolationScalars;
	}

	static List<Float> getIntegerScalars() {
		return integerScalars;
	}

	static List<Float> getInterpolationScalars() {
		return interpolationScalars;
	}

	static synchronized void configureAllowedScalars(int maximumScreenScalar) {
		int boundedMaximum = Math.max(1, maximumScreenScalar);
		integerScalars = createScalarSequence(
			boundedMaximum, 1.0f, MAX_INTEGER_SCALAR);
		interpolationScalars = createScalarSequence(
			boundedMaximum, 0.5f, MAX_INTERPOLATION_SCALAR);
		renderingScalar = normalizeScalar(renderingScalar, getAllowedScalars());
		pendingRenderingScalar = normalizeScalar(pendingRenderingScalar, getAllowedScalars());
	}

	static synchronized void loadFromClientSettings(Properties properties) {
		if (properties == null) {
			return;
		}

		String configuredAlgorithm = properties.getProperty(SCALING_TYPE_KEY);
		if (hasText(configuredAlgorithm)) {
			scalingAlgorithm = parseAlgorithm(configuredAlgorithm);
		}
		if (WorldBuilderUiProfile.isEnabled()) {
			scalingAlgorithm = ScaledWindow.ScalingAlgorithm.INTEGER_SCALING;
		}

		String configuredScalar = properties.getProperty(UI_SCALE_KEY);
		if (!hasText(configuredScalar)) {
			configuredScalar = properties.getProperty(LEGACY_SCALAR_KEY);
		}
		if (hasText(configuredScalar)) {
			pendingRenderingScalar = parseScalar(configuredScalar);
			pendingRenderingScalar = normalizeScalar(
				pendingRenderingScalar, getAllowedScalars());
		}
	}

	static void saveToClientSettings(Properties properties) {
		if (properties == null) {
			return;
		}
		String scalar = String.valueOf(pendingRenderingScalar);
		properties.setProperty(SCALING_TYPE_KEY, String.valueOf(scalingAlgorithm.ordinal()));
		properties.setProperty(UI_SCALE_KEY, scalar);
		properties.setProperty(LEGACY_SCALAR_KEY, scalar);
	}

	static synchronized float scaleUp(SettingsStore settingsStore) {
		return changeScalar(true, settingsStore);
	}

	static synchronized float scaleDown(SettingsStore settingsStore) {
		return changeScalar(false, settingsStore);
	}

	static synchronized ScaledWindow.ScalingAlgorithm cycleScalingAlgorithm(
		SettingsStore settingsStore) {
		if (scalingAlgorithm == ScaledWindow.ScalingAlgorithm.INTEGER_SCALING) {
			scalingAlgorithm = ScaledWindow.ScalingAlgorithm.BILINEAR_INTERPOLATION;
		} else if (scalingAlgorithm == ScaledWindow.ScalingAlgorithm.BILINEAR_INTERPOLATION) {
			scalingAlgorithm = ScaledWindow.ScalingAlgorithm.BICUBIC_INTERPOLATION;
		} else {
			scalingAlgorithm = ScaledWindow.ScalingAlgorithm.INTEGER_SCALING;
			// Preserve the established fractional-to-integer transition: truncate.
			if (renderingScalar != (int) renderingScalar) {
				pendingRenderingScalar = (int) renderingScalar;
			}
		}
		pendingRenderingScalar = normalizeScalar(
			pendingRenderingScalar, getAllowedScalars());
		persist(settingsStore);
		return scalingAlgorithm;
	}

	static int scaleDimension(int sourceDimension) {
		return Math.round(sourceDimension * renderingScalar);
	}

	static int unscaleCoordinate(int scaledCoordinate) {
		return Math.round(scaledCoordinate / renderingScalar);
	}

	static void persist(SettingsStore settingsStore) {
		if (settingsStore == null) {
			throw new IllegalArgumentException("settingsStore");
		}
		Properties properties = settingsStore.load();
		if (properties == null) {
			properties = new Properties();
		}
		saveToClientSettings(properties);
		settingsStore.save(properties);
	}

	private static float changeScalar(boolean increase, SettingsStore settingsStore) {
		markLoginRedrawPending();
		List<Float> scalars = getAllowedScalars();
		float normalizedCurrent = normalizeScalar(renderingScalar, scalars);
		int index = scalars.indexOf(normalizedCurrent);
		if (increase && index + 1 < scalars.size()) {
			index++;
		} else if (!increase && index > 0) {
			index--;
		}
		pendingRenderingScalar = scalars.get(index);
		persist(settingsStore);
		return pendingRenderingScalar;
	}

	private static List<Float> createScalarSequence(
		int maximumScreenScalar, float increment, float configuredMaximum) {
		List<Float> scalars = new ArrayList<Float>();
		for (float scalar = MIN_SCALAR;
			 scalar <= maximumScreenScalar && scalar <= configuredMaximum;
			 scalar += increment) {
			scalars.add(scalar);
		}
		if (scalars.isEmpty()) {
			scalars.add(MIN_SCALAR);
		}
		return Collections.unmodifiableList(scalars);
	}

	private static ScaledWindow.ScalingAlgorithm parseAlgorithm(String value) {
		try {
			int ordinal = Integer.parseInt(value.trim());
			ScaledWindow.ScalingAlgorithm[] algorithms = ScaledWindow.ScalingAlgorithm.values();
			if (ordinal >= 0 && ordinal < algorithms.length) {
				return algorithms[ordinal];
			}
		} catch (NumberFormatException ignored) {
			// Report the same bounded fallback for malformed and out-of-range values.
		}
		System.out.println("[legacy-scaling] Unknown scaling type '" + value
			+ "'; using integer scaling.");
		return ScaledWindow.ScalingAlgorithm.INTEGER_SCALING;
	}

	private static float parseScalar(String value) {
		try {
			float parsed = Float.parseFloat(value.trim());
			if (!Float.isNaN(parsed) && !Float.isInfinite(parsed)) {
				return parsed;
			}
		} catch (NumberFormatException ignored) {
			// Report the same bounded fallback for malformed and non-finite values.
		}
		System.out.println("[legacy-scaling] Unknown scalar '" + value + "'; using 1.0.");
		return MIN_SCALAR;
	}

	private static float normalizeScalar(float scalar, List<Float> allowedScalars) {
		if (Float.isNaN(scalar) || Float.isInfinite(scalar) || allowedScalars.isEmpty()) {
			return MIN_SCALAR;
		}
		float normalized = allowedScalars.get(0);
		for (Float allowed : allowedScalars) {
			if (scalar < allowed) {
				break;
			}
			normalized = allowed;
		}
		return normalized;
	}

	private static boolean hasText(String value) {
		return value != null && !value.trim().isEmpty();
	}
}
