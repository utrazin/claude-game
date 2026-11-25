/**
 * NoctBrush - Custom Procedural Texture Base
 * 
 * Provides an extensible base class for project-specific procedural textures
 * (e.g. wood grain, marble veins, dragon scales, hex shields) without modifying core.
 */

import type { Texture, ShapeLike, Bounds } from '../types.js';

/** Base class for custom textures. Extend it and implement `render`. */
export abstract class BaseTexture<O = Record<string, any>> implements Texture<O> {
  public attrs: O;

  constructor(attrs: O = {} as O) {
    this.attrs = { ...attrs };
  }

  /**
   * Renders the procedural texture inside a Shape or rectangular bounding box.
   * 
   * @param ctx Target Canvas 2D rendering context
   * @param target Host Shape (automatically clipped) or rectangular Bounds
   * @param overrides Optional per-render attribute overrides
   */
  abstract render(
    ctx: CanvasRenderingContext2D,
    target: ShapeLike | Bounds,
    overrides?: Partial<O>
  ): void;
}
