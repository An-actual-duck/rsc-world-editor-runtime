package com.openrsc.interfaces.misc;

/** Desktop World Editor keyboard mapping, kept independent from rendering and chat input. */
final class WorldEditorKeyboardShortcuts {
	enum Action {
		NONE,
		TOGGLE_CHAT,
		UNDO,
		REDO,
		SAVE,
		BRUSH,
		NAVIGATE,
		INSPECT,
		DOCK,
		TOGGLE_ELEVATION,
		TOGGLE_FLOOR_COLOR,
		TOGGLE_FLOOR_TEXTURE,
		TOGGLE_ROOF,
		TOGGLE_NORTH_WALL,
		TOGGLE_EAST_WALL,
		TOGGLE_DIAGONAL_WALL,
		EDIT_ELEVATION,
		EDIT_FLOOR_COLOR,
		EDIT_FLOOR_TEXTURE,
		EDIT_ROOF,
		EDIT_NORTH_WALL,
		EDIT_EAST_WALL,
		EDIT_DIAGONAL_WALL
	}

	private WorldEditorKeyboardShortcuts() {
	}

	static Action resolve(
		char typed,
		int key,
		int physicalKey,
		boolean control,
		boolean shift,
		boolean terrainMode,
		boolean shortcutsEnabled) {
		int effectiveKey=physicalKey>0?physicalKey:key;
		if (control && (effectiveKey == 10 || effectiveKey == 13)) {
			return Action.TOGGLE_CHAT;
		}
		if (!shortcutsEnabled) {
			return Action.NONE;
		}

		char letter = physicalKey>='A'&&physicalKey<='Z'?(char)('a'+physicalKey-'A'):normalizeLetter(typed);
		if (control && shift) {
			if(letter=='z')return Action.REDO;
			return letter == 's' ? Action.SAVE : Action.NONE;
		}
		if (control) {
			if(letter=='z')return Action.UNDO;
			if(letter=='y')return Action.REDO;
			if (!terrainMode) {
				return Action.NONE;
			}
			switch (letter) {
				case 'h': return Action.EDIT_ELEVATION;
				case 'c': return Action.EDIT_FLOOR_COLOR;
				case 't': return Action.EDIT_FLOOR_TEXTURE;
				case 'r': return Action.EDIT_ROOF;
				case 'n': return Action.EDIT_NORTH_WALL;
				case 'e': return Action.EDIT_EAST_WALL;
				case 'd': return Action.EDIT_DIAGONAL_WALL;
				default: return Action.NONE;
			}
		}
		if (shift) {
			if (!terrainMode) {
				return Action.NONE;
			}
			switch (letter) {
				case 'n': return Action.TOGGLE_NORTH_WALL;
				case 'e': return Action.TOGGLE_EAST_WALL;
				case 'd': return Action.TOGGLE_DIAGONAL_WALL;
				default: return Action.NONE;
			}
		}

		switch (letter) {
			case 'b': return Action.BRUSH;
			case 'n': return Action.NAVIGATE;
			case 'i': return Action.INSPECT;
			case 'd': return Action.DOCK;
			case 'h': return terrainMode ? Action.TOGGLE_ELEVATION : Action.NONE;
			case 'c': return terrainMode ? Action.TOGGLE_FLOOR_COLOR : Action.NONE;
			case 't': return terrainMode ? Action.TOGGLE_FLOOR_TEXTURE : Action.NONE;
			case 'r': return terrainMode ? Action.TOGGLE_ROOF : Action.NONE;
			default: return Action.NONE;
		}
	}

	private static char normalizeLetter(char typed) {
		if (typed >= 1 && typed <= 26) {
			return (char) ('a' + typed - 1);
		}
		return Character.toLowerCase(typed);
	}
}
