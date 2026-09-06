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
26,815 scenery and 967 boundaries; 146 instantiated NPC bounds cross absent
sectors without activating them. Raw, original-definition, canonical-tile and
derivation tampering refuse. This is an in-progress checkpoint, not full semantic
acceptance: exact NPC multiset/movement, composed placement collision, ladder199
removal/restoration and wrong-overlay control, real transition and client CPU/void
proofs still need completion. No runtime behavior change accompanies this test.
