package com.openrsc.interfaces.misc;

import com.openrsc.client.entityhandling.defs.TileDef;

/** Resolves author intent against the bound catalog; raw IDs remain an implementation detail. */
final class WorldEditorFloorSelection {
	interface Definitions { int size(); TileDef get(int id); boolean allowed(int id); }
	static int resolve(Definitions definitions, int appearance, boolean walkable, int level) {
		int blocking = walkable ? 0 : 1;
		if (appearance == 0) {
			for (int id = 0; id < definitions.size() && id < 249; id++) {
				TileDef value = definitions.get(id);
				if (value != null && definitions.allowed(id) && value.usesExplicitBaseColor()
					&& value.getObjectType() == blocking) return id + 1;
			}
			// Legacy base colour is visible on these levels only; no silent transparent substitute.
			return level == 1 || level == 2 ? -1 : walkable ? 0 : 255;
		}
		int original = appearance == 250 ? 2 : appearance;
		if (original < 1 || original > definitions.size() || !definitions.allowed(original - 1)) return -1;
		TileDef selected = definitions.get(original - 1);
		if (selected == null) return -1;
		if (selected.getWorldBuilderSourceOverlay() != 0) original = selected.getWorldBuilderSourceOverlay();
		TileDef source = definitions.get(original - 1);
		// Generated semantic floors take precedence over legacy ID-based gameplay.
		for (int id = 0; id < definitions.size() && id < 249; id++) {
			TileDef value = definitions.get(id);
			if (value != null && definitions.allowed(id) && value.getWorldBuilderSourceOverlay() == original
				&& value.getObjectType() == blocking) return id + 1;
		}
		// Unextended catalogs may still offer their unchanged legacy appearance.
		return source.getObjectType() == blocking ? original : -1;
	}
	static int paletteRgb(int index) {
		int n = index & 63, r, g, b;
		if (index < 64) { r = b = 255 - n * 4; g = 255 - (int)(n * 1.75); }
		else if (index < 128) { r = n * 3; g = 144; b = 0; }
		else if (index < 192) { r = 192 - (int)(n * 1.5); g = 144 - (int)(n * 1.5); b = 0; }
		else { r = 96 - (int)(n * 1.5); g = 48 + (int)(n * 1.5); b = 0; }
		return ((r & 248) << 16) | ((g & 248) << 8) | (b & 248);
	}
	private WorldEditorFloorSelection() { }
}
