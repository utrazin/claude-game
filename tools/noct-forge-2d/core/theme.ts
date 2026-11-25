/**
 * NoctAssetForge - Project Theme Definition Helper
 * 
 * Provides typed ergonomics and autocompletion for project-level theme tokens
 * (_theme.ts) without enforcing rigid styling constraints.
 */

import type { StrokeOptions } from './brush/types.js';
import type { StrokeStyle } from './brush/styles/stroke-style.js';
import type { ShapeStyle } from './brush/styles/shape-style.js';

/** Shape of a project theme passed to `defineTheme`: palette, ramps, strokes and shape styles. */
export interface ThemeDefinition {
  /** Project color palette hex or rgba mappings */
  palette?: Record<string, string>;
  /** Gradient ramps and shading steps */
  ramps?: Record<string, Record<string, string>>;
  /** Preconfigured StrokeStyle instances or options */
  strokes?: Record<string, StrokeStyle | StrokeOptions>;
  /** Preconfigured ShapeStyle instances */
  shapes?: Record<string, ShapeStyle | Record<string, any>>;
  [key: string]: any;
}

/**
 * Declares a project-level design system / theme token object.
 * Preserves strict literal types for palette keys and stroke presets.
 */
export function defineTheme<T extends ThemeDefinition>(theme: T): T {
  return theme;
}
