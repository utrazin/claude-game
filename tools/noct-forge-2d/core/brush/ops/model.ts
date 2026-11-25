/**
 * NoctBrush - 2D "modeling" operations: loft, sweep, morph.
 *
 * - loft:  surface between two curves (ruled band)
 * - sweep: a profile shape dragged along a path (optionally scaled and aligned to the path)
 * - morph: blend between two shapes or paths
 * - extrude2D: directional 2.5D extrusion with wall generation and depth ordering
 */

import type { AnchorName, Point, ShapeStyleOptions } from '../types.js';
import type { ShapeStyle } from '../styles/shape-style.js';
import { Shape, CompoundShape } from '../shapes/shape.js';
import { Polygon } from '../shapes/polygon.js';
import { Path } from '../shapes/path.js';
import { dist, lerp, polygonArea, resamplePolyline, sampleAtDistance, polylineLength, resolvePivot } from '../internal/points.js';

/** Options for `loft`: number of steps and smoothing. */
export interface LoftOptions {
  /** Points per section used to pair curves (default 32). */
  steps?: number;
  /**
   * Only for 3+ sections: join the section end points with a smooth Catmull-Rom curve instead of
   * straight segments, so the silhouette bulges smoothly through the sections (default false).
   */
  smooth?: boolean;
}

/**
 * Fills the surface between curves.
 *
 * - `loft(a, b)`: two open paths produce a polygon; two closed loops produce a ring (larger loop minus smaller loop).
 * - `loft([s0, s1, s2, ...])`: three or more OPEN section paths, all drawn in the same direction (e.g. left to right),
 *   produce one silhouette through every section. Sections act as rungs, so a vase is `loft([rim, belly, foot])`.
 *   Use `{ smooth: true }` for rounded profiles.
 */
export function loft(a: Path, b: Path, options?: LoftOptions): Shape;
export function loft(sections: Path[], options?: LoftOptions): Shape;
export function loft(first: Path | Path[], second?: Path | LoftOptions, third?: LoftOptions): Shape {
  const sections = Array.isArray(first) ? first : [first, second as Path];
  const options: LoftOptions = (Array.isArray(first) ? (second as LoftOptions | undefined) : third) ?? {};
  if (sections.length < 2 || sections.some(s => !(s instanceof Path))) {
    throw new Error('loft: provide two Paths (loft(a, b)) or an array of at least two Paths (loft([s0, s1, s2])).');
  }
  const steps = Math.max(2, options.steps ?? 32);

  if (sections.length === 2) {
    const [a, b] = sections;
    const pa = resamplePolyline(a.points, steps, a.closed);
    const pb = resamplePolyline(b.points, steps, b.closed);
    if (a.closed && b.closed) {
      const aBigger = polygonArea(pa) >= polygonArea(pb);
      return new CompoundShape([{ outer: aBigger ? pa : pb, holes: [aBigger ? pb : pa] }]);
    }
    return new Polygon([...pa, ...pb.reverse()]);
  }

  if (sections.some(s => s.closed)) {
    throw new Error('loft: a multi-section loft needs open paths. For closed loops use loft(outer, inner) or morph().');
  }
  // Each section is a rung from a start point to an end point; the silhouette is the boundary of all rungs:
  // first rung, chain of end points, last rung backwards, chain of start points backwards.
  const rungs = sections.map(s => resamplePolyline(s.points, steps, false));
  const starts = rungs.map(r => r[0]);
  const ends = rungs.map(r => r[r.length - 1]);
  const chain = (pts: Point[]): Point[] => (options.smooth ? Path.spline(pts, { steps: 8 }).points : pts);
  const lastRung = [...rungs[rungs.length - 1]].reverse();
  return new Polygon([
    ...rungs[0],
    ...chain(ends).slice(1),
    ...lastRung.slice(1),
    ...chain(starts).reverse().slice(1, -1),
  ]);
}

/** Options for `sweep`: steps, scale along the path, alignment and pivot. */
export interface SweepOptions {
  /** Number of stamped copies (default derived from path length and profile size, max 160). */
  steps?: number;
  /** Uniform scale, or a function of t (0..1) returning a number or { x, y }. */
  scale?: number | ((t: number) => number | Point);
  /** Rotate the profile to follow the path tangent; the profile is assumed to point along +x (default false). */
  align?: boolean;
  /** Point of the profile that rides the path (default 'center'). */
  pivot?: AnchorName | Point;
}

function pairwiseUnion(shapes: Shape[]): Shape {
  let level = shapes;
  while (level.length > 1) {
    const next: Shape[] = [];
    for (let i = 0; i < level.length; i += 2) {
      next.push(i + 1 < level.length ? level[i].union(level[i + 1]) : level[i]);
    }
    level = next;
  }
  return level[0];
}

/** Drags `profile` along `along` and returns the union of every stamp. Use more `steps` for large or sharp profiles. */
export function sweep(profile: Shape, along: Path, options: SweepOptions = {}): Shape {
  const pb = profile.bounds;
  const length = polylineLength(along.points, along.closed);
  const stamp = Math.max(1, Math.min(pb.width, pb.height) / 3);
  const steps = Math.max(2, Math.min(160, options.steps ?? Math.ceil(length / stamp) + 1));
  const pivot = resolvePivot(options.pivot, pb);
  const stamps: Shape[] = [];

  for (let i = 0; i < steps; i++) {
    const t = steps === 1 ? 0 : i / (steps - 1);
    const sample = sampleAtDistance(along.points, length * t, along.closed);
    const copy = profile.clone();
    const s = typeof options.scale === 'function' ? options.scale(t) : (options.scale ?? 1);
    const sx = typeof s === 'number' ? s : s.x;
    const sy = typeof s === 'number' ? s : s.y;
    if (sx !== 1 || sy !== 1) copy.scale(sx, sy, pivot);
    if (options.align) copy.rotate((Math.atan2(sample.tangent.y, sample.tangent.x) * 180) / Math.PI, pivot);
    copy.translate(sample.point.x - pivot.x, sample.point.y - pivot.y);
    stamps.push(copy);
  }
  return pairwiseUnion(stamps);
}

/** Options for `morph`: number of samples. */
export interface MorphOptions {
  /** Resampling density used to pair vertices (default 96). */
  samples?: number;
}

function bestShift(a: Point[], b: Point[]): number {
  let best = 0;
  let bestScore = Infinity;
  for (let shift = 0; shift < b.length; shift++) {
    let score = 0;
    for (let i = 0; i < a.length; i++) score += dist(a[i], b[(i + shift) % b.length]);
    if (score < bestScore) { bestScore = score; best = shift; }
  }
  return best;
}

/**
 * Blends two shapes (outer contours) or two paths. `t = 0` returns `a`, `t = 1` returns `b`.
 * Shapes return a Polygon, paths return a Path.
 */
export function morph(a: Shape, b: Shape, t: number, options?: MorphOptions): Polygon;
export function morph(a: Path, b: Path, t: number, options?: MorphOptions): Path;
export function morph(a: Shape | Path, b: Shape | Path, t: number, options: MorphOptions = {}): Polygon | Path {
  const samples = Math.max(8, options.samples ?? 96);
  const isPath = a instanceof Path;
  const closed = isPath ? (a as Path).closed && (b as Path).closed : true;
  const ptsA = resamplePolyline(isPath ? (a as Path).points : (a as Shape).toPoints(), samples, closed);
  let ptsB = resamplePolyline(isPath ? (b as Path).points : (b as Shape).toPoints(), samples, closed);
  if (closed) {
    const shift = bestShift(ptsA, ptsB);
    ptsB = ptsB.map((_, i) => ptsB[(i + shift) % ptsB.length]);
  }
  const out = ptsA.map((p, i) => lerp(p, ptsB[i], t));
  return isPath ? new Path(out, closed) : new Polygon(out);
}

/** Options for `extrude2D`: depth, angle and bevel of the extrusion. */
export interface Extrude2DOptions {
  /** Extrusion depth in pixels (default: 8). */
  depth?: number;
  /** Extrusion angle in degrees (default: 90 = downward in screen coordinates). */
  angle?: number;
  /** Optional bevel inset on the front face (default: 0). */
  bevel?: number;
}

/** Result of `extrude2D`: the front face, the side walls and both combined. */
export interface Extrude2DResult {
  /** The front face shape. */
  front: Shape;
  /** The visible side walls beneath/behind the front face. */
  sides: CompoundShape;
  /** The complete 2.5D silhouette (union of front and sides). */
  all: CompoundShape;
  /** Vector offset { x, y } of the extrusion. */
  offset: Point;
  /** Renders both sides and front in proper depth order. */
  draw(
    ctx: CanvasRenderingContext2D,
    styles?: {
      front?: ShapeStyle | ShapeStyleOptions;
      sides?: ShapeStyle | ShapeStyleOptions;
    }
  ): void;
}

/**
 * Generates 2.5D extrusion geometry with extruded side walls and front face.
 * Ideal for isometric tiles, buttons, coins, platform edges, plaques, and gems.
 */
export function extrude2D(shape: Shape, options: Extrude2DOptions = {}): Extrude2DResult {
  const depth = options.depth ?? 8;
  const angleDeg = options.angle ?? 90;
  const rad = (angleDeg * Math.PI) / 180;
  const dx = Math.cos(rad) * depth;
  const dy = Math.sin(rad) * depth;

  const baseFront = shape.clone();
  const front = options.bevel && options.bevel > 0
    ? baseFront.offset(-options.bevel)
    : baseFront;

  const back = shape.clone().translate(dx, dy);

  // Build bridging quads for every ring
  const wallQuads: Shape[] = [];
  for (const region of shape.regions) {
    const rings = [region.outer, ...region.holes];
    for (const ring of rings) {
      if (ring.length < 2) continue;
      for (let i = 0; i < ring.length; i++) {
        const p1 = ring[i];
        const p2 = ring[(i + 1) % ring.length];
        const p1Back = { x: p1.x + dx, y: p1.y + dy };
        const p2Back = { x: p2.x + dx, y: p2.y + dy };
        wallQuads.push(new Polygon([p1, p2, p2Back, p1Back]));
      }
    }
  }

  // Combine back and all walls
  const wallVolume = wallQuads.length > 0 ? pairwiseUnion(wallQuads) : new CompoundShape([]);
  const all = shape.union(back).union(wallVolume);
  const sides = all.subtract(front);

  return {
    front,
    sides,
    all,
    offset: { x: dx, y: dy },
    draw(ctx, styles = {}) {
      if (styles.sides) sides.draw(ctx, styles.sides);
      if (styles.front) front.draw(ctx, styles.front);
    },
  };
}
