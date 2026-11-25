# Pixel Art Engine (`@core/pixel`, `PixelCanvas`)

**Purpose.** Draw on a discrete integer grid, so every pixel is placed on purpose. Use it when the asset is pixel art, not when a vector asset is merely small.

---

## 1. Choosing a route

| Route | Use when | Note |
| :--- | :--- | :--- |
| `PixelCanvas` | You place pixels on a grid, with lines, rects, circles, spans and text-free sprite matrices. | The default. It merges runs of same-colored pixels into a few fills, so exports stay fast. |
| `PixelCanvas.fromShape` | A vector silhouette must become pixels, with a hard edge. | Rasterizes a shape into the grid and applies `alphaThreshold` or `'dither'`. |

---

## 2. Edge mode

In `defineAsset`, set `antialiasing: 'none'` for hard alpha edges (every pixel becomes fully opaque or fully transparent). Use `'dither'` for ordered Bayer 4x4 dithering on the edges. Leave `'native'` only for assets that must stay smooth.

`scale` stays at `1`. The grid size and the output size are linked through `pixelSize` in the `PixelCanvas` constructor: the output is the grid times `pixelSize`. Choose the grid to match the target look (for example, a 64 by 64 grid at `pixelSize` 4 gives a 256 pixel image).

---

## 3. Coordinates and palette

- Use integers. `PixelCanvas` floors coordinates, so a fractional value silently moves a pixel. Compute positions with `Math.floor` or round them yourself so the result is explicit.
- Keep the palette small: 8 to 16 clearly different colors per asset. Smooth gradients in Canvas2D break the grid look, so use `ditherRect` for a transition instead.
- Colors come from the project's theme, like any other asset. Do not hardcode hex values in the asset file.

---

## 4. Methods

The methods of `PixelCanvas`, `PixelBuffer` and the atomic helpers, with their signatures, are in [`core/docs/api/pixel.md`](../../docs/api/pixel.md).

---

## 5. Recommendations

- **Sprites that are fully hand-placed**: `drawMatrix` makes the sprite readable in the source. Keep the matrix close to the palette roles it uses.
- **Shapes built from geometry** (panels, frames, rings): `rect`, `line` and `circle`, then `addOutline` for the silhouette edge.
- **Faceted silhouettes** (blades, capes, triangles): `fillPolygon`, then `addOutline`.
- **Gradients that must stay pixel-clean**: `ditherRect`, not a smooth fill.

---

## 6. Rules for agents

1. Coordinates are integers, and the output scale is `1`.
2. Use at most 8 to 16 semantic colors per asset.
3. Do not mix a smooth vector gradient into a pixel asset.
4. Commit to the canvas once, with `render` or `buffer.commit`, not once per primitive.
