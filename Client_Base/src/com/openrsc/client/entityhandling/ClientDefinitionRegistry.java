package com.openrsc.client.entityhandling;

import com.openrsc.client.entityhandling.defs.DoorDef;
import com.openrsc.client.entityhandling.defs.ElevationDef;
import com.openrsc.client.entityhandling.defs.GameObjectDef;
import com.openrsc.client.entityhandling.defs.ItemDef;
import com.openrsc.client.entityhandling.defs.NPCDef;
import com.openrsc.client.entityhandling.defs.PrayerDef;
import com.openrsc.client.entityhandling.defs.SpellDef;
import com.openrsc.client.entityhandling.defs.SpriteDef;
import com.openrsc.client.entityhandling.defs.TileDef;
import com.openrsc.client.entityhandling.defs.extras.AnimationDef;
import com.openrsc.client.entityhandling.defs.extras.TextureDef;

import java.util.ArrayList;

/**
 * Owns client definition catalog storage and stable index-based access.
 * Authored definitions continue to be assembled by {@link EntityHandler}.
 */
final class ClientDefinitionRegistry {
	static final int FALLBACK_NPC_ID = 825;
	private static final int FALLBACK_ITEM_ID = 1544;
	private static final int FALLBACK_OBJECT_ID = 4;

	private final ArrayList<NPCDef> npcs = new ArrayList<>();
	private final ArrayList<ItemDef> items = new ArrayList<>();
	private final ArrayList<TextureDef> textures = new ArrayList<>();
	private final ArrayList<AnimationDef> animations = new ArrayList<>();
	private final ArrayList<SpriteDef> projectiles = new ArrayList<>();
	private final ArrayList<SpriteDef> guiParts = new ArrayList<>();
	private final ArrayList<SpriteDef> crowns = new ArrayList<>();
	private final ArrayList<SpellDef> spells = new ArrayList<>();
	private final ArrayList<PrayerDef> prayers = new ArrayList<>();
	private final ArrayList<TileDef> tiles = new ArrayList<>();
	private final ArrayList<DoorDef> doors = new ArrayList<>();
	private final ArrayList<ElevationDef> elevations = new ArrayList<>();
	private final ArrayList<GameObjectDef> objects = new ArrayList<>();
	private final ArrayList<String> models = new ArrayList<>();
	private final ClientDefinitionFallbackDiagnostics fallbackDiagnostics =
		new ClientDefinitionFallbackDiagnostics();
	private int inventoryPictureCount = 0;

	ArrayList<NPCDef> mutableNpcs() {
		return npcs;
	}

	ArrayList<ItemDef> mutableItems() {
		return items;
	}

	ArrayList<TextureDef> mutableTextures() {
		return textures;
	}

	ArrayList<AnimationDef> mutableAnimations() {
		return animations;
	}

	ArrayList<SpriteDef> mutableProjectiles() {
		return projectiles;
	}

	ArrayList<SpriteDef> mutableGuiParts() {
		return guiParts;
	}

	ArrayList<SpriteDef> mutableCrowns() {
		return crowns;
	}

	ArrayList<SpellDef> mutableSpells() {
		return spells;
	}

	ArrayList<PrayerDef> mutablePrayers() {
		return prayers;
	}

	ArrayList<TileDef> mutableTiles() {
		return tiles;
	}

	ArrayList<DoorDef> mutableDoors() {
		return doors;
	}

	ArrayList<ElevationDef> mutableElevations() {
		return elevations;
	}

	ArrayList<GameObjectDef> mutableObjects() {
		return objects;
	}

	int modelCount() {
		return models.size();
	}

	String modelName(int id) {
		if (id < 0 || id >= models.size()) {
			return null;
		}
		return models.get(id);
	}

	int inventoryPictureCount() {
		return inventoryPictureCount;
	}

	void includeInventorySprite(int spriteId) {
		if (spriteId + 1 > inventoryPictureCount) {
			inventoryPictureCount = spriteId + 1;
		}
	}

	int npcCount() {
		return npcs.size();
	}

	NPCDef npc(int id) {
		if (id < 0 || id >= npcs.size()) {
			return npcs.get(FALLBACK_NPC_ID);
		}
		return npcs.get(id);
	}

	int itemCount() {
		return items.size();
	}

	ItemDef item(int id) {
		int resolvedId = id;
		boolean noted = false;
		if (id < 0) {
			resolvedId = (resolvedId + 1) * -1;
			noted = true;
		}
		return item(id, resolvedId, noted);
	}

	ItemDef item(int id, boolean noted) {
		return item(id, id, noted);
	}

	private ItemDef item(int requestedId, int resolvedId, boolean noted) {
		if (resolvedId < 0 || resolvedId >= items.size()) {
			logItemFallback(requestedId, resolvedId, noted, "out-of-range");
			return items.get(FALLBACK_ITEM_ID);
		}
		ItemDef item = findItem(resolvedId, noted);
		if (item == null) {
			logItemFallback(requestedId, resolvedId, noted, "missing-definition");
			return items.get(FALLBACK_ITEM_ID);
		}
		if (isUnobtaniumPlaceholder(item)
			&& resolvedId != FALLBACK_ITEM_ID
			&& resolvedId != FALLBACK_ITEM_ID + 1) {
			logItemFallback(requestedId, resolvedId, noted, "placeholder-definition");
		}
		return item;
	}

	ItemDef findItem(int id, boolean noted) {
		if (id < 0 || id >= items.size()) {
			return null;
		}
		ItemDef item = items.get(id);
		if (item == null || item.id != id) {
			return null;
		}
		return noted ? ItemDef.asNote(item) : item;
	}

	static boolean isUnobtaniumPlaceholder(ItemDef item) {
		return item != null && "Unobtanium".equals(item.getName()) && item.getSpriteID() == 70;
	}

	private void logItemFallback(int requestedId, int resolvedId, boolean noted, String reason) {
		fallbackDiagnostics.logItemFallback(requestedId, resolvedId, noted, reason, items.size());
	}

	int textureCount() {
		return textures.size();
	}

	TextureDef texture(int id) {
		return id < 0 || id >= textures.size() ? null : textures.get(id);
	}

	int animationCount() {
		return animations.size();
	}

	AnimationDef animation(int id) {
		if (id < 0 || id >= animations.size()) {
			return animations.get(0);
		}
		return animations.get(id);
	}

	int projectileCount() {
		return projectiles.size();
	}

	SpriteDef projectile(int id) {
		return id < 0 || id >= projectiles.size() ? null : projectiles.get(id);
	}

	int guiPartCount() {
		return guiParts.size();
	}

	SpriteDef guiPart(int id) {
		return id < 0 || id >= guiParts.size() ? null : guiParts.get(id);
	}

	int crownCount() {
		return crowns.size();
	}

	SpriteDef crown(int id) {
		return id < 0 || id >= crowns.size() ? null : crowns.get(id);
	}

	int spellCount() {
		return spells.size();
	}

	SpellDef spell(int id) {
		return id < 0 || id >= spells.size() ? null : spells.get(id);
	}

	int prayerCount() {
		return prayers.size();
	}

	PrayerDef prayer(int id) {
		return id < 0 || id >= prayers.size() ? null : prayers.get(id);
	}

	int tileCount() {
		return tiles.size();
	}

	TileDef tile(int id) {
		return id < 0 || id >= tiles.size() ? null : tiles.get(id);
	}

	int doorCount() {
		return doors.size();
	}

	DoorDef door(int id) {
		return id < 0 || id >= doors.size() ? null : doors.get(id);
	}

	int elevationCount() {
		return elevations.size();
	}

	ElevationDef elevation(int id) {
		return id < 0 || id >= elevations.size() ? null : elevations.get(id);
	}

	int objectCount() {
		return objects.size();
	}

	GameObjectDef object(int id) {
		if (id < 0 || id >= objects.size() || (objects.get(id) != null && objects.get(id).id != id)) {
			for (int i = objects.size() - 1; i >= 0; i--) {
				if (objects.get(i).id == id) {
					return objects.get(i);
				}
			}
			return objects.get(FALLBACK_OBJECT_ID);
		}
		return objects.get(id);
	}

	int storeModel(String name) {
		if (name.equalsIgnoreCase("na")) {
			return 0;
		}
		int index = models.indexOf(name);
		if (index < 0) {
			models.add(name);
			return models.size() - 1;
		}
		return index;
	}
}
