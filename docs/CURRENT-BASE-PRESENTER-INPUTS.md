# Current Base desktop presenter inputs

Base retains native public terrain and gameplay. Its client also packages the
existing shared desktop presenter so the Editor can display the software frame
with fullscreen, logical-resolution scaling, and matching pointer coordinates.
Including these libraries does not enable Advanced terrain, lighting, effects,
assets, or player-client launch settings.

The selected Base artifact requires LWJGL 3.3.4 `lwjgl`, `lwjgl-glfw`, and
`lwjgl-opengl`, each with its code jar and Linux/Windows x64 native jars. SHA-256
pins live in `scripts/current-base-lwjgl.py`, verified against Maven Central.
No dependency jars are committed. Provision a fresh source checkout explicitly:

```bash
python3 scripts/current-base-lwjgl.py --download
python3 scripts/build-current-base.py
```

Offline test clones can provision from an already verified dependency directory:

```bash
python3 scripts/current-base-lwjgl.py --stage-from /absolute/source/PC_Client/lib/lwjgl
```

Normal Base builds do not download. Before replacing build output they reject
missing, modified, symlinked, or unexpected LWJGL inputs. Provisioning never
replaces an existing changed input. The source-tree candidate verifier compares
all packaged LWJGL classes and Linux/Windows native payload bytes with the pinned
inputs, so compilation through reflective bindings cannot conceal an incomplete
fullscreen presenter. Keep the verified dependency inputs available alongside
the source when performing independent candidate verification.

This is build/presentation evidence, not Windows runtime acceptance or a change
to installed-server or installed-player behavior.
