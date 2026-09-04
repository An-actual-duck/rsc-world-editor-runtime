# Current platform composition contracts

This directory is the provider-owned foundation for one current managed runtime
generation. `Current Base` is the conservative public destination and `Current
Advanced` is a bounded first-party composition on the same platform release.
Current Base is a buildable, non-installable `artifact-candidate`: its closed bundle is built
from this provider's server/client sources, uses only authentic/shared plugins,
and excludes the Advanced asset catalog. Current Advanced remains
`foundation-contract-only` and non-installable until its separate evidence is
complete. Base remains non-installable until a content-neutral server
configuration/definition payload and transactional state-migration row are
proved alongside these executable artifacts. Neither status means released.

Validate the catalog:

```bash
python3 scripts/current-platform-composition.py validate
```

Build the reproducible Current Base server/client pair and its exact identity:

```bash
python3 scripts/build-current-base.py
```

The official builder requires a clean provider checkout and always compiles
source; receipts and pre-existing ignored output are not inputs. Its narrow
`--test-allow-dirty` switch records dirty state and exists only for test
harnesses. The build provenance binds the provider commit, source-tree
fingerprint, and clean/dirty state. The builder normalizes all JAR entry order
and metadata, writes provider/build provenance, resolves the
closed artifact inventory, and invokes the source-tree candidate verifier. The
verifier checks the shared pairing marker, complete six-field artifact identity,
canonical map bootstrap classes, public plugin inventory/state policy contract,
and Advanced-only plugin/resource/configuration exclusion. It is not portable
installed-runtime startup/login enforcement; that remains a machine-visible
installability blocker.

Resolve and hash the built candidate inventory:

```bash
python3 scripts/current-platform-composition.py resolve \
  --variant current-base-v1 \
  --payload-root .
```

The six-field composition identity is derived from canonical manifest content,
the deterministic ordered module closure, and raw SHA-256 hashes of every
closed-inventory artifact. The resolved record also exposes `schemaSetHash`;
the platform manifest binds every schema ID and relative path to its exact file
SHA-256, so schema changes transitively change platform/composition identity.
Historical input adapters remain an Editor migration boundary and are never
installed as runtime modules. A receipt is installation evidence only: it
cannot suppress a source build or prove artifact identity.

The legacy descriptors in `server/conf/world-builder/` remain historical input
evidence for the rejected pinned-runtime strategy. They are not members of
either current composition.
