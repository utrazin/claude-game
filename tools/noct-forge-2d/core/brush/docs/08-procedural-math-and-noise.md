# Procedural Math and Noise (`@core`)

**Purpose.** Deterministic randomness, noise fields and numeric helpers. Use them so that variation between assets is reproducible across reloads and exports.

**Import.** Everything in this guide comes from `@core`.

---

## 1. Randomness

- Use `createRng(seed)` for every random choice. Never use `Math.random()` in asset code, because each run would produce a different image.
- Derive the seed from a stable name, such as the asset id or a variant label, so each variant keeps its look when other assets change.
- Use one generator per asset and draw from it in a fixed order. Reordering the draws changes every later value.

---

## 2. Noise and fractal noise

- `createNoise2D(seed)` returns a smooth field roughly in `[-1, 1]`. Sample it at scaled coordinates: the scale sets the feature size.
- `fbm2D` stacks several octaves of the same field. More octaves add detail and cost more to compute. Start with the defaults and add octaves only when the surface looks too smooth.
- For a closed loop, sample the noise on a circle in noise space, not on the angle itself. Sampling the angle directly produces a seam where the loop closes.

**Noise for organic contours.** Noise deforms an outline, but the outline itself is still built with the geometry API. See [guide 01, section 1](01-shapes-and-geometry.md#1-choosing-a-primitive) for choosing a base shape, and [guide 01, section 6](01-shapes-and-geometry.md#6-deformations) for displacement. Noise is not a substitute for building the contour from the geometry API.

---

## 3. Numeric helpers

- `clamp(value, min, max)` keeps a computed size within a range, for example a width that must stay readable.
- `mapRange(value, inMin, inMax, outMin, outMax)` converts a measured value into another scale, for example distance to opacity. It does not clamp, so pair it with `clamp` when the input can leave its range.

---

## 4. Dithering constants

`BAYER_4X4` is the ordered-dither threshold matrix used by the pixel engine. Its use is described in [guide 07](07-pixel-art-engine.md#2-edge-mode).

---

## 5. Recommendations

| Situation | Recommended | Avoid | Reason |
| :--- | :--- | :--- | :--- |
| Choosing a random variant | `createRng` seeded by a stable name | `Math.random()` | Same result on every export. |
| Surface variation (stone, cloud) | `fbm2D` with few octaves | One high-frequency noise | Layers of detail read as natural texture. |
| Organic outline | Noise displacement on a base shape | Clusters of circles | Continuous contour, no seams. |
| Value that must stay in range | `clamp` | Trusting the input | Keeps sizes and opacities valid. |
