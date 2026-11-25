# @core/brush - Procedural Textures & Stamps

> Auto-generated public API reference. Do not edit directly; re-run `npm run docs:api`.

Hole-aware procedural fills (Hatch, Stipple, Grit), cacheable raster/vector stamp tips (StampAsset) and procedural stamp scattering (StampScatter).

## Table of Contents

- [Classes & Constructors](#classes--constructors)
  - [`Hatch`](#hatch)
  - [`Stipple`](#stipple)
  - [`Grit`](#grit)
  - [`StampScatter`](#stampscatter)
  - [`BaseTexture`](#basetexture)
  - [`StampAsset`](#stampasset)
- [Functions & Operations](#functions--operations)
  - [`loadStamp`](#loadstamp)
- [Types & Interfaces](#types--interfaces)
  - [`StampAssetOptions`](#stampassetoptions)
  - [`Texture`](#texture)
  - [`StampStrokeConfig`](#stampstrokeconfig)
  - [`HatchOptions`](#hatchoptions)
  - [`HatchBounds`](#hatchbounds)
  - [`StippleOptions`](#stippleoptions)
  - [`StippleGradient`](#stipplegradient)
  - [`GritOptions`](#gritoptions)
  - [`StampScatterOptions`](#stampscatteroptions)

---

## Classes & Constructors

### `Hatch`

Hatching texture: parallel strokes clipped to a shape. Draw it with `render` or `spot`.

**Constructor:**
```ts
new Hatch(attrs?: HatchOptions): Hatch
```

**Properties:**

- `attrs: HatchOptions`
- `stroke: StrokeStyle<{}>`

**Instance Methods:**

- `.render(ctx: CanvasRenderingContext2D, target: Shape | HatchBounds, overrides?: Partial<HatchOptions>): void`
  Renders the hatching texture inside a Shape or rectangular bounding box. Strokes terminate NATURALLY with organic calligraphic tapered tips.
- `.spot(ctx: CanvasRenderingContext2D, center: Point, radius: number | { rx: number; ry: number; }, overrides?: Partial<HatchOptions>): void`
  Renders a targeted / localized focal hatch cluster around a specific center point. Strokes terminate NATURALLY with organic calligraphic tapered tips (NO dry geometric clipping!).

---

### `Stipple`

Stippling texture: random dots with an optional density gradient. Draw it with `render` or `spot`.

**Constructor:**
```ts
new Stipple(attrs?: StippleOptions): Stipple
```

**Properties:**

- `attrs: StippleOptions`

**Instance Methods:**

- `.render(ctx: CanvasRenderingContext2D, target: Shape | Bounds, overrides?: Partial<StippleOptions>): void`
  Renders the stipple texture inside a Shape or rectangular bounding box.
- `.spot(ctx: CanvasRenderingContext2D, center: Point, radius: number | { rx: number; ry: number; }, overrides?: Partial<StippleOptions>): void`
  Renders a targeted / localized stipple cluster around a specific center point.

---

### `Grit`

Grit texture: specks and scratches for wear. Draw it with `render` or `spot`.

**Constructor:**
```ts
new Grit(attrs?: GritOptions): Grit
```

**Properties:**

- `attrs: GritOptions`

**Instance Methods:**

- `.render(ctx: CanvasRenderingContext2D, target: Shape | Bounds, overrides?: Partial<GritOptions>): void`
  Renders grit flecks and scratches inside a Shape or rectangular bounding box.
- `.spot(ctx: CanvasRenderingContext2D, center: Point, radius: number | { rx: number; ry: number; }, overrides?: Partial<GritOptions>): void`
  Renders a targeted / localized grit cluster around a specific center point.

---

### `StampScatter`

Texture that scatters a stamp asset over a shape, with random scale and rotation.

**Constructor:**
```ts
new StampScatter(attrs: StampScatterOptions): StampScatter
```

**Properties:**

- `attrs: StampScatterOptions`

**Instance Methods:**

- `.render(ctx: CanvasRenderingContext2D, target: Shape | Bounds, overrides?: Partial<StampScatterOptions>): void`

---

### `BaseTexture`

Base class for custom textures. Extend it and implement `render`.

**Constructor:**
```ts
new BaseTexture<O = Record<string, any>>(attrs?: O): BaseTexture<O>
```

**Properties:**

- `attrs: O`

**Instance Methods:**

- `.render(ctx: CanvasRenderingContext2D, target: Bounds | ShapeLike, overrides?: Partial<O> | undefined): void`
  Renders the procedural texture inside a Shape or rectangular bounding box.

---

### `StampAsset`

A raster stamp (an image or a canvas) used as a brush tip or as a scatter texture.

**Constructor:**
```ts
new StampAsset(options: StampAssetOptions): StampAsset
```

**Properties:**

- `canvas: HTMLCanvasElement | OffscreenCanvas | HTMLImageElement | ImageBitmap`
- `size: number`
- `width: number`
- `height: number`

---

## Functions & Operations

### `loadStamp`

Normalizes and loads a raster stamp from a path or URL.
Automatically caches instances so duplicate calls reuse the same loaded image.

Supports:
- Global stamps: `@stamps/artistic/oil_bristle.png` or `stamps/artistic/oil_bristle.png` -> `/stamps/artistic/oil_bristle.png`
- Local/absolute URLs: `/projects/.../resources/stamps/my_stamp.png`

```ts
function loadStamp(pathOrUrl: string, baseSize?: number | undefined): Promise<StampAsset>
```

---

## Types & Interfaces

### `StampAssetOptions`

NoctBrush - StampAsset

Unifies raster stamp / dab textures for both strokes (lines) and fills (scatter textures).
Caches image data for high performance context.drawImage calls.

```ts
interface StampAssetOptions {
  source: HTMLCanvasElement | OffscreenCanvas | HTMLImageElement | ImageBitmap | undefined;
  draw: ((ctx: CanvasRenderingContext2D, size: number) => void) | undefined;
  baseSize: number | undefined;
}
```

### `Texture`

A texture attached to a ShapeStyle: any object with a `render` method.

```ts
interface Texture<TOptions = unknown> {
  render(ctx: CanvasRenderingContext2D, target: Bounds | ShapeLike, overrides?: Partial<TOptions> | undefined): void;
}
```

### `StampStrokeConfig`

A stamp-based stroke: stamp asset, spacing, scatter and angle dynamics.

```ts
interface StampStrokeConfig {
  asset: StampAsset;
  spacing: number | undefined;
  scatter: number | undefined;
  angleDynamics: "none" | "tangent" | "random" | undefined;
  sizeNoise: number | undefined;
}
```

### `HatchOptions`

Options for `Hatch`: spacing, angle, cross-hatching and jitter.

```ts
interface HatchOptions {
  stroke: StrokeStyle<{}> | StrokeOptions | undefined;
  angle: number | undefined;
  spacing: number | undefined;
  cross: boolean | undefined;
  crossAngle: number | undefined;
  lengthVariation: number | undefined;
  jitter: number | undefined;
  seed: number | undefined;
  hardClip: boolean | undefined;
  width: number | undefined;
  color: string | undefined;
}
```

### `HatchBounds`

Rectangle bounds for a Hatch texture.

```ts
interface HatchBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}
```

### `StippleOptions`

Options for `Stipple`: dot count, radius and gradient.

```ts
interface StippleOptions {
  count: number | undefined;
  density: number | undefined;
  minRadius: number | undefined;
  maxRadius: number | undefined;
  radius: number | undefined;
  color: string | undefined;
  gradient: StippleGradient | undefined;
  seed: number | undefined;
}
```

### `StippleGradient`

Direction of the stipple density gradient.

```ts
type StippleGradient = "none" | "left-to-right" | "right-to-left" | "top-to-bottom" | "bottom-to-top" | "radial-in" | "radial-out"
```

### `GritOptions`

Options for `Grit`: count, scratches, size and color.

```ts
interface GritOptions {
  count: number | undefined;
  scratches: number | undefined;
  scratchCount: number | undefined;
  size: number | undefined;
  color: string | undefined;
  seed: number | undefined;
}
```

### `StampScatterOptions`

Options for `StampScatter`: stamp asset, count, scale and rotation.

```ts
interface StampScatterOptions {
  asset: StampAsset;
  count: number | undefined;
  density: number | undefined;
  minScale: number | undefined;
  maxScale: number | undefined;
  scale: number | undefined;
  alpha: number | undefined;
  alphaNoise: number | undefined;
  randomRotation: boolean | undefined;
  angle: number | undefined;
  seed: number | undefined;
}
```

