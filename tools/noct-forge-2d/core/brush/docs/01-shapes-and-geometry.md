# Geometry and Shapes (`@core/brush`)

**Purpose.** Build closed, fillable silhouettes from parametric primitives, transforms, boolean operations and deformations. Everything here is vector geometry in memory until it is drawn.

**API reference:** [`core/docs/api/brush-geometry.md`](../../docs/api/brush-geometry.md). Signatures are not repeated here.

---

## 1. Choosing a primitive

| Need | Prefer | Why |
| :--- | :--- | :--- |
| Plates, panels, frames, buttons | `Polygon.rect` with `radius` or `bevel` | Corners are part of the constructor, so no later fillet is needed. |
| Gems, shields, arbitrary contours | `Polygon.fromPoints` followed by `roundCorners` | Free vertices stay editable, and fillets are uniform. |
| Regular symmetry (hex, octagon, star) | `Polygon.regular`, `Polygon.star` | Symmetry comes from the parameters, not hand-placed vertices. |
| Organic blobs (clouds, bushes) | `Polygon.lobes` or noise on a base shape | Avoids clusters of circles, which read as artificial. |

**Gotcha.** Primitives are centered on the origin by default. Set `cx` and `cy`, or call `moveTo(point, 'center')`, before composing with other geometry.

**Gotcha.** The `rotation` option turns points around the origin `(0, 0)`, not around the shape. A part built from free points, such as a stem or a horn, would leave the canvas. To turn a part in place, rotate it after it is built, with a pivot: `Polygon.stem(base, 40).rotate(180, base)`.

**Gotcha.** For `radius` on `Polygon.rect`, a value below `1` is a fraction of half the smaller side, and a value of `1` or more is in pixels. Use one convention per asset, and state it in the asset file.

---

## 2. Transforms are in place

`translate`, `rotate`, `scale` and `moveTo` change the receiver and return `this`. Call `clone()` before deriving a variant from a shape you still need.

Position all parts first (`attach`, `align`, `moveTo`) and draw last. Calling `draw` or `stroke` before the placement is final makes later fixes expensive.

Use `Group` to move composite parts together. `group.render(ctx)` draws each child with its own style.

---

## 3. Booleans return new shapes

`union`, `subtract`, `intersect`, `offset` and `roundCorners` return new instances and leave the inputs unchanged.

- Booleans are methods on `Shape`. Chain them (`a.union(b).subtract(c)`), and pass an array for a list (`a.union([b, c])`).
- Disjoint inputs stay as separate islands in `regions`.
- Subtracting a smaller shape from a larger one creates holes. Holes are filled with the even-odd rule.
- For lines, `unionLine` solidifies a path into the host and `cutLine` carves with it. Use them instead of converting by hand.

---

## 4. Corners and borders

- Round corners after a boolean, not before. The fillet then also smooths the concave corners the boolean created.
- For an inner frame or a raised plate, use `offset` with a negative distance (inset) or a positive one (outset). `offset` keeps the border width constant, while `scale` distorts rectangles.

---

## 5. Modeling operations

- `loft(a, b)` joins two profiles into a ruled surface. For three or more sections, pass an array; the sections act as rungs.
- `sweep(profile, path)` drags a cross-section along a path. Increase `steps` for large or sharp profiles.
- `morph(a, b, t)` interpolates between two shapes. Use it for in-betweens of similar silhouettes. Very different shapes produce unstable intermediate states.
- `extrude2D(shape, options)` returns a front face and side walls, which suits coins, tiles and buttons. The walls are separate geometry, so they can be styled separately.

---

## 6. Deformations

`displace`, `bend`, `taper`, `twist`, `warp` and `inflate` move existing vertices. A contour with few vertices cannot show fine displacement, so call `subdivide` first on coarse shapes.

Deformations take option objects. Check the signature in the API reference before calling them.

---

## 7. Placement and custom primitives

- `attach(subject, target, { from, at, offset })` attaches one part to another by anchor, for example a blade to a hilt.
- `align` and `distribute` work on several items at once. Use them instead of computing offsets by hand.
- `definePrimitive(name, generator)` registers a reusable parametric shape when the same silhouette is needed with different parameters.

---

## 8. Quick decision table

| Situation | Recommended | Avoid | Reason |
| :--- | :--- | :--- | :--- |
| Rectangle or plate corners | `Polygon.rect(w, h, { radius, bevel })` | `roundCorners` on a rect | The constructor is exact and cheaper. |
| Corners after a boolean | `.roundCorners(r)` | Recomputing vertices | Also smooths the concavities the boolean created. |
| Inner frame | `shape.offset(-d)` | `shape.scale(0.9)` | Constant border width. |
| Union of a dynamic list | `base.union(list)` | Manual reassignment loop | Same result, one call. |
| Part attached to another | `attach` | Manual `translate` by guessed numbers | The anchor relationship stays correct when sizes change. |
