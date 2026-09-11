package orsc;

/** Presentation-only opt-in for the isolated editor, never an installed player default. */
public final class WorldBuilderUiProfile {
	public static final String PROPERTY = "openrsc.worldBuilderPreservationUi";

	private WorldBuilderUiProfile() { }

	public static boolean isEnabled() {
		return Boolean.getBoolean("openrsc.worldBuilderMode") && Boolean.getBoolean(PROPERTY);
	}

	static int settingsTab(int relativeX) {
		return relativeX < 98 ? 0 : 1;
	}
}
