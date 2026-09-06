# Current Base public definition snapshot

These seven data files are provider-owned public definition inputs from the
reviewed public Git tree in `provenance.json`. No reference runtime is built or
executed. JSON is byte-identical; XML only normalizes CRLF to LF and supplies a
final newline. The integrity test reconstructs and hashes the original bytes,
so that normalization cannot conceal a definition change.

The historical public registries include 1,593 items (1,290 base plus 303
unconditionally appended stock Custom records), 836 NPCs (794 plus 42), 1,296
scenery definitions, 214 boundaries, and 25 tiles. Here “Custom” is a historical
filename, not permission to enable owner-specific gameplay or Advanced modules.
Items use explicit IDs; NPCs and XML registries use ordered indices.

This initial snapshot checkpoint is deliberately not a candidate-readiness
claim. Until the selected Base server/client loaders, client visual mappings,
runtime transformations, and data-driven gameplay hooks have been tested,
these files alone do not establish effective gameplay or state compatibility.
Generic and Advanced content sources remain independent.
