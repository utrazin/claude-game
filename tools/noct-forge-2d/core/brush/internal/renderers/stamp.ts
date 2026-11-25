/**
 * NoctBrush - Stamp Renderer
 * 
 * Draws brush tips (StampAsset) along a resolved trajectory.
 * Used for replicating digital painting behaviors like Photoshop/Krita stamps.
 */

import { createRng } from '../../../random.js';
import type { Point, StrokeOptions } from '../../types.js';
import { resolveTrajectory } from '../trajectory.js';

export function renderStampStroke(
  ctx: CanvasRenderingContext2D,
  points: Point[],
  attrs: StrokeOptions = {},
  closed = false
): void {
  if (!points || points.length < 2) return;
  const config = attrs.stamp;
  if (!config || !config.asset) return;

  const isClosed = attrs.closed ?? closed;
  const nodes = resolveTrajectory(points, {
    width: attrs.width ?? 2.0,
    closed: isClosed,
    taperStart: attrs.taperStart,
    taperEnd: attrs.taperEnd,
    caliperNoise: attrs.caliperNoise,
    jitter: attrs.jitter,
    seed: attrs.seed,
    scale: attrs.scale,
    join: attrs.join,
    miterLimit: attrs.miterLimit
  });

  if (nodes.length < 2) return;

  const stamp = config.asset;
  const spacingRatio = config.spacing ?? 0.25;
  const scatterAmt = config.scatter ?? 0;
  const sizeNoise = config.sizeNoise ?? 0;
  const angleDynamics = config.angleDynamics ?? 'none';
  const color = attrs.color ?? '#000000';

  const seed = attrs.seed ?? 123;
  const rng = createRng(seed);

  let nextDist = 0;
  const totalLength = nodes[nodes.length - 1].distance;

  // We loop over the distance accumulated, and interpolate between nodes
  let currentIndex = 0;

  // Helper to colorize stamp if necessary (using a tint approach)
  // For maximum performance, if we are painting solid colors, we might pre-tint the stamp or use globalCompositeOperation.
  // For now, we'll draw the stamp directly and use source-in if we need to tint, or just rely on the stamp's own color.
  // If the user wants a colored dab, they can generate the stamp with that color via `draw` in StampAsset.
  
  while (nextDist <= totalLength) {
    // Find the segment containing nextDist
    while (currentIndex < nodes.length - 1 && nodes[currentIndex + 1].distance < nextDist) {
      currentIndex++;
    }

    if (currentIndex >= nodes.length - 1) break;

    const curr = nodes[currentIndex];
    const next = nodes[currentIndex + 1];

    const segmentLen = next.distance - curr.distance;
    const t = segmentLen > 0 ? (nextDist - curr.distance) / segmentLen : 0;

    const x = curr.x + (next.x - curr.x) * t;
    const y = curr.y + (next.y - curr.y) * t;
    const nx = curr.nx + (next.nx - curr.nx) * t;
    const ny = curr.ny + (next.ny - curr.ny) * t;
    const w = curr.width + (next.width - curr.width) * t;

    // Apply scatter
    const scatterOffset = (rng.random() - 0.5) * scatterAmt * w;
    const fx = x + nx * scatterOffset;
    const fy = y + ny * scatterOffset;

    // Apply size noise
    const sizeMod = 1.0 + (rng.random() - 0.5) * sizeNoise;
    const finalSize = w * sizeMod;

    // Determine angle
    let angle = 0;
    if (angleDynamics === 'tangent') {
      angle = Math.atan2(ny, nx);
    } else if (angleDynamics === 'random') {
      angle = rng.random() * Math.PI * 2;
    }

    ctx.save();
    ctx.translate(fx, fy);
    if (angle !== 0) ctx.rotate(angle);
    
    // Draw the cached offscreen canvas centered
    const hw = finalSize / 2;
    ctx.drawImage(stamp.canvas, -hw, -hw, finalSize, finalSize);

    ctx.restore();

    nextDist += Math.max(1, w * spacingRatio); // ensure we make progress
  }
}
