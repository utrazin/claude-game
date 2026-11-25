/**
 * NoctBrush - Programmatic Visual Asset Creation Engine
 * 
 * Object-oriented, attribute-driven 2D procedural graphics library for coding agents.
 */

// Side-effects registration: boolean engine & built-in brushes
import './internal/boolean.js';
import './brushes/builtin.js';

// Core geometry classes
export { Shape, CompoundShape, type PolygonRegion } from './shapes/shape.js';
export { Polygon } from './shapes/polygon.js';
export { Path, PathBuilder } from './shapes/path.js';
export { Group, type GroupItem } from './shapes/group.js';

// Extensible Brushes & Styles
export {
  defineBrush,
  listBrushes,
  describeBrush,
  type BrushFactory,
  type BrushDefinition,
  type BrushDescription,
  type BrushLine,
  type BrushSegment,
  type BrushParams,
  type BrushBase,
  type BrushDraw,
  type BrushGeometry,
} from './brushes/define.js';
export { brushes, type DashedParams } from './brushes/builtin.js';
export { StrokeStyle } from './styles/stroke-style.js';
export { ShapeStyle } from './styles/shape-style.js';

// High-level modeling, symmetry & composition operations
export {
  loft,
  sweep,
  morph,
  extrude2D,
  type LoftOptions,
  type SweepOptions,
  type MorphOptions,
  type Extrude2DOptions,
  type Extrude2DResult,
} from './ops/model.js';
export {
  mirror,
  revolve,
  type MirrorOptions,
  type RevolveOptions,
} from './ops/symmetry.js';
export {
  attach,
  align,
  distribute,
  scatterAlong,
  type AttachOptions,
  type AlignMode,
  type DistributeOptions,
  type ScatterAlongOptions,
  type Scatterable,
} from './ops/place.js';
export {
  definePrimitive,
  listPrimitives,
  describePrimitive,
  type PrimitiveFactory,
  type PrimitivePlacement,
  type PrimitiveDefinition,
  type PrimitiveDescription,
  type PrimitiveGenerator,
  type PrimitivePointsResult,
} from './ops/primitive.js';

// Declarative parameter specs
export type {
  ParamSpec,
  ParamSpecs,
  ParamDescription,
} from './params.js';

// Procedural textures
export { Hatch } from './textures/hatch.js';
export { Stipple } from './textures/stipple.js';
export { Grit } from './textures/grit.js';
export { StampScatter } from './textures/stamp-scatter.js';
export { BaseTexture } from './textures/custom.js';

// Stamps
export { StampAsset, loadStamp, type StampAssetOptions } from './stamps/stamp-asset.js';

// Color utilities
export { alpha, lerpColor, parseColor, type RGBA } from '../color.js';

// Core types & options interfaces
export type {
  Point,
  Paint,
  Bounds,
  InsideCallback,
  ShapeLike,
  Placeable,
  PolygonOptions,
  RectOptions,
  CircleOptions,
  EllipseOptions,
  LineOptions,
  LineShapeOptions,
  ArcOptions,
  CurveOptions,
  SplineOptions,
  BezierOptions,
  WaveOptions,
  WaveShapeOptions,
  WobbleOptions,
  StrokeOptions,
  StrokeInput,
  ShadowOptions,
  ShapeStyleOptions,
  CelShadeOptions,
  StarOptions,
  CrescentOptions,
  LobeDefinition,
  LobesOptions,
  RibbonWidth,
  StemOptions,
  BuiltinBrushName,
  BrushName,
  LineCap,
  WobbleStyle,
  StrokeJoin,
  StrokePosition,
  DoubleLineOptions,
  AnchorName,
  AnchorRef,
  BoundingBox,
  EdgeInfo,
  GradientOptions,
  Texture,
  DisplaceOptions,
  BendOptions,
  TaperOptions,
  WarpOptions,
  TwistOptions,
  InflateOptions,
  OutlineOptions,
  ToShapeOptions,
  LineToShapeInput,
  StampStrokeConfig,
  OffsetOptions,
  Transformable,
} from './types.js';

export type { HatchOptions, HatchBounds } from './textures/hatch.js';
export type { StippleOptions, StippleGradient } from './textures/stipple.js';
export type { GritOptions } from './textures/grit.js';
export type { StampScatterOptions } from './textures/stamp-scatter.js';
