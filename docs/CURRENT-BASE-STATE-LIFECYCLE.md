# Current Base state lifecycle

Normal installed Base requires a private, pre-existing `current_base.db` under
`openrsc.currentBaseStateRoot`. It never creates or falls back to an in-runtime
database. This policy is unchanged.

## Isolated authoring

The inventory-bound Base profile now declares `authoringPolicy` with policy ID
`current-base-isolated-authoring-v1`. A Base authoring JVM uses
`-Dopenrsc.currentBaseAuthoringStateRoot=<project>/working/authoring-state` and
the existing `openrsc.worldBuilderWorkspaceRoot=<project>` binding. Its database
is an independent, pre-existing `world_builder.db`, never an installed database.
The directory must be canonical, private mode 0700, disjoint from runtime code
and working directory; the database and any SQLite sidecars must be singly linked
regular mode-0600 files. Installed and authoring root properties are mutually
exclusive. An installed database directory cannot double as authoring state.

The selected artifact must identify Current Base. Actual adaptive Builder config
validation still requires loopback, one player, registration disabled, explicit
Builder/adaptive modes and complete native-authority gates. Custom content overlays
are not admitted. Generic Builder keeps its existing `world_builder` behavior and
refuses Base-specific state properties. A property alone cannot enable authoring.
The Editor supplies its trusted empty Builder seed; this state-location boundary
does not replay installed-server migration on that disposable authoring database.

The headless state test constructs the actual packaged Base Server with a closed
synthetic native package and opens an invented private authoring SQLite database.
It proves routing and isolation, not Builder login or catalog/UI completeness.
Those are exercised by the Editor's authoring acceptance.

## Supported managed successor

`current-base-sqlite-to-current-base-v1` adds one bounded current-to-current row
to the existing migration tool. The CLI and evidence format are unchanged:

```text
com.openrsc.server.database.CurrentBaseStateMigration
  --contract <inventory-bound state-migration.json> --engine sqlite
  --source <closed current_base.db> --stage <new successor.db>
  --evidence <new evidence.json>
```

The row's `sourceSchemaFingerprints` is a closed three-entry allowlist of current
outputs already produced from the supported retro/core/initialized SQLite inputs.
This is not a new historical adapter or permission to customize SQLite schema.
The transformation ID `current-base-byte-copy-v1` means **no transformation**:
all database bytes, gameplay rows, retained skill columns, migration markers,
patch history and SQLite internal metadata are copied unchanged. The tool checks
the complete schema and all-row state digest, SQLite integrity, corresponding
reviewed migration marker and exact emitted patch-name multiplicities. The
initialized lineage retains its existing duplicated older patch records.

The source must be offline and free of WAL, SHM or journal sidecars. Stage and
evidence must be fresh, distinct paths. Source hashes before/after must match,
and successor bytes must equal the original source bytes. Repeated managed
successors remain supported because the database ledger is not rewritten;
new successor evidence is external. Unknown schemas, missing/forged markers,
unreviewed or incomplete patch history, active sidecars and existing outputs
refuse. A failure discards only the stage owned by that invocation.

The Editor still owns offline leases, preview, receipt/composition binding,
installation cutover, backups, rollback and recovery. This CLI does not prove
installation authority merely from a database marker, and does not acquire live
server leases or activate its output. Non-SQLite successor migrations and new
state-schema transformations are outside this bounded row.
