/**
 * NoctBrush - StrokeStyle Class
 * 
 * Encapsulates stroke visual attributes and provides immutable derivation (.with).
 * Delegates rendering to the unified BrushRegistry.
 */

import type { Point, StrokeOptions } from '../types.js';
import { brushRegistry } from '../brushes/registry.js';
// Ensure builtins are registered
import '../brushes/builtin.js';

/** A stroke: width, color, renderer and options. Immutable; derive variants with `.with`. */
export class StrokeStyle<P extends object = {}> {
  public readonly attrs: Readonly<StrokeOptions & P>;

  constructor(attrs: (StrokeOptions & P) = {} as (StrokeOptions & P)) {
    this.attrs = Object.freeze({ ...attrs });
  }

  get width(): number | undefined {
    return this.attrs.width;
  }

  get color(): string | undefined {
    return this.attrs.color;
  }

  get renderer(): string | undefined {
    return this.attrs.renderer;
  }

  /**
   * Derives a new StrokeStyle with specific attribute overrides (deep merges nested objects like double).
   * Preserves and merges custom brush parameters.
   */
  with<P2 extends object = P>(overrides: Partial<StrokeOptions & P & P2>): StrokeStyle<P & P2> {
    const merged = {
      ...this.attrs,
      ...overrides,
    } as unknown as (StrokeOptions & P & P2);
    if (this.attrs.double || overrides.double) {
      (merged as StrokeOptions).double = {
        ...this.attrs.double,
        ...overrides.double,
      };
    }
    return new StrokeStyle<P & P2>(merged);
  }

  /**
   * Renders a polyline or closed loop onto the 2D context using this style.
   * Dispatches dynamically to the registered brush corresponding to attrs.renderer.
   */
  render(ctx: CanvasRenderingContext2D, points: Point[], closed = false): void {
    if (!points || points.length < 2) return;
    const isClosed = this.attrs.closed ?? closed;
    const rendererName = this.attrs.renderer ?? 'ribbon';

    brushRegistry.render(
      rendererName,
      { ctx, points, closed: isClosed },
      { ...this.attrs, closed: isClosed }
    );
  }
}
