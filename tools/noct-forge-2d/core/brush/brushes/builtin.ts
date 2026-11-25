/**
 * NoctBrush - Built-in brushes. Registered as a side effect of importing `@core/brush`.
 *
 * Each built-in is a thin `defineBrush` wrapper around an internal renderer, so project brushes can
 * `extends` any of them: ribbon, clean, sketch, chalk, double, bristle, profile, dashed.
 */

import { renderRibbonStroke } from '../internal/renderers/ribbon.js';
import { renderSketchStroke } from '../internal/renderers/sketch.js';
import { renderChalkStroke } from '../internal/renderers/chalk.js';
import { renderDoubleStroke } from '../internal/renderers/double.js';
import { renderBristleStroke } from '../internal/renderers/bristle.js';
import { renderStampStroke } from '../internal/renderers/stamp.js';
import { polylineLength, slicePolyline } from '../internal/points.js';
import { brushRegistry } from '../internal/brush-registry.js';
import { Path } from '../shapes/path.js';
import type { LineCap } from '../types.js';
import { defineBrush } from './define.js';

const stamp = defineBrush({
  name: 'stamp',
  draw({ ctx, points, closed }, params) {
    renderStampStroke(ctx, points, params, closed);
  },
});

const ribbon = defineBrush({
  name: 'ribbon',
  doc: 'Expressive calligraphic vector stroke with subtle width variation and round/miter joins',
  params: {
    width: { default: 2, doc: 'Stroke width in pixels', min: 0.5 },
    color: { default: '#1c1714', doc: 'Stroke color (hex, rgb, rgba)' },
    caliperNoise: { default: 0.16, doc: 'Micro-caliper width jitter factor (0..0.4)' },
    taperEnd: { default: true, doc: 'Smoothly taper stroke tip' },
  },
  draw: ({ ctx, points }, p) => renderRibbonStroke(ctx, points, p),
});

const clean = defineBrush({
  name: 'clean',
  doc: 'Crisp uniform-width vector stroke without jitter or calligraphic variation',
  params: {
    width: { default: 2, doc: 'Stroke width in pixels', min: 0.5 },
    color: { default: '#1c1714', doc: 'Stroke color' },
  },
  draw: ({ ctx, points }, p) => renderRibbonStroke(ctx, points, p),
});

const sketch = defineBrush({
  name: 'sketch',
  doc: 'Multi-pass handdrawn blueprint stroke with corner overshoots and subtle jitter',
  params: {
    width: { default: 2, doc: 'Base stroke width in pixels' },
    color: { default: '#1c1714', doc: 'Stroke color' },
    passes: { default: 2, doc: 'Number of overlapping passes', min: 1, max: 4 },
    overshoot: { default: 4, doc: 'Pixel overshoot length at corners and junctions' },
  },
  draw: ({ ctx, points, closed }, p) => renderSketchStroke(ctx, points, p, closed),
});

const chalk = defineBrush({
  name: 'chalk',
  doc: 'Dry-media chalk stroke with porous grain noise and organic edge erosion',
  params: {
    width: { default: 3.2, doc: 'Stroke width in pixels' },
    color: { default: '#1c1714', doc: 'Stroke color' },
    grain: { default: 0.5, doc: 'Grain noise frequency factor (0..1)' },
    intensity: { default: 1.0, doc: 'Pigment deposit intensity/pressure (0.5 to 2.0)' },
  },
  draw: ({ ctx, points, closed }, p) => renderChalkStroke(ctx, points, p, closed),
});

const double = defineBrush({
  name: 'double',
  doc: 'Twin parallel border lines with configurable gap for decorative crests, frames and banners',
  params: {
    width: { default: 1.6, doc: 'Width of each individual line' },
    color: { default: '#1c1714', doc: 'Line color' },
  },
  draw: ({ ctx, points, closed }, p) => renderDoubleStroke(ctx, points, p, closed),
});

const bristle = defineBrush({
  name: 'bristle',
  doc: 'Multi-fiber dry brush stroke simulating traditional coarse horsehair brush marks',
  params: {
    width: { default: 3.0, doc: 'Overall stroke bundle width' },
    color: { default: '#1c1714', doc: 'Bristle color' },
    bristles: { default: 5, doc: 'Number of independent bristle fibers', min: 2, max: 12 },
  },
  draw: ({ ctx, points, closed }, p) => renderBristleStroke(ctx, points, p, closed),
});

/**
 * Variable-width solid line. Width at normalized position t (0..1 along the path) is `width * profile(t)`.
 * Open lines get `cap` ends; closed loops use a constant-width ring.
 */
const profile = defineBrush({
  name: 'profile',
  doc: 'Variable-width solid line shaped by a mathematical profile function of arc-length t (0..1)',
  params: {
    profile: { default: ((_t: number) => 1) as (t: number) => number, doc: 'Width multiplier along the line, t in 0..1' },
    cap: { default: 'round' as LineCap, doc: 'End cap of open lines' },
  },
  defaults: {
    width: 4,
  },
  draw: ({ ctx, points, closed }, p) => {
    const width = p.width ?? 4;
    const shape = new Path(points, closed).toShape({
      width: closed ? width : (t: number) => Math.max(0.05, width * p.profile(t)),
      cap: p.cap,
    });
    shape.fill(ctx, p.color ?? '#1c1714');
  },
});

/** Parameters of the `dashed` brush: dash length, gap and offset. */
export interface DashedParams {
  /** Dash length in pixels (default 8). */
  dash?: number;
  /** Gap length in pixels (default 6). */
  gap?: number;
  /** Starting phase offset along the pattern in pixels (default 0). */
  offset?: number;
}

/**
 * Dashed line brush using geometry rewriting hook. Extends ribbon and slices the polyline
 * into cleanly proportioned dashes before drawing.
 */
const dashed = defineBrush<DashedParams>({
  name: 'dashed',
  extends: 'ribbon',
  doc: 'Dashed line renderer with configurable dash length, gap and phase offset',
  params: {
    dash: { default: 8, doc: 'Dash segment length in pixels', min: 1 },
    gap: { default: 6, doc: 'Gap segment length in pixels', min: 1 },
    offset: { default: 0, doc: 'Phase offset in pixels along the pattern' },
  },
  path: ({ points, closed }, params) => {
    const totalLen = polylineLength(points, closed);
    if (totalLen < 1e-3) return [{ points, closed: false }];
    const dashLen = Math.max(1, params.dash ?? 8);
    const gapLen = Math.max(1, params.gap ?? 6);
    const cycle = dashLen + gapLen;
    const phase = ((params.offset ?? 0) % cycle + cycle) % cycle;

    const segments: { points: typeof points; closed: boolean }[] = [];
    let d = -phase;
    while (d < totalLen) {
      const d0 = Math.max(0, d);
      const d1 = Math.min(totalLen, d + dashLen);
      if (d1 > d0 + 0.1) {
        const t0 = d0 / totalLen;
        const t1 = d1 / totalLen;
        const pts = slicePolyline(points, t0, t1, closed);
        if (pts.length >= 2) segments.push({ points: pts, closed: false });
      }
      d += cycle;
    }
    return segments;
  },
});

brushRegistry.markBuiltins();

/** Factories for every built-in brush: `brushes.sketch({ width: 2, color })` returns a StrokeStyle. */
/** The built-in brush factories, for example `brushes.ribbon({ width: 3 })`. */
export const brushes = { ribbon, clean, sketch, chalk, double, bristle, profile, dashed };
