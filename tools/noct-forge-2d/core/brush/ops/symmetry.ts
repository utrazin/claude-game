/**
 * NoctBrush - Symmetry operations: mirror and revolve.
 *
 * - mirror:  symmetrize a shape, or build a full outline from half a contour
 * - revolve: silhouette of a solid of revolution (2D lathe) from a half profile
 */

import { Shape } from '../shapes/shape.js';
import { Path } from '../shapes/path.js';
import { dist } from '../internal/points.js';

/** Options for `mirror`: axis, position and which side to keep. */
export interface MirrorOptions {
  /** `'x'` reflects left <-> right across a vertical line (default); `'y'` reflects top <-> bottom across a horizontal line. */
  axis?: 'x' | 'y';
  /** Coordinate of the mirror line (x for axis 'x', y for axis 'y'). Overrides `side`. */
  at?: number;
  /**
   * Which edge of the item's bounds is the mirror line when `at` is omitted. `'max'` (default) mirrors toward
   * increasing coordinates: a LEFT half (axis 'x') is reflected to its right. Use `'min'` for a right half.
   */
  side?: 'min' | 'max';
  /** Paths only: return a closed loop (joins the last reflected point back to the first). Default false. */
  close?: boolean;
}

function mirrorLine(item: Shape | Path, options: MirrorOptions): number {
  if (options.at !== undefined) return options.at;
  const b = item.bounds;
  const min = (options.side ?? 'max') === 'min';
  if ((options.axis ?? 'x') === 'x') return min ? b.minX : b.maxX;
  return min ? b.minY : b.maxY;
}

/**
 * Builds a symmetric whole from one half.
 *
 * - Shape: returns the union of the shape and its reflection.
 * - Path: walks the path, then the reflected path backwards, so half a contour becomes a full outline.
 *   Use `{ close: true }` for a fillable loop: `mirror(halfOutline, { close: true }).close()`.
 */
export function mirror(item: Shape, options?: MirrorOptions): Shape;
export function mirror(item: Path, options?: MirrorOptions): Path;
export function mirror(item: Shape | Path, options: MirrorOptions = {}): Shape | Path {
  const axis = options.axis ?? 'x';
  const at = mirrorLine(item, options);
  if (item instanceof Path) {
    const joined = Path.concat(item, item.flip(axis, at).reverse());
    if (!options.close) return joined;
    const pts = joined.points;
    if (pts.length > 1 && dist(pts[0], pts[pts.length - 1]) < 0.001) pts.pop();
    return new Path(pts, true);
  }
  return item.union(item.flip(axis, at));
}

/** Options for `revolve`: axis, position and steps. */
export interface RevolveOptions {
  /** Axis of symmetry: `'x'` = vertical axis, profile reflected left <-> right (default); `'y'` = horizontal axis. */
  axis?: 'x' | 'y';
  /** Coordinate of the axis. Default: the profile's min edge, i.e. the profile is the right (or bottom) half. */
  at?: number;
  /** Optionally resample the profile to this many points before mirroring. */
  steps?: number;
}

/**
 * 2D lathe: the silhouette of a solid of revolution. Draw ONE side of the object as an open path
 * (e.g. the right half of a vase from rim to foot) and get the full filled shape.
 * The ends of the profile are joined to the axis with straight lines (flat rim and base).
 */
export function revolve(profile: Path, options: RevolveOptions = {}): Shape {
  const source = options.steps ? profile.resample(options.steps) : profile;
  return mirror(source, { axis: options.axis, at: options.at, side: 'min', close: true }).close();
}
