/**
 * NoctBrush - StampScatter Texture
 * 
 * Scatters StampAssets randomly within a bounded region or clipped shape.
 * Ideal for procedural foliage, grit, debris, or any scattered pattern.
 */

import { createRng } from '../../random.js';
import type { Point, Texture, Bounds, ShapeLike } from '../types.js';
import type { Shape } from '../shapes/shape.js';
import type { StampAsset } from '../stamps/stamp-asset.js';

/** Options for `StampScatter`: stamp asset, count, scale and rotation. */
export interface StampScatterOptions {
  /** The stamp asset to scatter */
  asset: StampAsset;
  /** Number of instances to scatter (default: 50) */
  count?: number;
  /** Scatter area density multiplier */
  density?: number;
  /** Minimum scale factor (default: 0.5) */
  minScale?: number;
  /** Maximum scale factor (default: 1.2) */
  maxScale?: number;
  /** Base scale modifier (default: 1.0) */
  scale?: number;
  /** Base opacity (0.0 to 1.0, default: 1.0) */
  alpha?: number;
  /** Amount of random opacity variation (0.0 to 1.0, default: 0) */
  alphaNoise?: number;
  /** Whether the stamps should rotate randomly (default: true) */
  randomRotation?: boolean;
  /** Fixed rotation in degrees (if randomRotation is false) */
  angle?: number;
  /** Deterministic PRNG seed */
  seed?: number;
}

/** Texture that scatters a stamp asset over a shape, with random scale and rotation. */
export class StampScatter implements Texture<StampScatterOptions> {
  public attrs: StampScatterOptions;

  constructor(attrs: StampScatterOptions) {
    this.attrs = { ...attrs };
  }

  render(
    ctx: CanvasRenderingContext2D,
    target: Shape | Bounds,
    overrides: Partial<StampScatterOptions> = {}
  ): void {
    if (isShape(target)) {
      target.clip(ctx, () => {
        const bounds = target.bounds;
        this.renderInternal(ctx, bounds, overrides);
      });
    } else {
      this.renderInternal(ctx, target, overrides);
    }
  }

  private renderInternal(
    ctx: CanvasRenderingContext2D,
    bounds: Bounds,
    overrides: Partial<StampScatterOptions> = {}
  ): void {
    const effective = { ...this.attrs, ...overrides };
    if (!effective.asset) return;

    const count = effective.count ?? (effective.density != null ? Math.round(effective.density * 100) : 50);
    const scaleBase = effective.scale ?? 1.0;
    const minS = effective.minScale ?? 0.5;
    const maxS = effective.maxScale ?? 1.2;
    const alphaBase = effective.alpha ?? 1.0;
    const alphaNoise = effective.alphaNoise ?? 0.0;
    const randRot = effective.randomRotation ?? true;
    const angleBase = effective.angle ?? 0;
    const rng = createRng(effective.seed ?? 303);

    const stampCanvas = effective.asset.canvas;
    const stampSize = effective.asset.size;

    ctx.save();

    for (let i = 0; i < count; i++) {
      const u = rng.random();
      const v = rng.random();
      
      const px = bounds.x + u * bounds.width;
      const py = bounds.y + v * bounds.height;
      const finalScale = scaleBase * (minS + rng.random() * (maxS - minS));
      const finalAlpha = Math.max(0, Math.min(1, alphaBase - rng.random() * alphaNoise));
      const angle = randRot ? rng.random() * Math.PI * 2 : (angleBase * Math.PI) / 180;

      ctx.save();
      ctx.globalAlpha = finalAlpha;
      ctx.translate(px, py);
      if (angle !== 0) ctx.rotate(angle);

      const renderSize = stampSize * finalScale;
      const halfSize = renderSize / 2;
      
      ctx.drawImage(stampCanvas, -halfSize, -halfSize, renderSize, renderSize);
      ctx.restore();
    }

    ctx.restore();
  }
}

function isShape(target: Shape | Bounds): target is Shape {
  return 'toPoints' in target && typeof target.toPoints === 'function';
}
