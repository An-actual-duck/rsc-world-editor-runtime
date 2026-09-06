# Current Base public definition snapshot

These data files are provider-owned public definition inputs from the
reviewed public Git tree in `provenance.json` and `gameplay-provenance.json`. No reference runtime is built or
executed. JSON is byte-identical; XML only normalizes CRLF to LF and supplies a
final newline. The integrity test reconstructs and hashes the original bytes,
so that normalization cannot conceal a definition change.

The historical public registries include 1,593 items (1,290 base plus 303
unconditionally appended stock Custom records), 836 NPCs (794 plus 42), 1,296
scenery definitions, 214 boundaries, and 25 tiles. Here “Custom” is a historical
filename, not permission to enable owner-specific gameplay or Advanced modules.
Items use explicit IDs; NPCs and XML registries use ordered indices.

The packaged-runtime probes compare actual server/client item, NPC, scenery,
boundary, tile, prayer and spell fields, exact spell rune maps, registry bounds,
and all 1,593 item sprite selections against these inputs. Server-only gameplay
fields are not asserted on client classes that do not represent them. The stock
sprite archive has a closed namespace inventory and independent source hash;
its historical Custom filename does not enable Advanced gameplay flags.

The gathering probe seeds real loaded inventory objects without a login or
database session. It exercises plugin tool selectors, all eight public axe
curves, mining chance boundaries, and resource respawn timing. It does not claim
an end-to-end live gathering session, full skill parity or candidate readiness.
Orb charging, elemental staff rune consumption, arena stones, genuine imported
map gameplay and client void-boundary checks remain separate verification work.
Generic and Advanced content sources remain independent.
