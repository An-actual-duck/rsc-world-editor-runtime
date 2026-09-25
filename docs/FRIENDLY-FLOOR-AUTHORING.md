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
255 retain their original level-dependent interpretation. Existing maps and
immutable projects are not rewritten or automatically extended.

## Current standard

Current Base's server/client content manifests apply `standard-floors-v1` to the
frozen provenance-backed TileDef.xml source. The transform preserves all source
bytes and appends two definitions per original appearance (objectType 0 and 1),
then two explicit base-color definitions. Base's 25 originals become 77 total.
The same deterministic transform runs for both archives. It fails before output
when any source is already marked, has noncanonical blocking, or would exceed
249 total definitions. Raw 250 and 255 remain reserved. Advanced/custom existing
catalogs do not silently gain new definitions; they can use only combinations
supported by their selected immutable content until an explicit compatible
content update supplies the standard.

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
sent to an older renderer that ignores its material semantics.

## Rendering and gameplay

Generated appearances preserve the material, water/bridge geometry, alternate
water material, and lava glow. Generated transparent non-water floors remain
transparent beside diagonal walls and remain selectable. Unmarked originals
retain historical blending and picking. Type-4 transparent bridge surfaces are
not mistaken for wholly invisible floors: their underlying water remains.

The standard selects generated definitions for both traversal states. It does
not add tile damage, swimming, fishing, or agility rules. Original raw overlays
2 and 11 block projectiles in the legacy and native loaders; newly generated
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
