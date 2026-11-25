/**
 * NoctBrush - Hierarchical Group Container
 * 
 * Aggregates multiple Shape, Path, or nested Group instances into a single logical entity.
 * Implements Placeable (bounds, center, anchor, translate) with collective vector transforms.
 * Optionally draws or strokes every child with a shared style.
 */

import type {
  Point,
  AnchorRef,
  BoundingBox,
  Placeable,
  ShapeStyleOptions,
  StrokeOptions,
} from '../types.js';
import type { Transformable } from '../types.js';
import { Shape } from './shape.js';
import { Path } from './path.js';
import { resolveAnchor, boundsFromExtents } from '../internal/geometry.js';
import { AnchorSet } from '../internal/anchors.js';
import { resolvePivot, translateVisitor, rotateVisitor, scaleVisitor } from '../internal/points.js';
import type { ShapeStyle } from '../styles/shape-style.js';
import type { StrokeStyle } from '../styles/stroke-style.js';

/** Anything a Group can contain: a Shape, a Path or another Group. */
export type GroupItem = Shape | Path | Group;
export type ItemStyle = ShapeStyle | ShapeStyleOptions | StrokeStyle | StrokeOptions;

export interface GroupEntry {
  item: GroupItem;
  style?: ItemStyle;
}

/** A set of shapes and paths that move, rotate and draw as one. */
export class Group implements Placeable, Transformable {
  public items: GroupItem[] = [];
  public entries: GroupEntry[] = [];

  constructor(itemsOrEntries: (GroupItem | GroupEntry)[] = []) {
    for (const entry of itemsOrEntries) {
      if ('item' in entry) {
        this.entries.push(entry);
        this.items.push(entry.item);
      } else {
        this.entries.push({ item: entry });
        this.items.push(entry);
      }
    }
  }

  /**
   * Adds an item to the group with an optional deferred style.
   */
  add(item: GroupItem, style?: ItemStyle): this {
    this.items.push(item);
    this.entries.push({ item, style });
    return this;
  }

  /**
   * Removes a child item from the group.
   */
  remove(item: GroupItem): this {
    const idx = this.items.indexOf(item);
    if (idx !== -1) {
      this.items.splice(idx, 1);
      this.entries.splice(idx, 1);
    }
    return this;
  }

  /**
   * Flattens nested groups into a flat array of leaf Shape and Path instances.
   */
  flatten(): (Shape | Path)[] {
    const out: (Shape | Path)[] = [];
    for (const item of this.items) {
      if (item instanceof Group) {
        out.push(...item.flatten());
      } else {
        out.push(item);
      }
    }
    return out;
  }

  /**
   * Aggregates the bounding box of all children.
   */
  get bounds(): BoundingBox {
    let minX = Infinity, maxX = -Infinity;
    let minY = Infinity, maxY = -Infinity;

    for (const item of this.items) {
      const b = item.bounds;
      if (b.minX < minX) minX = b.minX;
      if (b.maxX > maxX) maxX = b.maxX;
      if (b.minY < minY) minY = b.minY;
      if (b.maxY > maxY) maxY = b.maxY;
    }

    if (minX === Infinity) return boundsFromExtents(0, 0, 0, 0);
    return boundsFromExtents(minX, minY, Math.max(minX, maxX), Math.max(minY, maxY));
  }
  /**
   * The geometric center of the group's bounding box.
   */
  get center(): Point {
    return this.bounds.center;
  }

  /**
   * Resolves a named anchor point on the group's collective bounding box.
   */
  anchor(name: AnchorRef): Point {
    return this._anchors?.get(name) ?? resolveAnchor(this.bounds, name);
  }

  private _anchors?: AnchorSet;

  /**
   * Registers a custom named anchor on the group (absolute Point). It follows the group's
   * translate/rotate/scale/moveTo and clone(). Built-in names cannot be redefined.
   */
  setAnchor(name: string, at: Point): this {
    (this._anchors ??= new AnchorSet()).set(name, at);
    return this;
  }

  /** Names of the custom anchors set with setAnchor. */
  get anchorNames(): string[] {
    return this._anchors?.names() ?? [];
  }

  // ==========================================
  // COLLECTIVE 2D VECTOR TRANSFORMS
  // ==========================================

  /**
   * Translates all children in the group by (dx, dy).
   */
  translate(dx: number, dy: number): this {
    for (const item of this.items) {
      item.translate(dx, dy);
    }
    this._anchors?.visit(translateVisitor(dx, dy));
    return this;
  }

  /**
   * Rotates all children in the group around a shared pivot point (defaults to group center).
   */
  rotate(angleDegrees: number, pivot?: Point | AnchorRef): this {
    const piv = resolvePivot(pivot, this.bounds, this._anchors);
    for (const item of this.items) {
      item.rotate(angleDegrees, piv);
    }
    this._anchors?.visit(rotateVisitor(angleDegrees, piv));
    return this;
  }

  /**
   * Scales all children in the group around a shared pivot point (defaults to group center).
   */
  scale(sx: number, sy = sx, pivot?: Point | AnchorRef): this {
    const piv = resolvePivot(pivot, this.bounds, this._anchors);
    for (const item of this.items) {
      item.scale(sx, sy, piv);
    }
    this._anchors?.visit(scaleVisitor(sx, sy, piv));
    return this;
  }

  /**
   * Moves the group so that `myAnchor` aligns with `target`.
   */
  moveTo(target: Point, myAnchor: AnchorRef = 'center'): this {
    const current = this.anchor(myAnchor);
    const dx = target.x - current.x;
    const dy = target.y - current.y;
    return this.translate(dx, dy);
  }

  /**
   * Deep clones the group and all its children.
   */
  clone(): Group {
    const clonedEntries: GroupEntry[] = this.entries.map(e => ({
      item: e.item.clone(),
      style: e.style,
    }));
    const copy = new Group(clonedEntries);
    if (this._anchors) for (const name of this._anchors.names()) copy.setAnchor(name, this._anchors.get(name)!);
    return copy;
  }

  /**
   * Renders every child in the group. If an entry has an assigned style,
   * it uses that style; otherwise falls back to the provided fallbackStyle.
   */
  render(ctx: CanvasRenderingContext2D, fallbackStyle?: ItemStyle): this {
    for (const entry of this.entries) {
      const item = entry.item;
      const s = entry.style ?? fallbackStyle;
      if (item instanceof Group) {
        item.render(ctx, s);
      } else if (item instanceof Path) {
        if (s) item.stroke(ctx, s as StrokeStyle | StrokeOptions);
      } else if (typeof (item as Shape).draw === 'function') {
        (item as Shape).draw(ctx, (s as ShapeStyle | ShapeStyleOptions) ?? {});
      }
    }
    return this;
  }

  /**
   * Renders every child in the group using its own .draw() method.
   */
  draw(ctx: CanvasRenderingContext2D, style?: ShapeStyle | ShapeStyleOptions): this {
    return this.render(ctx, style);
  }

  /**
   * Strokes every child in the group.
   */
  stroke(ctx: CanvasRenderingContext2D, strokeStyle?: StrokeStyle | StrokeOptions): this {
    for (const item of this.items) {
      if (typeof (item as Shape).stroke === 'function') {
        (item as Shape).stroke(ctx, strokeStyle);
      }
    }
    return this;
  }
}
