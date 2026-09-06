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

## Historical Preservation JAG decoding

Default r64 Preservation server terrain comes from the four reviewed
`maps64.jag`, `maps64.mem`, `land64.jag`, and `land64.mem` archives—not from
the client's `Authentic_Landscape.orsc` ZIP. The input-adapter manifest now
binds a decode-only tool in the existing `server-runtime` artifact:
`com.openrsc.server.io.PreservationJagDecode`. Its exact seven option/value
pairs are `--contract`, `--maps-free`, `--maps-members`, `--land-free`,
`--land-members`, `--output`, and `--evidence`. Every path is absolute and
canonical; the two output paths must be new, disjoint, and have existing
parents. The contract is the complete shipped Preservation input-adapter
manifest, not an arbitrary decoder description.

The tool accepts only the contract-bound four public archive sizes/hashes.
It validates archive framing, complete bounded decompression, CRCs, entry
tables, duplicate hashes, stream consumption and resource limits before
creating output. Generic WorldLoader delegates to the same extracted pure
sector algorithm, preserving alternate/member behavior; migration uses only
the reviewed non-alternate member r64 policy. All 1,680 historical probes
(planes 0–3, archive X 48–68, archive Y 37–56) are recorded. Present sectors
are exactly 23,040 native bytes; absent sectors remain absent, not synthesized.
Evidence binds source and complete output inventories, confirms unchanged
inputs, and identifies selected free/member streams. Existing outputs and
aliases are refused. Failure retains any newly created partial output for
explicit recovery; it never force-cleans or overwrites another workspace.

This is raw decoding, not full WorldLoader behavior: the historical signed
short-to-int diagonal conversion is retained, discarded tile directions are
counted and hashed, and neither subsequent overlay processing nor static
placements are applied. In particular, WorldLoader copies the raw overlay
into its tile before using 250→2 for subsequent collision lookup; globally
rewriting raw overlays would not preserve that behavior.

Complete tests against the frozen original method establish byte/null parity
for all probes. The reviewed archives produce 352 sectors and 1,328 absent
probes, discarding 15,468 nonzero tile-direction values. Against all 1,764
client ZIP entries, 276 server sectors are byte-identical and 76 differ; no
server sector is missing from that ZIP. Its 1,412 additional entries comprise
1,328 absent server probes and 84 coordinates outside the server probe range.
Differences include 162,324 elevation values, 291 diagonal markers, and one
each of colour, overlay and roof. Client ZIP substitution is therefore not
an evidence-backed preservation strategy. This tool does not establish
client reconciliation, complete map conversion, gameplay parity, or runtime
promotion approval. Its closed evidence schema lives in the existing input
adapter schema's `jagDecodeEvidence` definition.

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

The installed-execution caller must start the verifier with its own stdin pipe,
keep the write end open without sending bytes until the verifier exits, and
close it to cancel. Pipe EOF (including loss of the parent process), unexpected
data, and ordinary JVM shutdown terminate the owned server/client Java processes
and remove the disposable credential. Child creation and credential publication
are synchronized with cancellation; cancelled work cannot publish verified
evidence. The caller allows the contract's 90-second cancellation cleanup budget
and retains the workspace as recovery-required if the process cannot exit.
Logs remain bounded. Direct hard-kill of the verifier, OS failure, blocked OS
operations, and arbitrary descendants not launched by this verifier are not a
portable cleanup guarantee; do not claim that SIGKILL completed recovery.

The separate installed-execution verifier now runs both server/client cycles
against `workspace/state/current_base.db`, outside its copied runtime roots,
and records `stateOutsideRuntimeRoots:true` in closed evidence. This proves
SQLite placement and persistence, not a complete immutable-release launcher:
configuration, logs, caches, map pointers, Editor activation/recovery binding,
and the public transition matrix still require integration. No production
release or real-target upgrade is authorized by these component checks.

Both installed-profile loaders accept the explicit launch property
`openrsc.worldBuilderInstalledMapRoot=/absolute/map/package`. When selected,
the map directory must be canonical, real and disjoint from the JVM working
directory and code-artifact directory. The active installed profile still binds
the manifest SHA-256 and package identity; missing/inactive profiles, empty
overrides, aliases, overlap and mismatches refuse without falling back to the
profile-relative package. Omitting the property retains the generic installed
profile's existing relative layout. This is a runtime launch capability, not an
Editor map-pointer transaction or permission to modify a running map.
The installed-execution verifier now runs both cycles against one copied map at
`workspace/maps/package`, outside both copied runtime trees, and proves that it
remains byte-identical. Closed evidence records `mapOutsideRuntimeRoots:true`
and `mapUnchanged:true`. Map-pointer activation and live-instance recovery still
belong to the unfinished Editor integration.

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

### Normal installed Current Base launch

The provider profile's `installedLaunch` contract defines normal server and
manually authenticated desktop client entrypoints. Its closed descriptor schema
is embedded at `current-base-runtime-profile-v1.schema.json#/$defs/installedLaunchDescriptor`;
no extra executable or target-selected launch flags are installed.

The server command is `java -cp <codeRoot>/core.jar:<codeRoot>/plugins.jar
com.openrsc.server.CurrentBaseInstalledServer --launch <absolute-descriptor>`.
The client command is `java -cp <codeRoot>/Open_RSC_Client.jar
orsc.CurrentBaseInstalledClient --launch <absolute-descriptor>`. These are argv
arrays, not shell strings. The process working directory must be the descriptor's
canonical `workingRoot`; changing `user.dir` is not supported. This contract is
POSIX-only.
The normal Base client selects the maintained software desktop renderer because
this composition does not ship native LWJGL executable dependencies. Generic and
Advanced renderer defaults are unchanged.
Normal installed connection lookups remain descriptor-bound after server-config
refresh; cached endpoint files cannot redirect a later manual login. Software
presentation includes actor sprites, with OpenGL-only sprite replay disabled.
The normal-launch integration lane requires a POSIX graphical test session,
`xdotool`, `xwd`, and Python Pillow. It targets only its owned client window,
enters invented fixture credentials through the login UI, and verifies visible
terrain/player pixels plus durable state across two complete restarts.
Managed shutdown drains queued database writes within the existing writer
deadline. A failed SQL write or unresolved drain produces a failed process exit,
not clean-stop success; session/log evidence and the role lease remain until
the actual JVM exits. Generic logger shutdown behavior is unchanged.
The complete reviewed server configuration includes `db_type: sqlite`
and `db_name: current_base`; managed launch never reads `connections.conf` or
`local.conf` implicitly. Immutable definitions, SQL queries/patches, plugin JARs,
and client caches resolve from the bound role code root, never the working tree.

Code-tree SHA-256 uses sorted UTF-8 portable relative paths, NUL, file SHA-256,
NUL. Map package fingerprints use the existing distinct path, NUL, decimal size,
NUL, SHA-256, newline recipe. Both reject links, hard-link aliases and special
entries, with bounded entry counts and total size. Code, working, map and durable
state roots are canonical and disjoint, including from the stable installation
anchor; `sideStateRoot` may be beneath its role's durable state root. Bound immutable
composition/profile/map-profile/configuration documents must also stay outside
all mutable working/state/side-state/installation roots. The public key remains
an explicit persistent side-state binding.
Runtime mutable roots have mode `0700`. Server side-state
contains an existing matching `server.pem` (mode `0600`), `client.pem`, and
`badwords.txt`, `goodwords.txt`, `alertwords.txt`; the installer explicitly preserves
or initializes these. The server never silently regenerates installed keys.
IP bans and their atomic-update temporary file also live in server side-state.
Client side-state contains its own public-key copy, optional `clientSettings.conf`,
`uid.dat`, `hideIp.txt`, and user-requested remembered `credentials.txt` (mode
`0600`). Remembered credentials are an existing player preference, never a
normal-launch authentication input or disposable execution profile. The client
has no reason to access server private state. Its normal
handshake pins the server public key to its descriptor's reviewed public PEM.

The installer precreates a stable private `installationRoot`, empty regular
`server.lock` and `client.lock` files, and private `sessions/server` and
`sessions/client` directories. The actual role JVM acquires its exclusive file
lock before initializing game classes or logging and retains it until OS process
teardown, including all shutdown-save hooks. Neither runtime nor Editor may
delete or replace these lock anchors. Editor mutation must acquire both role
locks in server-then-client order. Readiness files and process IDs are never
substitutes for those locks.

The fixed private `installationRoot/active-launch.json` is a closed
`current-base-installed-selection` object with `schemaVersion:1`,
`installationId`, `serverDescriptorSha256`, and `clientDescriptorSha256`.
The actual role JVM checks this current selection after acquiring its role
lease and again immediately before initializing game code. Missing, stale,
aliased or mismatched selections refuse; an old descriptor cannot restart
retired code/map against current player state. Editor changes this pointer
transactionally while holding both role leases and retains exact rollback
evidence. The descriptor does not hash this pointer, avoiding a hash cycle.
Any entry at `installationRoot/pending-cutover.json`, including a directory or
dangling symlink, refuses both roles after lease acquisition and before state,
session or game effects. The Editor owns creation, durable completion/rollback,
and removal of this guard; the runtime neither parses nor repairs it.

The same descriptor is restartable. After validation and lease acquisition,
the role generates a fresh 256-bit nonce, creates `sessionRoot/<nonce>` privately,
and prints `INSTALLED_SESSION <nonce>` before game logging starts. Old session
evidence is retained and never reused. `ready.json` is atomically published only
after server world/network readiness or a visible client window. Startup is
bounded to 120 seconds. A `shutdown.json` must exactly match the ready document
with only `action` changed to `shutdown`; it binds installation UUID, role,
nonce, descriptor SHA-256, composition-identity SHA-256, and map-manifest SHA-256.
The launcher performs clean shutdown before exiting; closing its stdout or the
Editor is not a normal server stop request. Uncertain process termination remains
recovery evidence, not proof of a completed save.

This runtime API is separate from the disposable installed-execution verifier.
It does not enable Editor activation, implement an Editor ledger/map transaction,
or by itself establish candidate acceptance.

### Interrupted disposable-verifier recovery

The installed-execution verifier additionally requires `--supervision` pointing
to a caller-prepared `controlRoot/authority.json` and `--supervision-sha256`
containing its journaled byte hash. The closed authority schema is embedded in
`current-base-installed-execution-evidence-v1.schema.json#/$defs/supervisionAuthority`.
It binds the invocation UUID, composition and verifier-contract hashes, absolute
workspace/control paths, ten named input paths, and device/inode identities of
four pre-existing, singly linked, empty mode-0600 files: `supervisor.lock`,
`server.lock`, `client.lock`, and `intent.json`. The control directory is private
0700, disjoint from workspace and inputs, and must remain at its original path.
The caller durably creates these files and journals the authority hash before
starting the verifier. This live authority is not a portable historical report.

`invocationSha256` is SHA-256 over the original fourteen option names, without
their `--` prefix, in sorted order: UTF-8 name, NUL, exact argument value, NUL.
The two supervision options are excluded to avoid a hash cycle. Input paths are
canonical absolute paths, bounded to 4096 characters. Authority, intent and
revocation documents are bounded to 64 KiB; all objects have exact closed fields.

The actual supervisor JVM takes its prebound lock before workspace effects.
The provider writes the prebound intent inode once, retaining its inode and
forcing its body and directory. The body contains a runtime-generated 256-bit
nonce plus exact private credential path, inode, size and SHA-256 ownership.
Actual child JVMs enter `CurrentBaseVerifierServer` / `orsc.CurrentBaseVerifierClient`
with exactly `--supervision`, `--supervision-sha256`, and `--intent-sha256`.
They acquire their role lease, validate both exact hashes and invocation binding,
and reject any `revocation.json` entry before game classes initialize. Leases
are retained through actual JVM exit, including shutdown hooks. Each child also
watches its own parent pipe; orphaned children request their own process exit.

Recovery uses the provider artifact, never an arbitrary target executable:

```text
java -cp <provider-core.jar> com.openrsc.server.database.CurrentBaseVerifierRecovery
  --contract <reviewed-verifier-contract>
  --supervision <absolute-authority.json> --supervision-sha256 <journaled-hash>
  --evidence <new-disjoint-output>
```

The command acquires supervisor, server, then client leases. It validates their
original inodes, validates the intent body against authority/invocation and
credential ownership, then durably creates an immutable `revocation.json`.
Recovery does not claim the intent body was externally hash-pinned: its inode
was pinned before launch; its full body is checked against the bound authority.
Every delayed parent or child rechecks revocation under its respective lease,
so a process created before the supervisor died cannot start gameplay later.
An empty prebound intent can be revoked only under all three leases. A partial,
inconsistent or replaced intent is retained and refused, never repaired.

Only an absent credential or the exact sealed, canonical, singly linked 0600
credential can be cleaned. A foreign/replaced/partial credential is retained.
File bodies and parent directory entries are forced for creation/deletion and
evidence publication. Recovery never removes the workspace or authority/anchors.
It creates a new disjoint private report using the embedded `recoveryEvidence`
schema: exit 0 means permanent closure and credential cleanup; 3 means busy;
2 means unsafe/refused. Existing valid revocation and absent credentials are
idempotently recoverable into a fresh report. The Editor must await the owned
recovery command's successful exit and validate that report before any separate
journal-owned workspace cleanup. Neither free ports nor PID disappearance nor
unbound free locks prove cleanup authority.

Normal successful verifier evidence contains its closed supervision binding.
Cancellation retains the existing 20-second owned-child shutdown, 10-second
forced-termination and 5-second log-drain bounds. Forced termination applies
only to disposable child handles created by this verifier; it is never used on
PID-discovered processes and never substitutes for lease/revocation proof.
