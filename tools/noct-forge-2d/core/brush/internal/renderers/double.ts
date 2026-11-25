/**
 * NoctBrush - Double Line Stroke Renderer
 * 
 * Renders twin parallel strokes with an offset gap:
 * - Ideal for heraldic shields, ornamental borders, parchment cards, and game HUD frames
 * - Computes clean normal offsets for open paths or closed perimeter loops
 */

import type { Point, StrokeOptions } from '../../types.js';
import { renderRibbonStroke } from './ribbon.js';

export function renderDoubleStroke(
  ctx: CanvasRenderingContext2D,
  points: Point[],
  attrs: StrokeOptions = {},
  closed = false
): void {
  if (!points || points.length < 2) return;

  const baseWidth = attrs.width ?? 1.6;
  const doubleOpt = typeof attrs.double === 'object' ? attrs.double : {};
  const gap = doubleOpt.distance ?? Math.max(3.0, baseWidth * 1.8);
  const halfGap = gap / 2;

  const n = points.length;
  const innerPoints: Point[] = [];
  const outerPoints: Point[] = [];

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
    let nx = 0, ny = 0;
    if (tLen > 0.0001) {
      nx = -ty / tLen;
      ny =  tx / tLen;
    }

    outerPoints.push({
      x: curr.x + nx * halfGap,
      y: curr.y + ny * halfGap,
    });

    innerPoints.push({
      x: curr.x - nx * halfGap,
      y: curr.y - ny * halfGap,
    });
  }

  // Draw outer ribbon
  renderRibbonStroke(ctx, outerPoints, {
    ...attrs,
    width: baseWidth,
    closed,
    seed: (attrs.seed ?? 100) + 1,
  });

  // Draw inner ribbon
  renderRibbonStroke(ctx, innerPoints, {
    ...attrs,
    width: baseWidth,
    closed,
    seed: (attrs.seed ?? 100) + 2,
  });
}
