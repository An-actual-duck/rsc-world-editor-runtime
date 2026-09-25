# Friendly floor authoring

World Builder exposes one Floor tool. Paint Floor writes the remembered palette
color and resolved overlay together. Walkable controls terrain blocking; scenery
and walls may still prevent movement. Select Texture offers None (use color).
A texture overrides the remembered color until None is selected again. Select
Color opens the 256-color palette. Copying a legacy invisible upper floor retains
invisible intent rather than converting it into a visible color.

The resolver examines the loaded, project-bound TileDef inventory. It chooses
semantic standard definitions when available, never assumes fixed extension IDs,
and disables unavailable walkability combinations. Legacy unextended catalogs
retain their supported selections. In particular, color-only legacy overlays
cannot supply visible base color on levels 1 and 2. Existing raw overlays 0 and
255 retain their original level-dependent interpretation. Existing map bytes are not rewritten; the Editor prepares a new immutable
content revision when extending an imported project.

## Current standard

Current Base's server/client content manifests apply `standard-floors-v1` to the
frozen provenance-backed TileDef.xml source. The transform preserves all source
bytes and appends two definitions per original appearance (objectType 0 and 1),
then two explicit base-color definitions. Base's 25 originals become 77 total.
The same deterministic transform runs for both archives. It fails before output
when any source is already marked, has noncanonical blocking, or would exceed
249 total definitions. Raw 250 and 255 remain reserved. Imported/custom catalogs use the separate append-only extension described below.
The frozen Base producer remains unchanged so its established generated IDs stay
stable.

Optional XML fields are:

* `worldBuilderMaterial`: only `base-color-v1`, with colour=0, unknown=0 and
  objectType 0 or 1. The renderer reads the tile's existing palette byte on all
  levels. The colour=0 placeholder is not a texture dependency.
* `worldBuilderSourceOverlay`: a positive raw overlay referring to an earlier,
  unmarked original with exactly matching colour/unknown and canonical
  objectType 0 or 1. It preserves visual identity while allowing independent
  terrain blocking. Chained/cyclic sources and combined markers are rejected.

Marked definitions must occupy raw IDs below 250. Explicit empty, zero,
duplicate, unsupported, inconsistent and reserved-slot markers are rejected by
both actual XML loaders. Installed Base server XML uses the same loader as
project definitions. Existing gzip legacy definitions retain their old loader.
No terrain encoding, packet layout, map ID, or original definition is changed.
The changed content transform and schema hashes bind the new Current Base
composition; marked content requires this runtime generation and must not be
sent to an older renderer that ignores its material semantics. Both client and
server JARs advertise `World-Builder-Floor-Semantics: standard-floors-v1`;
Current Base verification and Editor marked-content guards require this
capability before launch/export to prevent silent old-runtime interpretation.

## Rendering and gameplay

Generated appearances preserve the material, water/bridge geometry, alternate
water material, and lava glow. Generated transparent non-water floors remain
transparent beside diagonal walls and remain selectable. Unmarked originals
retain historical blending and picking. Type-4 transparent bridge surfaces are
not mistaken for wholly invisible floors: their underlying water remains.

Base selects generated definitions for both traversal states. Imported catalogs
can reuse safe originals with identical traversal state. Floor authoring does
not add tile damage, swimming, fishing, or agility rules. Original raw overlays
2 and 11 block projectiles in the legacy and native loaders when unmarked; newly generated
appearance variants do not inherit those ID-triggered gameplay rules. The UI
identifies that projectile behavior when an unextended legacy catalog must use
an original selection. Existing agility lava damage is tied to explicit obstacle
actions, and lava fishing to fishing locations/objects, not arbitrary painted
lava. Client type-2 OBJECT=128 is excluded from movement-blocking masks; terrain
walkability continues to use full-block flags and server objectType.

## Verification

Focused tests cover all palette values across signed levels and both traversal
states, original definition retention, raw save/reopen bytes, actual World face
inputs, invisible picking, alternate water plus bridge materials, strict client
and server XML rejection, actual UI pointer paths and outgoing paint packet
mask/color/overlay, remembered color, unavailable toggles, and copied upstairs
invisibility. Existing terrain stroke/drag/history/save/collision tests and
Current Base composition/content tests cover the affected integration paths.

`test-friendly-floor-ui.py` renders actual software controls and palette to
throwaway screenshots; `FRIENDLY_FLOOR_SCREENSHOTS` selects a retained temporary
artifact directory. Manager visually accepted the compact/expanded controls and
palette. This is isolated fixture acceptance, not a claim of running an owner's
installed editor or migrating existing project content.

## Imported catalog extension

`scripts/standard-floors.py:extend` is the provider reference for imported
catalogs. It validates all rows before returning output and preserves every
existing byte and raw ID. In original raw-ID order, then blocking-state order
(0, 1), it appends only missing partners. A matching marked partner must reference
that exact original ID; equal color/unknown alone never establishes visual
identity. A matching unmarked original can be reused except raw 2/11 (historical
projectile effects) and transparent non-water rows (which require semantic
markers for reliable picking). Missing explicit base-color states follow last.
Existing generated rows and duplicate partners remain untouched. Missing legacy
numeric fields retain the loaders' zero defaults; empty/duplicate/invalid markers,
chained sources and noncanonical blocking fail. Over 249 final rows fails before
output; no truncation, renumbering or partial extension occurs. Completed input
returns exactly the original bytes. Base's 25 originals extend minimally to 55
rows, while its previously shipped 77-row standard remains unchanged.

Generated rows assigned small IDs 2/11 do not inherit legacy projectile effects.
Both legacy and native server paths consult the semantic marker. Unmarked raw
2/11 and raw250 retain prior collision policy. Client legacy warnings use the
same distinction.

## Installed normal-player floor catalog

Normal client initialization reads `world-builder-configs/installed-floors.json`
relative to the client launch directory when present. Its exact schema is:

```json
{
  "schemaVersion": 1,
  "manifestType": "world-builder-installed-floor-definitions",
  "tileDefinitionsRelativePath": "world-builder-configs/TileDef.xml",
  "tileDefinitionsSha256": "<64 lowercase hexadecimal characters>"
}
```

The descriptor and XML must be regular, non-symlink files under the client root.
The fixed path, exact fields, types and SHA-256 are verified; the exact verified
XML bytes are passed to the existing strict floor loader. Absent descriptor/XML pairs
leave normal vanilla/custom loading unchanged; orphan XML and malformed present installations
fail initialization. Isolated Builder mode keeps its bound project catalog.
Editor target upgrades own transactional deployment/recovery of this pair and
the matching server definitions. Both JARs advertise
`World-Builder-Installed-Floors: installed-floors-v1`; the client contains
`orsc.WorldBuilderInstalledFloorDefinitions`. No normal client launch or real
server was performed during provider verification.

Additional focused probes cover deterministic minimal extension, partial and
already-complete inputs, preservation of custom values, capacity refusal,
actual client selection on minimal/full catalogs, verified normal-client
bootstrap and absent/hash/path/schema/XML/symlink cases, and old versus marked
projectile policy in the native collision plan.
