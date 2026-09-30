# Target-owned map integration

The product's September 30, 2026 direction is targeted map compatibility. The
provider's authoring game is not a replacement for the target's custom game.
The first adapter in `server/conf/world-builder/target-map-integration-v1.json`
upgrades an already layered v4 source layout. Preservation's pre-layered source
integration remains a separate adapter to implement; its existing Current Base
composition migration is not a targeted compatibility adapter.

## Artifact and consumer responsibilities

`scripts/stage-target-map-integration.py --runtime-root <staged-runtime>` copies
only the manifest and its SHA-256-bound Java source payloads from this provider.
It reads no target game and invokes no target code. Source payloads are limited
to map package decoding, map activation, map material definitions, and installed
floor loading. NPC/item/object definitions, appearance registries, interaction
handlers, plugins, and authoring content bundles are not payloads.

The Editor validates the pinned provider artifact, selects a complete adapter,
and previews exact target changes. Sources with `add-or-exact` may be absent or
byte-identical. `replace-reviewed-map-source` additionally accepts only the
listed beforeimage hashes. Mixed classes use exact, counted code edits; all
other source bytes remain target-owned. Required source hashes and entry probes
establish the pre-existing paired protocol integration. Probe strings alone
are not proof of arbitrary implementations.

The adapter preserves the target's old runtime profile and its original pinned
map identities, adding a generic installed profile. It does not replace custom
combat collision policies in `TileValue` or `RegionManager`. The target's
`mudclient` appearance loading and NPC/item/object initialization remain active.
Its only `EntityHandler` change appends verified floor materials after the
existing target floor initialization.

The consumer compiles source in disposable staging with controlled Java
arguments, `-proc:none`, no implicit source compilation, and no target Ant,
Gradle, shell, or annotation-processor execution. This row requires Java 17
with Java 8 source/bytecode compatibility. Elevation changes a byte field to an
integer, so the server source and plugin consumers must be recompiled together;
changing only the defining class would cause JVM field-linkage failures.
Client compilation is restricted to the selected source owners.

Before accepting rebuilt classes, the consumer must prove that baseline source
matches the active original classes. Otherwise stale source could erase a
binary-only customization. Unchanged unrelated class byte payloads and all
unrelated resources remain intact. Recompiled map consumers must retain their
unrelated behavior. Signed archives, unresolved binary-only ABI consumers,
ambiguous source hooks, and unsupported layouts require specific pre-mutation
refusals. A capability file is not a substitute for these checks.

Map import is a separate transaction after the targeted capability is verified.
The normal target source build remains valid because the same reviewed source
edits accompany the generated classes. No build-skip guard is installed.
Offline preview, exact confirmation, drift checks, backup, verification,
automatic failure rollback, interrupted recovery, and reversal evidence remain
Editor-owned requirements.

## Map capabilities and preservation evidence

The payload supports terrain v1/v2 encodings and placements v3/v4/v5. V5 bounds
may extend into missing terrain, but actual movement remains blocked there.
Uniform and run-length encoded wide elevation use the same unsigned 16-bit wire
representation as raw terrain. Content IDs are opaque placement identities,
never instructions to import editor NPC appearances into the target.

Installed floor loading verifies the complete existing prefix before appending
anything. Existing `TileDef` object identities and fields remain intact; hash,
XML, schema, size, ancestry, or prefix conflicts fail before list mutation.
Rendering changes concern explicit base color, transparent floor partners, and
material ancestry so generated materials retain their original appearance.

`tests/myworld/test-target-map-integration.py` compiles provider payloads and
uses disposable map and floor fixtures. Optional
`WORLD_BUILDER_MAP_SOURCE_REFERENCE` checks selected reference source bytes and
hook applicability without compiling or executing that reference. These checks
are not a full target-game acceptance claim: Editor integration must additionally
exercise source/binary preservation, custom dialogue, custom appearance,
item/object callbacks, plugin behavior, repeated import, and recovery.

The separate `test-target-map-adapter-compilation.py` reconstructs older map
source shapes from provider-owned source, compiles the complete server before
and after every shipped edit, and compiles changed client owners. A synthetic
plugin reads the changed elevation field across JAR ownership boundaries. The
before loader rejects v5; after integration the actual loader accepts the same
v5 package with elevation 65535 and retains the placed custom NPC ID. Synthetic
visual/dialogue/item/object callbacks and a custom method in the edited tile
class execute before and after; unrelated callback bytecode remains identical.
The plugin bytecode necessarily changes to use the integer field descriptor.

This fixture does not add its reconstructed source hashes to the production
adapter's accepted hashes. It proves the shipped edit syntax, map decoder,
linked map APIs, and callback preservation against coherent provider-owned
sources. It does not claim that the reference game was compiled or run, that a
native Windows compiler was tested, or that every custom server layout matches.
