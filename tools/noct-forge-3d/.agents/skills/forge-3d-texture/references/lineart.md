# Lineart: strokes on 3D surfaces

Ink lines for pixel art and for smooth painting with one API. Full signatures: [generated TexturePainter reference](../../../../docs/api/texture-painter.md) (`ink.*` and `paint_strokes`).

## First: a continuous texel grid
Pixel-art lines need a texel grid that continues across faces. Pack the asset's UVs as charts:

```bash
py -3.12 -m Tools.forge uv PROJECT --asset ID --layout charts --no-require-integer-uvs
```

`charts` unfolds neighbouring mesh faces together with their exact sizes (one texel is `1 / uv_scale` everywhere, a shared edge is the same UV segment on both faces), seams only at hard folds (> 50 degrees) and where the up direction would turn more than 24 degrees (an unrolled cone fans out), and turns each chart so the model's up is up in the texture. The option is remembered like the other UV options. With the default `faces` layout every face is its own island with its own grid: strokes still work, but break at every face edge.

## Paths
```python
from Tools.TexturePainter.ink import line, curve, bezier, arc, vertices, boundary, stroke, style
```
- From the geometry (preferred where it exists, nothing to guess): `boundary(element, group, other)` runs along the mesh edges between faces of two groups (`model_as_code_group`, e.g. a shell's `outer`/`edge`/`hem`; `other=None`: any other group or an open edge), chained into polylines. `vertices(element, names, closed=False)` passes through named mesh vertices (e.g. the hem row `c0o0..c0o6` of a `shell_draft`).
- Free curves, in model units: `line(points, closed=False)`, `curve(points, tension=0.0, closed=False)` (spline through the points; 0 = Catmull-Rom, 1 = straight), `bezier(p0, c1, c2, p1)` (3 points = quadratic), `arc(center, rx, ry=None, start=0, end=360)` (degrees, 0 = +x). Points `(x, y)` are projected along the stroke's `side`; `(x, y, z)` lie on the surface.

## Declare the line styles once
In a project with a theme, line styles are theme tokens (`theme.line("thick")`, [themes](theme.md)).
```python
thick = style(width=2, color=INK)                                   # most details
fine = thick.but(width=1)                                           # small details
trim = thick.but(color=GOLD, outline=INK_CLOTH)                     # derived styles keep the weight
painter.paint_strokes([
    trim(boundary("cloak", "outer", "edge"), on="cloak", groups="outer", align="inside"),
    thick(curve([(-2, 24), (0, 23), (2, 24)]), on="head", depth=(1.5, 1e3)),
    fine(line(nose), on="head"),
])
```
`style(**options)` accepts any `stroke` option except the path (a wrong name or value fails at declaration); a call can override (`thick(path, width=3)`). Keep the styles and the strokes in one module (for example `lines.py` next to the recipes) so every texture variant imports the same lines.

`paint_strokes` exists on the painter, elements, selections and `painter.layer(...)`. Strokes are drawn in list order, the outline of a stroke first. It returns an `InkReport` (texels per stroke); a stroke that writes nothing warns (`report.require_nonempty()` makes it an error).

## Pixel art (render mode `pixel`, the default)
Each stroke is rasterized on the texel grid of each chart:
1. the path is sampled every quarter texel and each sample lands on the texel that contains it (projected paths: on the front-most surface; the position is continuous on the chart grid and floored, so a straight line stays digital-straight even on faces seen at an angle);
2. the texels form an ordered pixel chain per chart, gaps closed with Bresenham;
3. L-shaped corner pixels are removed (pixel-perfect line);
4. the chain is thickened to exactly `width` whole texels across the line whatever its slope;
5. `outline` is a border of `outline_width` texels grown across texel edges (4-neighbourhood), so a staircase keeps a clean one-texel border.

Writes stay on texels of the same chart that the stroke's filters accept, alpha 0 or 1. `clean=False` (call level) replaces this with a plain `distance <= width / 2` mask.

### Shapes: `fill`
`stroke(line(points, closed=True), color=INK, fill=PINK)` paints a closed shape: the fill is drawn first on the texels inside the shape, minus the line, sealed so nothing peeks out of a cleaned pixel corner (this also works when the shape crosses a chart seam); then the outline and the line. Shape and outline always match, so do not paint the same shape again in the base recipe. `fill` may be a colour function like `color`.

## Smooth (render mode `smooth`)
The same strokes, anti-aliased, when the asset is smooth ([render modes](render-modes.md)); nothing changes in the recipe. Every texel is split into 4 x 4 subsamples over a one-texel box and each subsample is tested exactly like a pixel: inside the line (with `align`), the outline or the fill, and on a face the stroke may paint, judged by the face under the subsample, so edges along groups, elements and depth windows are smooth too. A layer's alpha is the share of subsamples where it is on top: a one-texel edge, no blur, and a fill meeting its line inside a texel adds up to full cover. Colour functions (`fill=iris`) are averaged over the subsamples where they change, so rings and bands inside a shape are smooth. Mirrored strokes are drawn once and copied texel by texel, as in pixel art.

`soft=` (on a stroke or `paint_strokes`) overrides the anti-aliasing box in texels: `soft=2` is a softer edge, and a stroke with `soft > 0` is smooth even on a pixel asset. `soft=0` on a smooth asset draws that stroke as pixel art.

`feather=w` (texels, smooth only) eases the line's and the outline's edge over `w` texels centred on it: a soft,
smoky edge at any density (a feather wider than the line also softens its core). Pixel art ignores it with a
warning.

## Chalk and stamped lines: the same tokens as the painting
`stroke(path, tip=Tip, brush=Brush)` shapes a line with the painting's tokens ([themes, marks and looks](theme.md)).
With a grain tip in smooth mode it stays the exact line above (same anti-aliasing, fill and outline as usual): its
width follows the brush profile along the whole path (`taper` to points within `taper_length` of the ends, a
smooth `swell`, `size`) and the tip's grain, box-projected on the surface like the texture's, breaks the outer
`falloff` of the half width (`density`): a chalk edge as crisp as the painting. With an image motif, or in pixel
art, the line is stamps along the path (the stamp engine; the grain anchored along the path; a 2D path lifted onto
the surface first). Stamped
lines take one colour; a `fill` and an `outline` are drawn under them as plain strokes (the outline band, or the
fill colour, under the line). `taper` with `taper_length` gives pointed ends, `swell` a smooth width variation
along the whole line (a 2D line lifted onto several UV charts keeps one profile). `seed` varies them. Declare them in the project theme like any
line style: `style(width=3, color=INK, tip=CHALK)`.

## Where a stroke lands
- `on=` element name prefixes, `groups=` face groups.
- 2D paths: texels facing `side` (`front`, `back`, `east`, `west`, `top`, `bottom`) by at least `normal_min` (0.15), inside the optional `depth=(lo, hi)` window along that direction. The front-most surface wins, so a line never shows through to a surface behind; use `on=`/`depth=` to choose a surface that is not the front-most.
- `align="inside"`: with `groups`/`on` keeping one side of a boundary, the whole width sits on that side (a trim along an opening, an outline along a hem).
- `wrap=True` (2D paths): a projected line only paints texels that face the projection (`normal_min`), so across a flared collar, a hem or a cone it skips the grazing, underside and back-facing faces and looks broken from other angles. With `wrap` the path is lifted onto every surface layer under it (inside `on`/`groups`/`depth`; each chart is one continuous surface; edge-on texels are skipped) and painted like a surface path: everything within the stroke's width of the lifted path, whichever way it faces. Use it for lines that cross sloped or folded surfaces. With `fill`, the shape is the projected polygon: every texel under it, on every surface layer inside `on`/`groups`/`depth`, is inside (the outline is the lifted line); the fill is drawn once, before the outline and the line.
- `seam="fill"|"none"` (pixel art): each chart draws its own pixel chain, so a thick line is cut at a chart edge and thins out there. `fill` completes it: texels of the neighbouring chart within the line (and outline) width of the path that touch a drawn texel across the seam are added; chains inside a chart do not change. Default `fill` for surface paths (`wrap`, `vertices`, `boundary`, `(x, y, z)` points) and `none` for projected 2D lines, so existing pixel art is untouched.
- `mirror="x"|"y"|"z"` (free paths) also draws the reflection across that model axis.
- `side_offset=` (texels, like `width`) draws the line parallel to its path, that far to one side: toward the side `on`/`groups` allow when only one side of the path is allowed (inside a boundary), else to the left (mirrored copies to the right). Lines side by side along one path (a gold trim edged by ink lines) are separate strokes with offsets, so each is a real line in its own style.
- `offset=` (tuple, or `element_name -> tuple`) shifts texel positions and surface paths into the recipe's frame (for example `lambda name: (0, 0 if name.startswith(LOWER) else -LEG_LIFT, 0)`).
- Units: `width` and `outline_width` are texels at the render mode's `reference` density (pixel art: the asset's own texels; the smooth twin of a pixel asset: the pixel asset's texels, so `width=2` has the same size on the model in both); `soft` is texels.

## Limits worth knowing
- A chart seam cuts the grid, so a pixel line crossing one restarts its staircase there (one texel kink at most); `seam="fill"` keeps its width across the seam. Hard folds and the side of a cone or sphere are where seams fall; the front of a part is grown first so it stays one chart.
- `mirror="x"` is exact: the +x half is drawn and every texel is copied onto its mirror image (charts are exact reflections). Strokes without `mirror` (a lopsided mouth, scars) stay as drawn.
- Faces shared with `share_uv` are painted through their owner; `share_uv` is not available with `charts`.
- Not implemented: dashes, gradients along a stroke, automatic edge lines (tapering: a stamped line's `brush`).
