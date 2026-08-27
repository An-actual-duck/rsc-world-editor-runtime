package com.openrsc.interfaces.misc;

import com.openrsc.client.model.Sprite;
import orsc.graphics.RendererTransparency;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Collections;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

/** Cached, semantic access to the replaceable world-editor icon set. */
public final class WorldEditorIconRegistry {
	public static final int ICON_SIZE = 24;
	private static final int ALPHA_THRESHOLD = 64;
	private static final String DEVELOPMENT_ROOT = "dev/myworld/assets/ui/world-editor";
	private static final String RESOURCE_ROOT = "myworld-assets/ui/world-editor/";

	public enum Key {
		TOOLBAR_COLLAPSE("toolbar-collapse.png", "Dock"),
		TOOLBAR_EXPAND("toolbar-expand.png", "Open"),
		MODE_NAVIGATE("mode-navigate.png", "Nav"),
		MODE_INSPECT("mode-inspect.png", "Look"),
		MODE_SCENERY("mode-scenery.png", "Obj"),
		MODE_NPC("mode-npc.png", "NPC"),
		MODE_ITEMS("mode-items.png", "Item"),
		MODE_REGION(null, "Region"),
		MODE_REGION_COPY(null, "Copy"),
		MODE_REGION_PASTE(null, "Paste"),
		FIELD_ELEVATION("field-elevation.png", "Elev"),
		FIELD_FLOOR_COLOR("field-floor-color.png", "Color"),
		FIELD_FLOOR_TEXTURE("field-floor-texture.png", "Floor"),
		FIELD_ROOF("field-roof.png", "Roof"),
		FIELD_WALL_NORTH("field-wall-north.png", "N Wall"),
		FIELD_WALL_EAST("field-wall-east.png", "E Wall"),
		FIELD_WALL_DIAGONAL("field-wall-diagonal.png", "D Wall"),
		TOOL_BRUSH_1X1("tool-brush-1x1.png", "1x1"),
		TOOL_BRUSH_3X3("tool-brush-3x3.png", "3x3"),
		TOOL_FREEHAND("tool-freehand.png", "Hand"),
		TOOL_LINE("tool-line.png", "Line"),
		TOOL_RECTANGLE(null, "Box"),
		PROFILE_BUILD("profile-build.png", "Build"),
		ACTION_SAVE("action-save.png", "Save"),
		ACTION_PIN("action-pin.png", "Pin"),
		ACTION_CLOSE("action-close.png", "Close");

		private final String filename;
		private final String fallbackLabel;

		Key(String filename, String fallbackLabel) {
			this.filename = filename;
			this.fallbackLabel = fallbackLabel;
		}

		public String filename() {
			return filename;
		}

		public String fallbackLabel() {
			return fallbackLabel;
		}
	}

	private final Map<Key, Sprite> sprites = new EnumMap<Key, Sprite>(Key.class);
	private final Map<Key, String> failures = new EnumMap<Key, String>(Key.class);
	private boolean initialized;

	public synchronized void initialize() {
		if (initialized) {
			return;
		}
		initialized = true;
		for (Key key : Key.values()) {
			try {
				Sprite sprite = load(key);
				if (sprite == null) {
					failures.put(key, "missing");
				} else {
					sprites.put(key, sprite);
				}
			} catch (IOException | RuntimeException exception) {
				String message = exception.getMessage();
				failures.put(key, message == null || message.trim().isEmpty() ? "invalid" : message.trim());
			}
		}
		if (!failures.isEmpty()) {
			System.out.println("[world-editor icons] " + failures.size() + " unavailable; labeled fallbacks active: "
				+ joinFailures());
		}
	}

	public Sprite get(Key key) {
		initialize();
		return sprites.get(key);
	}

	public boolean isLoaded(Key key) {
		initialize();
		return sprites.containsKey(key);
	}

	public int loadedCount() {
		initialize();
		return sprites.size();
	}

	public List<Key> missingKeys() {
		initialize();
		return Collections.unmodifiableList(new ArrayList<Key>(failures.keySet()));
	}

	private Sprite load(Key key) throws IOException {
		if (key == Key.TOOL_RECTANGLE) {
			return rectangleIcon();
		}
		if (key == Key.MODE_REGION) return regionIcon(false);
		if (key == Key.MODE_REGION_COPY) return regionCopyIcon();
		if (key == Key.MODE_REGION_PASTE) return regionIcon(true);
		BufferedImage image = read(key.filename());
		if (image == null) {
			return null;
		}
		if (image.getWidth() != ICON_SIZE || image.getHeight() != ICON_SIZE) {
			throw new IOException("expected 24x24, got " + image.getWidth() + "x" + image.getHeight());
		}
		if (!image.getColorModel().hasAlpha()) {
			throw new IOException("PNG has no alpha channel");
		}
		int[] pixels = new int[ICON_SIZE * ICON_SIZE];
		image.getRGB(0, 0, ICON_SIZE, ICON_SIZE, pixels, 0, ICON_SIZE);
		for (int i = 0; i < pixels.length; i++) {
			int alpha = pixels[i] >>> 24;
			if (alpha < ALPHA_THRESHOLD) {
				pixels[i] = RendererTransparency.TRANSPARENT_SAMPLE;
			} else {
				int rgb = pixels[i] & RendererTransparency.RGB_MASK;
				pixels[i] = rgb == RendererTransparency.TRANSPARENT_SAMPLE
					? RendererTransparency.OPAQUE_BLACK_REPLACEMENT : rgb;
			}
		}
		Sprite sprite = new Sprite(pixels, ICON_SIZE, ICON_SIZE);
		sprite.setShift(0, 0);
		sprite.setRequiresShift(false);
		sprite.setSomething(ICON_SIZE, ICON_SIZE);
		return sprite;
	}

	private static Sprite rectangleIcon() {
		int[] pixels = new int[ICON_SIZE * ICON_SIZE];
		java.util.Arrays.fill(pixels, RendererTransparency.TRANSPARENT_SAMPLE);
		for (int x = 4; x <= 19; x++) {
			pixels[4 * ICON_SIZE + x] = 0xffffff;
			pixels[5 * ICON_SIZE + x] = 0xffffff;
			pixels[18 * ICON_SIZE + x] = 0xffffff;
			pixels[19 * ICON_SIZE + x] = 0xffffff;
		}
		for (int y = 4; y <= 19; y++) {
			pixels[y * ICON_SIZE + 4] = 0xffffff;
			pixels[y * ICON_SIZE + 5] = 0xffffff;
			pixels[y * ICON_SIZE + 18] = 0xffffff;
			pixels[y * ICON_SIZE + 19] = 0xffffff;
		}
		Sprite sprite = new Sprite(pixels, ICON_SIZE, ICON_SIZE);
		sprite.setShift(0, 0);
		sprite.setRequiresShift(false);
		sprite.setSomething(ICON_SIZE, ICON_SIZE);
		return sprite;
	}

	private static Sprite regionIcon(boolean paste) {
		int[] pixels = new int[ICON_SIZE * ICON_SIZE];
		java.util.Arrays.fill(pixels, RendererTransparency.TRANSPARENT_SAMPLE);
		int[][] points = paste
			? new int[][]{{7,5},{19,5},{19,18},{7,18}}
			: new int[][]{{4,5},{16,4},{18,16},{10,19},{3,14}};
		for (int index = 0; index < points.length; index++) {
			int[] first = points[index], second = points[(index + 1) % points.length];
			line(pixels, first[0], first[1], second[0], second[1], 0xffffff);
			for (int y = first[1] - 1; y <= first[1] + 1; y++) {
				for (int x = first[0] - 1; x <= first[0] + 1; x++) {
					if (x >= 0 && x < ICON_SIZE && y >= 0 && y < ICON_SIZE) {
						pixels[y * ICON_SIZE + x] = 0xffffff;
					}
				}
			}
		}
		if (paste) {
			for (int x = 3; x <= 12; x++) pixels[11 * ICON_SIZE + x] = 0xffffff;
			for (int x = 8; x <= 12; x++) {
				int offset = x - 8;
				pixels[(7 + offset) * ICON_SIZE + x] = 0xffffff;
				pixels[(15 - offset) * ICON_SIZE + x] = 0xffffff;
			}
		}
		Sprite sprite = new Sprite(pixels, ICON_SIZE, ICON_SIZE);
		sprite.setShift(0, 0);sprite.setRequiresShift(false);sprite.setSomething(ICON_SIZE, ICON_SIZE);
		return sprite;
	}

	private static Sprite regionCopyIcon() {
		int[] pixels = new int[ICON_SIZE * ICON_SIZE];
		java.util.Arrays.fill(pixels, RendererTransparency.TRANSPARENT_SAMPLE);
		for (int x = 4; x <= 15; x++) {
			pixels[4 * ICON_SIZE + x] = 0xffffff;
			pixels[15 * ICON_SIZE + x] = 0xffffff;
			pixels[8 * ICON_SIZE + x + 4] = 0xffffff;
			pixels[19 * ICON_SIZE + x + 4] = 0xffffff;
		}
		for (int y = 4; y <= 15; y++) {
			pixels[y * ICON_SIZE + 4] = 0xffffff;
			pixels[y * ICON_SIZE + 15] = 0xffffff;
			pixels[(y + 4) * ICON_SIZE + 8] = 0xffffff;
			pixels[(y + 4) * ICON_SIZE + 19] = 0xffffff;
		}
		Sprite sprite = new Sprite(pixels, ICON_SIZE, ICON_SIZE);
		sprite.setShift(0, 0);sprite.setRequiresShift(false);sprite.setSomething(ICON_SIZE, ICON_SIZE);
		return sprite;
	}

	private static void line(int[] pixels,int x0,int y0,int x1,int y1,int color){
		int dx=Math.abs(x1-x0),sx=x0<x1?1:-1,dy=-Math.abs(y1-y0),sy=y0<y1?1:-1,error=dx+dy;
		while(true){if(x0>=0&&x0<ICON_SIZE&&y0>=0&&y0<ICON_SIZE)pixels[y0*ICON_SIZE+x0]=color;if(x0==x1&&y0==y1)break;int doubled=error*2;if(doubled>=dy){error+=dy;x0+=sx;}if(doubled<=dx){error+=dx;y0+=sy;}}
	}

	private BufferedImage read(String filename) throws IOException {
		Path userDirectory = Paths.get(System.getProperty("user.dir", ".")).normalize();
		Path[] candidates = new Path[] {
			userDirectory.resolve(DEVELOPMENT_ROOT).resolve(filename).normalize(),
			userDirectory.resolve("..").resolve(DEVELOPMENT_ROOT).resolve(filename).normalize()
		};
		for (Path candidate : candidates) {
			File file = candidate.toFile();
			if (file.isFile()) {
				return ImageIO.read(file);
			}
		}
		try (InputStream input = WorldEditorIconRegistry.class.getClassLoader()
			.getResourceAsStream(RESOURCE_ROOT + filename)) {
			return input == null ? null : ImageIO.read(input);
		}
	}

	private String joinFailures() {
		StringBuilder text = new StringBuilder();
		for (Key key : Key.values()) {
			String failure = failures.get(key);
			if (failure == null) {
				continue;
			}
			if (text.length() > 0) {
				text.append(", ");
			}
			text.append(key.filename() == null ? key.name() : key.filename()).append(" (").append(failure).append(')');
		}
		return text.toString();
	}
}
