package com.openrsc.server;

import com.openrsc.server.constants.Spells;
import com.openrsc.server.constants.ItemId;
import java.util.Collections;
import java.util.EnumMap;
import java.util.Map;
import java.util.Optional;
import com.openrsc.server.model.entity.player.Player;

/** Public Current Base dispatch; data IDs are not the owner's spell-book IDs. */
public final class CurrentBasePublicContent {
    private CurrentBasePublicContent() { }

    public static boolean isEnabled() {
        CurrentCompositionIdentity identity = CurrentCompositionIdentity.current();
        return identity.isEnabled() && "current-base-v1".equals(identity.value("variantId"));
    }

    private static final Spells[] PUBLIC_SPELLS = {
        Spells.WIND_STRIKE,
        Spells.CONFUSE,
        Spells.WATER_STRIKE,
        Spells.ENCHANT_LVL1_AMULET,
        Spells.EARTH_STRIKE,
        Spells.WEAKEN,
        Spells.FIRE_STRIKE,
        Spells.BONES_TO_BANANAS,
        Spells.WIND_BOLT,
        Spells.CURSE,
        Spells.LOW_LEVEL_ALCHEMY,
        Spells.WATER_BOLT,
        Spells.VARROCK_TELEPORT,
        Spells.ENCHANT_LVL2_AMULET,
        Spells.EARTH_BOLT,
        Spells.LUMBRIDGE_TELEPORT,
        Spells.TELEKINETIC_GRAB,
        Spells.FIRE_BOLT,
        Spells.FALADOR_TELEPORT,
        Spells.CRUMBLE_UNDEAD,
        Spells.WIND_BLAST,
        Spells.SUPERHEAT_ITEM,
        Spells.CAMELOT_TELEPORT,
        Spells.WATER_BLAST,
        Spells.ENCHANT_LVL3_AMULET,
        Spells.IBAN_BLAST,
        Spells.ARDOUGNE_TELEPORT,
        Spells.EARTH_BLAST,
        Spells.HIGH_LEVEL_ALCHEMY,
        Spells.CHARGE_WATER_ORB,
        Spells.ENCHANT_LVL4_AMULET,
        Spells.WATCHTOWER_TELEPORT,
        Spells.FIRE_BLAST,
        Spells.CLAWS_OF_GUTHIX,
        Spells.SARADOMIN_STRIKE,
        Spells.FLAMES_OF_ZAMORAK,
        Spells.CHARGE_EARTH_ORB,
        Spells.WIND_WAVE,
        Spells.CHARGE_FIRE_ORB,
        Spells.WATER_WAVE,
        Spells.CHARGE_AIR_ORB,
        Spells.VULNERABILITY,
        Spells.ENCHANT_LVL5_AMULET,
        Spells.EARTH_WAVE,
        Spells.ENFEEBLE,
        Spells.FIRE_WAVE,
        Spells.STUN,
        Spells.CHARGE
    };
    private static final Map<Spells, Integer> SPELL_MAP = createSpellMap();

    private static Map<Spells, Integer> createSpellMap() {
        EnumMap<Spells, Integer> result = new EnumMap<>(Spells.class);
        for (int id = 0; id < PUBLIC_SPELLS.length; id++) result.put(PUBLIC_SPELLS[id], id);
        return Collections.unmodifiableMap(result);
    }

    public static Map<Spells, Integer> spellMap() { return SPELL_MAP; }

    /** Stock elemental staves replace their matching rune, not a chance to save it. */
    public static boolean staffSuppliesRune(int staffId, int runeId) {
        if (runeId == ItemId.AIR_RUNE.id()) return staffId == ItemId.STAFF_OF_AIR.id()
            || staffId == ItemId.BATTLESTAFF_OF_AIR.id() || staffId == ItemId.ENCHANTED_BATTLESTAFF_OF_AIR.id();
        if (runeId == ItemId.WATER_RUNE.id()) return staffId == ItemId.STAFF_OF_WATER.id()
            || staffId == ItemId.BATTLESTAFF_OF_WATER.id() || staffId == ItemId.ENCHANTED_BATTLESTAFF_OF_WATER.id();
        if (runeId == ItemId.EARTH_RUNE.id()) return staffId == ItemId.STAFF_OF_EARTH.id()
            || staffId == ItemId.BATTLESTAFF_OF_EARTH.id() || staffId == ItemId.ENCHANTED_BATTLESTAFF_OF_EARTH.id();
        if (runeId == ItemId.FIRE_RUNE.id()) return staffId == ItemId.STAFF_OF_FIRE.id()
            || staffId == ItemId.BATTLESTAFF_OF_FIRE.id() || staffId == ItemId.ENCHANTED_BATTLESTAFF_OF_FIRE.id();
        return false;
    }

    private static final int[] PICKAXES = {1262, 1261, 1260, 1259, 1258, 156};
    private static final int[] PICKAXE_LEVELS = {41, 31, 21, 6, 1, 1};
    private static final int[] PICKAXE_REPEATS = {12, 8, 5, 3, 2, 1};
    private static final int[] PICKAXE_BONUSES = {16, 8, 4, 2, 1, 0};
    private static final int[] WOOD_AXES = {1480, 405, 204, 203, 428, 88, 12, 87};

    public static int pickaxeRequiredLevel(int id) {
        for (int i = 0; i < PICKAXES.length; i++) if (PICKAXES[i] == id) return PICKAXE_LEVELS[i];
        return Integer.MAX_VALUE;
    }

    public static int pickaxeRepeat(int id) {
        for (int i = 0; i < PICKAXES.length; i++) if (PICKAXES[i] == id) return PICKAXE_REPEATS[i];
        return 1;
    }

    public static int pickaxeBonus(int id) {
        for (int i = 0; i < PICKAXES.length; i++) if (PICKAXES[i] == id) return PICKAXE_BONUSES[i];
        return 0;
    }

    public static int selectPickaxe(Player player, int level) {
        for (int id : PICKAXES) {
            if (level >= pickaxeRequiredLevel(id)
                && player.getCarriedItems().hasCatalogID(id, Optional.of(false))) return id;
        }
        return -1;
    }

    public static int selectWoodcuttingAxe(Player player) {
        // Stock axes have no axe-specific Woodcutting level restriction;
        // the resource definition supplies the required skill level.
        for (int id : WOOD_AXES) {
            if (player.getCarriedItems().hasCatalogID(id, Optional.of(false))) return id;
        }
        return -1;
    }
}
