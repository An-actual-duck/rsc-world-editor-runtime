# In-Game World Editor: Foundation and Entity Tools

Status: the inspection foundation is complete. Scenery and NPC editing delegate
to the established administrator commands. Terrain draft painting covers the
complete raw tile record through compact Surface and Structure tools. An
explicit save now durably materializes terrain drafts into the matching server
and client landscape archives. Undo/redo, publish, and terrain patch replay
remain intentionally unavailable.

## Raw terrain contract

Both custom clients and the server consume `Custom_Landscape.orsc`, a ZIP whose
sector entries are named `h{plane}x{sectorX}y{sectorY}`. A sector is 48 by 48
tiles in X-major order (`x * 48 + y`). Each tile is exactly ten big-endian
bytes:

| Offset | Width | Field | Raw range |
|---:|---:|---|---:|
| 0 | 1 | elevation | unsigned 0..255 |
| 1 | 1 | ground texture | unsigned 0..255 |
| 2 | 1 | ground overlay | unsigned 0..255 |
| 3 | 1 | roof texture | unsigned 0..255 |
| 4 | 1 | horizontal wall | unsigned 0..255 |
| 5 | 1 | vertical wall | unsigned 0..255 |
| 6 | 4 | diagonal wall encoding | signed 32-bit integer, preserved byte-exactly |

Diagonal values `1..11999` mean definition `raw - 1`, NW-SE. Values
`12001..23999` mean definition `raw - 12001`, NE-SW. Zero means none; 12000
and values outside those ranges are reserved/invalid for editor authoring.

World Y encodes the plane in 944-tile bands. The request must satisfy
`floorDiv(worldY, 944) == plane`. Archive coordinates are:

```text
baseY   = worldY - plane * 944
sectorX = floorDiv(worldX + 2304, 48)
sectorY = floorDiv(baseY + 1776, 48)
localX  = floorMod(worldX, 48)
localY  = floorMod(baseY, 48)
```

The authoritative response reports both raw archive fields and the current
runtime tile's derived traversal mask/projectile flag. Collision is derived
from overlay definitions, horizontal/vertical walls, diagonal walls, runtime
scenery, and neighboring tiles; it must never be inferred from one raw field.
Raw ground overlay `255` is the explicit exception to one-based definition
lookup: it displays and blends the tile's `groundTexture` color like overlay
`0`, while contributing full terrain collision.
The Surface UI calls raw `groundTexture` **Floor Color**; it selects one of the
256 base palette colors and does not affect collision. It calls raw
`groundOverlay` **Floor Texture**; nonzero values are one-based tile-definition
references, and that definition's object type determines terrain blocking.

Uniform 48-by-48 server regions may be memory-compressed to one shared
`TileValue`. Every post-load collision writer uses the mutable-tile API, which
expands that region into independent copies before changing one coordinate.
Terrain painting and runtime scenery/boundary registration therefore cannot
mutate collision on untouched tiles through the compressed representation.

## Protocol and authorization

- Client to server opcode 152 and server to client opcode 151 are reserved for
  one versioned editor envelope. Version 1 supports close, terrain inspect/copy,
  scenery inspect, NPC inspect, and terrain-paint operations. A paint request
  carries one coordinate, a seven-bit field mask, and candidate Elevation,
  Floor Color, Floor Texture, Roof, East Wall, North Wall, and Diagonal Wall values. The accepted response contains the
  complete canonical terrain record; the client does not preview rejected data.
- `allow_in_game_world_editor` defaults false and is explicitly false in both
  MyWorld configurations.
- `::worldeditormode` is server authoritative. It requires the gate, an
  administrator account, and the custom desktop-capable protocol.
- The server grants one active owner globally using an opaque random 64-bit
  session ID. Every request must carry the exact next sequence. Ownership is
  released on explicit close or player unregister/disconnect.
- Android never creates or opens the shell. Normal play receives no editor
  packets and adds no menu entries while the shell is closed.

## UI contract

The movable desktop overlay exposes mutually exclusive Navigate, Inspect,
Terrain, Scenery, and NPC tabs. Navigate continuously reports the player,
last-clicked tile, and stored inactive brush positions. Its coordinate teleport
and click-teleport preference use existing staff-authorized movement and are
active only in Navigate. Inspect restores ordinary walking and is the only mode
that adds terrain, boundary, scenery, and NPC inspection entries. It displays
the last authoritative result. Every target also has a right-click copy action,
and Inspect can copy its last successful result. Copies remain local and seed
the matching editor selection. Terrain snapshots use player-facing
coordinates, named planes, floor color/texture semantics, normalized north/east/
diagonal wall definitions, and derived collision while retaining raw archive
fields in the copied snapshot. Object and NPC results are resolved against the
live authoritative world and labelled `runtime-authoritative`.

Terrain uses Surface and Structure sub-tabs within the existing window size.
Surface exposes three independently enabled raw-byte fields: Elevation, Floor
Color, and Floor Texture. Structure exposes Roof, North Wall, East Wall, and
Diagonal Wall fields with resolved definition labels; diagonal orientation is
selected as `\\` or `/` and encoded into the archive convention. Zero removes
the selected component. Copying an inspected terrain tile seeds both pages
without changing which fields are enabled. The editor uses a one-tile brush and
a low-priority-number Paint action. The server validates the feature gate,
administrator, session ID, sequence, coordinate/plane agreement, field mask,
byte ranges, and Floor Texture definition. Accepted records enter a coalesced,
4,096-tile server-lifetime draft and update runtime elevation/overlay collision.
Inspection reads through this draft. The client applies only accepted full
records. Brush choices are centered 1x1 and centered 3x3 squares; Roof may use
either, while any wall field forces an exact 1x1 stroke to avoid generating an
internal wall grid. Normal clicks send one or nine tiles. Ctrl + left-drag
collects each distinct footprint tile once, commits on release, and flushes long
drags in bounded 64-tile chunks while continuing to collect. Each chunk is one
sequenced request and one response of authoritative full-tile snapshots. The
server rejects duplicate, malformed, cross-plane, out-of-world, or oversized
lists and prevalidates every coordinate and projected draft-size change before
committing the chunk; the client applies it with one rebuild. The UI reports
pending/accepted counts plus click-to-ack and rebuild time. An optional
non-persistent Build mode temporarily selects classic lighting, faceted geometry,
an editor tile grid, disabled terrain variation and relief, daytime tone, limited
fog distance, and paused scenery animation refresh; closing the editor restores
the exact prior runtime renderer settings. The
client advances a terrain-cache revision
so older background preload products cannot win. Legacy water-like overlays
normally extend visual faces onto four cardinal neighbors; transient editor
metadata suppresses that spill for painted overlays so brush previews match
their exact raw-tile footprint without changing existing world water. Terrain
overlay, directional wall, diagonal wall, and projectile collision ownership is
tracked separately from runtime scenery/boundaries. Removing terrain therefore
cannot erase an overlapping dynamic collision source. `Save edits` invokes the
existing `::saveworldedits` commit point. Terrain remains a server-lifetime
draft until that explicit save succeeds.

Scenery exposes an object-definition
selector with resolved name and Place, Rotate, and Remove tools. These tools are
limited to type-0 scenery; boundary walls remain inspection-only. NPC exposes a
definition selector with resolved name, a roam radius from 0 through 64, and
Place and Remove tools. Active tools add low-priority-number context actions so
one click performs one operation while the editor tab is selected. They invoke
the existing `aobject`, `rotateobject`, `robject`, `cnpc`, and `rpc`
administrator commands, retaining their authorization, validation, runtime
registration, and pending-edit behavior. `Save queued edits` invokes the
existing `saveworldedits` command. Undo and redo are deliberately deferred until
the complete editing workflow exists; no partial command-queue undo semantics
are introduced here.

## Terrain save contract

Saving terrain requires the administrator who owns the active editor session.
The server verifies that its landscape still matches the digest captured when
the draft was opened and that the tracked server and client archives are
byte-identical. It writes and verifies temporary output before replacing either
archive, confirms their resulting SHA-256 hashes match, and preserves a
timestamped pre-save copy under
`server/conf/server/data/world-editor-backups/`. Replacement uses an atomic move
where supported and restores both copies from the backup if replacement or
final verification fails. The in-memory draft is cleared only after the saved
archive reopens successfully; failures retain the recoverable draft.

This commit point updates the two workspace `Custom_Landscape.orsc` files. It
does not publish, deploy, or transmit a new archive to other connected clients.
Those steps remain part of the normal manager review and release workflow.

## Future patch/recovery decision

The future durable format will be an append-only, versioned patch journal, not
a rewritten ZIP as the editing working copy. Each transaction will carry an
opaque transaction ID, editor identity, base archive digest, ordered before/after
raw tile records or entity loc records, and a commit marker. Startup recovery
may replay committed transactions only. The current verified archive
materializer and backups provide durable manual saves, but no append-only
journal or startup replay exists yet.
