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
