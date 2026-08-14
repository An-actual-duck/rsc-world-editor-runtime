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
./scripts/test.sh
git push origin main
./scripts/ai-workspace.sh recycle ai-1
```

The product manager can then run this from the Editor manager checkout:

```bash
./scripts/product-manager.sh adopt-runtime
```

That command selects only this clean published `main`, advances the bounded
Editor lock/protocol inputs, materializes the detached dependency, runs parity
and the full Editor suite, commits, and publishes the integration. An optional
exact SHA may be supplied as an additional guard. The owner need not shuttle
the commit between sessions.

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
