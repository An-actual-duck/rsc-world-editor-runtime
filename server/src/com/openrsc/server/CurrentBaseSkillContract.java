package com.openrsc.server;

/** Conservative public numeric skill identities; never an unbound runtime default. */
public final class CurrentBaseSkillContract {
    private CurrentBaseSkillContract() { }
    private static final String[] NAMES = {
        "Attack", "Defense", "Strength", "Hits", "Ranged", "Prayer", "Magic", "Cooking",
        "Woodcutting", "Fletching", "Fishing", "Firemaking", "Crafting", "Smithing",
        "Mining", "Herblaw", "Agility", "Thieving"
    };
    public static boolean selected() {
        CurrentCompositionIdentity identity = CurrentCompositionIdentity.current();
        return identity.isEnabled() && "current-base-v1".equals(identity.value("variantId"));
    }
    public static String[] names() { return NAMES.clone(); }
    public static int styleSkill(int style) {
        switch (style) {
            case 1: return 2;
            case 2: return 0;
            case 3: return 1;
            default: return -1;
        }
    }
    public static int[] meleeExperienceWeights(int style) {
        switch (style) {
            case 0: return new int[]{1, 1, 1, 1};
            case 1: return new int[]{0, 0, 3, 1};
            case 2: return new int[]{3, 0, 0, 1};
            case 3: return new int[]{0, 3, 0, 1};
            default: throw new IllegalArgumentException("public combat style outside 0..3");
        }
    }
}
