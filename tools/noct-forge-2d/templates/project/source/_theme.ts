/**
 * Project Design System & Theme Tokens
 *
 * Single source of truth for palettes, ramps, strokes, and shape styles.
 * Never hardcode raw hex colors or stroke settings in asset files.
 */

import { StrokeStyle, ShapeStyle, alpha } from '@core/brush';

export const PALETTES = {
  bg: '#14121a',
  surface: '#242030',
  surfaceLit: '#38324a',
  accent: '#e6a15c',
  accentLit: '#ffc885',
  ink: '#0d0b12',
  white: '#f5f3fa',
};

export const RAMPS = {
  surface: {
    lit: PALETTES.surfaceLit,
    base: PALETTES.surface,
    dark: PALETTES.bg,
  },
  accent: {
    lit: PALETTES.accentLit,
    base: PALETTES.accent,
    dark: '#9e6231',
  },
};

export const STROKES = {
  bold: new StrokeStyle({
    width: 4,
    color: PALETTES.ink,
    renderer: 'ribbon',
    join: 'round',
  }),

  fine: new StrokeStyle({
    width: 1.5,
    color: PALETTES.ink,
    renderer: 'clean',
  }),

  // A built-in renderer with a join; define custom brushes with defineBrush (guide 03) when needed:
  inkArt: new StrokeStyle({
    width: 3.5,
    color: PALETTES.ink,
    renderer: 'ribbon',
    join: 'round',
  }),
};

export const SHAPE_STYLES = {
  panel: new ShapeStyle({
    fill: PALETTES.surface,
    stroke: STROKES.bold,
    shadow: {
      color: alpha(PALETTES.ink, 0.4),
      x: 0,
      y: 4,
      blur: 8,
    },
  }),

  // Volume with cel-shaded lighting:
  gem: new ShapeStyle({
    fill: RAMPS.accent.base,
    celShade: {
      shade: RAMPS.accent.dark,
      lightPivot: 'topLeft',
      litScale: 0.84,
    },
    stroke: STROKES.fine,
  }),
};
