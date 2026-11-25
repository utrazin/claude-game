/**
 * NoctBrush - Brush Registry Re-export (for internal backwards compatibility).
 *
 * Prefer importing `defineBrush`, `listBrushes` and `describeBrush` from `@core/brush`.
 */

export { brushRegistry, type BrushRegistry } from '../internal/brush-registry.js';
export type {
  BrushLine,
  BrushParams,
  BrushBase,
  BrushDraw,
  BrushGeometry,
  BrushSegment,
  BrushDefinition,
  BrushDescription,
} from './define.js';
