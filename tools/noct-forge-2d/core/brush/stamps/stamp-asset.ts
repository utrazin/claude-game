/**
 * NoctBrush - StampAsset
 * 
 * Unifies raster stamp / dab textures for both strokes (lines) and fills (scatter textures).
 * Caches image data for high performance context.drawImage calls.
 */

export interface StampAssetOptions {
  /** HTML Image, Canvas, or OffscreenCanvas to use as stamp source. */
  source?: HTMLImageElement | HTMLCanvasElement | OffscreenCanvas | ImageBitmap;
  /**
   * @deprecated Procedural draw functions are non-canonical. Export procedural assets to PNG instead.
   */
  draw?: (ctx: CanvasRenderingContext2D, size: number) => void;
  /** The native resolution size of the stamp (default: 64 or image natural width) */
  baseSize?: number;
}

const stampCache = new Map<string, Promise<StampAsset>>();

/** A raster stamp (an image or a canvas) used as a brush tip or as a scatter texture. */
export class StampAsset {
  public canvas: HTMLCanvasElement | OffscreenCanvas | HTMLImageElement | ImageBitmap;
  public size: number;
  public width: number;
  public height: number;

  constructor(options: StampAssetOptions) {
    this.size = options.baseSize ?? 64;
    this.width = this.size;
    this.height = this.size;

    if (options.source) {
      this.canvas = options.source;
      const naturalW = (options.source as HTMLImageElement).naturalWidth;
      const canvasW = (options.source as HTMLCanvasElement).width;
      this.width = naturalW || canvasW || this.size;

      const naturalH = (options.source as HTMLImageElement).naturalHeight;
      const canvasH = (options.source as HTMLCanvasElement).height;
      this.height = naturalH || canvasH || this.size;

      this.size = options.baseSize ?? Math.max(this.width, this.height);
    } else if (options.draw) {
      // Backward compatibility for existing procedural draws until migrated
      if (typeof OffscreenCanvas !== 'undefined') {
        this.canvas = new OffscreenCanvas(this.size, this.size);
      } else {
        const c = document.createElement('canvas');
        c.width = this.size;
        c.height = this.size;
        this.canvas = c;
      }
      
      const ctx = this.canvas.getContext('2d') as CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;
      if (ctx) {
        options.draw(ctx as CanvasRenderingContext2D, this.size);
      }
    } else {
      throw new Error('StampAsset requires a raster image source or loadStamp(url).');
    }
  }

}

/** Decodes a stamp image from a URL. Used only by `loadStamp`, which owns caching and path normalization. */
async function loadStampImage(url: string, baseSize?: number): Promise<StampAsset> {
  const img = new Image();
  img.crossOrigin = 'anonymous';
  img.src = url;

  if (img.decode) {
    await img.decode();
  } else {
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = (e) => reject(new Error(`Failed to load stamp image from ${url}: ${e}`));
    });
  }

  return new StampAsset({ source: img, baseSize });
}

/**
 * Normalizes and loads a raster stamp from a path or URL.
 * Automatically caches instances so duplicate calls reuse the same loaded image.
 * 
 * Supports:
 * - Global stamps: `@stamps/artistic/oil_bristle.png` or `stamps/artistic/oil_bristle.png` -> `/stamps/artistic/oil_bristle.png`
 * - Local/absolute URLs: `/projects/.../resources/stamps/my_stamp.png`
 */
export async function loadStamp(pathOrUrl: string, baseSize?: number): Promise<StampAsset> {
  let url = pathOrUrl;
  if (url.startsWith('@stamps/')) {
    url = url.replace('@stamps/', '/stamps/');
  } else if (url.startsWith('stamps/')) {
    url = '/' + url;
  }

  if (stampCache.has(url)) {
    return stampCache.get(url)!;
  }

  const promise = loadStampImage(url, baseSize);
  stampCache.set(url, promise);
  return promise;
}
