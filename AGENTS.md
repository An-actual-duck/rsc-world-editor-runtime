# RSC World Editor Runtime AI Collaboration Rules

This repository is the independent client/server runtime provider for RSC
World Editor. The World Editor manager is the product-level manager across the
Editor and runtime repositories. It may coordinate this runtime manager and
its workers as part of an assigned World Builder objective. The repositories
remain independent: this is not Spoiled Milk, does not own a public game
server, and must never inspect or modify `/home/justin/Core-Framework`.

Before changing anything, identify the checkout role and run:

```bash
git status --short --branch
./scripts/ai-workspace.sh status
```

## Roles and default staffing

- `/home/justin/rsc-world-editor-runtime` is the runtime manager checkout. It
  owns runtime `main`, reviews exact handoffs, runs provider tests, and
  publishes provider commits. The product manager may operate this checkout
  for repository management, integration, and small localized runtime changes.
- `/home/justin/rsc-world-editor-runtime-ai-1` is the normal runtime
  implementation worker.
- Runtime `ai-2` and `ai-3` are dormant overflow/review slots. They are used
  only for genuinely independent work and need not be monitored while IDLE.
- `/home/justin/rsc-world-editor` is the product and consuming Editor manager.
  After publishing tested runtime work, it may select the exact commit in
  `runtime-provider.lock` as a normal step of the active cross-repository
  objective.
- `/home/justin/rsc-world-editor/.runtime-provider` is a disposable detached
  dependency checkout, never a development worktree.

## Product-manager authority

An assigned World Builder objective that requires client/server behavior
authorizes the product manager to:

1. start or revise a coherent runtime worker assignment;
2. review, test, merge, publish, and recycle its exact READY handoff;
3. report or directly consume the resulting published runtime SHA in the
   Editor repository; and
4. coordinate related Editor work without asking the owner to relay prompts,
   commits, or a separate lock-advance instruction.

Related requirements may be added, removed, or corrected on the active branch.
A new branch is required only when the work becomes unrelated, independently
releasable, or unsafe to review as one diff. READY means ready for review, not
that scope can never be adjusted.

This authority does not include deployment, a live-server action, mutation of
real player/user data, destructive Git history, or a release/upload not already
requested by the owner.

## Independence boundary

- Manage only `rsc-world-editor-runtime`, its `origin` remote, its registered
  runtime workers, and product-level coordination with `rsc-world-editor`.
- Never run collaboration, release, deployment, database, or live-server
  scripts belonging to Core-Framework or Spoiled Milk.
- Never inspect, activate, collect, merge, or report
  `/home/justin/Core-Framework-ai-*`.
- Never merge or import Spoiled Milk `main`. Required behavior is implemented
  deliberately on this runtime's own topic branches.
- This repository publishes source commits only. World Editor owns product
  packaging, candidates, updates, release gates, releases, and user workspaces.
- The inherited game source and historical documentation are runtime inputs,
  not evidence that this repository owns the Spoiled Milk game or server.

## Runtime worker rules

1. Use one descriptive topic branch for one coherent umbrella; never work on
   `main` or detached `HEAD`.
2. Accept manager follow-ups that add, remove, or correct related details
   without demanding a new authorization or branch.
3. Checkpoint with `./scripts/ai-workspace.sh checkpoint -m "message"` and
   hand off the exact tested review tip with
   `./scripts/ai-workspace.sh handoff -m "message"`.
4. Report changed files, exact tests/builds, real-runtime evidence, untested
   behavior, risks, and the exact pushed SHA.
5. Do not modify the Editor lock, publish Editor releases, deploy, or operate a
   live game server.

## Runtime manager rules

1. Keep manager `main` clean and published except during deliberate repository
   management, direct localized work, or integration.
2. Begin collection with `./scripts/ai-manager.sh status`. The manager handles
   prompts, follow-ups, handoff inspection, exact diffs, merging, publication,
   and recycling; the owner need not act as courier.
3. Rescue unique dirty work before cleanup. Never overwrite work of uncertain
   ownership and never permit two sessions in one worktree.
4. Inspect and test the exact READY tip before merging. Direct manager changes
   receive equivalent review and risk-appropriate verification without a
   synthetic worker handoff.
5. Run focused tests for narrow low-risk changes and the full runtime suite for
   behavioral/runtime integration intended for Editor adoption.
6. Push tested runtime `main`, recycle only after publication, and make the
   exact published commit available to the product manager. In-scope Editor
   adoption may proceed immediately.

## Preservation rules

- Never use `git stash`, `git clean`, `git reset --hard`, forced checkout,
  forced branch deletion, or forced worktree removal as routine workflow.
- Never delete a dirty slot; rescue and push it first.
- Do not run two AI sessions in the same worktree.
- If Git state is unexpected, stop editing and inventory it from the runtime
  manager checkout.

The authoritative workflow is in
[`docs/RUNTIME-PROVIDER-WORKFLOW.md`](docs/RUNTIME-PROVIDER-WORKFLOW.md).
