# Procedural Textures (`Hatch`, `Stipple`, `Grit`, `StampScatter`)

**Purpose.** Add engraving, grain, porosity and wear to flat surfaces. Every texture clips to its host shape, so the texture never leaves the silhouette.

**API reference:** [`core/docs/api/brush-textures.md`](../../docs/api/brush-textures.md). Option names, defaults and types are there, not here.

---

## 1. Choosing a texture

| Surface reads as | Texture | Why |
| :--- | :--- | :--- |
| Engraving, metal hatching, shading by lines | `Hatch` | Line direction carries form. Crossed hatching adds a second tone. |
| Stone, parchment, porous or granular material | `Stipple` | Dot density controls tone without a directional bias. |
| Dirt, scratches, impact marks | `Grit` | Irregular spots and linear scratches read as wear. |
| Many repeated small objects (leaves, pebbles, stars) | `StampScatter` with a stamp asset | Places the stamp many times with per-copy variation. |

**Recommendation.** Use one texture family per surface. A panel with hatching, stipple and grit at once usually reads as noise. Pick the one the material needs and use it at a low density.

---

## 2. Attached or standalone

- **Attached** (`texture` in `shape.draw`): the texture is part of the shape's style and is clipped to the silhouette. Use it for almost every case.
- **Standalone** (`texture.render(ctx, target)`): draws over any shape or bounding box. Use it when the texture must be drawn at a different time than the fill, or over a group.
- **Spot** (`texture.spot(ctx, center, radius)`): a local cluster around a point, such as occlusion in a corner or a focal wear mark. Keep the radius small compared with the shape, or the cluster looks like a second texture.

---

## 3. Density and seed

- Density controls how much the texture reads. Start with a low value and increase it only when the surface looks empty at export size.
- Set `seed` when the texture must be identical across exports, for example in a sprite sheet where frames must match. Without a seed, each render can differ.
- Texture scale is in pixels, so a texture tuned for a 128 px asset looks too coarse at 32 px. Tune textures at the asset's final export size.

---

## 4. Order of operations

Textures run after the base fill and before the `inside` callback (see [guide 03, section 3](03-styles-and-themes.md#3-drawing-order)).

If a decoration inside `inside` (a gem, a plate, a cutout) must be worn too, apply the wear inside the `inside` callback, after the decoration. A texture passed to `draw` is painted underneath it.

---

## 5. Quick decision table

| Situation | Recommended | Avoid | Reason |
| :--- | :--- | :--- | :--- |
| Shading on metal | `Hatch` with a spacing set for the export size | Stipple to fake lines | Hatching keeps direction, which reads as metal. |
| Stone surface | `Stipple` with a gradient toward the shadow side | A uniform stipple across the whole shape | Uniform dots read as noise, not light. |
| Wear on a blade | `Grit` with scratches, applied inside `inside` if the blade has details | Scratches drawn as paths | Clipped to the blade, and follows its geometry. |
| Repeated natural objects | `StampScatter` with a stamp | Placing each object by hand | Per-copy variation and clipping come for free. |
