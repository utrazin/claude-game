# @core - Shared Utilities

> Auto-generated public API reference. Do not edit directly; re-run `npm run docs:api`.

Asset contract (`defineAsset`, `createCanvas`), deterministic random, noise, color helpers, theme definition, sheet packing and the Bayer dithering matrix. Pixel rendering lives in `@core/pixel`.

## Table of Contents

- [Functions & Operations](#functions--operations)
  - [`defineAsset`](#defineasset)
  - [`createCanvas`](#createcanvas)
  - [`createRng`](#createrng)
  - [`createNoise2D`](#createnoise2d)
  - [`createNoise3D`](#createnoise3d)
  - [`fbm2D`](#fbm2d)
  - [`mapRange`](#maprange)
  - [`clamp`](#clamp)
  - [`BAYER_4X4`](#bayer_4x4)
  - [`packGrid`](#packgrid)
  - [`packCompact`](#packcompact)
  - [`parseColor`](#parsecolor)
  - [`alpha`](#alpha)
  - [`lerpColor`](#lerpcolor)
  - [`defineTheme`](#definetheme)
- [Types & Interfaces](#types--interfaces)
  - [`AssetFormat`](#assetformat)
  - [`AssetRenderContext`](#assetrendercontext)
  - [`Drawable`](#drawable)
  - [`AntialiasingMode`](#antialiasingmode)
  - [`FullRenderContext`](#fullrendercontext)
  - [`AssetDefinitionInput`](#assetdefinitioninput)
  - [`AssetDefinition`](#assetdefinition)
  - [`CanvasOptions`](#canvasoptions)
  - [`Rng`](#rng)
  - [`NoiseFunction2D`](#noisefunction2d)
  - [`NoiseFunction3D`](#noisefunction3d)
  - [`FbmOptions`](#fbmoptions)
  - [`RectItem`](#rectitem)
  - [`PlacedRect`](#placedrect)
  - [`PackResult`](#packresult)
  - [`GridPackOptions`](#gridpackoptions)
  - [`CompactPackOptions`](#compactpackoptions)
  - [`RGBA`](#rgba)
  - [`ThemeDefinition`](#themedefinition)

---

## Functions & Operations

### `defineAsset`

Declares an asset for rendering and export.
Applies convenient defaults for format, transparency, and scaling.

```ts
function defineAsset(definition: AssetDefinitionInput): AssetDefinition
```

---

### `createCanvas`

Convenient DOM helper: creates and configures an HTML5 Canvas inside root.
Accepts either explicit dimensions (width, height, options?)
or an AssetRenderContext object (context, options?).

Automatically applies backing store scaling (canvas.width = width * scale)
and adjusts ctx.scale(scale, scale) so vector paths rasterize at true physical density.

```ts
function createCanvas(root: HTMLElement, context: AssetRenderContext, options?: CanvasOptions | undefined): { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D; }
function createCanvas(root: HTMLElement, width: number, height: number, options?: CanvasOptions | undefined): { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D; }
```

---

### `createRng`

Creates a deterministic PRNG using Mulberry32 algorithm.
Accepts a number seed or string (e.g. asset name or hash).

```ts
function createRng(seed?: string | number): Rng
```

---

### `createNoise2D`

Creates a 2D simplex noise function with optional seed.
Returns values roughly in range [-1, 1].

```ts
function createNoise2D(seed?: string | number | undefined): NoiseFunction2D
```

---

### `createNoise3D`

Creates a 3D simplex noise function with optional seed.
Returns values roughly in range [-1, 1].

```ts
function createNoise3D(seed?: string | number | undefined): NoiseFunction3D
```

---

### `fbm2D`

Evaluates Fractal Brownian Motion (fBm) in 2D.
Combines multiple octaves of noise for realistic natural textures (stone, clouds, wood, terrain).
Returns normalized value in roughly [0, 1].

```ts
function fbm2D(noise: NoiseFunction2D, x: number, y: number, options?: FbmOptions): number
```

---

### `mapRange`

Linear value remapping helper: maps val from [inMin, inMax] to [outMin, outMax]

```ts
function mapRange(val: number, inMin: number, inMax: number, outMin: number, outMax: number): number
```

---

### `clamp`

Clamps a number between min and max

```ts
function clamp(val: number, min: number, max: number): number
```

---

### `BAYER_4X4`

The 4x4 Bayer threshold matrix, normalized to (0, 1), used for ordered dithering.

```ts
const BAYER_4X4: number[][]
```

---

### `packGrid`

Grid Packing:
1. Takes the max width and max height among all items to define uniform cell size.
2. Determines optimal rows and columns by increasing rows first, then columns.
3. Centers each item inside its cell.
4. Emergent resolution based on item count and spacing.

```ts
function packGrid<T extends RectItem>(items: T[], options?: GridPackOptions): PackResult<T>
```

---

### `packCompact`

Compact Packing (Growing 2D Bin Packing):
Packs rectangles as tightly as possible without overlap.
Emergent resolution expanding horizontally or vertically to maintain a balanced aspect ratio.

```ts
function packCompact<T extends RectItem>(items: T[], options?: CompactPackOptions): PackResult<T>
```

---

### `parseColor`

Parses hex (#rgb, #rrggbb, #rrggbbaa) or rgb/rgba strings into { r, g, b, a }.

```ts
function parseColor(color: string): RGBA
```

---

### `alpha`

Derives an RGBA color string with the specified opacity (0.0 to 1.0).

```ts
function alpha(color: string, opacity: number): string
```

---

### `lerpColor`

Linearly interpolates between two colors (hex or rgb/rgba).
`t` is clamped between 0 and 1.

```ts
function lerpColor(colorA: string, colorB: string, t: number): string
```

---

### `defineTheme`

Declares a project-level design system / theme token object.
Preserves strict literal types for palette keys and stroke presets.

```ts
function defineTheme<T extends ThemeDefinition>(theme: T): T
```

---

## Types & Interfaces

### `AssetFormat`

Output file format of an exported asset.

```ts
type AssetFormat = "png" | "jpeg"
```

### `AssetRenderContext`

Context passed to an asset's `render` function: its size, scale, format and frame.

```ts
interface AssetRenderContext {
  width: number;
  height: number;
  scale: number;
  format: AssetFormat;
  project: string | undefined;
  sourcePath: string | undefined;
  preview: boolean | undefined;
  resolveResource: ((relPath: string) => string) | undefined;
  frameIndex: number | undefined;
  frameCount: number | undefined;
}
```

### `Drawable`

Standard contract for objects capable of rendering to Canvas2D (Shapes, Polygons, Paths, Groups).

```ts
interface Drawable {
  draw: ((ctx: CanvasRenderingContext2D, style?: any) => void) | undefined;
  fill: ((ctx: CanvasRenderingContext2D, fillStyle?: any) => void) | undefined;
  stroke: ((ctx: CanvasRenderingContext2D, strokeStyle?: any) => void) | undefined;
}
```

### `AntialiasingMode`

Edge mode of an asset: 'native' keeps smooth edges, 'none' makes them hard, 'dither' uses an ordered Bayer pattern.

```ts
type AntialiasingMode = "native" | "none" | "dither"
```

### `FullRenderContext`

Context passed to `render`: the canvas, its 2D context and the render context fields.

```ts
interface FullRenderContext {
  root: HTMLElement;
  canvas: HTMLCanvasElement;
  ctx: CanvasRenderingContext2D;
  width: number;
  height: number;
  scale: number;
  format: AssetFormat;
  project: string | undefined;
  sourcePath: string | undefined;
  preview: boolean | undefined;
  resolveResource: ((relPath: string) => string) | undefined;
  frameIndex: number | undefined;
  frameCount: number | undefined;
}
```

### `AssetDefinitionInput`

Input of `defineAsset`: size, scale, format, frames, edge mode and the `render` function.

```ts
interface AssetDefinitionInput {
  width: number;
  height: number;
  frames: number | undefined;
  fps: number | undefined;
  animations: Record<string, number[]> | undefined;
  format: AssetFormat | undefined;
  quality: number | undefined;
  scale: number | undefined;
  background: string | undefined;
  name: string | undefined;
  id: string | undefined;
  antialiasing: AntialiasingMode | undefined;
  alphaThreshold: number | undefined;
  render: (context: FullRenderContext) => void | Promise<void>;
}
```

### `AssetDefinition`

The normalized asset definition returned by `defineAsset`.

```ts
interface AssetDefinition {
  format: AssetFormat;
  scale: number;
  background: string;
  quality: number;
  antialiasing: AntialiasingMode | undefined;
  alphaThreshold: number | undefined;
  render: (root: HTMLElement, context: AssetRenderContext) => void | Promise<void>;
  width: number;
  height: number;
  frames: number | undefined;
  fps: number | undefined;
  animations: Record<string, number[]> | undefined;
  name: string | undefined;
  id: string | undefined;
}
```

### `CanvasOptions`

Options for `createCanvas`: crisp edges, alpha and scale.

```ts
interface CanvasOptions {
  crisp: boolean | undefined;
  alpha: boolean | undefined;
  scale: number | undefined;
  antialiasing: AntialiasingMode | undefined;
  alphaThreshold: number | undefined;
}
```

### `Rng`

NoctAssetForge - Core Random Utilities

Deterministic, seedable pseudo-random number generator.
Allows procedural visual variations to remain repeatable between runs and exports.

```ts
interface Rng {
  random: () => number;
  float: (min: number, max: number) => number;
  int: (min: number, max: number) => number;
  boolean: (chance?: number | undefined) => boolean;
  pick: <T>(items: readonly T[]) => T;
  shuffle: <T>(items: readonly T[]) => T[];
  color: (palette?: readonly string[] | undefined) => string;
}
```

### `NoiseFunction2D`

Samples the noise field in two dimensions

Coordinates should be finite, bigger than -2^31 and smaller than 2^31.

```ts
type NoiseFunction2D = (x: number, y: number) => number
```

### `NoiseFunction3D`

Samples the noise field in three dimensions

Coordinates should be finite, bigger than -2^31 and smaller than 2^31.

```ts
type NoiseFunction3D = (x: number, y: number, z: number) => number
```

### `FbmOptions`

Options for `fbm2D`: octaves, persistence, lacunarity and scale.

```ts
interface FbmOptions {
  octaves: number | undefined;
  persistence: number | undefined;
  lacunarity: number | undefined;
  scale: number | undefined;
}
```

### `RectItem`

NoctAssetForge - Sheet & Atlas Packing Algorithms

Provides deterministic 2D layout algorithms for group exports:
1. packGrid: Uniform cell grid with emergent dimensions (increments row first, then col).
2. packCompact: 2D rectangle bin-packing for minimal area without overlaps.

```ts
interface RectItem {
  name: string | undefined;
  width: number;
  height: number;
}
```

### `PlacedRect`

A rectangle placed by a packing algorithm, with its position in the sheet.

```ts
interface PlacedRect<T extends RectItem = RectItem> {
  item: T;
  x: number;
  y: number;
  width: number;
  height: number;
  cellX: number | undefined;
  cellY: number | undefined;
  cellWidth: number | undefined;
  cellHeight: number | undefined;
}
```

### `PackResult`

Result of a packing algorithm: the sheet size and the placed rectangles.

```ts
interface PackResult<T extends RectItem = RectItem> {
  width: number;
  height: number;
  cols: number | undefined;
  rows: number | undefined;
  gap: number;
  items: PlacedRect<T>[];
}
```

### `GridPackOptions`

Options for `packGrid`: spacing between cells and an optional column count.

```ts
interface GridPackOptions {
  gap: number | undefined;
  cols: number | undefined;
  rows: number | undefined;
}
```

### `CompactPackOptions`

Options for `packCompact`: spacing between rectangles.

```ts
interface CompactPackOptions {
  gap: number | undefined;
}
```

### `RGBA`

Color Utilities for NoctAssetForge

Deterministic color manipulation (opacity/alpha, lightening, darkening, interpolation)
allowing coding agents to derive tonal variations and transparent states from _theme tokens
without violating the "No Hardcoded Styling" rule.

```ts
interface RGBA {
  r: number;
  g: number;
  b: number;
  a: number;
}
```

### `ThemeDefinition`

Shape of a project theme passed to `defineTheme`: palette, ramps, strokes and shape styles.

```ts
interface ThemeDefinition {
  palette: Record<string, string> | undefined;
  ramps: Record<string, Record<string, string>> | undefined;
  strokes: Record<string, StrokeStyle<{}> | StrokeOptions> | undefined;
  shapes: Record<string, ShapeStyle | Record<string, any>> | undefined;
}
```

