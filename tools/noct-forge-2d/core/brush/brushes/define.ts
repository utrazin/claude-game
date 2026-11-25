/**
 * NoctBrush - defineBrush: create reusable line types with typed parameters, inheritance and geometry hooks.
 */

import type { Point, StrokeOptions } from '../types.js';
import type { ParamDescription, ParamSpecs } from '../params.js';
import { StrokeStyle } from '../styles/stroke-style.js';
import { brushRegistry } from '../internal/brush-registry.js';

/** Geometry handed to a brush: a polyline in canvas pixels. */
export interface BrushLine {
  ctx: CanvasRenderingContext2D;
  points: Point[];
  closed: boolean;
}

/** A polyline segment produced by a geometry hook (`path`). */
export interface BrushSegment {
  points: Point[];
  closed?: boolean;
}

/** Resolved parameters seen by `draw()`: StrokeOptions + custom params, defaults already applied. */
export type BrushParams<P extends object = {}> = StrokeOptions & P & { readonly [extra: string]: unknown };

/** Calls the parent brush's `draw` with the same line. Pass overrides to tweak its parameters. */
export type BrushBase = (overrides?: Record<string, unknown>) => void;

/** Line drawing routine. Receives the canvas context and polyline points. */
export type BrushDraw<P extends object = {}> = (line: BrushLine, params: BrushParams<P>, base: BrushBase) => void;

/**
 * Geometry rewriting hook. Receives the input polyline and returns one or more polylines
 * (e.g. dashes, scallops, zigzags) which are then rendered by `draw()`.
 */
export type BrushGeometry<P extends object = {}> = (
  line: { points: Point[]; closed: boolean },
  params: BrushParams<P>,
) => (Point[] | BrushSegment)[];

/** Definition of a custom brush, passed to `defineBrush`. */
export interface BrushDefinition<P extends object = {}> {
  /** Unique brush name, used as `renderer: '<name>'`. */
  name: string;
  /** Human-readable explanation shown in `describeBrush()` and generated docs. */
  doc?: string;
  /** Parent brush to inherit defaults, geometry hooks, and `draw` from. */
  extends?: string;
  /**
   * Custom parameters of this brush, each with its default, documentation and optional min/max.
   * Use this for every key that is not a StrokeOptions key.
   */
  params?: ParamSpecs<P>;
  /**
   * StrokeOptions values this brush sets on top of its parent (e.g. `{ width: 3 }`).
   * Do not declare custom keys here: put them in `params`.
   */
  defaults?: Partial<StrokeOptions>;
  /** Optional geometry pre-processor: rewrites the polyline (dashes, zigzags, etc.) before drawing. */
  path?: BrushGeometry<P>;
  /** Renderer. Optional when `extends` is set (the parent's draw is inherited). */
  draw?: BrushDraw<P>;
  /** Allow replacing an existing brush definition with the same name deliberately. */
  override?: boolean;
}

/** Introspection result of a brush, returned by `describeBrush`. */
export interface BrushDescription {
  name: string;
  doc?: string;
  extends?: string;
  chain: string[];
  builtin: boolean;
  reshapesLine: boolean;
  params: ParamDescription[];
}

/** Creates a `StrokeStyle` for the brush. Overrides are StrokeOptions plus the brush's custom params. */
export type BrushFactory<P extends object = {}> = ((overrides?: Partial<StrokeOptions> & Partial<P>) => StrokeStyle<P>) & {
  /** Name usable as `renderer: '<name>'`. */
  readonly brushName: string;
};

/**
 * Registers a brush and returns a factory that produces StrokeStyle instances.
 *
 * ```ts
 * const inkBleed = defineBrush({
 *   name: 'inkBleed',
 *   extends: 'ribbon',
 *   doc: 'Calligraphic stroke with edge ink bleeding marks',
 *   params: {
 *     bleed: { default: 0.4, doc: 'Intensity of edge bleeding (0..1)' },
 *   },
 *   draw({ ctx, points }, p, base) {
 *     base();
 *     // custom decorative marks using p.bleed
 *   },
 * });
 * const bold = inkBleed({ width: 5, color: '#111' });
 * ```
 */
export function defineBrush<P extends object = {}>(def: BrushDefinition<P>): BrushFactory<P> {
  brushRegistry.define(def);
  const factory = ((overrides: Record<string, unknown> = {}) =>
    new StrokeStyle<P>({ ...brushRegistry.resolveParams(def.name, overrides), renderer: def.name } as any)) as BrushFactory<P>;
  Object.defineProperty(factory, 'brushName', { value: def.name, enumerable: true });
  return factory;
}

/** Names of every registered brush (built-in and project-defined). */
export function listBrushes(): string[] {
  return brushRegistry.names();
}

/** Detailed description of a brush: doc, parent chain, parameter specs and defaults. */
export function describeBrush(name: string): BrushDescription {
  return brushRegistry.describe(name);
}
