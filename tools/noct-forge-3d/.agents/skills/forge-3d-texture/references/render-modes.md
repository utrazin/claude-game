# Render modes: pixel art and smooth

One recipe paints both. The mode belongs to the asset, never to the recipe: the asset's `texture_filter` in `project.json` picks it (`nearest` = pixel art, `linear` = smooth), because the filter a texture is viewed with decides how it has to be painted.

| | pixel | smooth |
|---|---|---|
| UV density (`--uv-scale`, set when the asset is created) | 8 px/unit | 16 px/unit |
| island padding / edge dilation | 1 | 4 (the whole padding is dilated on save) |
| texel edges | hard (alpha 0 or 1) | exact area coverage, a one-texel edge |
| subsamples per texel | 1 | 4 x 4, only where the colour changes |

Override any value in the asset record: `"render": {"density": 24, "padding": 4, "aa": 1.0, "samples": 4, "reference": 8}`. `aa` is the anti-aliasing box in texels (1 = exact coverage; larger is softer), `samples` the subsamples per texel side, `reference` the density stroke widths are written in.

## What smooth mode changes
- `paint_surface_arrays` and `paint_field`: each texel's colour is the average over its area. A hard condition in a recipe (`y > 0.4`, `np.select` rings, a band, a buckle) becomes a smooth edge without touching the recipe. Only texels whose centre colour differs from a neighbour are subsampled, so a flat area costs one evaluation per texel. The callback must colour each row from that row's fields (`model_position`, `normal`, ...), which every recipe in the repository already does.
- `paint_strokes`: see [lineart](lineart.md#smooth-render-mode-smooth). Widths keep their size on the model (`reference`).
- `save()` dilates the whole island padding, which a linear filter reads.
- `project_decal`, `project_planar` and `project_triplanar` average the image over the texel area (anti-aliased borders, filtered images); `layers="front"`, `fade` and `mirror="x"` work in both modes ([texture painter API](texture-painter-api.md)).
- `paint_surface` (per-sample callbacks), `fill`, noise paint as before.

## Pixel art and smooth side by side: twins
A model can have a smooth twin:

```bash
py -3.12 -m Tools.forge asset twin PROJECT --asset SOURCE --id SOURCE_smooth
py -3.12 -m Tools.forge texture PROJECT --asset SOURCE_smooth --variant VARIANT
```

The twin (`"twin_of": SOURCE`) gets a copy of the source's current model (never regenerated), its own UVs at the mode's density and padding, and every source variant with the source's recipes. It has no model recipe: edit the source (recipe or Blockbench), then `forge asset twin PROJECT --asset TWIN --sync` copies the model again and repacks it with the twin's remembered UV options; repaint afterwards. `--mode pixel` makes a pixel twin of a smooth asset.

## Cost
Painting time grows with the texel count (density squared) and the base recipe's per-texel work; smooth textures add subsamples only along colour edges. 16 px/unit is twice the linear resolution of the pixel art: for the same recipe, a smooth asset at that density takes a few times longer than its pixel twin. That holds for the density alone: the strokes can cost far more. A `wrap=True` line is lifted onto every chart under it, so many wrapped strokes over an atlas packed per face (hundreds of small charts), or several projections of the same line, can take minutes. Prefer continuous charts for surfaces lines cross, wrap only the lines that cross sloped surfaces, and paint broad patterns (stripes, patches) as [procedural fields](procedural-fields.md) of the model-space position rather than as many projected strokes. `forge texture` streams the recipe's prints and its elapsed time to stderr, so print a line per phase in a heavy recipe to see where the time goes. Raise `density` only when the asset is seen closer than the default.
