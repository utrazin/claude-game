import { createNoise2D } from '../../../noise.js';
import type { Point, StrokeOptions } from '../../types.js';
import { resolveTrajectory } from '../trajectory.js';

export function renderChalkStroke(
  ctx: CanvasRenderingContext2D,
  points: Point[],
  attrs: StrokeOptions = {},
  closed = false
): void {
  if (!points || points.length < 2) return;

  const baseWidth = attrs.width ?? 3.2;
  const color = attrs.color ?? '#1c1714';
  const seed = attrs.seed ?? 555;
  
  // Dry media parameters
  const grain = attrs.grain ?? 0.5; 
  const intensity = (attrs as any).intensity ?? 1.0; 

  // Higher grain = finer noise frequency
  const grainScale = (1.1 - grain); 
  
  const toothNoise = createNoise2D(seed);

  const nodes = resolveTrajectory(points, {
    width: baseWidth,
    closed: attrs.closed ?? closed,
    taperStart: attrs.taperStart ?? true,
    taperEnd: attrs.taperEnd ?? true,
    caliperNoise: 0.15, // Let the trajectory wiggle slightly
    jitter: 0,
    seed,
  });

  if (nodes.length < 2) return;

  ctx.save();
  ctx.fillStyle = color;

  let nextDist = 0;
  const totalLength = nodes[nodes.length - 1].distance;
  let currentIndex = 0;
  const stepSize = 0.4; 

  while (nextDist <= totalLength) {
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

    if (w > 0.1) {
      // Denser rendering across the width for softer/intense media
      const perpSteps = Math.ceil(w * 2.5); 
      
      for (let p = 0; p <= perpSteps; p++) {
        const cross = (p / perpSteps) - 0.5;
        const px = x + nx * w * cross;
        const py = y + ny * w * cross;
        
        // Evaluate paper tooth: -1 to 1
        const noiseVal = toothNoise(px * grainScale, py * grainScale);
        
        // Center density is high, edges fall off
        const coreBias = 1.2 - Math.pow(Math.abs(cross * 2.0), 1.3) * 2.2;
        
        // Intensity multiplies the chance of pigment catching the tooth
        const pigmentProb = (noiseVal + coreBias) * intensity;
        
        // Threshold
        if (pigmentProb > 0.0) {
          ctx.globalAlpha = Math.min(1.0, pigmentProb * 1.5);
          ctx.fillRect(px, py, 1.2, 1.2);
        }
      }
    }
    nextDist += stepSize;
  }

  ctx.restore();
}
