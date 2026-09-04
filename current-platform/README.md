# Current platform composition contracts

This directory is the provider-owned foundation for one current managed runtime
generation. `Current Base` is the conservative public destination and `Current
Advanced` is a bounded first-party composition on the same platform release.
Both are intentionally marked `foundation-contract-only` and `installable:
false` until complete server/client artifacts and executable migration rows are
attached to their closed bundle specifications.

Validate the catalog:

```bash
python3 scripts/current-platform-composition.py validate
```

Resolve and hash the present contract-only inventory:

```bash
python3 scripts/current-platform-composition.py resolve \
  --variant current-base-v1 \
  --payload-root .
```

The six-field composition identity is derived from canonical manifest content,
the deterministic ordered module closure, and raw SHA-256 hashes of every
closed-inventory artifact. Historical input adapters remain an Editor migration
boundary and are never installed as runtime modules. A receipt is installation
evidence only: it cannot suppress a source build or prove artifact identity.

The legacy descriptors in `server/conf/world-builder/` remain historical input
evidence for the rejected pinned-runtime strategy. They are not members of
either current composition.
