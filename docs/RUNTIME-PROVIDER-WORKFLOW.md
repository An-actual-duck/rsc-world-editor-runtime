# Runtime provider workflow

This repository supplies the pinned adaptive client/server runtime used by RSC
World Editor. It is operationally independent from Spoiled Milk while being
coordinated by the World Editor product manager.

```text
/home/justin/rsc-world-editor-runtime       runtime manager
/home/justin/rsc-world-editor-runtime-ai-1  normal runtime worker
/home/justin/rsc-world-editor-runtime-ai-2  dormant overflow worker
/home/justin/rsc-world-editor-runtime-ai-3  dormant overflow worker
```

The consuming Editor records an exact published commit in
`runtime-provider.lock`. A runtime commit changes an Editor build only after
the product manager deliberately adopts it, materializes it, runs parity, and
verifies the Editor. When runtime work belongs to the active World Builder
objective, this adoption is a normal completion step and does not need a
second owner prompt.

## Normal task cycle

The product manager starts runtime AI-1 with a coherent objective:

```bash
./scripts/ai-workspace.sh status
./scripts/ai-workspace.sh start ai-1 fix/descriptive-runtime-task
```

The owner may add, remove, or revise related details while the branch is
active. The manager sends follow-ups; a replacement branch or “correction
prompt” is unnecessary unless the objective becomes unrelated.

The worker checkpoints during iteration and marks only the exact review tip
READY:

```bash
./scripts/ai-workspace.sh checkpoint -m "Checkpoint runtime task"
./scripts/ai-workspace.sh handoff -m "Finish runtime task"
```

The manager reviews the complete diff, runs the appropriate builds/tests,
merges, publishes, and recycles:

```bash
./scripts/ai-manager.sh status
git diff main...fix/descriptive-runtime-task
./scripts/ai-manager.sh merge fix/descriptive-runtime-task
# Choose affected tests; for client-only presentation:
./scripts/test.sh --group presentation
git push origin main
./scripts/ai-workspace.sh recycle ai-1
```

The product manager can then run this from the Editor manager checkout:

```bash
./scripts/product-manager.sh adopt-runtime --verification presentation --reason "Reviewed client-only presentation diff; persistence unchanged"
```

That command selects only this clean published `main`, advances the bounded
Editor lock/protocol inputs, materializes the detached dependency, runs parity
and scope-selected Editor checks, commits, and publishes the integration. An optional
exact SHA may be supplied as an additional guard. The owner need not shuttle
the commit between sessions. Select `presentation`, `transactions`, or `full`
after reviewing the complete provider diff; the required reason is recorded in
the integration commit. A lock change alone does not justify both full suites.

## Verification scope and budgets

Follow the product manager's `docs/TESTING-POLICY.md` in the independent Editor
repository. UI iteration targets 1–3 minutes of verification; a refreshed owner
candidate targets 5–10 minutes including packaging. These are targets, not
guarantees. Explain newly discovered risk and obtain owner agreement before
expanding a small UI task to broad verification; never silently omit safety tests.

The presentation profile runs existing viewport, widescreen-input, software
scale and authoring-only Preservation UI regressions headlessly. Compile affected code and check actual visuals and
pointer alignment separately; fullscreen/readiness logs do not prove appearance.
Add dependency/archive checks when those inputs change. State/data/protocol or
transaction changes require their affected integration and refusal/recovery tests.
Broad integration uses `./scripts/test.sh --full`. Production acceptance keeps
all full-suite, exact-artifact and release requirements. A restricted owner-test
candidate is not production acceptance and need not repeat unchanged gameplay
or migration suites for a UI-only diff.

World Builder launches may opt into `openrsc.worldBuilderPreservationUi=true`
alongside `openrsc.worldBuilderMode=true`. This presentation-only profile uses
Preservation-style Social/General tabs, classic sprites/text spellbooks, and
the existing software integer x1/x2 scaling. The logical minimum is 640x480,
not Preservation's 512x346, because the existing map-editor dock is 396 pixels
tall. The window remains resizable; no fullscreen/aspect-fit scale is implied.
General retains scaling, middle-mouse tilt/classic mode, coordinates, and
available roof/flicker controls. Spoiled Milk renderer controls, custom HUDs,
spellbook/minimap layout controls, focus menus and related developer hotkeys
are absent in this profile. Editor tools, camera rotation/pitch and extended
zoom remain; installed-player defaults and persisted map/server data do not change.
The consuming Editor must select software presentation and keep camera pitch
and extended zoom enabled in its authoring launch command. Existing immutable
project runtime capsules are not rewritten by selecting this profile.

Authoring Magic/Prayer uses two classic text-list tabs; Summoning is hidden.
Definitions and spell/prayer IDs still come from the selected composition;
Base's canonical prayers cannot be replaced by an Advanced prayer-book packet.
Coordinates sit one text line below their previous top-right position. Editor
selection/paste/line/move/lockdown markers and the build grid project directly
through the software scene camera when no captured GPU frame exists. This
does not create a geometry frame or change navigation's fresh-frame latch.

Preserve exact tested/published handoffs. Reuse verified immutable build outputs
only when source, dependencies, options and toolchain match; keep mutable test
state isolated. Do not overlap builds and tests in one output directory. Check
DISPLAY/Java prerequisites first, and resume only failed/unexecuted tests after
environment fixes with unchanged inputs. Bare `scripts/test.sh` remains the full
gate for compatibility; agent work must use an explicit selection.

## Staffing

Runtime AI-1 is sufficient for normal sequential work. AI-2 and AI-3 stay
detached and IDLE unless two tasks are genuinely independent or an isolated
review is valuable. Do not activate multiple sessions in one slot, and do not
use extra workers merely because they exist.

Small runtime repository-management or localized changes may be performed by
the manager. Substantial client/server behavior normally uses runtime AI-1 so
the manager can independently review integration.

## Scope

Runtime-owned work includes adaptive authentication and binding, native
terrain and placement behavior, client/server startup, loaders/rendering,
provider builds, and runtime regression coverage. World Editor owns launchers,
project storage, discovery/conversion tooling, export/import, candidate
inspection, packaging, updates, release gates, and user-facing releases.

The repository has no live deployment role. Its inherited Spoiled Milk
deployment and release scripts are historical runtime inputs and remain outside
this workflow. Core-Framework managers, workers, branches, and live-server
state are never inspected or operated.
