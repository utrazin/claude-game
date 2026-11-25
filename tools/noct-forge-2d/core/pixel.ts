/**
 * NoctAssetForge - Pixel Art Utilities
 * 
 * Lightweight, zero-dependency helper routines for authentic, discrete pixel art.
 * Ensures zero sub-pixel antialiasing, clean Bresenham lines/circles and character matrix
 * rendering (ASCII sprites), all drawn through `PixelCanvas`.
 */

import { BAYER_4X4 } from './noise.js';
import type { Drawable } from './asset.js';

/** Options for `PixelCanvas.fromShape`: fill color, alpha threshold, dithering and target canvas. */
export interface FromShapeOptions {
  /** Fill color string for the rasterized vector shape (default: '#ffffff') */
  color?: string;
  /** Alias for color */
  fill?: string;
  /** Block multiplier pixel size (default: 1) */
  pixelSize?: number;
  /** Alpha cutoff threshold from 0 to 255 (default: 128) */
  alphaThreshold?: number;
  /** Anti-aliasing conversion: 'none' for hard cutoff, 'dither' for Bayer 4x4 matrix */
  antialiasing?: 'none' | 'dither';
  /** Optional existing PixelCanvas to stamp onto */
  target?: PixelCanvas;
}

/**
 * High-level, discrete Pixel Art Canvas for programmatic sprite and asset generation.
 * Encapsulates an integer grid, scaling, ASCII matrices, lines, circles, and Bayer dithering.
 * Batches adjacent same-color pixels during render() for maximum performance.
 */
export class PixelCanvas {
  readonly width: number;
  readonly height: number;
  readonly pixelSize: number;
  private readonly grid: (string | null)[][];

  constructor(width: number, height: number, pixelSize: number = 1) {
    this.width = Math.floor(width);
    this.height = Math.floor(height);
    this.pixelSize = Math.max(1, Math.floor(pixelSize));
    this.grid = Array.from({ length: this.height }, () => Array(this.width).fill(null));
  }

  /**
   * Rasterizes any vector Shape or Path from @core/brush directly into the discrete pixel grid.
   * Enables hybrid vector-to-pixel modeling (design silhouettes with Bézier curves or CSG, then
   * detail or dither on the discrete integer grid).
   */
  static fromShape(
    shape: Drawable,
    width: number,
    height: number,
    options: FromShapeOptions = {}
  ): PixelCanvas {
    const pc = options.target ?? new PixelCanvas(width, height, options.pixelSize ?? 1);
    if (typeof document === 'undefined') return pc;

    const offCanvas = document.createElement('canvas');
    offCanvas.width = width;
    offCanvas.height = height;
    const offCtx = offCanvas.getContext('2d', { willReadFrequently: true });
    if (!offCtx) return pc;

    const fillColor = options.color ?? options.fill ?? '#ffffff';
    if (typeof shape.draw === 'function') {
      shape.draw(offCtx, { fill: fillColor });
    } else if (typeof shape.fill === 'function') {
      shape.fill(offCtx, fillColor);
    } else if (typeof shape.stroke === 'function') {
      shape.stroke(offCtx, { color: fillColor, width: 1 });
    }

    const imgData = offCtx.getImageData(0, 0, width, height);
    const data = imgData.data;
    const threshold = options.alphaThreshold ?? 128;
    const isDither = options.antialiasing === 'dither';

    for (let y = 0; y < height; y++) {
      const rowOffset = y * width * 4;
      const bayerRow = BAYER_4X4[y % 4];
      for (let x = 0; x < width; x++) {
        const idx = rowOffset + x * 4;
        const a = data[idx + 3];
        if (a === 0) continue;

        let isOpaque = false;
        if (isDither) {
          isOpaque = (a / 255) >= bayerRow[x % 4];
        } else {
          isOpaque = a >= threshold;
        }

        if (isOpaque) {
          const r = data[idx];
          const g = data[idx + 1];
          const b = data[idx + 2];
          const hex = options.color ?? options.fill
            ? (options.color ?? options.fill!)
            : `#${r.toString(16).padStart(2, '0')}${g.toString(16).padStart(2, '0')}${b.toString(16).padStart(2, '0')}`;
          pc.set(x, y, hex);
        }
      }
    }

    return pc;
  }

  /**
   * Sets a single pixel at grid coordinates (x, y).
   */
  set(x: number, y: number, color: string | null): this {
    const ix = Math.floor(x);
    const iy = Math.floor(y);
    if (ix >= 0 && ix < this.width && iy >= 0 && iy < this.height) {
      this.grid[iy][ix] = color;
    }
    return this;
  }

  /**
   * Gets the color at grid coordinates (x, y).
   */
  get(x: number, y: number): string | null {
    const ix = Math.floor(x);
    const iy = Math.floor(y);
    if (ix >= 0 && ix < this.width && iy >= 0 && iy < this.height) {
      return this.grid[iy][ix];
    }
    return null;
  }

  /**
   * Clears the entire grid or fills it with a background color.
   */
  clear(color: string | null = null): this {
    for (let y = 0; y < this.height; y++) {
      this.grid[y].fill(color);
    }
    return this;
  }

  /**
   * Draws a horizontal pixel span on the grid.
   */
  hSpan(y: number, x0: number, x1: number, color: string): this {
    const startX = Math.max(0, Math.min(Math.floor(x0), Math.floor(x1)));
    const endX = Math.min(this.width - 1, Math.max(Math.floor(x0), Math.floor(x1)));
    const iy = Math.floor(y);
    if (iy < 0 || iy >= this.height) return this;

    for (let x = startX; x <= endX; x++) {
      this.grid[iy][x] = color;
    }
    return this;
  }

  /**
   * Draws a vertical pixel span on the grid.
   */
  vSpan(x: number, y0: number, y1: number, color: string): this {
    const startY = Math.max(0, Math.min(Math.floor(y0), Math.floor(y1)));
    const endY = Math.min(this.height - 1, Math.max(Math.floor(y0), Math.floor(y1)));
    const ix = Math.floor(x);
    if (ix < 0 || ix >= this.width) return this;

    for (let y = startY; y <= endY; y++) {
      this.grid[y][ix] = color;
    }
    return this;
  }

  /**
   * Draws a filled or outlined rectangle.
   */
  rect(x: number, y: number, w: number, h: number, color: string, filled: boolean = true): this {
    const ix = Math.floor(x);
    const iy = Math.floor(y);
    const iw = Math.floor(w);
    const ih = Math.floor(h);

    if (filled) {
      for (let r = 0; r < ih; r++) {
        this.hSpan(iy + r, ix, ix + iw - 1, color);
      }
    } else {
      this.hSpan(iy, ix, ix + iw - 1, color);
      this.hSpan(iy + ih - 1, ix, ix + iw - 1, color);
      if (ih > 2) {
        this.vSpan(ix, iy + 1, iy + ih - 2, color);
        this.vSpan(ix + iw - 1, iy + 1, iy + ih - 2, color);
      }
    }
    return this;
  }

  /**
   * Draws a discrete line using Bresenham's algorithm.
   */
  line(x0: number, y0: number, x1: number, y1: number, color: string): this {
    let cx0 = Math.floor(x0);
    let cy0 = Math.floor(y0);
    const cx1 = Math.floor(x1);
    const cy1 = Math.floor(y1);

    const dx = Math.abs(cx1 - cx0);
    const dy = -Math.abs(cy1 - cy0);
    const sx = cx0 < cx1 ? 1 : -1;
    const sy = cy0 < cy1 ? 1 : -1;
    let err = dx + dy;

    while (true) {
      this.set(cx0, cy0, color);
      if (cx0 === cx1 && cy0 === cy1) break;
      const e2 = 2 * err;
      if (e2 >= dy) {
        err += dy;
        cx0 += sx;
      }
      if (e2 <= dx) {
        err += dx;
        cy0 += sy;
      }
    }
    return this;
  }

  /**
   * Draws a circle using the Midpoint (Bresenham) circle algorithm.
   */
  circle(xc: number, yc: number, radius: number, color: string, filled: boolean = false): this {
    const r = Math.floor(radius);
    const ox = Math.floor(xc);
    const oy = Math.floor(yc);

    if (r <= 0) {
      return this.set(ox, oy, color);
    }

    let x = 0;
    let y = r;
    let d = 3 - 2 * r;

    const plot = (px: number, py: number) => {
      if (filled) {
        this.hSpan(oy + py, ox - px, ox + px, color);
        this.hSpan(oy - py, ox - px, ox + px, color);
        this.hSpan(oy + px, ox - py, ox + py, color);
        this.hSpan(oy - px, ox - py, ox + py, color);
      } else {
        this.set(ox + px, oy + py, color);
        this.set(ox - px, oy + py, color);
        this.set(ox + px, oy - py, color);
        this.set(ox - px, oy - py, color);
        this.set(ox + py, oy + px, color);
        this.set(ox - py, oy + px, color);
        this.set(ox + py, oy - px, color);
        this.set(ox - py, oy - px, color);
      }
    };

    while (y >= x) {
      plot(x, y);
      x++;
      if (d > 0) {
        y--;
        d = d + 4 * (x - y) + 10;
      } else {
        d = d + 4 * x + 6;
      }
    }
    return this;
  }

  /**
   * Draws a character matrix / ASCII sprite directly onto the grid.
   * Characters mapped to 'transparent', '.', ' ' or undefined are skipped.
   */
  drawMatrix(
    matrix: string[] | string[][],
    palette: Record<string, string>,
    ox: number = 0,
    oy: number = 0
  ): this {
    const startX = Math.floor(ox);
    const startY = Math.floor(oy);

    for (let r = 0; r < matrix.length; r++) {
      const row = matrix[r];
      for (let c = 0; c < row.length; c++) {
        const char = row[c];
        if (char === '.' || char === ' ') continue;
        const color = palette[char];
        if (!color || color === 'transparent') continue;
        this.set(startX + c, startY + r, color);
      }
    }
    return this;
  }

  /**
   * Applies Bayer 4x4 ordered dithering across a rectangular region.
   * Useful for authentic retro shading, lighting gradients, and texture ramps.
   */
  ditherRect(
    x: number,
    y: number,
    w: number,
    h: number,
    colorBase: string,
    colorDither: string,
    threshold: number = 0.5
  ): this {
    const ix = Math.floor(x);
    const iy = Math.floor(y);
    const iw = Math.floor(w);
    const ih = Math.floor(h);

    for (let r = 0; r < ih; r++) {
      const py = iy + r;
      const bRow = BAYER_4X4[Math.abs(py) % 4];
      for (let c = 0; c < iw; c++) {
        const px = ix + c;
        const t = bRow[Math.abs(px) % 4];
        const color = threshold >= t ? colorDither : colorBase;
        this.set(px, py, color);
      }
    }
    return this;
  }

  /**
   * Rasterizes a convex or arbitrary simple polygon using horizontal scanline conversion.
   * Supports vertices as tuples [x, y] or point objects { x, y }.
   */
  fillPolygon(points: Array<[number, number] | { x: number; y: number }>, color: string): this {
    if (points.length < 3) return this;

    const normalized: [number, number][] = points.map(p =>
      Array.isArray(p) ? [p[0], p[1]] : [p.x, p.y]
    );

    let minY = this.height;
    let maxY = 0;
    for (const [_, py] of normalized) {
      if (py < minY) minY = py;
      if (py > maxY) maxY = py;
    }
    minY = Math.max(0, Math.floor(minY));
    maxY = Math.min(this.height - 1, Math.ceil(maxY));

    for (let y = minY; y <= maxY; y++) {
      const nodeX: number[] = [];
      const cy = y + 0.5;

      for (let i = 0; i < normalized.length; i++) {
        const j = (i + 1) % normalized.length;
        const [x0, y0] = normalized[i];
        const [x1, y1] = normalized[j];

        if ((y0 < cy && y1 >= cy) || (y1 < cy && y0 >= cy)) {
          const t = (cy - y0) / (y1 - y0);
          nodeX.push(x0 + t * (x1 - x0));
        }
      }

      nodeX.sort((a, b) => a - b);
      for (let k = 0; k < nodeX.length; k += 2) {
        if (k + 1 < nodeX.length) {
          const startX = Math.round(nodeX[k]);
          const endX = Math.round(nodeX[k + 1]);
          this.hSpan(y, startX, endX, color);
        }
      }
    }

    return this;
  }

  /**
   * Adds an automatic boundary outline around all non-transparent pixels.
   * Essential for classic retro fighting-game cel shading, character borders, and sprite isolation.
   */
  addOutline(outlineColor: string, includeDiagonals: boolean = true): this {
    const toFill: [number, number][] = [];
    const deltas = includeDiagonals
      ? [
          [-1, 0], [1, 0], [0, -1], [0, 1],
          [-1, -1], [1, -1], [-1, 1], [1, 1],
        ]
      : [
          [-1, 0], [1, 0], [0, -1], [0, 1],
        ];

    for (let y = 0; y < this.height; y++) {
      for (let x = 0; x < this.width; x++) {
        if (this.grid[y][x] === null) {
          let hasNeighbor = false;
          for (const [dx, dy] of deltas) {
            const nx = x + dx;
            const ny = y + dy;
            if (nx >= 0 && nx < this.width && ny >= 0 && ny < this.height) {
              if (this.grid[ny][nx] !== null) {
                hasNeighbor = true;
                break;
              }
            }
          }
          if (hasNeighbor) {
            toFill.push([x, y]);
          }
        }
      }
    }

    for (const [x, y] of toFill) {
      this.grid[y][x] = outlineColor;
    }
    return this;
  }

  /**
   * Renders the discrete pixel grid onto a Canvas 2D context.
   * Batches adjacent same-color pixels into horizontal spans for maximum performance.
   *
   * @param ctx Target canvas 2D rendering context
   * @param dx Canvas X offset (default: 0)
   * @param dy Canvas Y offset (default: 0)
   */
  render(ctx: CanvasRenderingContext2D, dx: number = 0, dy: number = 0): void {
    const size = this.pixelSize;
    const offX = Math.floor(dx);
    const offY = Math.floor(dy);

    for (let y = 0; y < this.height; y++) {
      const row = this.grid[y];
      let runColor: string | null = null;
      let runStart = 0;

      for (let x = 0; x <= this.width; x++) {
        const color = x < this.width ? row[x] : null;

        if (color !== runColor) {
          if (runColor && runColor !== 'transparent') {
            ctx.fillStyle = runColor;
            ctx.fillRect(
              offX + runStart * size,
              offY + y * size,
              (x - runStart) * size,
              size
            );
          }
          runColor = color;
          runStart = x;
        }
      }
    }
  }
}
