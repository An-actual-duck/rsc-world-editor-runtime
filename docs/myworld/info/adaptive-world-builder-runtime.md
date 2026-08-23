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
`server/conf/world-builder/adaptive-runtime-capability-v3.json`. Server and
client code independently pin the same values.

| Role | Identity |
|---|---|
| Capability | `adaptive-world-builder-runtime-capability-v3` |
| Runtime profile | `adaptive-world-builder` |
| Server build | `rsc-world-editor-runtime-adaptive-builder-server-v3` |
| Client build | `rsc-world-editor-runtime-adaptive-builder-client-v3` |
| Loader | `generic-signed-layered-loader-v3-project-content` |
| Authoring | `generic-signed-layered-authoring-v2-u16-elevation` |
| Definition binding | `world-builder-definition-catalog-binding-v2` |
| Client asset binding | `world-builder-project-content-asset-binding-v2` |
| Protocol | `world-builder-native-layered-protocol-v2-u16-elevation` |
| Effective composition | `world-builder-effective-static-composition-v1` |
| Package schema | `layered-world-package-v1` |
| Coordinate model | `signed-layered-v1` |
| Placement encoding | `layered-world-placements-v3` |

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
definitions already referenced by the map. A material-free project retains the
World Editor's strict eight-field schema-version-1 JSON with exactly
`schemaVersion`, `manifestType`, `catalogId`, `tiles`, `boundaries`, `scenery`,
`npcs`, and `groundItems`.
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

## Project-local custom content

Definition-catalog schema version 2 adds exactly one `customContent` object.
That object binds a portable bundle ID and semantic version, an asset-manifest
ID, and ordered definition arrays for textures, animations, tiles, boundaries,
scenery, NPCs, and items. Each definition carries an explicit `add` or
`replace` operation. Adds may extend ID-indexed catalogs only where the client
and server can represent the result safely; renderer-indexed textures and
animations must extend their packaged catalogs contiguously. Sparse NPC,
scenery, boundary, tile, and item additions remain explicit, with null holes
never treated as definitions. NPC ID 846 is covered by tests only as one
beyond-packaged-catalog example and has no special runtime behavior.
The v3 capability descriptor publishes the exact packaged counts used by the
producer when assigning IDs: 55 textures, 1,080 animations, 26 tiles, 214
boundaries, 1,332 scenery definitions, 845 NPCs, and 3,309 items. A future
runtime whose packaged catalogs change must publish a new capability identity
and matching counts instead of silently reinterpreting a bundle.

The asset evidence is a strict `world-builder-custom-content-assets`
schema-version-1 JSON manifest. It binds the same bundle ID and version and a
sorted inventory of project-local payloads. Every row contains exactly a
portable key, one of the four kinds below, a manifest-relative canonical path,
byte size, SHA-256, decoded dimensions, and frame count:

- `texture-png` supplies floor and wall texture pixels;
- `npc-animation-png` supplies one horizontal 15, 18, 24, or 27-frame sheet as
  determined exactly by the animation's `hasA` and `hasF` flags;
- `item-sprite-png` supplies inventory and ground-item pixels; and
- `scenery-model-ob3` supplies one structurally validated scenery model.

All listed payloads must be referenced and all referenced payloads must exist
with the declared kind. Catalog, manifest, and payload fingerprints are checked
independently by client and server before the binding handshake. Unknown keys,
noncanonical or escaping paths, symbolic links, hard links, malformed images or
models, oversized inventories, ID collisions, unsafe ID holes, missing
animation/model/texture/sprite dependencies, bundle disagreement, and evidence
mismatch fail before editable world activation.

The bundle is data only. It cannot contain or activate Java classes, scripts,
serialized objects, server plug-ins, packet handlers, commands, quests, or any
other creator-supplied behavior. Asset files remain below the isolated UUID
project's `working/` tree. Schema version 1 continues to load without a custom
manifest or custom payloads, preserving existing material-free projects.

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

The desktop client independently requires:

- `-Dopenrsc.worldBuilderMode=true`
- `-Dopenrsc.worldBuilderAdaptiveMode=true`
- loopback host and a project-owned credential
- the server-produced
  `<project>/run/world-builder/runtime-binding.properties`
- client definition and asset evidence files inside `<project>/working/`

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
only when protocol, package, manifest, world space, declared level, initial
coordinates, and native coverage match the verified binding. A malformed or
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
- exactly one v3 placement set for every declared level;
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

The editor envelope is capability version 2 and carries elevation as an
unsigned short. Absolute sets and configurable-step Raise/Lower operations
are accepted only by native layered authoring. Every tile in a stroke is
calculated and bounds-checked before the draft changes, so any overflow or
underflow rejects the complete stroke. Unsupported terrain encodings, record
widths, editor envelopes, or client/server runtime identities fail closed;
there is no clamp, byte truncation, fallback save, or silent downgrade.

Frozen legacy landscape archives remain 10-byte records and readable. They
cannot store elevations above 255, and the legacy pack/save path refuses such
a value instead of narrowing it.

## Empty and existing-level authoring

Existing copied levels are editable only under explicit adaptive activation.
New terrain sectors use the shared canonical void tile:

```text
elevation=0, ground texture=1, ground overlay=8,
roof=0, horizontal wall=0, vertical wall=0, diagonal wall=0
```

The standalone-empty origin is stricter: one global level `0`, one terrain
sector covering the configured `0..32767` client-carrier start, one empty v3
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

## Verified save and recovery

`::saveworldedits` materializes the complete effective package, including all
unchanged boundary records and all edited terrain/scenery/NPC/ground-item
records. Publication is copy-on-write:

1. verify the current working and immutable baseline closed inventories;
2. construct canonically ordered package bytes in a sibling stage;
3. force staged file content to storage;
4. reload and validate the exact staged bytes with the generic runtime and
   active definition contracts;
5. revalidate after observer boundaries and immediately before publication;
6. write durable transaction evidence and require atomic same-filesystem
   directory moves;
7. re-read and verify the published package; and
8. remove the prior package and transaction evidence only after success.

A failed save restores and verifies the prior complete working package. A
startup recovery marker distinguishes an old complete package, a new complete
package, and an interrupted swap. Unowned staging state or unverifiable
recovery state blocks startup for manual review. Source baseline and target
server data are never save destinations. The runtime fingerprints the source
baseline before and after publication; the standalone preparer retains target
fingerprint responsibility because no target path enters this process.

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
review—confirms rendering, navigation, existing-level edits, new void terrain,
placements/collision, save, close/reopen, and client reconnect.
