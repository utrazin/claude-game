/**
 * NoctBrush - Sketch Stroke Renderer
 * 
 * Renders rough, expressive hand-drawn sketch lines:
 * - Multi-pass strokes with subtle position/jitter variations
 * - Corner overshoot (cross-over tails) simulating rapid architect/comic sketches
 * - Differentiated line weights per pass (underdrawing + ink accent)
 */

import { createRng } from '../../../random.js';
import type { Point, StrokeOptions } from '../../types.js';
import { renderRibbonStroke } from './ribbon.js';

export function renderSketchStroke(
  ctx: CanvasRenderingContext2D,
  points: Point[],
  attrs: StrokeOptions = {},
  closed = false
): void {
  if (!points || points.length < 2) return;

  const passes = attrs.passes ?? 2;
  const overshoot = attrs.overshoot ?? (closed ? 5.0 : 4.0);
  const baseWidth = attrs.width ?? 2.0;
  const seed = attrs.seed ?? 333;
  const rng = createRng(seed);

  const n = points.length;

  // Calculate average segment length along the path
  let totalLen = 0;
  for (let i = 0; i < n - 1; i++) {
    totalLen += Math.hypot(points[i + 1].x - points[i].x, points[i + 1].y - points[i].y);
  }
  const avgSegmentLen = totalLen / Math.max(1, n - 1);

  // A path is a dense smooth curve if it has many tightly-spaced sub-points (< 6px apart)
  // without sharp intentional corners. Faceted/chiseled curves have longer straight segments (>= 6px).
  const isDenseSmoothCurve = !closed && (n > 22 || (n > 6 && avgSegmentLen < 6.0));

  // 1. CORNER OVERSHOOT MODE (For polygons, faceted shapes, and chiseled curves)
  if (overshoot > 0 && !isDenseSmoothCurve) {
    const edgeCount = closed ? n : n - 1;

    for (let pass = 0; pass < passes; pass++) {
      const passWidth = baseWidth * (pass === 0 ? 1.0 : 0.7);
      const passSeed = seed + pass * 101;
      const passRng = createRng(passSeed);

      for (let i = 0; i < edgeCount; i++) {
        const p1 = points[i];
        const p2 = points[(i + 1) % n];

        const dx = p2.x - p1.x;
        const dy = p2.y - p1.y;
        const len = Math.hypot(dx, dy);
        if (len < 1.0) continue;

        const ux = dx / len;
        const uy = dy / len;
        const nx = -uy;
        const ny =  ux;

        // Jitter per edge
        const jx1 = (passRng.random() - 0.5) * 1.5;
        const jy1 = (passRng.random() - 0.5) * 1.5;
        const jx2 = (passRng.random() - 0.5) * 1.5;
        const jy2 = (passRng.random() - 0.5) * 1.5;

        // Overshoot factor variation per end
        const osStart = overshoot * (0.6 + passRng.random() * 0.8);
        const osEnd   = overshoot * (0.6 + passRng.random() * 0.8);

        // Slight mid-curve bow for sketchy hand-drawn line
        const midT = 0.5;
        const bow = (passRng.random() - 0.5) * 1.2;
        const midX = p1.x + dx * midT + nx * bow + (jx1 + jx2) / 2;
        const midY = p1.y + dy * midT + ny * bow + (jy1 + jy2) / 2;

        const startPt: Point = {
          x: p1.x - ux * osStart + jx1,
          y: p1.y - uy * osStart + jy1,
        };
        const endPt: Point = {
          x: p2.x + ux * osEnd + jx2,
          y: p2.y + uy * osEnd + jy2,
        };

        renderRibbonStroke(ctx, [startPt, { x: midX, y: midY }, endPt], {
          ...attrs,
          width: passWidth,
          closed: false,
          taperStart: true,
          taperEnd: true,
          caliperNoise: 0.25,
          jitter: 0.5,
          seed: passSeed + i * 17,
        });
      }
    }
    return;
  }

  // 2. STANDARD MULTI-PASS CONTINUOUS SKETCH
  for (let pass = 0; pass < passes; pass++) {
    const passWidth = baseWidth * (pass === 0 ? 1.0 : 0.65);
    const passSeed = seed + pass * 79;
    const passRng = createRng(passSeed);

    const jitteredPoints: Point[] = points.map(p => ({
      x: p.x + (passRng.random() - 0.5) * (pass === 0 ? 0.6 : 1.4),
      y: p.y + (passRng.random() - 0.5) * (pass === 0 ? 0.6 : 1.4),
    }));

    renderRibbonStroke(ctx, jitteredPoints, {
      ...attrs,
      width: passWidth,
      closed,
      taperStart: true,
      taperEnd: true,
      caliperNoise: 0.28,
      jitter: 0.7,
      seed: passSeed,
    });
  }
}
