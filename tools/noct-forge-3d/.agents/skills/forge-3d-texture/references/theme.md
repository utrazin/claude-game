# Themes, marks and looks

A project's painting is described by **tokens** declared once in `projects/<p>/theme.py` and explained in words in
`projects/<p>/STYLE.md`. Recipes take tokens from the theme instead of writing colours, grains and sizes inline,
and derive variations with `with_` (marks) or `but` (line styles, looks). One engine paints every mark: brush
layers over a material, scattered or regular prints, single prints and stamped lines.

```bash
py -3.12 -m Tools.forge theme PROJECT                    # list and check the tokens
py -3.12 -m Tools.forge theme PROJECT --sheet sheet.png  # draw palette, tips, brushes and line styles
py -3.12 -m Tools.forge theme PROJECT --init             # write theme.py and STYLE.md templates (never overwrites)
```

## What belongs where

| Where | What |
|---|---|
| `theme.py` (project) | palette and ramps, tips (grains, motifs), brushes, patterns, line styles, the paint layers, material looks and their stacks, project helpers in `extras` |
| `STYLE.md` (project) | art direction in words; resolution, edge treatment, layer rules: what the tokens cannot say |
| the asset's scripts | which texel is which material (`classify`), where lines and prints go (paths, points, origins on this model), which style each variant uses |
| the core | the engine: surface view, material map, stamps, looks, layers, ink |

## Tokens (`Tools.TexturePainter.marks`)

| Token | Describes | Build |
|---|---|---|
| `Tip` | what one stamp leaves | `Tip.grain(speck, cluster, clump, scale)` (a tiling grain; `scale` model units per grain pixel), `Tip.solid()`, `Tip.image(png, colored=True)` (a printed motif; its alpha is the shape) |
| `Brush` | how a stroke of stamps moves | `radius`, `size` (multiplies any radius), `grain` (multiplies the tip's grain), `length` (stamps per stroke; (1, 1) = single prints), `spacing`, `turn`, `direction`, `spread`, `align`, `density`, `taper`, `size_jitter`, `jitter` (colour), `falloff`, `coverage` |
| `Pattern` | where strokes start | `Pattern.scatter(coverage=...` or `count=..., weight=Field)`, `Pattern.lattice(spacing, jitter=)`, `Pattern.at(points)` |
| `Direction` | which way strokes run | `around()`, `fall()`, `diagonal()`, `away(origin)`, `toward(origin)`, `fixed(v)` |
| line style | an ink line | `ink.style(width=, color=, ..., feather=, tip=, brush=)` |

Sizes are model units, so a token looks the same at any texture density.

## Painting marks

```python
from Tools.TexturePainter.marks import Pattern
theme = recipe_paths(__file__).theme()
fur = painter.material_map(classify).mask("fur")              # or a region: element.stamp(...)
painter.stamp(Pattern.scatter(coverage=0.6), tip=theme.tip("chalk"), brush=theme.brush("dab"),
              colors=[theme.color("ink")], where=fur, seed=3, opacity=0.4)
painter.stamp(Pattern.lattice(1.5, jitter=0.3), tip=theme.tip("star"), brush=theme.brush("print"),
              colors=["#ffd27a"], mirror="x")                  # regular prints, exactly symmetric
```

A stamp sits on the surface facing its normal; it paints texels inside its outline that face the same way, lie
near its plane and on the same surface layer (`occlusion=True`: a stamp on a cloak never reaches the robe under
it). Inside the outline the grain decides: ink where the grain is above `1 - density * pressure * falloff`
(`pressure`: 0..1 per texel). `edge="soft"` eases the grain threshold (anti-aliased specks); the default `hard`
keeps the grain crisp. `tip_colors` gives each stroke a colour gradient to its far end (fur roots to tips).

## Stamped and feathered lines

`stroke(path, tip=..., brush=...)` draws a line as stamps along the path with the same engine (the grain is
anchored along the path, so it shows); the stamp diameter is the line width. `feather=w` (smooth mode) eases a line's edge over
`w` texels. See [lineart](lineart.md).

## Looks in layers (`Tools.TexturePainter.looks`)

A texture is built on the theme's paint layers (`PaintLayer(name, blend, opacity)`, bottom first): the first is
opaque (each material's flat `base`, then its passes), the others transparent over it, each written to the
painter layer of its name (`painter.save(hide=("shading",))` leaves one out).

- `Look`: `base`, named colour lists (`colors`), named `tips` ("tip" is the default), `brush`, size classes
  (`sizes`: name -> (min, max) radius), the `stack` of `Pass`es, `strengths`, and per layer a `LayerStyle` (its
  own brush, tip and an `Overlay`: a flat colour eased in along the light, a shadow or light veil).
- `Pass`: colour list, where strokes start (`weight`) and how hard they press (`pressure`), as smooth steps of
  the material's shading (`field="value"` or `"lit"`), its `layer`, opacity, coverage, size class, tip, grain.
- `Region`: part of a material painted its own way (element prefixes `on`, face `groups`).
- `Style`: a look per material plus regions: one texture variant.

```python
materials = painter.material_map(classify)        # (names, material, value, fixed) per texel, cached
paint_looks(painter, style, materials, theme.layers)
with painter.layer("ink"):
    painter.paint_strokes(strokes)
```

`classify(view)` gets `painter.surface()` (per texel `position`, `normal`, `element`, `group`, `entries`) and
returns the material names, per texel the material index (-1: no material, keeps `fixed`), the shading value
(0 dark .. 1 lit, e.g. `Field.light(key, fill=...)`) and the fixed RGB. The map is cached in
`<project>/.cache/texture` until the model or the classify module changes.

## Theme template

```python
# projects/<p>/theme.py
from Tools.TexturePainter.ink import style
from Tools.TexturePainter.looks import PaintLayer
from Tools.TexturePainter.marks import Brush, Tip
from Tools.TexturePainter.theme import define_theme

CHALK = Tip.grain(speck=0.9, cluster=5.0, clump=0.55, scale=1 / 11)
THEME = define_theme(
    "my_project",
    palette={"ink": "#0e1222"},
    tips={"chalk": CHALK},
    brushes={"chalk": Brush(radius=(0.5, 0.9), length=(3, 7))},
    lines={"thick": style(width=2, color="#0e1222")},
    layers=(PaintLayer("texture"), PaintLayer("shading"), PaintLayer("lighting")),
)
```

`define_theme` checks every token (colours, types, looks against the layers) and fails listing every problem;
`theme.tip("x")` and the other lookups fail with the known names. Example: `projects/cloaked_cat/theme.py`.
