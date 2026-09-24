# Terrain material correction, September 2026

The resident GPU mesh now resolves legacy material resources before decoding
solid RGB. The texture channel holds genuine texture IDs; a solid material uses
`Scene.TRANSPARENT` there and decoded RGB in the fallback channel. Fully
transparent geometry has the sentinel in both channels. This matches the
existing object mesh producer's contract. Fallback RGB is never looked up in
the texture catalog, including black (`0`) and other small values.

This fixes terrain's black resource `-1` (including overlay 10's material), and
solid wall/roof resources. Genuine texture 0 retains its ID and UVs. Collision,
definitions, terrain bytes, saving, and wire formats are unchanged. Overlay 10
remains blocking according to its existing definition; this rendering repair
does not turn it into an invisible walkable floor.

## Focused verification

After `./scripts/build-client.sh`, run:

```sh
python3 tests/myworld/test-opengl-world-texture-reference-cache.py
python3 tests/myworld/test-opengl-world-texture-reference-cache.py --render
python3 tests/myworld/test-client-world-model-product-split.py
python3 tests/myworld/test-renderer-v2-world-geometry.py
python3 tests/myworld/test-renderer-v2-object-chunk-primitive-builder.py
python3 tests/myworld/test-renderer-material-family.py
./scripts/test.sh --group presentation
```

The first test is registered in the full test runner. It exercises the actual
World GPU builder for terrain, wall, and roof front/back resources, classic and
remaster material color resolution, genuine texture UVs, and texture-reference
cache behavior. Occupied texture IDs 0 through 3 cannot capture equivalent RGB
values. Black, low blue, white, transparent materials, and genuine textures are
covered.

The optional `--render` mode requires an available display/OpenGL context and
creates only a hidden disposable window. It uses the production vertex upload,
texture atlas, texture-enabled batch classification and binding, then checks
framebuffer pixels. It covers fixed-function rendering with solid and genuine
textured batches. It does not exercise the full remaster shader, software
rasterizer, gameplay, terrain painting, or an installed user project. The
headless checks verify remaster's raw material input separately.

## Floor semantics follow-on

The upper-floor inconsistency remains separate. Both `World`'s shared terrain
face-input collector and its old raster terrain loop replace the base resource
with transparency on planes 1 and 2. Existing legacy maps and canonical
conversions retain overlay 0, so deleting those branches would fill untouched
upper-level empty areas.

Legacy upper overlay 0 also remains walkable; migrating it to blocking overlay
8 would change collision. A migration must preserve invisible/walkable
semantics explicitly before overlay 0 can consistently mean selected ground
color at every signed level. The old bytes alone do not distinguish an
intentionally invisible tile from an owner-authored tile expecting visible
base color; do not infer this from its stored color. Overlay 26 is an existing
invisible path candidate in the Advanced catalog, but is absent from Current
Base and arbitrary imported catalogs need not assign that meaning to 26.

A provider-owned explicit representation and versioned Editor migration are
required, with composition-aware catalog handling and persistence/export/
recovery checks. No plane-dependent behavior or migration is changed by this
material correction.
