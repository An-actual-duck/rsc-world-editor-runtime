package orsc;

/** Bound Base public skill and combat-style presentation, separate from Advanced controls. */
public final class CurrentBaseSkillContract {
    private CurrentBaseSkillContract() { }
    public static boolean selected() {
        CurrentCompositionIdentity identity = CurrentCompositionIdentity.current();
        return identity.isEnabled() && "current-base-v1".equals(identity.value("variantId"));
    }
    public static String[] names() {
        return new String[]{"Attack", "Defense", "Strength", "Hits", "Ranged", "Prayer", "Magic",
            "Cooking", "Woodcutting", "Fletching", "Fishing", "Firemaking", "Crafting", "Smithing",
            "Mining", "Herblaw", "Agility", "Thieving"};
    }
    public static String[] styleLabels() {
        return new String[]{"Select combat style", "Controlled (+1 of each)", "Aggressive (+3 strength)",
            "Accurate   (+3 attack)", "Defensive  (+3 defense)"};
    }
}
