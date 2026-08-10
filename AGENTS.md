# RSC World Editor Runtime AI Collaboration Rules

This repository is the independent client/server runtime provider for
`rsc-world-editor`. It is not Spoiled Milk, does not own a public game server,
and must never inspect or modify `/home/justin/Core-Framework`.

Before changing anything, identify the session role and run:

```bash
git status --short --branch
./scripts/ai-workspace.sh status
```

## Roles

- `/home/justin/rsc-world-editor-runtime` is the runtime manager checkout. It
  owns `main`, reviews exact handoffs, runs provider tests, and publishes
  provider commits.
- `/home/justin/rsc-world-editor-runtime-ai-1` through `-ai-3` are neutral
  runtime worker slots. A worker edits only after the manager starts a focused
  topic branch.
- `/home/justin/rsc-world-editor` is the consuming World Editor manager. It may
  select an exact published runtime commit for `runtime-provider.lock`, but it
  does not edit this checkout directly.
- `/home/justin/rsc-world-editor/.runtime-provider` is a disposable detached
  dependency checkout, never a development worktree.

## Independence boundary

- Manage only this repository, its `origin` remote, and its registered
  `rsc-world-editor-runtime-ai-*` worktrees.
- Never run collaboration, release, deployment, database, or live-server
  scripts belonging to Core-Framework or Spoiled Milk.
- Never merge or import Spoiled Milk `main`. Required upstream behavior must be
  implemented deliberately on this runtime's own topic branches.
- This repository publishes source commits only. World Editor owns product
  packaging, candidates, releases, updates, and end-user workspaces.
- The inherited game source and historical documentation are runtime inputs,
  not evidence that this repository owns the Spoiled Milk game or server.

## Worker rules

1. Use one descriptive topic branch per task; never work on `main` or detached
   `HEAD`.
2. Checkpoint with `./scripts/ai-workspace.sh checkpoint -m "message"` and
   hand off with `./scripts/ai-workspace.sh handoff -m "message"`.
3. Report changed files, exact tests/builds, real-runtime evidence, untested
   behavior, risks, and the exact pushed SHA.
4. Do not modify World Editor's lock, publish World Editor releases, or operate
   any live game server.

## Manager rules

1. Keep the manager checkout on clean `main` except for deliberate repository
   management or integration.
2. Begin collection with `./scripts/ai-manager.sh status`.
3. Rescue unique dirty work before cleanup; never stash, force-reset, or
   force-delete it.
4. Inspect and test the exact READY handoff before merging.
5. Push tested `main`, then recycle only after the handoff is contained in
   published `origin/main`.
6. Give the World Editor manager an exact published SHA. Advancing its lock is
   a separate, explicit World Editor operation.

## Preservation rules

- Never use `git stash`, `git clean`, `git reset --hard`, forced checkout,
  forced branch deletion, or forced worktree removal as routine workflow.
- Never delete a dirty slot; rescue and push it first.
- Do not run two AI sessions in the same worktree.
- If Git state is unexpected, stop editing and inventory it from the runtime
  manager checkout.

The authoritative workflow is in
[`docs/RUNTIME-PROVIDER-WORKFLOW.md`](docs/RUNTIME-PROVIDER-WORKFLOW.md).
