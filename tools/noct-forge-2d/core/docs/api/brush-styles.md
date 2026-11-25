# @core/brush - Styles, Brushes & Themes

> Auto-generated public API reference. Do not edit directly; re-run `npm run docs:api`.

Visual attributes, fill/stroke styles, cel-shading lights, extensible brush definitions (defineBrush), built-in renderers and color helpers.

## Table of Contents

- [Classes & Constructors](#classes--constructors)
  - [`StrokeStyle`](#strokestyle)
  - [`ShapeStyle`](#shapestyle)
- [Functions & Operations](#functions--operations)
  - [`defineBrush`](#definebrush)
  - [`listBrushes`](#listbrushes)
  - [`describeBrush`](#describebrush)
  - [`brushes`](#brushes)
  - [`alpha`](#alpha)
  - [`lerpColor`](#lerpcolor)
  - [`parseColor`](#parsecolor)
- [Types & Interfaces](#types--interfaces)
  - [`BrushFactory`](#brushfactory)
  - [`BrushDefinition`](#brushdefinition)
  - [`BrushDescription`](#brushdescription)
  - [`BrushLine`](#brushline)
  - [`BrushSegment`](#brushsegment)
  - [`BrushParams`](#brushparams)
  - [`BrushBase`](#brushbase)
  - [`BrushDraw`](#brushdraw)
  - [`BrushGeometry`](#brushgeometry)
  - [`DashedParams`](#dashedparams)
  - [`ParamSpec`](#paramspec)
  - [`ParamSpecs`](#paramspecs)
  - [`ParamDescription`](#paramdescription)
  - [`RGBA`](#rgba)
  - [`Paint`](#paint)
  - [`StrokeOptions`](#strokeoptions)
  - [`StrokeInput`](#strokeinput)
  - [`ShadowOptions`](#shadowoptions)
  - [`ShapeStyleOptions`](#shapestyleoptions)
  - [`CelShadeOptions`](#celshadeoptions)
  - [`BuiltinBrushName`](#builtinbrushname)
  - [`BrushName`](#brushname)
  - [`StrokeJoin`](#strokejoin)
  - [`StrokePosition`](#strokeposition)
  - [`GradientOptions`](#gradientoptions)

---

## Classes & Constructors

### `StrokeStyle`

A stroke: width, color, renderer and options. Immutable; derive variants with `.with`.

**Constructor:**
```ts
new StrokeStyle<P extends object = {}>(attrs?: StrokeOptions & P): StrokeStyle<P>
```

**Properties:**

- `attrs: Readonly<StrokeOptions & P>`
- `width: number | undefined`
- `color: string | undefined`
- `renderer: string | undefined`

**Instance Methods:**

- `.with<P2 extends object = P>(overrides: Partial<StrokeOptions & P & P2>): StrokeStyle<P & P2>`
  Derives a new StrokeStyle with specific attribute overrides (deep merges nested objects like double). Preserves and merges custom brush parameters.
- `.render(ctx: CanvasRenderingContext2D, points: Point[], closed?: boolean): void`
  Renders a polyline or closed loop onto the 2D context using this style. Dispatches dynamically to the registered brush corresponding to attrs.renderer.

---

### `ShapeStyle`

A style for shapes: fill, stroke, shadow, textures and an inner callback.

**Constructor:**
```ts
new ShapeStyle(attrs?: ShapeStyleOptions): ShapeStyle
```

**Properties:**

- `attrs: Readonly<ShapeStyleOptions>`
- `fill: Paint | undefined`
- `celShade: CelShadeOptions | undefined`
- `texture: Texture<unknown> | Texture<unknown>[] | undefined`
- `stroke: StrokeStyle<{}> | StrokeOptions | undefined`
- `shadow: ShadowOptions | undefined`
- `strokePosition: StrokePosition | undefined`
- `inside: InsideCallback | undefined`

**Instance Methods:**

- `.with(overrides: Partial<ShapeStyleOptions>): ShapeStyle`
  Derives a new ShapeStyle with specific attribute overrides. Performs deep merge on composite attributes (stroke, shadow, celShade) to prevent losing preset configurations.

---

## Functions & Operations

### `defineBrush`

Registers a brush and returns a factory that produces StrokeStyle instances.

```ts
const inkBleed = defineBrush({
  name: 'inkBleed',
  extends: 'ribbon',
  doc: 'Calligraphic stroke with edge ink bleeding marks',
  params: {
    bleed: { default: 0.4, doc: 'Intensity of edge bleeding (0..1)' },
  },
  draw({ ctx, points }, p, base) {
    base();
    // custom decorative marks using p.bleed
  },
});
const bold = inkBleed({ width: 5, color: '#111' });
```

```ts
function defineBrush<P extends object = {}>(def: BrushDefinition<P>): BrushFactory<P>
```

---

### `listBrushes`

Names of every registered brush (built-in and project-defined).

```ts
function listBrushes(): string[]
```

---

### `describeBrush`

Detailed description of a brush: doc, parent chain, parameter specs and defaults.

```ts
function describeBrush(name: string): BrushDescription
```

---

### `brushes`

The built-in brush factories, for example `brushes.ribbon({ width: 3 })`.

```ts
const brushes: { ribbon: BrushFactory<{ width: number; color: string; caliperNoise: number; taperEnd: boolean; }>; clean: BrushFactory<{ width: number; color: string; }>; sketch: BrushFactory<{ width: number; color: string; passes: number; overshoot: number; }>; chalk: BrushFactory<{ width: number; color: string; grain: number; intensity: number; }>; double: BrushFactory<{ width: number; color: string; }>; bristle: BrushFactory<{ width: number; color: string; bristles: number; }>; profile: BrushFactory<{ profile: (t: number) => number; cap: LineCap; }>; dashed: BrushFactory<DashedParams>; }
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

### `parseColor`

Parses hex (#rgb, #rrggbb, #rrggbbaa) or rgb/rgba strings into { r, g, b, a }.

```ts
function parseColor(color: string): RGBA
```

---

## Types & Interfaces

### `BrushFactory`

Creates a `StrokeStyle` for the brush. Overrides are StrokeOptions plus the brush's custom params.

```ts
type BrushFactory<P extends object = {}> = ((overrides?: (Partial<StrokeOptions> & Partial<P>) | undefined) => StrokeStyle<P>) & { readonly brushName: string; }
```

### `BrushDefinition`

Definition of a custom brush, passed to `defineBrush`.

```ts
interface BrushDefinition<P extends object = {}> {
  name: string;
  doc: string | undefined;
  extends: string | undefined;
  params: ParamSpecs<P> | undefined;
  defaults: Partial<StrokeOptions> | undefined;
  path: BrushGeometry<P> | undefined;
  draw: BrushDraw<P> | undefined;
  override: boolean | undefined;
}
```

### `BrushDescription`

Introspection result of a brush, returned by `describeBrush`.

```ts
interface BrushDescription {
  name: string;
  doc: string | undefined;
  extends: string | undefined;
  chain: string[];
  builtin: boolean;
  reshapesLine: boolean;
  params: ParamDescription[];
}
```

### `BrushLine`

Geometry handed to a brush: a polyline in canvas pixels.

```ts
interface BrushLine {
  ctx: CanvasRenderingContext2D;
  points: Point[];
  closed: boolean;
}
```

### `BrushSegment`

A polyline segment produced by a geometry hook (`path`).

```ts
interface BrushSegment {
  points: Point[];
  closed: boolean | undefined;
}
```

### `BrushParams`

Resolved parameters seen by `draw()`: StrokeOptions + custom params, defaults already applied.

```ts
type BrushParams<P extends object = {}> = StrokeOptions & P & { readonly [extra: string]: unknown; }
```

### `BrushBase`

Calls the parent brush's `draw` with the same line. Pass overrides to tweak its parameters.

```ts
type BrushBase = (overrides?: Record<string, unknown> | undefined) => void
```

### `BrushDraw`

Line drawing routine. Receives the canvas context and polyline points.

```ts
type BrushDraw<P extends object = {}> = (line: BrushLine, params: BrushParams<P>, base: BrushBase) => void
```

### `BrushGeometry`

Geometry rewriting hook. Receives the input polyline and returns one or more polylines
(e.g. dashes, scallops, zigzags) which are then rendered by `draw()`.

```ts
type BrushGeometry<P extends object = {}> = (line: { points: Point[]; closed: boolean; }, params: BrushParams<P>) => (Point[] | BrushSegment)[]
```

### `DashedParams`

Parameters of the `dashed` brush: dash length, gap and offset.

```ts
interface DashedParams {
  dash: number | undefined;
  gap: number | undefined;
  offset: number | undefined;
}
```

### `ParamSpec`

Declaration of one parameter: its default plus optional documentation and valid range.

```ts
interface ParamSpec<T = unknown> {
  default: T;
  doc: string | undefined;
  min: number | undefined;
  max: number | undefined;
  options: readonly T[] | undefined;
}
```

### `ParamSpecs`

One spec per key of `P`.

```ts
type ParamSpecs<P extends object> = { [K in keyof P]-?: ParamSpec<P[K]>; }
```

### `ParamDescription`

Flattened description of a parameter, as returned by `describeBrush` / `describePrimitive`.

```ts
interface ParamDescription {
  name: string;
  type: string;
  default: unknown;
  doc: string | undefined;
  min: number | undefined;
  max: number | undefined;
  options: readonly unknown[] | undefined;
  declaredBy: string;
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

### `Paint`

A fill paint: a color string, a canvas gradient or a canvas pattern.

```ts
type Paint = string | CanvasGradient | CanvasPattern
```

### `StrokeOptions`

Stroke options: width, color, renderer, join and the settings of each brush.

```ts
interface StrokeOptions {
  width: number | undefined;
  color: string | undefined;
  renderer: "stamp" | BrushName | undefined;
  stamp: StampStrokeConfig | undefined;
  join: StrokeJoin | undefined;
  miterLimit: number | undefined;
  scale: number | undefined;
  seed: number | undefined;
  taperStart: boolean | undefined;
  taperEnd: boolean | undefined;
  closed: boolean | undefined;
  caliperNoise: number | undefined;
  jitter: number | undefined;
  passes: number | undefined;
  position: StrokePosition | undefined;
  overshoot: number | undefined;
  double: DoubleLineOptions | undefined;
  grain: number | undefined;
  bristles: number | undefined;
}
```

### `StrokeInput`

StrokeOptions plus custom keys consumed by project brushes (see defineBrush).

```ts
type StrokeInput = StrokeOptions & { [extra: string]: unknown; }
```

### `ShadowOptions`

Drop shadow: color, offset and blur.

```ts
interface ShadowOptions {
  color: string;
  x: number;
  y: number;
  blur: number | undefined;
}
```

### `ShapeStyleOptions`

Plain options object for a ShapeStyle.

```ts
interface ShapeStyleOptions {
  fill: Paint | undefined;
  celShade: CelShadeOptions | undefined;
  texture: Texture<unknown> | Texture<unknown>[] | undefined;
  stroke: StrokeStyle<{}> | StrokeOptions | undefined;
  strokePosition: StrokePosition | undefined;
  shadow: ShadowOptions | undefined;
  inside: InsideCallback | undefined;
}
```

### `CelShadeOptions`

Cel shading: shade color, light pivot and light scale.

```ts
interface CelShadeOptions {
  shade: string;
  lightPivot: Point | AnchorName | undefined;
  litScale: number | { x: number; y: number; } | undefined;
}
```

### `BuiltinBrushName`

Brushes shipped with the engine.

```ts
type BuiltinBrushName = "double" | "ribbon" | "clean" | "sketch" | "chalk" | "bristle" | "profile" | "dashed"
```

### `BrushName`

Any registered brush name: built-ins (autocompleted) or names created with defineBrush.

```ts
type BrushName = (string & {}) | BuiltinBrushName
```

### `StrokeJoin`

How strokes join at corners: round, miter or bevel.

```ts
type StrokeJoin = "round" | "miter" | "bevel"
```

### `StrokePosition`

Where a stroke sits relative to the outline: center, inside or outside.

```ts
type StrokePosition = "center" | "inside" | "outside"
```

### `GradientOptions`

Options for `createGradient`: linear or radial, direction, color stops and points.

```ts
interface GradientOptions {
  type: "linear" | "radial" | undefined;
  direction: number | "vertical" | "horizontal" | "diagonal" | undefined;
  stops: [number, string][];
  from: Point | AnchorName | undefined;
  to: Point | AnchorName | undefined;
  center: Point | AnchorName | undefined;
  r1: number | undefined;
  r2: number | undefined;
}
```

