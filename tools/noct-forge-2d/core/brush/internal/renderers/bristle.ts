/**
 * NoctBrush - Bristle / Dry Brush Stroke Renderer
 * 
 * Simulates coarse bristle brushes and dry Japanese sumi-e ink:
 * - Longitudinal fibers running along the trajectory with random skip-outs
 * - Organic pressure-dependent spread and gaps between bristles
 */

import { createRng } from '../../../random.js';
import type { Point, StrokeOptions } from '../../types.js';
import { renderRibbonStroke } from './ribbon.js';

export function renderBristleStroke(
  ctx: CanvasRenderingContext2D,
  points: Point[],
  attrs: StrokeOptions = {},
  closed = false
): void {
  if (!points || points.length < 2) return;

  const baseWidth = attrs.width ?? 3.0;
  const bristleCount = attrs.bristles ?? Math.max(4, Math.round(baseWidth * 1.6));
  const seed = attrs.seed ?? 888;
  const n = points.length;

  for (let b = 0; b < bristleCount; b++) {
    const bristleRng = createRng(seed + b * 67);
    const offsetRatio = (b / (bristleCount - 1) - 0.5) * 2;
    const baseOffset = offsetRatio * (baseWidth * 0.45);
    const fiberWidth = (baseWidth / bristleCount) * (0.6 + bristleRng.random() * 0.7);

    // Skip certain bristles entirely or partially for dry-brush look
    if (bristleRng.random() < 0.15) continue;

    const fiberPoints: Point[] = [];
    for (let i = 0; i < n; i++) {
      const prev = points[(i - 1 + n) % n];
      const curr = points[i];
      const next = points[(i + 1) % n];

      let tx: number, ty: number;
      if (!closed && i === 0) {
        tx = next.x - curr.x;
        ty = next.y - curr.y;
      } else if (!closed && i === n - 1) {
        tx = curr.x - prev.x;
        ty = curr.y - prev.y;
      } else {
        tx = next.x - prev.x;
        ty = next.y - prev.y;
      }

      const tLen = Math.hypot(tx, ty);
      const nx = tLen > 0 ? -ty / tLen : 0;
      const ny = tLen > 0 ?  tx / tLen : 0;

      const jitter = (bristleRng.random() - 0.5) * 0.8;
      const d = baseOffset + jitter;

      fiberPoints.push({
        x: curr.x + nx * d,
        y: curr.y + ny * d,
      });
    }

    ctx.save();
    ctx.globalAlpha = 0.6 + bristleRng.random() * 0.35;
    renderRibbonStroke(ctx, fiberPoints, {
      ...attrs,
      width: fiberWidth,
      closed,
      taperStart: true,
      taperEnd: true,
      caliperNoise: 0.3,
      jitter: 0.6,
      seed: seed + b * 211,
    });
    ctx.restore();
  }
}
