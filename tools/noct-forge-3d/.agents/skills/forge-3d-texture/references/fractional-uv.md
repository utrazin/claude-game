# Fractional UV Specification

Full `UVBuilder` signatures: [generated recipe-context reference](../../../../docs/api/recipe-context.md).

Advanced policy for polygon meshes. Flag: `require_integer_uvs=False` (CLI: `--no-require-integer-uvs`).

## Technical Invariants
- **Coordinate System:** Bounds centers align to 0.5-pixel multiples. Preserves distances at target `uv_scale`. No per-vertex snapping.
- **Pixel Coverage:** Positive-area intersection (threshold > 1e-12 px²). Fully opaque coverage; no antialiasing.
- **Padding:** Surrounds integer pixel allocation; does not modify geometry or UV scale.
- **Non-Planar Quads:** Uses rectangular parameter grid sized by averaged opposite edges.

## Charts layout (`--layout charts`)
The default `faces` layout gives every face its own island, grid orientation and phase (non-planar quads become stretched rectangles), so the texel grid breaks at every edge. `--layout charts` (with `--no-require-integer-uvs`; remembered in `uv_packing.layout`) grows islands across shared edges instead (`Tools/uv_charts.py`):
- **Exact size:** rigid unfolding keeps every face's true size, so one texel is `1 / uv_scale` everywhere and a shared edge is the same UV segment on both faces: the grid continues from face to face.
- **When a face joins:** across an edge with a fold of at most 50 degrees, when its closing vertices miss by at most 1 texel (absorbed as a slight shear), without overlap, while the up direction turns at most 24 degrees within the chart. Charts grow from front-facing faces first.
- **Orientation:** each chart is turned so the model's +Y is up in the texture.
- **Texel ownership:** faces carry `model_as_code_chart`. The texture painter gives every texel a chart touches to exactly one face (the one containing its centre, else the first covering it), and dilates whole charts into the padding only.

Use it for pixel art and lineart ([lineart](lineart.md)). `share_uv` is not available with charts. A UV rule can chart only some meshes or give them their own density ([UV recipes](uv-recipes.md)).

## Explicit UV Sharing (`share_uv`)
- Requires matching dimensions (cubes/quads) or identical vertex count, cyclic order, and projected layout (polygons, tolerance `1e-8` px).
- Follower faces are read-only and point to owner faces. Cycles and chains prohibited.

```python
from Tools.uv_builder import UVBuilder

UVBuilder("projects/<name>/model.bbmodel", require_integer_uvs=False).share_uv(   # two identically built meshes
    target=("arm_R", "side_000"), source=("arm_L", "side_000")).save()
```

### Mirrored pairs (`mirror=True`)
A left/right pair can share one island reflected: `share_uv(target=("ear_R", "side_000"), source=("ear_L", "side_000"), mirror=True)`. The follower must be the owner's reflection (same layout reflected across its width or height, vertex order reversed); otherwise saving raises `UV mirror shape differs` and writes nothing. Cube faces become the owner's rectangle flipped horizontally. Density, pixel grid and texel count stay exactly the owner's: only the image appears reflected on the follower. Shared regions cannot hold asymmetric details (a scar on one side): keep those faces unshared. Declare each pair in the UV recipe; nothing is shared automatically.

### Padding and smooth textures
Assets with `"texture_filter": "linear"` need `island_padding >= 4` (smoothing and mipmaps read neighbor pixels); `forge texture` and `forge status` warn below that. Set it in the UV recipe or with `--island-padding 4` (a twin made with `forge asset twin` gets it). Smooth assets dilate the whole padding on save; see [render modes](render-modes.md).

In the `charts` layout every quad is given its canonical A-C diagonal (the shorter one; mirror-consistent ties) before unfolding: an unfolded chart is not an exact affine image of every face, so the diagonal a quad is drawn with bends its texture, and mirrored quads must bend the same way. The shape does not change.

`share_uv(target, *, source, mirror=False)` takes `(element, face)` pairs; `clear_sharing()` resets the plan; `save()` repacks and writes the model. Face names depend on the shape: primitives use `side_000`, sweeps and segments use `<section>__<section>_side_000`; list them with `list(painter.element(name).faces)`.
