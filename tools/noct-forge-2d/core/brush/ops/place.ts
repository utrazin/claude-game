/**
 * NoctBrush - Placement helpers: attach, align, distribute, scatterAlong.
 *
 * Work on anything placeable (Shape, Path, Group, ...): they only need bounds, anchors and translate.
 */

import type { AnchorRef, Placeable, Point } from '../types.js';
import type { Path } from '../shapes/path.js';

/** Options for `attach`: the anchor on the subject (`from`), the anchor on the target (`at`) and an offset. */
export interface AttachOptions {
  /** Anchor of the subject that is moved onto the target (default 'center'). A Point is absolute. */
  from?: AnchorRef | Point;
  /** Anchor of the target to attach to (default 'center'). Ignored when the target is a Point. */
  at?: AnchorRef | Point;
  /** Extra offset applied after attaching. */
  offset?: Point;
}

function isPlaceable(value: Placeable | Point): value is Placeable {
  return typeof (value as Placeable).anchor === 'function';
}

function resolvePoint(owner: Placeable, anchor: AnchorRef | Point): Point {
  return typeof anchor === 'string' ? owner.anchor(anchor) : anchor;
}

/**
 * Moves `subject` so its `from` anchor lands on the target's `at` anchor.
 * `attach(lid, box, { from: 'bottom', at: 'top', offset: { x: 0, y: -2 } })`
 */
export function attach<T extends Placeable>(subject: T, target: Placeable | Point, options: AttachOptions = {}): T {
  const from = resolvePoint(subject, options.from ?? 'center');
  const to = isPlaceable(target) ? resolvePoint(target, options.at ?? 'center') : target;
  const off = options.offset ?? { x: 0, y: 0 };
  subject.translate(to.x - from.x + off.x, to.y - from.y + off.y);
  return subject;
}

/** Alignment accepted by `align`: 'left', 'right', 'top', 'bottom', 'centerX' or 'centerY'. */
export type AlignMode = 'left' | 'right' | 'top' | 'bottom' | 'centerX' | 'centerY';

/**
 * Aligns items on a shared edge or center line.
 * `reference` picks the line: the union bounds of all items (default) or the first item.
 */
export function align<T extends Placeable>(items: T[], mode: AlignMode, reference: 'bounds' | 'first' = 'bounds'): T[] {
  if (items.length < 2) return items;
  const boxes = items.map(i => i.bounds);
  const ref = reference === 'first'
    ? boxes[0]
    : {
        minX: Math.min(...boxes.map(b => b.minX)),
        maxX: Math.max(...boxes.map(b => b.maxX)),
        minY: Math.min(...boxes.map(b => b.minY)),
        maxY: Math.max(...boxes.map(b => b.maxY)),
      };
  const refCenterX = (ref.minX + ref.maxX) / 2;
  const refCenterY = (ref.minY + ref.maxY) / 2;

  items.forEach((item, i) => {
    const b = boxes[i];
    switch (mode) {
      case 'left': item.translate(ref.minX - b.minX, 0); break;
      case 'right': item.translate(ref.maxX - b.maxX, 0); break;
      case 'top': item.translate(0, ref.minY - b.minY); break;
      case 'bottom': item.translate(0, ref.maxY - b.maxY); break;
      case 'centerX': item.translate(refCenterX - b.center.x, 0); break;
      case 'centerY': item.translate(0, refCenterY - b.center.y); break;
    }
  });
  return items;
}

/** Options for `distribute`: the gap between items. */
export interface DistributeOptions {
  /** Fixed gap between neighbours. When omitted, the first and last items stay put and gaps are equalized. */
  gap?: number;
}

/** Spreads items along an axis in the given order. */
export function distribute<T extends Placeable>(items: T[], axis: 'x' | 'y', options: DistributeOptions = {}): T[] {
  if (items.length < 2) return items;
  const min = (b: Placeable['bounds']) => (axis === 'x' ? b.minX : b.minY);
  const max = (b: Placeable['bounds']) => (axis === 'x' ? b.maxX : b.maxY);
  const move = (item: T, d: number) => (axis === 'x' ? item.translate(d, 0) : item.translate(0, d));

  let gap = options.gap;
  if (gap === undefined) {
    const first = items[0].bounds;
    const last = items[items.length - 1].bounds;
    const sizes = items.reduce((sum, it) => sum + (max(it.bounds) - min(it.bounds)), 0);
    gap = (max(last) - min(first) - sizes) / (items.length - 1);
  }

  let cursor = min(items[0].bounds);
  for (const item of items) {
    const b = item.bounds;
    move(item, cursor - min(b));
    cursor += max(b) - min(b) + gap;
  }
  return items;
}

/** Anything `scatterAlong` can clone and orient: Shape, Path or Group. */
export interface Scatterable extends Placeable {
  clone(): unknown;
  rotate(angleDegrees: number, pivot?: Point | AnchorRef): unknown;
  scale(sx: number, sy?: number, pivot?: Point | AnchorRef): unknown;
}

/** Options for `scatterAlong`: count, spacing, range along the path and rotation. */
export interface ScatterAlongOptions {
  /** Number of copies (default 5, or derived from `spacing`). One copy is placed at the middle of `from..to`. */
  count?: number;
  /** Distance in pixels between copies along the path. Overrides `count`. */
  spacing?: number;
  /** Start of the covered range, normalized arc length 0..1 (default 0). */
  from?: number;
  /** End of the covered range, normalized arc length 0..1 (default 1). */
  to?: number;
  /** Rotate each copy so its +x axis follows the path tangent (default true). */
  align?: boolean;
  /** Extra rotation in degrees applied after aligning. Use -90 to make +x-pointing items stand on the path's left side. */
  rotation?: number;
  /** Anchor of each copy that rides the path (built-in, custom, or absolute-from-bounds Point). Default 'center'. */
  pivot?: AnchorRef;
  /** Pixels to push each copy along the path normal (positive = left of travel direction). */
  offset?: number;
  /** Uniform scale of each copy, or a function of t (0..1) for tapering rows of spikes, teeth or leaves. */
  scale?: number | ((t: number) => number);
}

/**
 * Places copies of `item` along a path: spikes on a spine, beads on a string, leaves on a vine.
 * `item` is cloned for each position (or produced by a factory `(index, t) => item`, for per-copy variation).
 * Returns the placed copies; wrap them with `new Group(copies)` to draw or transform them together.
 */
export function scatterAlong<T extends Scatterable>(
  path: Path,
  item: T | ((index: number, t: number) => T),
  options: ScatterAlongOptions = {},
): T[] {
  const from = options.from ?? 0;
  const to = options.to ?? 1;
  const span = to - from;
  const fullLoop = path.closed && Math.abs(span - 1) < 1e-9;

  let count = options.count ?? 5;
  if (options.spacing && options.spacing > 0) {
    count = Math.max(1, Math.floor((path.length * Math.abs(span)) / options.spacing) + (fullLoop ? 0 : 1));
  }
  count = Math.max(1, Math.floor(count));

  const align = options.align ?? true;
  const out: T[] = [];
  for (let i = 0; i < count; i++) {
    const t = count === 1 ? from + span / 2 : from + span * (fullLoop ? i / count : i / (count - 1));
    const copy = (typeof item === 'function' ? (item as (i: number, t: number) => T)(i, t) : item.clone()) as T;

    const s = typeof options.scale === 'function' ? options.scale(t) : options.scale;
    if (s !== undefined && s !== 1) copy.scale(s, s, options.pivot ?? 'center');

    const tangent = path.tangentAt(t);
    const angle = (align ? (Math.atan2(tangent.y, tangent.x) * 180) / Math.PI : 0) + (options.rotation ?? 0);
    if (angle !== 0) copy.rotate(angle, options.pivot ?? 'center');

    const normal = path.normalAt(t);
    const at = path.pointAt(t);
    const d = options.offset ?? 0;
    attach(copy, { x: at.x + normal.x * d, y: at.y + normal.y * d }, { from: options.pivot ?? 'center' });
    out.push(copy);
  }
  return out;
}