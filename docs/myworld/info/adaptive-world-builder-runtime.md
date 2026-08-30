# Adaptive World Builder Runtime Contract

Status: implemented upstream runtime capability. This document describes the
runtime boundary consumed by the standalone World Builder repository. It does
not authorize a release, target installation, or production-profile change.

The adaptive runtime opens one already-prepared, isolated signed-layered
project. It does not discover, convert, import, or update a target server. The
standalone World Builder owns those operations and must verify that the target
is offline before it prepares this runtime. Once started, this runtime has no
target path and accepts authored output only inside the selected project.

## Stable identities

The machine-readable source of truth is
`server/conf/world-builder/adaptive-runtime-capability-v5.json`. Server and
client code independently pin the same values.

| Role | Identity |
|---|---|
| Capability | `adaptive-world-builder-runtime-capability-v5` |
| Runtime profile | `adaptive-world-builder` |
| Server build | `rsc-world-editor-runtime-adaptive-builder-server-v5` |
| Client build | `rsc-world-editor-runtime-adaptive-builder-client-v5` |
| Loader | `generic-signed-layered-loader-v6-project-content-bundle-v3` |
| Authoring | `generic-signed-layered-authoring-v2-u16-elevation` |
| Definition binding | `world-builder-definition-catalog-binding-v1` |
| Client asset binding | `world-builder-client-asset-binding-v1` |
| Protocol | `world-builder-native-layered-protocol-v2-u16-elevation` |
| Effective composition | `world-builder-effective-static-composition-v1` |
| Package schema | `layered-world-package-v1` |
| Coordinate model | `signed-layered-v1` |
| Placement encoding | `layered-world-placements-v4` for newly saved work; v3 remains readable |

The ordered `encodingVersions` capability list is `[1, 2, 3, 4]`: legacy and
wide terrain plus placement payloads v3 and v4. Target-server integration must
preserve that complete declaration so World Editor can reject an incompatible
install before copying or activating a map package.

`scripts/write-adaptive-world-builder-runtime-evidence.py` emits canonical
`world-builder-runtime-evidence` schema-version-1 JSON for adaptive discovery.
It hashes a real, bounded, non-linked definition-catalog evidence file rather
than publishing a placeholder hash. Example:

```bash
./scripts/write-adaptive-world-builder-runtime-evidence.py \
  --side server \
  --definition-catalog working/runtime/server/evidence/definitions.json \
  --definition-catalog-id creator.catalog.v1 \
  > working/runtime/server/evidence/runtime.json
```

Run it again with `--side client` and the client catalog. The resulting server
and client evidence must match the target capability descriptor exactly. The
standalone preparer remains responsible for inventorying those files and for
supplying the actual client asset identity and hash.

The definition catalog is the project authoring authority, not an inventory of
definitions already referenced by the map. It is the World Editor's strict
eight-field schema-version-1 JSON with exactly `schemaVersion`, `manifestType`,
`catalogId`, `tiles`, `boundaries`, `scenery`, `npcs`, and `groundItems`.
`manifestType` must be `world-builder-definition-catalog`, and `catalogId` must
equal the configured definition identity. Each family is a strictly increasing
array of non-negative integer IDs; for example:

```json
{"schemaVersion":1,"manifestType":"world-builder-definition-catalog","catalogId":"creator.catalog.v1","tiles":[0,7],"boundaries":[0,1],"scenery":[0,1],"npcs":[0,1],"groundItems":[10,11]}
```

The server verifies that every catalog ID exists in its loaded definitions and
that every definition already referenced by the effective map composition is a
member of the catalog. The authenticated binding carries the four placement
families as separate `authorable*Ids` fields. Both adopted and standalone
projects use those fields for new boundary, scenery, NPC, and ground-item
placements; a valid catalog ID remains authorable even when the map does not
currently use it.

NPC base and custom definition files are one sequential registry; embedded
`id` fields do not create sparse slots. Before authentication, both runtime
consumers therefore count the exact base/custom rows and require every catalog
NPC plus every patch/world overlay ID to be below that count. The Editor may
normalize a sparse neutral provider record or unresolved placement by adding
project-local custom rows and deterministic gap placeholders. Those rows are
ordinary hashed content-bundle evidence: the selected server is unchanged,
target code is never executed, and an unbacked sparse catalog fails closed
before either side activates.

## Required project layout

The runtime accepts the Phase 3 project layout only:

```text
<project>/
  source/
    layered-baseline/package/       immutable source package
  working/
    layered-world/package/          only authored package destination
    runtime/server/                 isolated server process root
    runtime/client/                 isolated desktop client root
  run/
    world-builder/
      adaptive-runtime.lock
      effective-static-composition.json
      runtime-binding.properties
      ready
      shutdown.request              created only to request shutdown
```

The server process current directory must be the canonical
`working/runtime/server` directory. Every workspace component and package file
must be a normal contained path: symbolic links, hard-linked package/evidence
files, path escapes, case aliases, Windows-hostile names, untracked package
files, and oversized inventories fail before readiness. The source baseline
and working package must be different filesystem identities and neither may
contain the other.

The runtime holds `adaptive-runtime.lock` for its process lifetime. Readiness
is published only after the package, definitions, assets, composition, and
binding pass. A second runtime cannot own the same project. Unexpected control
failure removes readiness and requests local server shutdown.

## Explicit activation

Package shape never activates this profile. The isolated server must enable
all of the following as one bounded selection:

- `world_builder_mode=true`
- `world_builder_adaptive_mode=true`
- `world_builder_layered_review_mode=true`
- `layered_native_world_runtime_profile=adaptive-world-builder`
- all layered location, spatial, protocol-client, package, residency,
  readiness, prediction, symmetric-residency, and atomic-activation gates
- loopback-only bind address, SQLite database `world_builder`, empty table
  prefix, one maximum player, packet registration off, and in-game editor on

The preparer must also supply the working package path, exact manifest and
closed-inventory hashes, immutable source-baseline inventory hash, one of the
origins `target-layered`, `target-packed`, or `standalone-empty`, definition
and asset IDs/hashes/evidence paths, and the initial global coordinate. The
definition and asset evidence files must be inside `working/`.

Target-backed projects bind the Editor-owned
`project-local-custom-content-v3` capability. Bundle v1 and v2 remain accepted
for existing projects. The only accepted content input
is the exact `working/content-bundle` directory with manifest type
`world-builder-project-content-bundle`, schema version 3. Its closed inventory
contains captured server definition files for tiles, boundaries, scenery,
NPCs, and items plus the existing client `library.orsc`, `models.orsc`,
`Authentic_Sprites.orsc`, `Custom_Sprites.osar`, and `Menus.osar` archives.
Loose images, loose models, scripts, classes, plug-ins, and target behavior are
not content-bundle inputs and are never executed.

For an in-range scenery ID, a captured server definition can name a historical
model alias that the packaged client never used and the captured model archive
does not contain. The client retains its trusted packaged definition for that
same ID while applying the project catalog. At model-load time it uses that
packaged model only when the requested archive entry is proven absent and the
packaged entry is proven present. A real project model always wins, explicit
empty/`na` models remain invisible, and beyond-packaged scenery IDs still
require their exact project model. Each activated alias resolution is reported
with its scenery ID and both model names; no target code is executed to infer
the mapping.

### Versioned item-visual closure

`project-local-custom-content-v1` cannot author a new ground-item visual. The
captured server item JSON contains gameplay fields but no client item-to-sprite
mapping, while the definition catalog contains IDs only. In particular, the
frozen fixture declares item `9000` without the `ItemDef` values that select and
recolour its visual. A runtime must not infer those values from the item ID.
The client therefore refuses a bundle-v1 item that has no pre-existing packaged
client definition. Existing IDs may retain their exact packaged visual mapping;
new IDs cannot activate under bundle-v1.

Bundle v1 remains accepted only when every target ground-item ID already has a
packaged client visual; its new-item refusal remains fail-closed. Bundle v2
adds a sorted manifest `itemVisuals` array, a separately bound
`itemVisualFingerprintSha256`, and the preserved static-evidence role
`metadata.item-visuals` at
`server/conf/world-builder/item-visuals-v1.json`. The array contains exactly
one record for every target ground-item ID absent from the packaged catalog,
with exactly these fields:

```json
{
  "itemId": 9000,
  "authenticSpriteId": null,
  "customSpriteAssetRole": "asset.sprite.custom",
  "customSpriteSubspace": "items",
  "customSpriteEntry": "0",
  "pictureMask": 3368601,
  "blueMask": 1122867
}
```

- `itemId` is the exact ground-item catalog ID (`0..65535`).
- `authenticSpriteId` is `null` for a named mapping or an unsigned-short
  `0..65535` ID whose exact `sprites/ID.dat` palette-frame entry must decode in
  `asset.sprite.authentic`; the decoded sprite installs at renderer slot
  `2150 + ID`.
- `customSpriteAssetRole` is exactly `asset.sprite.custom` or
  `asset.spritepack`; `customSpriteSubspace` and `customSpriteEntry` identify
  one decoded, nonempty GZIP OSAR entry in that named archive. Decoded item
  sprites remain role-specific even when both archives contain the same
  subspace/entry pair, so the legacy merged sprite tree cannot change the
  selected source.
- `pictureMask` and `blueMask` are exact signed 32-bit values.

Exactly one mapping form is present: an authentic ID with all three custom
fields null, or all three custom fields with the authentic ID null. Both
processes verify the evidence file and decode the exact referenced archive
entry before authentication. The client emits deterministic source,
dimensions, pixel SHA-256, and mask evidence when each sprite is installed.
The reviewed Editor fixture freezes definition
`f97a96299023e4cf1d738c1f3520af0c2e4339ed95aab952814832cc77e52baf`,
asset `e0ab18b793a91db852557689b9734eeb1d459e216be61b902d75a69e6e2c5bfa`,
item-visual
`f9aaf43d6cac1c96bbf10d129e1976f9638562036e1b187f684e7219a7cda8d3`,
and bundle
`88542556c723be2c4312f48eb2b42f65fb08a169edd21afa55eda075c6d4aa8b`.
Floors and walls have no sprite lookup: floor IDs and axial wall IDs are
one-less than unsigned-byte terrain values, so their exact catalog range is
`0..254`, and their XML colour/material fields are the visual definition.
Scenery, NPC, and ground-item placement IDs are unsigned-short values
`0..65535`.

### Versioned NPC animation-registry closure

Bundle v3 adds the definition-evidence role `metadata.npc-animations` at
`server/conf/world-builder/npc-animations-v1.json`. Its exact manifest type is
`world-builder-npc-animation-registry`, schema version 1. Records are sorted by
unique `animationId` and preserve the target's `name`, `category`, signed
colour and gender fields, combat/special-frame flags, exact 15/18/27 renderer
shape, custom OSAR subspace/entry/hash, authentic base sprite ID, and one
SHA-256 for every consecutive authentic frame.

Both processes structurally decode the bound custom archive, require the exact
`category/name` entry and renderer frame count, and verify every authentic
frame payload before authentication. The client installs the definitions by
their original IDs before loading project NPCs, including safe sparse IDs, so
private-server NPC definitions no longer depend on a coincidentally matching
packaged animation registry. Unknown keys, duplicate IDs, unsafe names,
special frames without combat frames, missing entries, malformed archives,
nonconsecutive ranges, and hash drift fail closed. No target classes or JARs
are inspected or executed.

Both processes receive and independently verify these properties:

- `openrsc.worldBuilderContentBundle`
- `openrsc.worldBuilderContentCapabilityId`
- `openrsc.worldBuilderContentBundleSha256`
- `openrsc.worldBuilderContentDefinitionSha256`
- `openrsc.worldBuilderContentAssetSha256`
- `openrsc.worldBuilderContentItemVisualSha256` (64 zeroes for bundle v1)

The bundle path must resolve exactly to the isolated project's working copy.
Unknown keys or files, path escapes, symbolic or hard links, portable-name
collisions, incomplete family bindings, unsafe catalog holes, payload/hash
mismatch, domain-fingerprint mismatch, catalog disagreement, and
client/server identity disagreement all fail before editable readiness. A
content-neutral standalone project keeps all six values empty and continues
to use packaged definitions and assets.

The desktop client independently requires:

- `-Dopenrsc.worldBuilderMode=true`
- `-Dopenrsc.worldBuilderAdaptiveMode=true`
- loopback host and a project-owned credential
- the server-produced
  `<project>/run/world-builder/runtime-binding.properties`
- client definition and asset evidence files inside `<project>/working/`
- the same five project-content properties used by the server for a
  target-backed project

The binding contains exact server/client builds, protocol, loader, package,
manifest, package inventory, definitions, assets, levels, origin, initial
location, and effective-composition hash. The client validates it before
login, validates its loaded definitions, and sends the binding fingerprint in
the private loopback login flow. The server opens the editor only after a
constant-time comparison with its in-memory fingerprint. Any mismatch fails
before an editable session.

## Strict terrain startup and readiness

Only the combination of `openrsc.worldBuilderMode=true`,
`openrsc.worldBuilderAdaptiveMode=true`, and a fully verified adaptive runtime
binding activates strict terrain startup. Neither property alone, loopback,
missing files, editor availability, nor package shape activates it.

In that strict profile the selected signed layered package is the sole terrain
authority. Client `World` construction does not resolve, probe, open, hash, or
read `Authentic_Landscape.orsc` or `Custom_Landscape.orsc`. The legacy archive
open, archive hash, and sector-entry read paths each carry an adaptive tripwire;
reaching one fails with the entry-point name instead of falling back. Normal
preservation and Spoiled Milk clients retain the same legacy archive choice,
open, and hash behavior.

The decorative legacy login-world is also disabled before it can load its
Lumbridge terrain/models. A strict Builder client auto-authenticates into the
verified package instead; any accidental direct login-world load fails closed.
An unrecoverable strict-runtime loop failure closes the local client with exit
status `1` rather than leaving a detached UI process alive.

World state is withheld on both sides until the private binding handshake is
complete. The server does not send scene context, terrain, or scene entities
to an adaptive player before `builderbind` succeeds. The client accepts the
first terrain context only after the server-authored editor-open receipt and
only when protocol, package, manifest, world space, declared startup level,
initial coordinates, and native coverage match the verified binding. After
that handshake, the same authenticated draft may activate a newly authored
signed level in memory when its terrain context retains the exact bound
package/manifest/world-space identity and proves native coverage. The startup
binding is never rewritten; the new level becomes immutable package evidence
only through the normal verified save. Validation occurs before scene-state
mutation, and the 64-level adaptive bound still applies. A malformed or
mismatched context fails before it becomes the active scene scope.

The game view remains on its loading frame, and all World Editor mouse,
keyboard, menu, drag-brush, and navigation input remains blocked, until the
initial region has loaded and the verified native terrain snapshot is resident.
The regular renderer-ready predicate carries the same gate. This prevents a
strict adaptive session from exposing legacy terrain, zero-filled client
state, or a stale scene while native delivery is pending.

## Generic package contract

The adaptive profile accepts exactly one package with one `global` static
world space. It does not pin a package ID, version, manifest, level list,
sector count, placement count, or Spoiled Milk content identity. Bounds are:

- 1 through 64 declared levels;
- 1 through 8,192 48-by-48 terrain sectors;
- exactly one consistently encoded v3 or v4 placement set for every declared level;
- at most 100,000 total static placements; and
- the closed package guard's file, directory, per-file, and total-byte limits.

Every level must have terrain. Every placement and NPC roam rectangle must be
covered by package terrain. Terrain, boundaries, scenery, NPCs, and respawning
ground items are definition-checked before world population. Direction, ID,
amount, respawn, collision, coordinate, and coverage rules remain those of the
native layered package loader. Unknown, unsupported, duplicate, ambiguous, or
out-of-coverage content is rejected; nothing is silently skipped.

The runtime loads all four static placement families and publishes their exact
effective ordered records, source paths, source encodings, and hashes in
`effective-static-composition.json`. The adaptive profile is a complete package
replacement, so legacy configuration overlays do not enter the effective
model. Package boundary placements are inspectable and preserved exactly;
terrain wall fields, scenery, NPCs, and ground-item spawns retain their
existing editor operations.

## Wide terrain elevation v2

Native terrain capability v2 stores elevation as an unsigned 16-bit value
from `0` through `65535`. Rendering, collision sampling, walls, roofs,
entities, camera projection, terrain picking, and minimap geometry continue to
consume elevation units at the historical multiplication-by-3 scale; v2
widens the authored range but does not change that scale.

The v1 terrain encodings (`uniform-layered-sector-v1`,
`rle-layered-sector-v1`, and `raw-layered-sector-v1`) are frozen. Their
one-byte elevation is decoded unsigned and promoted exactly into the runtime
integer model. New or saved Builder terrain uses the explicitly named v2
encodings ending in `-v2-u16`; raw v2 records are 11 bytes in network order:
two elevation bytes, the five unchanged byte fields, then all four diagonal
wall bytes. No non-elevation field is translated during promotion or save.

The editor envelope is capability version 4 and carries elevation as an
unsigned short. Absolute sets and configurable-step Raise/Lower operations
are accepted only by native layered authoring. Every tile in a stroke is
calculated and bounds-checked before the draft changes, so any overflow or
underflow rejects the complete stroke. Unsupported terrain encodings, record
widths, editor envelopes, or client/server runtime identities fail closed;
there is no clamp, byte truncation, fallback save, or silent downgrade.

Frozen legacy landscape archives remain 10-byte records and readable. They
cannot store elevations above 255, and the legacy pack/save path refuses such
a value instead of narrowing it.

## Session operation Undo and Redo

Editor envelope v4 retains positive operation tokens for terrain requests and
adds authoritative placement-history acknowledgements. A click, Line, or
Rectangle uses one token. Every acknowledged batch in one continuous freehand
drag shares a token, so the complete gesture is one history operation rather
than a stack of network chunks. Scenery Place, Move, Rotate, and Remove; NPC
Place and Remove; and ground-item Place and Remove each enter the same ordered
session stack. A scenery move is one atomic two-location operation.

The server retains at most 64 operations and 65,536 referenced terrain or
placement states for the active Editor session. It stores the first
before-state and final after-state for each affected identity. Undo and Redo
compare every current authoritative state against the expected side before
changing any draft state; drift refuses the complete operation. A new edit
clears Redo. Placement reversals register or retire their live runtime entity,
so scenery, NPC, and ground-item visuals update without restarting the Builder.
History never changes the target server and is cleared when the Editor session
closes or an Editor-owned package publication replaces the running package.
Client-side availability is only a presentation hint. Undo and Redo requests
always reach the authoritative session stack once current edits are settled;
a delayed or missed placement message cannot disable a valid operation.

The session stack covers layered terrain clicks, freehand gestures, Lines,
Rectangles, and the three placement families. An operation that allocates new
terrain establishes a safe history boundary because sector allocation is not
yet reversible. Editor-owned Region transactions remain separate durable
package transactions; the existing exact last-Paste Undo continues to apply
there.

The shared definition browser covers scenery, NPCs, ground items, walls, and
floor textures. Wall results are built from the complete loaded runtime door
inventory, with curated labels layered over custom runtime definitions, and a
selection is converted back to the terrain archive's one-based wall byte.
Floor results use the raw overlay value shown in the terrain controls, include
the no-overlay value and bridge-transition alias, expose traversal metadata,
and remain filtered to the active project's declared authoring definitions.

## Empty and existing-level authoring

Existing copied levels are editable only under explicit adaptive activation.
New terrain sectors use the shared canonical void tile:

```text
elevation=0, ground texture=1, ground overlay=8,
roof=0, horizontal wall=0, vertical wall=0, diagonal wall=0
```

The standalone-empty origin is stricter: one global level `0`, one terrain
sector covering the configured `0..32767` client-carrier start, one empty v4
placement set, and no placements. New standalone projects require the exact
centered 3-by-3 visibility seed emitted by the Editor: all ten raw terrain
bytes are zero for the nine seed tiles, while the other 2,295 tiles remain
canonical structural void. The start must therefore be at least one tile from
every edge of its sole sector. Exact legacy standalone projects at coordinate
`0,0` retain their original all-void sector for compatibility; no other
unseeded shape is accepted. Adaptive player initialization intentionally
bypasses ordinary production login recovery, because production correctly
treats overlay 8 as non-playable while an empty Builder uses it as an authoring
canvas. The definition catalog must expose overlay 8's one-based tile
definition ID 7.

New adaptive placement IDs use only family, signed level, coordinate, and a
bounded deterministic collision slot under `world-builder.authored.*`. Host
paths, time, randomness, package identity, and Spoiled Milk identity never
enter them. Existing arbitrary placement and placement-set IDs are retained
across edit/save.

Go/Create navigation publishes a newly allocated void-backed level or work
area to the running authenticated client and enters it in the same session.
The client extends only its in-memory active-level set after the exact terrain
context passes validation; saving and reopening is recovery and persistence
verification, not a prerequisite for navigation. Canonical automatic
ladder/stair pairing uses this same live activation path when it creates an
adjacent level and inverse object.

The scenery Move tool preserves that exact placement ID, definition, direction,
level, and package owner while changing only its coordinates. The server stages
the source removal, destination membership, complete collision footprint, NPC
blocking footprint, and draft records as one transaction. A destination outside
allocated terrain, across a package or level boundary, or overlapping any other
scenery footprint is refused before the source is changed. The client presents
an explicit source marker and live wireframe destination ghost; Escape,
right-click, a tool/mode change, or closing the editor cancels selection without
issuing a mutation.

## Verified save and recovery

`::saveworldedits` materializes the complete effective package, including all
unchanged boundary records and all edited terrain/scenery/NPC/ground-item
records. The authenticated command validates and locks the active draft
immediately, acknowledges the request, then reconstructs the immutable package
snapshot and performs package I/O on one dedicated save worker. Terrain edits
are indexed once by sector before reconstruction; snapshot cost therefore does
not multiply every accumulated tile edit by every sector in a large map.
Normal game updates remain responsive; further mutations, duplicate saves, and
Editor closure are refused until the verified completion or failure message is
delivered. If the user selects Save while an authoritative brush, line,
rectangle, or placement response is still arriving, the client visibly queues
the save and submits it automatically after the last response instead of
silently ignoring the request. The queued state is polled on every rendered
Editor frame. If no acknowledgement progress arrives for ten seconds, the
client submits the already-requested save behind the edit packets on the same
connection, reports the exact unacknowledged count, and tells the user to
reopen after completion to reconcile the server-authoritative result. A late
edit acknowledgement cannot clear the active-save guard, and an explicit edit
refusal still saves all earlier accepted work rather than abandoning the Save
request.
Publication is copy-on-write:

1. match the current working and immutable baseline inventories to their
   startup-validated exact fingerprints;
2. construct canonically ordered package bytes in a sibling stage;
3. hash every staged file against the in-memory model;
4. reload and validate the closed staged package with the generic runtime and
   active definition contracts;
5. prove the staged, current, and baseline inventory fingerprints again after
   observer boundaries and immediately before publication;
6. force durable transaction evidence and require atomic same-filesystem
   directory moves;
7. publish the already-validated stage without rewriting its bytes; and
8. remove the prior package and transaction evidence only after both moves
   succeed.

The stage is intentionally validated as one transaction instead of issuing a
separate synchronous storage flush for every terrain-sector file. That keeps
save latency from scaling with thousands of filesystem flush round trips while
the forced transaction record, retained previous package, atomic moves, and
startup recovery continue to distinguish every interruption point.

A failed save restores and verifies the prior complete working package. A
startup recovery marker distinguishes an old complete package, a new complete
package, and an interrupted swap. Unowned staging state or unverifiable
recovery state blocks startup for manual review. Source baseline and target
server data are never save destinations. The runtime rechecks the source
baseline immediately before publication; the standalone preparer retains
target fingerprint responsibility because no target path enters this process.

## Preservation and integration boundary

`preservation-r64-replacement`, `spoiled-milk-replacement`,
`spoiled-milk-builder-draft`, and `spoiled-milk-world-builder-export` retain
their previous identities, exact content/count checks, and behavior. Adaptive
code does not infer or alter any of those profiles.

The standalone repository must still:

1. perform read-only discovery and conversion;
2. prepare the exact isolated layout and truthful configuration/evidence;
3. prove source and target drift has not occurred;
4. launch only these isolated client/server copies; and
5. keep target installation behind its separate offline, preview,
   confirmation, backup, receipt, rollback, undo, and no-force transaction.

This upstream runtime does not patch unknown client/server binaries, distribute
maps to players, or grant import authority.

## Verification

Automated coverage lives in
`tests/myworld/test-adaptive-world-builder-runtime.py` plus the native layered
package, placement, protocol, persistence, editor, and runtime suites. It uses
temporary content-neutral packages and checks deterministic output across
absolute roots, all placement families, canonical empty terrain, strict client
binding, capability evidence, link/path/size attacks, staged-byte tampering,
interrupted recovery, and source/target preservation. The startup harness also
constructs the real client `World` from adopted and standalone-empty bindings
while both legacy archives are absent, records zero legacy read attempts,
forces every guarded legacy entry point, and verifies that server binding,
native context, initial-region load, and residency are all required before the
adaptive world-ready predicate succeeds.

Before a downstream release, an owner must still visually run both an adopted
generic project and standalone empty project. The owner—not an AI screenshot
review—confirms rendering, navigation, existing-level edits, same-session
Go/Create and ladder/stair level creation, new void terrain,
placements/collision, save, close/reopen, and client reconnect.
