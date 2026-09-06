# Genuine Preservation map semantic acceptance (in progress)

This runtime test umbrella consumes an explicitly supplied, sealed Editor map
derivation. It does not grant production promotion or provide a target descriptor.
The input is read-only; runtime installation, oracle products and negative controls
belong to fresh external temporary directories. No map payload is committed here.

```bash
WORLD_BUILDER_PRESERVATION_SEMANTIC_PROBE=/absolute/sanitized/project-stage \
  python3 tests/myworld/test-preservation-genuine-map-semantics.py -v
```

Without the external probe the tests report unavailable/skipped, not a fabricated
historical pass. Exact manifest, derivation, reconciliation and decoder hashes
anchor the accepted fixture, then their complete declared raw/canonical/derived
inventories and original map/definition inputs are rechecked. New fixture identities
require review; caller-authored trust flags cannot authorize different bytes.

## Independent terrain oracle

The reference is the public historical commit
`c0102e60774ab9c9076aabae49f6f97fb6fc4b00`, tree
`6db5536d795abf34f303bb03b20c43b8cfb9e3fe`, tracked
`server/src/com/openrsc/server/io/WorldLoader.java` SHA-256
`24eda72c42d5e7befb69b8e0f493cfa90f64b39f15edbf44ac5a4b824ae3db79`.
Its `loadSection` implementation was inspected read-only from that exact public
Git object after the reference's contributor instructions; historical code is
never built or executed.

The Python oracle forward-scatters the original loader's collision writes over
raw server sectors, using separately sealed historical TileDef/DoorDef XML. It
does not call the native collision plan. Preserve the original sector/tile load
order, per-tile traversal reset, signed-byte positive-overlay test after 250→2,
negative-axis reciprocal wall writes, both diagonal encodings and the historical
projectile allowlist. The exact reviewed map has no present archive-Y56 sectors,
so its present tiles do not cross the historical 944-row plane seam.

Do not substitute runtime3999's loader as an identical oracle: it introduces
unsigned/custom-overlay support and splits terrain/dynamic collision state into
counters. The test compares historical movement/projectile outcomes and raw
overlay/walls/diagonal separately from additional current counter diagnostics.
Elevation, ground texture and roof are intentionally client-preserved presentation,
not historical server collision expectations. Missing terrain is tested as explicit
current blocked void rather than falsely claiming a raw-sector equality result.

Initial focused execution passes all 811,008 present-tile comparisons with zero
differences. Real Current Base population loads 3,609 NPCs, 1,019 ground items,
26,815 scenery and 967 boundaries. Exact NPC identities, starts, bounds, respawn
and multiplicity match the sealed historical derivation. All 146 crossing bounds
retain blocked void, with actual adjacency, A* and forced WalkingQueue refusal
at a present/absent edge of every rectangle. No absent terrain is activated.

The independent populated-world oracle additionally follows the exact historical
`World.java` SHA-256 `540bf30ae801822c93fd54a936f3e34633494473e99e3dd5e0977167a960539c`
and `Constants.java` SHA-256
`f3b04a325a9b518ca7827c27976cf29094c1ba2dbd60af88e376f820132befe5` at c0102.
It composes effective historical scenery/boundaries, their footprints, rotations,
reciprocal bits and projectile-clip rules without invoking the native planner.
Movement matches on all 811,008 populated tiles, but **7,376 projectile flags
differ**. The current classifier's unconditional `name.contains("tree")` branch
explains every discrepancy: adding that branch only to a separate diagnostic
oracle leaves zero residual differences. It is not substituted for the original
oracle; the semantic test remains failing pending a reviewed Base-only correction.
No runtime behavior change accompanies this checkpoint.

Actual ladder199 removal and reconstructed native-identity re-registration restore
the original collision state exactly. Correct overlay0 exposes traversal0 after
removal; the separately copied wrong-overlay8 control retains traversal64 despite
its dynamic scenery count reaching zero. Direct re-registration of an already
removed instance is correctly refused. Both cases retain the outstanding tree
projectile refusal; a diagnostic sub-result is not an overall test pass.

The existing real Player/plugin transition harness now also passes on the sealed
352-sector package using `world-builder-installed`, instead of its separate
1,764-sector ZIP fixture. This proves those actual transition consumers and all
18 reviewed edge lookups/destinations, not every plugin in the game.
Raw, original-definition, canonical-tile and derivation tampering refuse.

The packaged server's real presentation encoder and the packaged client's native
chunk parser feed the actual `World.buildCpuSectionWindow` consumer for all 352
sector-centered 3×3 windows. Every present tile retains its canonical elevation,
texture, overlay, roof, walls and diagonal. Missing cells remain explicit void;
the legacy landscape read counter stays zero. Snapshots are injected only to
isolate this CPU consumer from GUI scheduling: this is not an authenticated
packet/session, rendered mesh/frame or normal-login proof. Canonical storage and
wire both order vertical then horizontal walls; historical JAG uses the reverse.

The historical projectile comparison covers `projectileAllowed` and the default
distance-check product. Modern `HOSTILE_PROJECTILE` distance checks consume a
separate collision mask; their combat dispatch and positive public behavior still
need explicit policy acceptance. A passing tile-flag comparison must not be
reported as proof of every ranged/spell attack. Production promotion remains
outside these headless tests.
