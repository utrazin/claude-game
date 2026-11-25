# @core/brush - Geometry, Primitives & 2D Modeling

> Auto-generated public API reference. Do not edit directly; re-run `npm run docs:api`.

Declarative vector shapes, parametric primitives, CSG booleans, deformation hooks, bilateral symmetry, lathe/revolve, lofting, extrusion and semantic layout placement.

## Table of Contents

- [Classes & Constructors](#classes--constructors)
  - [`Shape`](#shape)
  - [`CompoundShape`](#compoundshape)
  - [`Polygon`](#polygon)
  - [`Group`](#group)
- [Functions & Operations](#functions--operations)
  - [`loft`](#loft)
  - [`sweep`](#sweep)
  - [`morph`](#morph)
  - [`extrude2D`](#extrude2d)
  - [`mirror`](#mirror)
  - [`revolve`](#revolve)
  - [`attach`](#attach)
  - [`align`](#align)
  - [`distribute`](#distribute)
  - [`scatterAlong`](#scatteralong)
  - [`definePrimitive`](#defineprimitive)
  - [`listPrimitives`](#listprimitives)
  - [`describePrimitive`](#describeprimitive)
- [Types & Interfaces](#types--interfaces)
  - [`PolygonRegion`](#polygonregion)
  - [`GroupItem`](#groupitem)
  - [`LoftOptions`](#loftoptions)
  - [`SweepOptions`](#sweepoptions)
  - [`MorphOptions`](#morphoptions)
  - [`Extrude2DOptions`](#extrude2doptions)
  - [`Extrude2DResult`](#extrude2dresult)
  - [`MirrorOptions`](#mirroroptions)
  - [`RevolveOptions`](#revolveoptions)
  - [`AttachOptions`](#attachoptions)
  - [`AlignMode`](#alignmode)
  - [`DistributeOptions`](#distributeoptions)
  - [`ScatterAlongOptions`](#scatteralongoptions)
  - [`Scatterable`](#scatterable)
  - [`PrimitiveFactory`](#primitivefactory)
  - [`PrimitivePlacement`](#primitiveplacement)
  - [`PrimitiveDefinition`](#primitivedefinition)
  - [`PrimitiveDescription`](#primitivedescription)
  - [`PrimitiveGenerator`](#primitivegenerator)
  - [`PrimitivePointsResult`](#primitivepointsresult)
  - [`Point`](#point)
  - [`Bounds`](#bounds)
  - [`InsideCallback`](#insidecallback)
  - [`ShapeLike`](#shapelike)
  - [`Placeable`](#placeable)
  - [`PolygonOptions`](#polygonoptions)
  - [`RectOptions`](#rectoptions)
  - [`CircleOptions`](#circleoptions)
  - [`EllipseOptions`](#ellipseoptions)
  - [`StarOptions`](#staroptions)
  - [`CrescentOptions`](#crescentoptions)
  - [`LobeDefinition`](#lobedefinition)
  - [`LobesOptions`](#lobesoptions)
  - [`StemOptions`](#stemoptions)
  - [`AnchorName`](#anchorname)
  - [`AnchorRef`](#anchorref)
  - [`BoundingBox`](#boundingbox)
  - [`EdgeInfo`](#edgeinfo)
  - [`DisplaceOptions`](#displaceoptions)
  - [`BendOptions`](#bendoptions)
  - [`TaperOptions`](#taperoptions)
  - [`WarpOptions`](#warpoptions)
  - [`TwistOptions`](#twistoptions)
  - [`InflateOptions`](#inflateoptions)
  - [`OutlineOptions`](#outlineoptions)
  - [`OffsetOptions`](#offsetoptions)
  - [`Transformable`](#transformable)

---

## Classes & Constructors

### `Shape`

Base class of every filled shape: transforms, anchors, booleans, deformations and drawing.

**Properties:**

- `regions: PolygonRegion[]` — Copy of every disconnected filled region (outer ring + holes).
- `bounds: BoundingBox` — Axis-aligned bounding box and its center.
- `center: Point`
- `anchorNames: string[]` — Names of the custom anchors set with `setAnchor`.

**Instance Methods:**

- `.clone(): Shape`
  Independent deep clone.
- `.toPoints(): Point[]`
  Copy of the outer ring of the primary region.
- `.anchor(name: AnchorRef): Point`
  Point of the shape by name: the 9 built-in bounding-box anchors ('center', 'top', 'bottomLeft', ...) or a custom anchor registered with `setAnchor`.
- `.setAnchor(name: string, at: Point): this`
  Registers a custom named anchor (e.g. 'hilt', 'socket') at an absolute point. Custom anchors move with `translate/rotate/scale/moveTo`, are kept by `clone()` and `flip()`, and are dropped by operations that build new geometry (booleans, offsets, deformations). Built-in names cannot be redefined.
- `.vertex(index: number): Point`
  Vertex of the primary outer ring (negative indices wrap).
- `.edge(index: number): EdgeInfo`
  Edge i -> i+1 of the primary outer ring: midpoint, outward normal, tangent, angle, length.
- `.translate(dx: number, dy: number): this`
- `.rotate(angleDegrees: number, pivot?: Point | AnchorRef | undefined): this`
  Rotates by degrees around a Point or anchor name, built-in or custom (default: center).
- `.scale(sx: number, sy?: number, pivot?: Point | AnchorRef | undefined): this`
  Scales around a Point or anchor name, built-in or custom (default: center). `sy` defaults to `sx`.
- `.moveTo(target: Point, myAnchor?: AnchorRef): this`
  Translates so that `myAnchor` (built-in or custom) lands on `target`.
- `.offset(distance: number, options?: OffsetOptions): Shape`
  Inset (distance < 0) or outset (distance > 0) by a constant distance.
- `.roundCorners(radius: number | number[], stepsPerCorner?: number): Shape`
  Circular fillet on every corner. Radius may be a number or one per vertex.
- `.union(other: Shape | Point[] | Path | (Shape | Point[] | Path)[], pathWidth?: RibbonWidth): CompoundShape`
  Geometric union (CSG). Accepts Shape, Path (converted with pathWidth, default 2), Point[], or an array of them.
- `.subtract(other: Shape | Point[] | Path | (Shape | Point[] | Path)[], pathWidth?: RibbonWidth): CompoundShape`
  Cuts `other` out of this shape (CSG). Accepts Shape, Path (converted with pathWidth, default 2), Point[], or an array of them.
- `.intersect(other: Shape | Point[] | Path | (Shape | Point[] | Path)[], pathWidth?: RibbonWidth): CompoundShape`
  Keeps only the overlap with `other` (CSG). Accepts Shape, Path (converted with pathWidth, default 2), Point[], or an array of them.
- `.unionLine(path: Path, widthOrStroke?: LineToShapeInput, cap?: LineCap): CompoundShape`
  Unites a Path directly with this shape as a solid ribbon. Accepts thickness, ToShapeOptions, or a StrokeStyle/StrokeOptions.
- `.cutLine(path: Path, widthOrStroke?: LineToShapeInput, cap?: LineCap): CompoundShape`
  Cuts this shape along a Path using a cutting ribbon. Accepts thickness, ToShapeOptions, or a StrokeStyle/StrokeOptions.
- `.mapVertices(fn: (p: Point, index: number, count: number) => void | Point): CompoundShape`
  Replaces every vertex: `fn(p, index, count)` returns the new point (or mutates the copy it receives).
- `.displace(options?: DisplaceOptions): CompoundShape`
  Organic noise displacement along the contour normal (or free 'xy' jitter). Deterministic via `seed`.
- `.subdivide(maxEdge: number): CompoundShape`
  Inserts vertices so no edge is longer than `maxEdge`.
- `.resample(count: number): CompoundShape`
  Re-spaces the outer ring to `count` evenly spaced vertices (holes get a proportional count).
- `.smooth(iterations?: number): CompoundShape`
  Chaikin corner cutting; each iteration doubles the vertex count and softens corners.
- `.bend(options: BendOptions): CompoundShape`
  Curves the shape by `angle` degrees along an axis.
- `.taper(options?: TaperOptions): CompoundShape`
  Scales the cross-section linearly along an axis (narrow one end, widen the other).
- `.warp(fn: (p: Point, uv: Point) => void | Point, options?: WarpOptions): CompoundShape`
  Free-form warp: `fn(p, uv)` receives a copy of each vertex and its normalized position `uv` (0..1) inside the shape's bounds, and returns the new point. Edges are subdivided first (`densify`, default 6px). Example: `shape.warp((p, uv) => ({ x: p.x + Math.sin(uv.y * 6) * 8, y: p.y }))`.
- `.twist(options: TwistOptions): CompoundShape`
  Rotates vertices progressively along an axis (0 at the min end, `angle` degrees at the max end).
- `.inflate(options: InflateOptions): CompoundShape`
  Swells (amount > 0) or pinches (amount < 0) the area around `center` with smooth radial falloff.
- `.flip(axis?: "x" | "y", at?: number | undefined): CompoundShape`
  Mirror copy across a line. `axis: 'x'` reflects left <-> right across the vertical line x = `at`; `axis: 'y'` reflects top <-> bottom across the horizontal line y = `at`. `at` defaults to the bounds center. Returns a NEW shape (the original is untouched); custom anchors are mirrored too. To get a symmetric whole instead of just the reflection use `mirror(shape, { axis })`.
- `.perimeter(): Path`
  The primary outer ring as a closed Path. Use `contours()` to include holes and islands.
- `.contours(): Path[]`
  Every ring (outer rings and holes of all regions) as closed Paths.
- `.outline(options?: OutlineOptions): CompoundShape`
  Turns the contour into filled geometry: a band of `width` around every ring. The result is a regular shape: fill it, texture it, union it, clip with it.
- `.createGradient(ctx: CanvasRenderingContext2D, options: GradientOptions): CanvasGradient`
  Linear or radial gradient fitted to this shape's bounds.
- `.fill(ctx: CanvasRenderingContext2D, fillStyle: Paint): this`
  Fills with the given paint (holes via even-odd).
- `.clip(ctx: CanvasRenderingContext2D, fn: InsideCallback): this`
  Runs `fn` with the context clipped to this shape. The clip is always restored.
- `.stroke(ctx: CanvasRenderingContext2D, strokeStyle?: StrokeStyle<{}> | StrokeOptions | undefined): this`
  Strokes the contour with a brush. Position 'center' | 'inside' | 'outside'.
- `.draw(ctx: CanvasRenderingContext2D, style?: ShapeStyle | ShapeStyleOptions | undefined): this`
  Full pipeline: shadow, outside stroke, fill (optionally cel-shaded), textures, `inside` callback, then center/inside stroke.

---

### `CompoundShape`

Shape made of one or more regions, each with optional holes.
Produced by booleans, offsets, deformations and `Path.close()`.

**Constructors:**
```ts
new CompoundShape(regions: PolygonRegion[]): CompoundShape
new CompoundShape(points: Point[], holes?: Point[][] | undefined): CompoundShape
```

**Instance Methods:**

- `.clone(): CompoundShape`
  Independent deep clone.

---

### `Polygon`

A closed, fillable polygon, built from points or from a parametric constructor such as `Polygon.rect`.

**Constructor:**
```ts
new Polygon(attrsOrPoints: Point[] | PolygonOptions): Polygon
```

**Static Factories:**

- `Polygon.fromPoints(points: Point[], attrs?: Partial<PolygonOptions>): Polygon`
  Instantiates a Polygon from arbitrary polyline/polygon points. Supports optional center offset, rotation, corner rounding, and wobble. `rotation` turns the points around the origin (0, 0), not around the shape. To turn a shape in place, call `.rotate(degrees, pivot)` on the result.
- `Polygon.regular(sides: number, radius: number, attrs?: Partial<PolygonOptions>): Polygon`
  Regular N-sided equilateral polygon (e.g. 3 = triangle, 5 = pentagon, 6 = hexagon).
- `Polygon.triangle(base: number, height: number, attrs?: Partial<PolygonOptions>): Polygon`
  Parametric Triangle with explicit base width and height.
- `Polygon.diamond(width: number, height: number, attrs?: Partial<PolygonOptions>): Polygon`
  Parametric Diamond / Rhombus with explicit width and height.
- `Polygon.star(points: number, outerRadius: number, innerRadiusOrAttrs?: number | Partial<StarOptions> | undefined, attrs?: Partial<StarOptions> | undefined): Polygon`
  Parametric Star with outer point radius and inner valley radius. Can be called with (points, outerRadius, innerRadius?, options?) or (points, outerRadius, options?) omitting innerRadius. Supports concave/convex edge curvature via options.bulge.
- `Polygon.crescent(radius: number, thickness: number, options?: CrescentOptions): Polygon`
  Parametric Crescent Moon shape with outer radius, central thickness, and sharp cusps.
- `Polygon.lobes(lobes: LobeDefinition[], options?: LobesOptions): Polygon`
  Generates a continuous organic envelope enclosing multiple ellipse lobes (clouds, bushes, slime) via analytical raycasting from the barycenter without sharp CSG boolean seams.
- `Polygon.stem(base: Point, height: number, options?: StemOptions): Polygon`
  Parametric tapered stem, horn, or vine with quadratic curve and wind sway. `base` is where the stem attaches. To turn a stem around its attachment point, use `Polygon.stem(base, height).rotate(degrees, base)`. The `rotation` option pivots on the origin.
- `Polygon.rect(width: number, height: number, attrs?: Partial<RectOptions>): Polygon`
  Parametric Rectangle with individual corner radii and wobble support. Supports both explicit pixel radii (>= 1.0) and proportional factors (< 1.0).
- `Polygon.circle(radius: number, attrs?: Partial<CircleOptions>): Polygon`
  Parametric Circle with optional simplex noise wobble.
- `Polygon.ellipse(rx: number, ry: number, attrs?: Partial<EllipseOptions>): Polygon`
  Parametric Ellipse with rx, ry and rotation.
- `Polygon.capsule(width: number, height: number, attrs?: Partial<RectOptions>): Polygon`
  Parametric Capsule / Pill shape.

**Instance Methods:**

- `.clone(): Polygon`
  Independent deep clone.
- `.roundCorners(radius: number | number[], stepsPerCorner?: number): Polygon`
  Applies circular arc filleting to all corners of this polygon. Works on any polygon, including those generated from arbitrary points.

---

### `Group`

A set of shapes and paths that move, rotate and draw as one.

**Constructor:**
```ts
new Group(itemsOrEntries?: (GroupItem | GroupEntry)[]): Group
```

**Properties:**

- `items: GroupItem[]`
- `entries: GroupEntry[]`
- `bounds: BoundingBox` — Aggregates the bounding box of all children.
- `center: Point` — The geometric center of the group's bounding box.
- `anchorNames: string[]` — Names of the custom anchors set with setAnchor.

**Instance Methods:**

- `.add(item: GroupItem, style?: ItemStyle | undefined): this`
  Adds an item to the group with an optional deferred style.
- `.remove(item: GroupItem): this`
  Removes a child item from the group.
- `.flatten(): (Shape | Path)[]`
  Flattens nested groups into a flat array of leaf Shape and Path instances.
- `.anchor(name: AnchorRef): Point`
  Resolves a named anchor point on the group's collective bounding box.
- `.setAnchor(name: string, at: Point): this`
  Registers a custom named anchor on the group (absolute Point). It follows the group's translate/rotate/scale/moveTo and clone(). Built-in names cannot be redefined.
- `.translate(dx: number, dy: number): this`
  Translates all children in the group by (dx, dy).
- `.rotate(angleDegrees: number, pivot?: Point | AnchorRef | undefined): this`
  Rotates all children in the group around a shared pivot point (defaults to group center).
- `.scale(sx: number, sy?: number, pivot?: Point | AnchorRef | undefined): this`
  Scales all children in the group around a shared pivot point (defaults to group center).
- `.moveTo(target: Point, myAnchor?: AnchorRef): this`
  Moves the group so that `myAnchor` aligns with `target`.
- `.clone(): Group`
  Deep clones the group and all its children.
- `.render(ctx: CanvasRenderingContext2D, fallbackStyle?: ItemStyle | undefined): this`
  Renders every child in the group. If an entry has an assigned style, it uses that style; otherwise falls back to the provided fallbackStyle.
- `.draw(ctx: CanvasRenderingContext2D, style?: ShapeStyle | ShapeStyleOptions | undefined): this`
  Renders every child in the group using its own .draw() method.
- `.stroke(ctx: CanvasRenderingContext2D, strokeStyle?: StrokeStyle<{}> | StrokeOptions | undefined): this`
  Strokes every child in the group.

---

## Functions & Operations

### `loft`

Fills the surface between curves.

- `loft(a, b)`: two open paths produce a polygon; two closed loops produce a ring (larger loop minus smaller loop).
- `loft([s0, s1, s2, ...])`: three or more OPEN section paths, all drawn in the same direction (e.g. left to right),
  produce one silhouette through every section. Sections act as rungs, so a vase is `loft([rim, belly, foot])`.
  Use `{ smooth: true }` for rounded profiles.

```ts
function loft(a: Path, b: Path, options?: LoftOptions | undefined): Shape
function loft(sections: Path[], options?: LoftOptions | undefined): Shape
```

---

### `sweep`

Drags `profile` along `along` and returns the union of every stamp. Use more `steps` for large or sharp profiles.

```ts
function sweep(profile: Shape, along: Path, options?: SweepOptions): Shape
```

---

### `morph`

Blends two shapes (outer contours) or two paths. `t = 0` returns `a`, `t = 1` returns `b`.
Shapes return a Polygon, paths return a Path.

```ts
function morph(a: Shape, b: Shape, t: number, options?: MorphOptions | undefined): Polygon
function morph(a: Path, b: Path, t: number, options?: MorphOptions | undefined): Path
```

---

### `extrude2D`

Generates 2.5D extrusion geometry with extruded side walls and front face.
Ideal for isometric tiles, buttons, coins, platform edges, plaques, and gems.

```ts
function extrude2D(shape: Shape, options?: Extrude2DOptions): Extrude2DResult
```

---

### `mirror`

Builds a symmetric whole from one half.

- Shape: returns the union of the shape and its reflection.
- Path: walks the path, then the reflected path backwards, so half a contour becomes a full outline.
  Use `{ close: true }` for a fillable loop: `mirror(halfOutline, { close: true }).close()`.

```ts
function mirror(item: Shape, options?: MirrorOptions | undefined): Shape
function mirror(item: Path, options?: MirrorOptions | undefined): Path
```

---

### `revolve`

2D lathe: the silhouette of a solid of revolution. Draw ONE side of the object as an open path
(e.g. the right half of a vase from rim to foot) and get the full filled shape.
The ends of the profile are joined to the axis with straight lines (flat rim and base).

```ts
function revolve(profile: Path, options?: RevolveOptions): Shape
```

---

### `attach`

Moves `subject` so its `from` anchor lands on the target's `at` anchor.
`attach(lid, box, { from: 'bottom', at: 'top', offset: { x: 0, y: -2 } })`

```ts
function attach<T extends Placeable>(subject: T, target: Point | Placeable, options?: AttachOptions): T
```

---

### `align`

Aligns items on a shared edge or center line.
`reference` picks the line: the union bounds of all items (default) or the first item.

```ts
function align<T extends Placeable>(items: T[], mode: AlignMode, reference?: "bounds" | "first"): T[]
```

---

### `distribute`

Spreads items along an axis in the given order.

```ts
function distribute<T extends Placeable>(items: T[], axis: "x" | "y", options?: DistributeOptions): T[]
```

---

### `scatterAlong`

Places copies of `item` along a path: spikes on a spine, beads on a string, leaves on a vine.
`item` is cloned for each position (or produced by a factory `(index, t) => item`, for per-copy variation).
Returns the placed copies; wrap them with `new Group(copies)` to draw or transform them together.

```ts
function scatterAlong<T extends Scatterable>(path: Path, item: T | ((index: number, t: number) => T), options?: ScatterAlongOptions): T[]
```

---

### `definePrimitive`

Wraps a point generator into a parametric polygon/shape factory.
Accepts either:
- Simple signature: `definePrimitive('gear', (params) => [...points])`
- Full definition: `definePrimitive({ name: 'gear', doc: '...', params: { ... }, generate: (p) => ... })`

```ts
function definePrimitive<P extends object>(nameOrDef: string | PrimitiveDefinition<P>, generator?: PrimitiveGenerator<P> | undefined): PrimitiveFactory<P>
```

---

### `listPrimitives`

Names of all registered custom primitives.

```ts
function listPrimitives(): string[]
```

---

### `describePrimitive`

Introspection for a primitive's parameters, defaults and documentation.

```ts
function describePrimitive(name: string): PrimitiveDescription
```

---

## Types & Interfaces

### `PolygonRegion`

A filled region: an outer ring and its holes.

```ts
interface PolygonRegion {
  outer: Point[];
  holes: Point[][];
}
```

### `GroupItem`

Anything a Group can contain: a Shape, a Path or another Group.

```ts
type GroupItem = Shape | Path | Group
```

### `LoftOptions`

Options for `loft`: number of steps and smoothing.

```ts
interface LoftOptions {
  steps: number | undefined;
  smooth: boolean | undefined;
}
```

### `SweepOptions`

Options for `sweep`: steps, scale along the path, alignment and pivot.

```ts
interface SweepOptions {
  steps: number | undefined;
  scale: number | ((t: number) => number | Point) | undefined;
  align: boolean | undefined;
  pivot: Point | AnchorName | undefined;
}
```

### `MorphOptions`

Options for `morph`: number of samples.

```ts
interface MorphOptions {
  samples: number | undefined;
}
```

### `Extrude2DOptions`

Options for `extrude2D`: depth, angle and bevel of the extrusion.

```ts
interface Extrude2DOptions {
  depth: number | undefined;
  angle: number | undefined;
  bevel: number | undefined;
}
```

### `Extrude2DResult`

Result of `extrude2D`: the front face, the side walls and both combined.

```ts
interface Extrude2DResult {
  front: Shape;
  sides: CompoundShape;
  all: CompoundShape;
  offset: Point;
  draw(ctx: CanvasRenderingContext2D, styles?: { front?: ShapeStyle | ShapeStyleOptions | undefined; sides?: ShapeStyle | ShapeStyleOptions | undefined; } | undefined): void;
}
```

### `MirrorOptions`

Options for `mirror`: axis, position and which side to keep.

```ts
interface MirrorOptions {
  axis: "x" | "y" | undefined;
  at: number | undefined;
  side: "min" | "max" | undefined;
  close: boolean | undefined;
}
```

### `RevolveOptions`

Options for `revolve`: axis, position and steps.

```ts
interface RevolveOptions {
  axis: "x" | "y" | undefined;
  at: number | undefined;
  steps: number | undefined;
}
```

### `AttachOptions`

Options for `attach`: the anchor on the subject (`from`), the anchor on the target (`at`) and an offset.

```ts
interface AttachOptions {
  from: Point | AnchorRef | undefined;
  at: Point | AnchorRef | undefined;
  offset: Point | undefined;
}
```

### `AlignMode`

Alignment accepted by `align`: 'left', 'right', 'top', 'bottom', 'centerX' or 'centerY'.

```ts
type AlignMode = "top" | "bottom" | "left" | "right" | "centerX" | "centerY"
```

### `DistributeOptions`

Options for `distribute`: the gap between items.

```ts
interface DistributeOptions {
  gap: number | undefined;
}
```

### `ScatterAlongOptions`

Options for `scatterAlong`: count, spacing, range along the path and rotation.

```ts
interface ScatterAlongOptions {
  count: number | undefined;
  spacing: number | undefined;
  from: number | undefined;
  to: number | undefined;
  align: boolean | undefined;
  rotation: number | undefined;
  pivot: AnchorRef | undefined;
  offset: number | undefined;
  scale: number | ((t: number) => number) | undefined;
}
```

### `Scatterable`

Anything `scatterAlong` can clone and orient: Shape, Path or Group.

```ts
interface Scatterable {
  clone(): unknown;
  rotate(angleDegrees: number, pivot?: Point | AnchorRef | undefined): unknown;
  scale(sx: number, sy?: number | undefined, pivot?: Point | AnchorRef | undefined): unknown;
  bounds: BoundingBox;
  center: Point;
  anchor(name: AnchorRef): Point;
  translate(dx: number, dy: number): this;
}
```

### `PrimitiveFactory`

A factory created by `definePrimitive`. Call it with parameters and placement options.

```ts
type PrimitiveFactory<P extends object> = ((params?: Partial<P> | undefined, placement?: Partial<Pick<PolygonOptions, "center" | "wobble" | "seed" | "cx" | "cy" | "rotation" | "roundness">> | undefined) => Shape) & { readonly primitiveName: string; }
```

### `PrimitivePlacement`

Placement and finishing options accepted by every primitive.

```ts
type PrimitivePlacement = { center?: Point | undefined; wobble?: boolean | WobbleOptions | undefined; seed?: number | undefined; cx?: number | undefined; cy?: number | undefined; rotation?: number | undefined; roundness?: number | undefined; }
```

### `PrimitiveDefinition`

Definition of a custom primitive, passed to `definePrimitive`.

```ts
interface PrimitiveDefinition<P extends object> {
  name: string;
  doc: string | undefined;
  extends: string | undefined;
  params: ParamSpecs<P> | undefined;
  defaults: Partial<P> | undefined;
  generate: PrimitiveGenerator<P> | undefined;
  override: boolean | undefined;
}
```

### `PrimitiveDescription`

Introspection result of a primitive, returned by `describePrimitive`.

```ts
interface PrimitiveDescription {
  name: string;
  doc: string | undefined;
  extends: string | undefined;
  chain: string[];
  params: ParamDescription[];
}
```

### `PrimitiveGenerator`

Function that returns the points of a primitive from its parameters.

```ts
type PrimitiveGenerator<P extends object> = (params: P) => PrimitivePointsResult
```

### `PrimitivePointsResult`

What a primitive generator returns: a point list, or an outer contour with holes.

```ts
type PrimitivePointsResult = Point[] | { outer: Point[]; holes?: Point[][] | undefined; }
```

### `Point`

NoctBrush - Core Attribute Interfaces & Types

```ts
interface Point {
  x: number;
  y: number;
}
```

### `Bounds`

A rectangle with position and size.

```ts
interface Bounds {
  x: number;
  y: number;
  width: number;
  height: number;
}
```

### `InsideCallback`

Callback that draws inside a shape, clipped to its silhouette.

```ts
type InsideCallback = (ctx: CanvasRenderingContext2D, shape: ShapeLike) => void
```

### `ShapeLike`

Anything with bounds, a center and anchors, such as a Shape or a Group.

```ts
interface ShapeLike {
  bounds: BoundingBox;
  center: Point;
  anchor(name: AnchorName): Point;
  toPoints(): Point[];
  offset(distance: number, options?: { miterLimit?: number | undefined; } | undefined): ShapeLike;
  createGradient(ctx: CanvasRenderingContext2D, options: GradientOptions): CanvasGradient;
  fill(ctx: CanvasRenderingContext2D, fillStyle: Paint): this;
  stroke(ctx: CanvasRenderingContext2D, strokeStyle?: StrokeStyle<{}> | StrokeOptions | undefined): this;
  draw(ctx: CanvasRenderingContext2D, options?: ShapeStyleOptions | undefined): this;
  clip(ctx: CanvasRenderingContext2D, fn: InsideCallback): unknown;
}
```

### `Placeable`

Anything that can be positioned: Shape, Path, Group. Used by attach/align/distribute.

```ts
interface Placeable {
  bounds: BoundingBox;
  center: Point;
  anchor(name: AnchorRef): Point;
  translate(dx: number, dy: number): this;
}
```

### `PolygonOptions`

Options for polygon constructors: center, rotation, rounding, wobble and seed.

```ts
interface PolygonOptions {
  sides: number | undefined;
  radius: number | undefined;
  innerRadius: number | undefined;
  cx: number | undefined;
  cy: number | undefined;
  center: Point | undefined;
  rotation: number | undefined;
  roundness: number | undefined;
  bevel: number | undefined;
  wobble: boolean | WobbleOptions | undefined;
  seed: number | undefined;
}
```

### `RectOptions`

Options for `Polygon.rect` and `Polygon.capsule`: size, corner radius, bevel and center.

```ts
interface RectOptions {
  width: number;
  height: number;
  cx: number | undefined;
  cy: number | undefined;
  radius: number | [number, number, number, number] | undefined;
  bevel: number | [number, number, number, number] | undefined;
  rotation: number | undefined;
  wobble: boolean | WobbleOptions | undefined;
  seed: number | undefined;
}
```

### `CircleOptions`

Options for `Polygon.circle`: center, number of segments and wobble.

```ts
interface CircleOptions {
  radius: number;
  cx: number | undefined;
  cy: number | undefined;
  segments: number | undefined;
  wobble: boolean | WobbleOptions | undefined;
  seed: number | undefined;
}
```

### `EllipseOptions`

Options for `Polygon.ellipse`: radii, center, rotation and segments.

```ts
interface EllipseOptions {
  rx: number;
  ry: number;
  cx: number | undefined;
  cy: number | undefined;
  rotation: number | undefined;
  segments: number | undefined;
  wobble: boolean | WobbleOptions | undefined;
  seed: number | undefined;
}
```

### `StarOptions`

Options for `Polygon.star`: inner radius and edge bulge, plus the polygon options.

```ts
interface StarOptions {
  innerRadius: number | undefined;
  bulge: number | undefined;
  sides: number | undefined;
  radius: number | undefined;
  cx: number | undefined;
  cy: number | undefined;
  center: Point | undefined;
  rotation: number | undefined;
  roundness: number | undefined;
  bevel: number | undefined;
  wobble: boolean | WobbleOptions | undefined;
  seed: number | undefined;
}
```

### `CrescentOptions`

Options for `Polygon.crescent`: arc angle, rotation and segments.

```ts
interface CrescentOptions {
  arcAngle: number | undefined;
  rotation: number | undefined;
  segments: number | undefined;
  sides: number | undefined;
  radius: number | undefined;
  innerRadius: number | undefined;
  cx: number | undefined;
  cy: number | undefined;
  center: Point | undefined;
  roundness: number | undefined;
  bevel: number | undefined;
  wobble: boolean | WobbleOptions | undefined;
  seed: number | undefined;
}
```

### `LobeDefinition`

One ellipse lobe of `Polygon.lobes`: center and radii.

```ts
interface LobeDefinition {
  cx: number;
  cy: number;
  rx: number;
  ry: number | undefined;
}
```

### `LobesOptions`

Options for `Polygon.lobes`: number of segments.

```ts
interface LobesOptions {
  segments: number | undefined;
  sides: number | undefined;
  radius: number | undefined;
  innerRadius: number | undefined;
  cx: number | undefined;
  cy: number | undefined;
  center: Point | undefined;
  rotation: number | undefined;
  roundness: number | undefined;
  bevel: number | undefined;
  wobble: boolean | WobbleOptions | undefined;
  seed: number | undefined;
}
```

### `StemOptions`

Options for `Polygon.stem`: sway, base and top width, and segments.

```ts
interface StemOptions {
  sway: number | undefined;
  baseWidth: number | undefined;
  topWidth: number | undefined;
  segments: number | undefined;
  sides: number | undefined;
  radius: number | undefined;
  innerRadius: number | undefined;
  cx: number | undefined;
  cy: number | undefined;
  center: Point | undefined;
  rotation: number | undefined;
  roundness: number | undefined;
  bevel: number | undefined;
  wobble: boolean | WobbleOptions | undefined;
  seed: number | undefined;
}
```

### `AnchorName`

Built-in anchor names of a shape: center, the four edges and the four corners.

```ts
type AnchorName = "center" | "top" | "bottom" | "left" | "right" | "topLeft" | "topRight" | "bottomLeft" | "bottomRight"
```

### `AnchorRef`

Anything accepted where an anchor is expected: one of the 9 built-in `AnchorName`s or a custom
anchor registered with `setAnchor(name, point)`. Built-in names keep editor autocompletion.

```ts
type AnchorRef = AnchorName | (string & {})
```

### `BoundingBox`

Bounding box of a shape, with its edges, size and center.

```ts
interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  left: number;
  right: number;
  top: number;
  bottom: number;
  center: Point;
}
```

### `EdgeInfo`

One edge of a polygon: its midpoint, normal, tangent and length.

```ts
interface EdgeInfo {
  index: number;
  start: Point;
  end: Point;
  mid: Point;
  normal: Point;
  tangent: Point;
  angle: number;
  normalAngle: number;
  length: number;
}
```

### `DisplaceOptions`

Options for `displace`: amplitude, frequency, seed and mode.

```ts
interface DisplaceOptions {
  amplitude: number | undefined;
  frequency: number | undefined;
  seed: number | undefined;
  densify: number | undefined;
  mode: "normal" | "xy" | undefined;
}
```

### `BendOptions`

Options for `bend`: angle and axis.

```ts
interface BendOptions {
  angle: number;
  axis: "x" | "y" | undefined;
  pivot: Point | undefined;
}
```

### `TaperOptions`

Options for `taper`: axis and the scale at each end.

```ts
interface TaperOptions {
  axis: "x" | "y" | undefined;
  from: number | undefined;
  to: number | undefined;
  pivot: Point | undefined;
}
```

### `WarpOptions`

Options for `warp`: densification before the warp.

```ts
interface WarpOptions {
  densify: number | undefined;
}
```

### `TwistOptions`

Options for `twist`: angle and axis.

```ts
interface TwistOptions {
  angle: number;
  axis: "x" | "y" | undefined;
  pivot: Point | undefined;
  densify: number | undefined;
}
```

### `InflateOptions`

Options for `inflate`: amount and radius.

```ts
interface InflateOptions {
  amount: number;
  center: Point | undefined;
  radius: number | undefined;
  densify: number | undefined;
}
```

### `OutlineOptions`

Options for `outline`: band width, position and miter limit.

```ts
interface OutlineOptions {
  width: number | undefined;
  position: StrokePosition | undefined;
  miterLimit: number | undefined;
}
```

### `OffsetOptions`

Options for `Shape.offset()` and `offsetPolygon()`.

```ts
interface OffsetOptions {
  miterLimit: number | undefined;
}
```

### `Transformable`

Anything that can be moved, rotated and scaled in place: `Shape`, `Path` and `Group`.

```ts
interface Transformable {
  bounds: BoundingBox;
  center: Point;
  translate(dx: number, dy: number): this;
  rotate(angleDegrees: number, pivot?: Point | AnchorRef | undefined): this;
  scale(sx: number, sy?: number | undefined, pivot?: Point | AnchorRef | undefined): this;
  moveTo(target: Point, myAnchor?: AnchorRef | undefined): this;
}
```

