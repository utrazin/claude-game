# TexturePainter API Reference

Full method signatures (`TexturePainter`, `ElementPainter`, `FacePainter`,
`FaceCanvas`, `DecalCanvas`, `TextureExporter`, selections, regions, fields):
[generated TexturePainter reference](../../../../docs/api/texture-painter.md).

Declarative surface painting, geometric contact fields and standalone bitmaps. Colors are `(r, g, b)` or `(r, g, b, a)` with 0-255 integers.

```python
# runnable: paint a small box model
import tempfile
from pathlib import Path
from lib import ModelBuilder, Placement
from Tools.TexturePainter import DecalCanvas, TexturePainter

builder = ModelBuilder("crate")
builder.add_group("root")
builder.add_cylinder("drum", "root", radius=1.5, height=3, segments=8)
builder.add_cylinder("lid", "root", radius=1.6, height=0.4, segments=8,
                     placement=Placement.at("drum:top").pivot("base"))
model_path = Path(tempfile.mkdtemp()) / "model.bbmodel"
builder.export_bbmodel(model_path, auto_uv=True)

painter = TexturePainter.from_bbmodel(str(model_path))
names = [e.name for e in painter.all_elements()]           # element names; painter.element(name) raises KeyError if unknown
drum = painter.element("drum")
drum.fill_all((90, 60, 40, 255))
print(list(drum.faces)[:3], list(drum.groups))
drum.band("y", 0.0, 0.3).fill((50, 35, 25, 255))
drum.group("side").apply_gradient((120, 90, 60, 255), (70, 50, 35, 255))
first = next(iter(drum.faces.values()))
first.apply_noise(variance=6, seed=1)
first.stamp(["#.#", ".#.", "#.#"], {"#": (255, 255, 255, 255)}, clip=True)   # without clip=True a pattern larger than the face raises
drum.paint_surface(lambda sample: (200, 40, 40, 255) if sample.face_uv[1] > 0.9 else None)
field = painter.creases(max_internal_angle=100) | painter.contacts(tolerance=0.2)
field = field.mask(lambda hit: hit.normalized_distance < 0.8)
field.paint(lambda hit: (0, 0, 0, int(160 * (1.0 - hit.normalized_distance))), blend="multiply")
painter.save(str(model_path.with_name("texture.png")), edge_dilation=0)

sprite = DecalCanvas(64, 64)
sprite.define_region("tile", 0, 0, 32, 32)
sprite.region("tile").fill((100, 150, 80, 255))
sprite.save(model_path.with_name("tile.png"))
```

## Painting Decision Matrix (Which approach to choose?)
| Painting Space | Primary Tool / API | Best For | Mental Model |
|---|---|---|---|
| **2D Face UV** | `FacePainter` (`element.face(name)`) | Single UV islands, procedural ASCII patterns (`stamp`), pixel-precise 2D rects/circles. | Operates on the unwrapped 2D pixel grid of one face. |
| **3D Geometric Slice** | `SurfaceRegion` (`element.band`, `element.patch`) | Color transitions along axes (Y-gradient, belts, boots), rectangular cuts on 3D sides. | Slices 3D mesh points before rasterization. |
| **Universal 3D Projection** | `project_decal(source, side=...)` | Decals, emblems, face expressions, external PNG assets, angled stamps across multiple faces/cubes. | Projects from a camera plane onto any 3D surface. |
| **Seamless Triplanar** | `project_triplanar(source, scale=...)` | Continuous textures (leather, stone, fabric, noise) across complex forms without visible UV seams. | Blends projections along X, Y, and Z by surface normal. |
| **Seamless Planar** | `project_planar(source, side=..., scale=...)` | A tile that must keep one direction (weave, stripes, planks) continuous across several elements. | Repeats the image along one side's axes in model units. |
| **Procedural Fields** | `element.paint_field(field.ramp(...) or field.dither(...))` | Noise, cracks, grain, weave, gradients by height or facing, with pixel-art dithering or smooth color, continuous across faces. | Evaluates a composable field at each texel's 3D position. See [procedural fields](procedural-fields.md). |
| **Lineart Strokes** | `painter.paint_strokes([stroke(curve(...), width=2, color=...)])` | Ink lines, outlines, trims, stitches, curves; pixel art (`soft=0`) or smooth (`soft>0`); 2D paths on a `side`, 3D paths on the surface. | Measures each texel's distance to the path. See [lineart](lineart.md). |
| **Brush strokes and prints** | `painter.stamp(Pattern..., tip=, brush=, colors=)`, `paint_looks(...)` | Painted textures (chalk, dry brush, fur tufts), scattered or regular prints of a motif, single prints, materials painted in layered passes. | Strokes of stamps on the 3D surface, from theme tokens. See [themes, marks and looks](theme.md). |
| **Non-Destructive Layers** | `painter.layer(name)` | Modular assets (facial expressions, armor overlays, hair variations), clean compositing and game-ready layer export. | Independent transparent buffers alpha-composited into atlas. |

> **Color Format Requirement:** Colors must strictly be `(r, g, b)` or `(r, g, b, a)` with **0-255 integers**, or hex strings (`#rgb`, `#rrggbb`). Normalized floats `0.0 - 1.0` intentionally raise a `ValueError`.

## Names
- `painter.element(name)` raises `KeyError` for an unknown name (`painter.all_elements()` lists them).
- `element.faces` is a dict of face painters: `north south east west up down` for cubes, mesh face names (`side_000`, `cap_top_001`) for polygon meshes. `element.face(name)` and `element.group(name)` (a mesh's face group such as `side`) select faces; `ElementPainter.VALID_FACES` lists the cube faces.

## Essential operations (full signatures in the generated reference)

- `fill(color)` / `fill_all(color)`, `draw_rect`, `draw_line`, `draw_circle`,
  `set_pixel`, `apply_gradient(top, bottom)`, `apply_noise(variance, seed)`.
- `element.band(axis, start, end)` and `element.patch(side, center, size)` select
  3D regions; `element.paint_surface(callback)` paints from `sample` data.
- `project_decal(...)` projects PNGs/decals; `project_triplanar(...)` blends
  seamless X/Y/Z projections. On a single 2D face use `face.stamp(...)`/`face.blit(...)`.
- Projections (`project_decal`, `project_planar`) take `layers="all"|"front"` (`front`: only the surface layer in
  front along `side`, so the wall behind a collar or a shell stays untouched; `all` is the default) and
  `fade=(f0, f1)` (the image fades in from facing `f0` to full at `f1` instead of a hard `normal_threshold` cut, so
  grazing faces lose it gradually). In a smooth asset every projection averages the image over the texel area
  ([render modes](render-modes.md)). `mirror="x"` (decal, planar, triplanar) paints the +x half and copies each texel
  onto its mirror image, so both halves are identical by construction (the projection must cover the +x side).
- `painter.select(tag=...)` paints tagged elements; `painter.layer(name)` +
  `compose_atlas(texture=0)` / `export_layers()` handle overlays and expressions. `painter.select(tag=..., texture=...)` selects by tag and/or UV texture slot, and `painter.save(paths.texture)` saves and registers every texture slot (`texture.png` for `"default"`, `texture_<slot>.png` for named slots; `paths.texture_for(slot)` resolves one slot's path).

## Speed of surface callbacks
`paint_surface(callback)` calls Python once per texel; the engine itself works on whole faces. For heavy per-texel math (noise, fbm) on large atlases use `paint_surface_arrays(callback)`: it receives one face's samples as arrays (`rows.model_position`, `rows.normalized_position`, `rows.model_normal`, `rows.x`, ...) and returns an `(N, 4)` RGBA array, or `(colors, keep)` to paint only some rows. Both give the same result for the same colors.

## Painted (non pixel art) textures
- Pack UVs denser (`forge uv PROJECT --asset ID --uv-scale 16 --island-padding 4`), so strokes have texels to land on and smoothing does not mix islands (see [padding](fractional-uv.md#padding-and-smooth-textures)).
- Project images with `filtering="bilinear"`; keep `edge_dilation` at the island padding.
- Register `"texture_filter": "linear"` on the asset in `project.json`: viewers, `capture` and GLB exports then smooth the texture (default `nearest` keeps pixel art crisp). Compare both with the viewer's Smooth Texture toggle or `capture --filter nearest|linear`.

## Art requests (external producer, only when the user asks)
Only when the user explicitly asks for images produced elsewhere (the 2D asset forge, another tool or person): list them in the project's `art.json` (name, full description including style such as pixel art or painted, exact pixel size, optional guide), give the producer its path or the `forge art prompt` text, then `forge art pull` and print `painter.art(id)` in the recipe. Read [art requests](art-requests.md).

## Layers Architecture
- `with painter.layer("name"): ...` or `painter.layer("name")`: Paints onto an independent named layer in memory.
- `painter.layer("name", blend="multiply", opacity=0.5)` / `add_layer(...)`: how the layer composites over the ones under it (`normal`, `multiply`, `screen`, `add`).
- `painter.clear_layer("name")`: Clears all pixels in a specific layer.
- `painter.compose_atlas(edge_dilation=0, hide=())`: Composites all visible layers into a single atlas image, each with its blend and opacity; `hide` leaves layers out (also `save(..., hide=)`).
- `painter.surface()`: every texel as one view (`position`, `normal`, `element`, `group`, `select`, `write`); `painter.material_map(classify)`: a cached material map ([themes](theme.md)).
- `painter.export_layers(output_dir)`: Exports each visible layer as an independent transparent PNG file (ideal for modular game engines, face expressions, equipment overlays).

## Contact and crease fields
`painter.creases(max_internal_angle=100, spread=1.0)` finds folds; `painter.contacts(tolerance=, spread=1.0)` finds where parts touch. Combine with `|`, filter with `field.mask(predicate)` where `predicate(hit)` returns a bool (`hit.normalized_distance`, `hit.distance`, `hit.intensity`, `hit.kind`, `hit.surface`), then `field.paint(callback, blend="multiply")`; `callback(hit)` returns a color. Blend modes: `replace normal multiply screen add`.

## Decal Canvas & Standalone Bitmaps
- `DecalCanvas` can be imported directly (`from Tools.TexturePainter import DecalCanvas`) or created via factory: `TexturePainter.create_canvas(width, height, background=(0, 0, 0, 0))`.
- Inherits all discrete 2D primitives (`fill`, `set_pixel`, `draw_rect`, `draw_circle`, `draw_line`, `apply_noise`, `apply_gradient`, `draw_pattern`, `stamp`, `blit`) plus sub-regions: `define_region(name, x, y, w, h)`, `region(name)`, `tile_grid(tile_w, tile_h, names)`, `make_seamless()`, `compose()` and `save(path)`.

## Related commands
`py -3.12 -m Tools.forge texture PROJECT --asset ID` runs the registered paint recipe against existing UVs. `py -3.12 -m Tools.forge status PROJECT --asset ID` reports artifact state. Recipe paths come from `Tools.recipe_context.recipe_paths(__file__)`; no fixed folder depth or model recipe dependency is required. See [pipeline](../../../../docs/pipeline.md).
