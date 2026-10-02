package orsc;

/** Captured NPC tint semantics independent of private animation addressing. */
public final class NpcAnimationMaskPolicy {
	private NpcAnimationMaskPolicy() { }
	public static String derive(int sourceId, boolean custom, int colour) {
		if (colour == 1) return "hair-and-skin";
		if (sourceId >= 230 && custom) return "literal-and-skin";
		if (colour == 2) return "top-and-skin";
		if (colour == 3) return "bottom-and-skin";
		return "literal-only";
	}
	/** Two signed mask ints packed without allocation in the rendering loop. */
	public static long resolve(String policy, int colour, int hair, int top, int bottom, int skin) {
		int primary = colour;
		if ("hair-and-skin".equals(policy)) primary = hair;
		else if ("top-and-skin".equals(policy)) primary = top;
		else if ("bottom-and-skin".equals(policy)) primary = bottom;
		else if (!"literal-and-skin".equals(policy) && !"literal-only".equals(policy))
			throw new IllegalArgumentException("Unknown NPC mask policy");
		int secondary = "literal-only".equals(policy) ? 0 : skin;
		return ((long) primary << 32) | (secondary & 0xffffffffL);
	}
}
