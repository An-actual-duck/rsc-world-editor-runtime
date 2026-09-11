package orsc;

import java.util.Properties;

final class SpellbookLayoutSettings {
	static final String PROPERTY_KEY = "spellbook_layout";
	private static volatile Mode mode = Mode.ICONS;

	private SpellbookLayoutSettings() {
	}

	static Mode getMode() {
		return mode;
	}

	static boolean usesTextLayout() {
		return !WorldBuilderUiProfile.isEnabled() && mode == Mode.TEXT;
	}

	static Mode cycleMode() {
		mode = mode.next();
		return mode;
	}

	static Mode setMode(Mode next) {
		mode = next == null ? Mode.ICONS : next;
		return mode;
	}

	static void loadFromClientSettings(Properties props) {
		if (props == null) {
			return;
		}
		mode = Mode.from(props.getProperty(PROPERTY_KEY));
	}

	static void saveToClientSettings(Properties props) {
		if (props != null) {
			props.setProperty(PROPERTY_KEY, mode.id);
		}
	}

	enum Mode {
		ICONS("icons", "@gre@Icons"),
		TEXT("text", "@yel@Text");

		final String id;
		final String label;

		Mode(String id, String label) {
			this.id = id;
			this.label = label;
		}

		Mode next() {
			return this == ICONS ? TEXT : ICONS;
		}

		static Mode from(String value) {
			if (value == null || value.trim().isEmpty()) {
				return ICONS;
			}
			String normalized = value.trim().toLowerCase();
			return "text".equals(normalized) || "list".equals(normalized)
				? TEXT
				: ICONS;
		}
	}
}
