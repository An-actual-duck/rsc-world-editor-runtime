# Current platform composition contracts

This directory is the provider-owned foundation for one current managed runtime
generation. `Current Base` is the conservative public destination and `Current
Advanced` is a bounded first-party composition on the same platform release.
Current Base is an installable `release-candidate`: its closed bundle is built
from this provider's server/client sources, uses only authentic/shared plugins,
includes a provider-owned conservative configuration and definition catalog,
and excludes the Advanced asset catalog. Current Advanced remains
`foundation-contract-only` and non-installable until its separate evidence is
complete. Base is verified by the closed compiled
retro/core/initialized SQLite rows and separate retro MariaDB row, and the
built server/client loopback execution scenario through login, canonical map
load, durable gameplay state, logout, and restart. Neither status means
released.

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
the conservative server-content inventory, and Advanced-only
plugin/resource/configuration exclusion. The migration manifest binds the
compiled main class in the `server-runtime` artifact (there is deliberately no
unreviewed free-standing migration executable), its four exact source-schema
fingerprints, closed invocation, and evidence contract. It is still a source-tree candidate
verifier rather than an installed-runtime launch tool. The built server and
client themselves parse the exact composition identity and enforce its six
fields before configuration transfer and again on every login connection;
mismatches are refused before login state is accepted.

The full runtime suite's Current Base execution gates require a working local
Docker daemon with the already-pinned image
`mariadb@sha256:611a2fcc5fa7c6ceb8644c6f74b25ede004ff6c3a6b38c8f8c23d3bbf6c26430`
available, and a usable desktop X display named by `DISPLAY`. The MariaDB gate
publishes only an ephemeral port on literal `127.0.0.1`; the desktop gate runs
the built client against a disposable loopback server and temporary state.
Neither gate downloads an image, uses external credentials, or touches an
installed target.

Current Base requires `-Dopenrsc.currentBaseStateRoot=/absolute/private/state`
on the server JVM. This is a provider-owned launch input, not a legacy database
name override. The directory must already exist, be canonical and unlinked,
have mode `0700`, and be disjoint from both the server working directory and
the runtime artifact directory. It contains the already-migrated
`current_base.db` with mode `0600`; safe private SQLite recovery sidecars remain
alongside it. Missing databases, symlinks, hard-link aliases, non-private modes,
noncanonical names, and runtime-directory overlap are refused before opening.
The JDBC connection uses an escaped file URI in existing-file read/write mode;
it never creates a replacement database or silently falls back to `inc/sqlite`.
An unbound historical runtime keeps its ordinary location and cannot opt into
this Current Base property. Unsupported non-POSIX permission checks fail closed.

The separate installed-execution verifier now runs both server/client cycles
against `workspace/state/current_base.db`, outside its copied runtime roots,
and records `stateOutsideRuntimeRoots:true` in closed evidence. This proves
SQLite placement and persistence, not a complete immutable-release launcher:
configuration, logs, caches, map pointers, Editor activation/recovery binding,
and the public transition matrix still require integration. No production
release or real-target upgrade is authorized by these component checks.

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
