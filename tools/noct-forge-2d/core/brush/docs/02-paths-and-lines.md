# Lines, Curves and Paths (`Path`, `PathBuilder`)

**Purpose.** Build open lines, curves and chained trajectories. A `Path` is rendered as a stroke, or converted into a filled ribbon or a closed shape when the line must be filled.

**API reference:** [`core/docs/api/brush-paths.md`](../../docs/api/brush-paths.md). Signatures are not repeated here.

---

## 1. Choosing a constructor

| Need | Prefer | Why |
| :--- | :--- | :--- |
| Straight segment | `Path.line` | Accepts `wobble` for hand-drawn edges. |
| Several known points, no tangent control | `Path.polyline` | Exact points, no smoothing. |
| Smooth path through known points | `Path.spline` | Catmull-Rom interpolation through every point. |
| One bulge between two endpoints | `Path.curve` with `bow` | `bow` is the sagitta. A positive value bulges to the right-hand side of the direction of travel (screen coordinates, y down). |
| Precise tangents at both ends | `Path.bezier` | Two control points define the start and end direction. |
| Circular arc | `Path.arc` | Center is a `Point`, not separate `cx` and `cy` arguments. Start and end angles are in degrees. |
| Oscillation (energy, water, branches) | `Path.wave` | Cycles and amplitude are explicit parameters. |
| Multi-segment outline mixing the above | `Path.builder()` | Each segment continues from the current point. |

**Gotcha.** `Path.arc` takes its center as a `Point`. `Polygon.circle` takes `cx` and `cy` in its options. Check which family you are calling.

---

## 2. Building an outline

Use `PathBuilder` for outlines that mix line, curve and arc segments. Do not join point arrays by hand. `Path.concat` is the right tool when the parts already exist as separate paths. It welds coinciding endpoints, and the result is closed only if the last path is closed.

Close the outline with `close(roundRadius?)`. Passing a radius rounds the seam between the last and first point too. Calling `roundCorners` later on an open path rounds only the corners it has.

---

## 3. Stroke or fill

- **Stroke** (`path.stroke(ctx, style)`): line art, gestures, outlines with a `StrokeStyle`. Use this when the line itself is the visual element.
- **Ribbon** (`path.toShape(width)` or `toRibbon`): a fillable band with a constant or varying width (a function of `t`). Use it when the line must be textured, clipped or booleaned with other shapes.
- **Closed shape** (`close()`): a fillable region bounded by the path. Use it for silhouettes drawn as a curve.

Converting to a shape before drawing lets textures and `inside` details clip to the shape. A plain stroke does not offer that.

---

## 4. Joins and caps

`StrokeStyle` joins control corners: `round` gives a soft tip, `miter` gives a sharp projected vertex (blades, crowns, gems), and `bevel` cuts the corner flat. `miter` can spike on very acute angles, so `miterLimit` is there to clamp it.

Ribbon caps (`cap`) apply only to open lines converted to shapes. Closed lines do not have caps.

---

## 5. Measuring along a path

`length`, `pointAt(t)`, `tangentAt(t)` and `normalAt(t)` use normalized arc length (`t` from 0 to 1). Use them to place anchors or attachments along a line, for example `shape.moveTo(path.pointAt(0.5))`.

---

## 6. Quick decision table

| Situation | Recommended | Avoid | Reason |
| :--- | :--- | :--- | :--- |
| Sharp corners on a polyline | `roundCorners(r)` | Smoothing by hand | Tangent arcs, correct at every vertex. |
| Line that must be filled or cut | `toShape` / `toRibbon` | Stroking and hoping to clip | Only shapes accept textures and clipping. |
| Closed silhouette from a curve | `close(radius)` | `close()` followed by manual rounding | Rounds the seam too. |
| Hand-drawn edge | `Path.line` with `wobble` | Random jitter in the points | Wobble is seeded and reproducible. |
