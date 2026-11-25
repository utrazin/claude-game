# @core/pixel - Pixel Art Engine

> Auto-generated public API reference. Do not edit directly; re-run `npm run docs:api`.

Discrete integer-grid drawing through `PixelCanvas`: lines, rectangles, circles, polygon fills, outlines, character-matrix sprites and Bayer dithering.

## Table of Contents

- [Classes & Constructors](#classes--constructors)
  - [`PixelCanvas`](#pixelcanvas)
- [Types & Interfaces](#types--interfaces)
  - [`FromShapeOptions`](#fromshapeoptions)

---

## Classes & Constructors

### `PixelCanvas`

High-level, discrete Pixel Art Canvas for programmatic sprite and asset generation.
Encapsulates an integer grid, scaling, ASCII matrices, lines, circles, and Bayer dithering.
Batches adjacent same-color pixels during render() for maximum performance.

**Constructor:**
```ts
new PixelCanvas(width: number, height: number, pixelSize?: number): PixelCanvas
```

**Properties:**

- `width: number`
- `height: number`
- `pixelSize: number`

**Static Factories:**

- `PixelCanvas.fromShape(shape: Drawable, width: number, height: number, options?: FromShapeOptions): PixelCanvas`
  Rasterizes any vector Shape or Path from

**Instance Methods:**

- `.set(x: number, y: number, color: string | null): this`
  Sets a single pixel at grid coordinates (x, y).
- `.get(x: number, y: number): string | null`
  Gets the color at grid coordinates (x, y).
- `.clear(color?: string | null): this`
  Clears the entire grid or fills it with a background color.
- `.hSpan(y: number, x0: number, x1: number, color: string): this`
  Draws a horizontal pixel span on the grid.
- `.vSpan(x: number, y0: number, y1: number, color: string): this`
  Draws a vertical pixel span on the grid.
- `.rect(x: number, y: number, w: number, h: number, color: string, filled?: boolean): this`
  Draws a filled or outlined rectangle.
- `.line(x0: number, y0: number, x1: number, y1: number, color: string): this`
  Draws a discrete line using Bresenham's algorithm.
- `.circle(xc: number, yc: number, radius: number, color: string, filled?: boolean): this`
  Draws a circle using the Midpoint (Bresenham) circle algorithm.
- `.drawMatrix(matrix: string[] | string[][], palette: Record<string, string>, ox?: number, oy?: number): this`
  Draws a character matrix / ASCII sprite directly onto the grid. Characters mapped to 'transparent', '.', ' ' or undefined are skipped.
- `.ditherRect(x: number, y: number, w: number, h: number, colorBase: string, colorDither: string, threshold?: number): this`
  Applies Bayer 4x4 ordered dithering across a rectangular region. Useful for authentic retro shading, lighting gradients, and texture ramps.
- `.fillPolygon(points: ([number, number] | { x: number; y: number; })[], color: string): this`
  Rasterizes a convex or arbitrary simple polygon using horizontal scanline conversion. Supports vertices as tuples [x, y] or point objects { x, y }.
- `.addOutline(outlineColor: string, includeDiagonals?: boolean): this`
  Adds an automatic boundary outline around all non-transparent pixels. Essential for classic retro fighting-game cel shading, character borders, and sprite isolation.
- `.render(ctx: CanvasRenderingContext2D, dx?: number, dy?: number): void`
  Renders the discrete pixel grid onto a Canvas 2D context. Batches adjacent same-color pixels into horizontal spans for maximum performance.

---

## Types & Interfaces

### `FromShapeOptions`

Options for `PixelCanvas.fromShape`: fill color, alpha threshold, dithering and target canvas.

```ts
interface FromShapeOptions {
  color: string | undefined;
  fill: string | undefined;
  pixelSize: number | undefined;
  alphaThreshold: number | undefined;
  antialiasing: "none" | "dither" | undefined;
  target: PixelCanvas | undefined;
}
```

