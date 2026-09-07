package com.openrsc.server;

/** Current Base public combat selection and reviewed numeric projectile tables. */
public final class CurrentBaseCombatContract {
    private CurrentBaseCombatContract() { }
    public static boolean selected() {
        CurrentCompositionIdentity identity = CurrentCompositionIdentity.current();
        return identity.isEnabled() && "current-base-v1".equals(identity.value("variantId"));
    }

    public static double spellPower(com.openrsc.server.constants.Spells spell) {
        switch (spell) {
            case WIND_STRIKE: return 1.0;
            case WATER_STRIKE: return 2.0;
            case EARTH_STRIKE: return 3.0;
            case FIRE_STRIKE: return 4.0;
            case WIND_BOLT: return 4.5;
            case WATER_BOLT: return 5.0;
            case EARTH_BOLT: return 5.5;
            case FIRE_BOLT: return 6.0;
            case WIND_BLAST: return 6.5;
            case WATER_BLAST: return 7.0;
            case EARTH_BLAST: return 7.5;
            case FIRE_BLAST: return 8.0;
            case WIND_WAVE: return 8.5;
            case WATER_WAVE: return 9.0;
            case EARTH_WAVE: return 9.5;
            case FIRE_WAVE: return 10.0;
            default: return -1.0;
        }
    }

    /** Consume the stock ring's persistent budget; caller owns damage/death delivery. */
    public static int consumeRecoil(com.openrsc.server.model.entity.player.Player wearer, int incomingDamage) {
        if (!selected()) throw new IllegalStateException("public recoil requires bound Current Base");
        if (incomingDamage <= 0 || !wearer.getCarriedItems().getEquipment().hasEquipped(1314)) return 0;
        int used = wearer.getCache().hasKey("ringofrecoil") ? Math.max(0, wearer.getCache().getInt("ringofrecoil")) : 0;
        int remaining = Math.max(0, wearer.getConfig().RING_OF_RECOIL_LIMIT - used);
        int reflected = Math.min(remaining, incomingDamage / 10 + 1);
        if (reflected >= remaining) {
            wearer.getCache().remove("ringofrecoil");
            wearer.getCarriedItems().shatter(new com.openrsc.server.model.container.Item(1314));
        } else {
            if (used == 0) wearer.message("You start a new ring of recoil");
            wearer.getCache().set("ringofrecoil", used + reflected);
        }
        return reflected;
    }

    public static int rangedAim(int id) {
        switch (id) {
            case 189: return 10;
            case 59: case 60: return 12;
            case 188: case 649: return 15;
            case 648: case 651: return 20;
            case 650: case 653: case 827: case 1013: case 1122: case 1135: return 25;
            case 652: case 655: case 1015: case 1076: case 1123: case 1128: return 30;
            case 1088: case 1136: return 33;
            case 654: case 657: case 1024: case 1075: case 1124: case 1129: return 35;
            case 656: case 1068: case 1077: case 1081: case 1125: case 1130: case 1132: case 1453: return 40;
            case 1089: case 1137: return 41;
            case 1069: case 1078: case 1126: case 1131: return 45;
            case 1090: case 1138: return 49;
            case 1070: case 1079: case 1127: case 1133: return 50;
            case 1080: case 1134: return 55;
            case 1091: case 1139: return 57;
            case 1092: case 1140: return 65;
            default: return 0;
        }
    }

    public static int rangedPower(int id) {
        switch (id) {
            case 11: case 574: case 1013: case 1122: return 15;
            case 1015: case 1123: return 17;
            case 190: case 592: case 638: case 639: return 20;
            case 1024: case 1124: return 22;
            case 640: case 641: case 1068: case 1076: case 1125: case 1128: return 25;
            case 1069: case 1126: return 27;
            case 827: case 1135: return 29;
            case 642: case 643: case 786: case 1070: case 1075: case 1127: case 1129: return 30;
            case 644: case 645: case 1077: case 1081: case 1130: case 1132: return 35;
            case 1088: case 1136: return 37;
            case 646: case 647: case 1078: case 1131: return 40;
            case 1079: case 1133: return 45;
            case 1089: case 1137: return 46;
            case 1080: case 1134: case 1449: case 1450: case 1451: case 1452: return 50;
            case 1090: case 1138: return 53;
            case 1091: case 1139: return 61;
            case 1092: case 1140: return 69;
            default: return 0;
        }
    }

    public static int rangedPowerRetro(int id) {
        switch (id) {
            case 189: return 14;
            case 188: return 20;
            case 59: case 60: return 22;
            default: return 0;
        }
    }
}
