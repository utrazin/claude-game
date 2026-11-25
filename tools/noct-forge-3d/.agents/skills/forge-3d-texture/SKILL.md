---
name: forge-3d-texture
description: Pack UVs or paint textures on an existing Forge3D BBModel with independent UV and painting commands, including expression variants sharing one atlas layout.
---

# Forge 3D Surface and Texture

UV and painting are separate operations. UV reads the current BBModel geometry and embedded options; painting requires existing explicit UVs and its own paint recipe. Neither reads or executes the geometry recipe. Run only the operation requested.

```bash
py -3.12 -m Tools.forge uv PROJECT --asset ID --island-padding 1
py -3.12 -m Tools.forge texture PROJECT --asset ID
py -3.12 -m Tools.forge texture PROJECT --asset ID --variant angry
```

For pixel art and lineart pack with `--layout charts --no-require-integer-uvs`: neighbouring faces share one continuous texel grid instead of one island per face (see [fractional UV and sharing](references/fractional-uv.md#charts-layout---layout-charts)). If a polygon collapses at density 1, increase `--uv-scale` without changing the model recipe. Read [fractional UV and sharing](references/fractional-uv.md) for organic polygons and explicit shared islands. Packing may change atlas dimensions; it never repaints existing PNGs.

For a custom UV plan, use the asset's optional `generate_uv.py`, which `forge uv` runs. It can set a density per region, give flat-colour parts one texel each (`layout="flat"`), draw a face at a fixed size (`layout="fixed"`, `pin`) and choose the packer (`maxrects`, `shelf`, `grouped`). Read [UV recipes](references/uv-recipes.md) first. Without a recipe the automatic packing applies.

Edit the registered `generate_texture.py` using `recipe_paths(__file__)`: `.model` is the BBModel, `.texture` the selected destination, `.variant` the expression name. Use `TexturePainter.from_bbmodel(paths.model)` and save to `paths.texture`. Read [painter API](references/texture-painter-api.md) for selections, layers, decals and triplanar projection. Full signatures: [generated TexturePainter reference](../../../docs/api/texture-painter.md), [recipe context](../../../docs/api/recipe-context.md), [CLI](../../../docs/api/cli.md).

Pixel art or smooth is the asset's render mode, not the recipe's: `texture_filter` `nearest` paints hard texels, `linear` paints anti-aliased shapes, edges and lines from the same recipe. For a smooth version of a pixel asset (or the reverse) create a twin with `forge asset twin` instead of a second recipe set: read [render modes](references/render-modes.md).

For structured procedural variation (stone, wood, cloth, rust, clouds; pixel art with dithering or painted), compose `Field`s and paint them with `paint_field`: read [procedural fields](references/procedural-fields.md) before writing noise in a recipe. For painted (non pixel art) textures and fast per-texel callbacks, read the matching sections of the painter API reference. For ink lines, outlines, trims and curves (one style set for both render modes), compose `line`/`curve`/`bezier`/`arc` paths with `stroke(...)` and paint them with `paint_strokes`: read [lineart](references/lineart.md). Images produced outside the repository (2D asset forge, another tool or person) are requested only when the user explicitly asks: read [art requests](references/art-requests.md).

A project's visual tokens (palette, grains and motifs of its stamps, brushes, print patterns, line styles, paint layers, material looks) live in `projects/<p>/theme.py`, explained in `STYLE.md`; recipes take them with `recipe_paths(__file__).theme()`. Brush strokes, prints and stamped lines share one stamp engine: read [themes, marks and looks](references/theme.md) before painting materials in layers or writing a brush in a recipe; check and draw the tokens with `py -3.12 -m Tools.forge theme PROJECT [--sheet OUT.png]`.

`painter.element(name)` rejects unknown names. Noise uses a fixed seed by default. Keep `edge_dilation <= island_padding` to avoid bleeding. Register source texture links through the painter/export command; unsigned PNGs are valid when dimensions and UV data are compatible.

Register variants with `Tools.forge variant PROJECT angry --asset ID`, optionally choosing `--output` under assets or a variant-specific `--recipe`. Painting a nondefault variant leaves the active BBModel texture unchanged; `--set-active` is explicit. Read [variant and product contracts](../../../docs/exports.md) before expression work. Final GLB/PNG delivery uses `forge-3d-export`.
