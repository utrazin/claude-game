/**
 * NoctAssetForge - Core Procedural Noise Utilities
 * 
 * Simple wrappers around simplex-noise with seed support and Fractal Brownian Motion (FBM).
 * Useful for textures, organic variation, wear patterns, heightmaps, and masks.
 */

import {
  createNoise2D as baseCreateNoise2D,
  createNoise3D as baseCreateNoise3D,
  type NoiseFunction2D,
  type NoiseFunction3D,
} from 'simplex-noise';
import { createRng } from './random.js';

export type { NoiseFunction2D, NoiseFunction3D };

/**
 * Creates a 2D simplex noise function with optional seed.
 * Returns values roughly in range [-1, 1].
 */
export function createNoise2D(seed?: number | string): NoiseFunction2D {
  if (seed === undefined) {
    return baseCreateNoise2D();
  }
  const rng = createRng(seed);
  return baseCreateNoise2D(rng.random);
}

/**
 * Creates a 3D simplex noise function with optional seed.
 * Returns values roughly in range [-1, 1].
 */
export function createNoise3D(seed?: number | string): NoiseFunction3D {
  if (seed === undefined) {
    return baseCreateNoise3D();
  }
  const rng = createRng(seed);
  return baseCreateNoise3D(rng.random);
}

/** Options for `fbm2D`: octaves, persistence, lacunarity and scale. */
export interface FbmOptions {
  /** Number of noise octaves (layers of detail). Default: 4 */
  octaves?: number;
  /** Amplitude decay per octave (roughness). Default: 0.5 */
  persistence?: number;
  /** Frequency multiplier per octave. Default: 2.0 */
  lacunarity?: number;
  /** Initial scale/frequency multiplier. Default: 1.0 */
  scale?: number;
}

/**
 * Evaluates Fractal Brownian Motion (fBm) in 2D.
 * Combines multiple octaves of noise for realistic natural textures (stone, clouds, wood, terrain).
 * Returns normalized value in roughly [0, 1].
 */
export function fbm2D(
  noise: NoiseFunction2D,
  x: number,
  y: number,
  options: FbmOptions = {}
): number {
  const octaves = options.octaves ?? 4;
  const persistence = options.persistence ?? 0.5;
  const lacunarity = options.lacunarity ?? 2.0;
  const initialScale = options.scale ?? 1.0;

  let total = 0;
  let frequency = initialScale;
  let amplitude = 1.0;
  let maxValue = 0;

  for (let i = 0; i < octaves; i++) {
    total += (noise(x * frequency, y * frequency) * 0.5 + 0.5) * amplitude;
    maxValue += amplitude;
    amplitude *= persistence;
    frequency *= lacunarity;
  }

  return total / maxValue;
}

/**
 * Linear value remapping helper: maps val from [inMin, inMax] to [outMin, outMax]
 */
export function mapRange(
  val: number,
  inMin: number,
  inMax: number,
  outMin: number,
  outMax: number
): number {
  return outMin + ((val - inMin) / (inMax - inMin)) * (outMax - outMin);
}

/**
 * Clamps a number between min and max
 */
export function clamp(val: number, min: number, max: number): number {
  return Math.min(Math.max(val, min), max);
}

/** The 4x4 Bayer threshold matrix, normalized to (0, 1), used for ordered dithering. */
export const BAYER_4X4: number[][] = [
  [0, 8, 2, 10],
  [12, 4, 14, 6],
  [3, 11, 1, 9],
  [15, 7, 13, 5],
].map(row => row.map(v => (v + 0.5) / 16));
