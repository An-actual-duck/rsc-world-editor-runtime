# Lossless imported NPC frames

Client and server advertise `World-Builder-Npc-Rgb: npc-rgb-frames-v1`.
Producers must require both markers before capturing RGB animation records.
The client also publishes `World-Builder-Npc-Animation-Count: 1080`, the upper
bound of the packaged animation table across supported sprite settings. The
focused rendering test checks this bound against the actual table loader.
Producers allocate appended animation IDs above this bound and every imported
NPC layer or existing project registry ID. Existing IDs are not renumbered.

The project NPC animation registry retains schema version 1. Original rows
retain exactly their existing keys and paired archive semantics. An explicit
RGB row replaces `customSpriteSubspace`, `customSpriteEntry`, and
`customEntrySha256` with `frameSource: "authentic-rgb"`. All other fields remain
required. Unknown modes, mixed row shapes, and RGB IDs below 1080 are rejected.

Each RGB frame is stored in the bound authentic archive at
`sprites/<authenticBaseSpriteId + frameOffset>.dat`; the registry authentic
frame hashes bind these exact bytes. Its representation is the existing
`Sprite.pack` big-endian format: signed int width and height, one shift byte,
four signed ints for x/y shift and width/height bounds, then one RGB int per
pixel. Zero is transparent. Nonzero pixels are normalized 24-bit RGB, not ARGB.
Positive dimensions and bounds are at most 4096; offsets are within ±4096.
Payload length must be exact, frames are bounded to 16 MiB, and the registry
has a 256 MiB decoded RGB payload budget.

These frames are authoritative in both authentic and custom sprite modes.
They bypass neither archive hashes nor project identity checks. Their
AnimationDef identity is bound when project definitions load; authentic
startup retains their explicit frame base. Original paired animation records
and ordinary packaged animation loading retain their prior behavior.

Run `python3 tests/myworld/test-project-npc-rgb-frames.py` for actual client
initialization and software drawing across both modes, eight directions, and
three walk beats, plus malformed payload refusal by both runtime roles.

Acceptance on 2026-09-28 used a disposable Editor-captured project containing
NPC 866 and the owner's tracked Naga direction sheet. Both runtime roles
accepted the unchanged captured bundle. The client resolved its appended
animation 1080 and drew the complete body in all 48 walk poses (two modes,
eight directions, three beats). A retained contact sheet was visually checked
for full body, blades, mirrored directions, and corresponding animation beats.
This was real software rendering through `drawNPC`; a networked gameplay
session and native OpenGL presentation were not exercised by this probe.

## Captured NPC mask policy

Both private authoring roles advertise `World-Builder-Npc-Mask-Policy: npc-mask-policy-v1`.
This marker is not a target map/runtime compatibility requirement. Existing
compatible game servers and clients need no upgrade merely to capture these
private presentation rows.
Producers must require this paired capability before emitting the optional RGB
row fields `npcMaskPolicy`, `sourceAnimationId`, and `sourceCustomSprites`.
These fields are all present or all absent, and are forbidden on non-RGB rows.
Source animation IDs are integers 0..65535 and the source flag is a JSON boolean.
The consumer binds that provenance to its independently verified source profile;
the runtime checks its internal consistency, not arbitrary target-source truth.

The policy is derived in this exact order from the original animation ID,
original custom-sprite flag and `charColour`:

1. Color 1: `hair-and-skin`.
2. Custom sprites enabled and original ID >=230: `literal-and-skin`.
3. Color 2: `top-and-skin`.
4. Color 3: `bottom-and-skin`.
5. Otherwise: `literal-only`.

The first mask is the named NPC palette value, or literal `charColour`.
The second is NPC skin except for `literal-only`, where it is zero.
Unknown or inconsistent policies are refused by client and server. Private
animation allocation and the authoring client's sprite flag cannot change these
captured semantics. Rows without a policy retain the previous ID-dependent
behavior. NPC composition continues passing a zero blue mask; frame pixels are
never pre-tinted. This adds no gameplay, NPC identity, or target mutation rules.

`python3 tests/myworld/test-project-npc-mask-policy.py` checks both-role rejection
and actual `drawNPC` framebuffer parity against source-addressed legacy rows:
threshold IDs, both source/private flags, five color selectors, 15/18/27 frames,
eight walk and eight combat directions, animation beats, wield layers, repeated
slots, shifted bounds, clipping, transparent/near-black/mask pixels. The source
mask arithmetic is independently asserted against the previous branch ordering.
