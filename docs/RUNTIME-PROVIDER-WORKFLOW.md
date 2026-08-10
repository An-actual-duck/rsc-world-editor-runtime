# Runtime provider workflow

This repository supplies the pinned adaptive client/server runtime used by
RSC World Editor. It is operationally independent from Spoiled Milk.

```text
/home/justin/rsc-world-editor-runtime       manager; main only
/home/justin/rsc-world-editor-runtime-ai-1  neutral runtime worker
/home/justin/rsc-world-editor-runtime-ai-2  neutral runtime worker
/home/justin/rsc-world-editor-runtime-ai-3  neutral runtime worker
```

The consuming editor records an exact commit and repository URL in
`runtime-provider.lock`. A newer runtime commit never changes an Editor build
until the Editor manager explicitly advances that lock and reruns parity,
candidate, archive, and native-launch validation.

## Normal task cycle

From the runtime manager checkout:

```bash
./scripts/ai-workspace.sh status
./scripts/ai-workspace.sh start ai-1 fix/descriptive-runtime-task
```

From the assigned worker:

```bash
./scripts/ai-workspace.sh checkpoint -m "Checkpoint runtime task"
./scripts/ai-workspace.sh handoff -m "Finish runtime task"
```

After review and tests, from the runtime manager:

```bash
./scripts/ai-manager.sh merge fix/descriptive-runtime-task
git push origin main
./scripts/ai-workspace.sh recycle ai-1
```

The manager then reports the exact published SHA to the World Editor manager.
The runtime manager never edits the Editor lock itself.

## Scope

Runtime-owned work includes adaptive authentication and binding, native
terrain protocol/runtime behavior, client/server startup, provider builds, and
provider regression coverage. World Editor owns launchers, project storage,
candidate inspection, product packaging, automatic updates, release gates,
and user-facing releases.

The repository has no live deployment role. Its inherited Spoiled Milk
deployment and release scripts are historical runtime inputs and are outside
this workflow.
