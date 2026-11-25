/**
 * @internal Brush registry (line types) engine. Not reachable from the public entry points:
 * projects use `defineBrush()`, `listBrushes()` and `describeBrush()` from `@core/brush`.
 *
 * A *brush* is a named line renderer with typed default parameters that may inherit from another brush.
 * It may also own a geometry hook (`path`) that rewrites the polyline (dashes, zigzags, ...) before drawing.
 */

import type { Point } from '../types.js';
import {
  fingerprint,
  specDefaults,
  typeOfDefault,
  type ParamDescription,
  type ParamSpec,
} from '../params.js';
import type {
  BrushBase,
  BrushDefinition,
  BrushDescription,
  BrushDraw,
  BrushGeometry,
  BrushLine,
  BrushParams,
  BrushSegment,
} from '../brushes/define.js';

interface BrushEntry {
  name: string;
  doc?: string;
  parent?: string;
  specs: Record<string, ParamSpec>;
  defaults: Record<string, unknown>;
  draw?: BrushDraw<any>;
  geometry?: BrushGeometry<any>;
  builtin: boolean;
  fingerprint: string;
}

function mergeDefined(target: Record<string, unknown>, source: Record<string, unknown>): void {
  for (const key of Object.keys(source)) {
    if (source[key] !== undefined) target[key] = source[key];
  }
}

function toSegments(result: (Point[] | BrushSegment)[], fallbackClosed: boolean): BrushSegment[] {
  return result
    .map((item: Point[] | BrushSegment) => (Array.isArray(item) ? { points: item, closed: false } : { points: item.points, closed: item.closed ?? fallbackClosed }))
    .filter((seg: BrushSegment) => seg.points.length >= 2);
}

class BrushRegistry {
  private readonly entries = new Map<string, BrushEntry>();

  define(def: BrushDefinition<any>): void {
    if (!def.name) throw new Error('defineBrush: "name" is required.');
    if (!def.draw && !def.extends && !def.path) {
      throw new Error(`defineBrush("${def.name}"): provide "draw", "path" or "extends".`);
    }
    if (def.extends) {
      if (def.extends === def.name) throw new Error(`defineBrush("${def.name}"): a brush cannot extend itself.`);
      if (!this.entries.has(def.extends)) {
        throw new Error(`defineBrush("${def.name}"): parent brush "${def.extends}" is not defined. ${this.hint()}`);
      }
    }

    const specs = (def.params ?? {}) as Record<string, ParamSpec>;
    const defaults = { ...specDefaults(specs), ...(def.defaults ?? {}) } as Record<string, unknown>;
    const entry: BrushEntry = {
      name: def.name,
      doc: def.doc,
      parent: def.extends,
      specs,
      defaults,
      draw: def.draw,
      geometry: def.path,
      builtin: false,
      fingerprint: '',
    };
    entry.fingerprint = fingerprint([def.extends, def.doc, specs, defaults, def.draw?.toString(), def.path?.toString()]);

    const existing = this.entries.get(def.name);
    if (existing) {
      // Re-evaluating the same module (HMR, repeated imports) is harmless and stays silent.
      if (existing.fingerprint === entry.fingerprint) return;
      if (!def.override) {
        throw new Error(
          `defineBrush("${def.name}"): a different brush with this name is already registered` +
            `${existing.builtin ? ' (built-in)' : ''}. Pick another name, or pass { override: true } to replace it deliberately.`,
        );
      }
    }
    this.entries.set(def.name, entry);
  }

  /** Marks every brush registered so far as built-in (called once by brushes/builtin.ts). */
  markBuiltins(): void {
    for (const entry of this.entries.values()) entry.builtin = true;
  }

  has(name: string): boolean {
    return this.entries.has(name);
  }

  names(): string[] {
    return [...this.entries.keys()].sort();
  }

  private hint(): string {
    return `Registered brushes: ${this.names().join(', ')}.`;
  }

  /** Root-to-leaf inheritance chain for a brush. */
  private chain(name: string): BrushEntry[] {
    const out: BrushEntry[] = [];
    const seen = new Set<string>();
    let current: string | undefined = name;
    while (current) {
      if (seen.has(current)) throw new Error(`Brush inheritance cycle at "${current}".`);
      seen.add(current);
      const entry = this.entries.get(current);
      if (!entry) throw new Error(`Unknown brush "${current}". ${this.hint()} Add new ones with defineBrush().`);
      out.unshift(entry);
      current = entry.parent;
    }
    return out;
  }

  /** Defaults of the whole chain merged with explicit options (explicit wins, `undefined` is ignored). */
  resolveParams(name: string, options: Record<string, unknown>): Record<string, unknown> {
    const params: Record<string, unknown> = {};
    for (const entry of this.chain(name)) mergeDefined(params, entry.defaults);
    mergeDefined(params, options);
    return params;
  }

  describe(name: string): BrushDescription {
    const chain = this.chain(name);
    const defaults = this.resolveParams(name, {});
    const params: ParamDescription[] = [];
    const keys = new Set<string>();
    for (const entry of chain) {
      for (const key of Object.keys(entry.specs)) keys.add(key);
      for (const key of Object.keys(entry.defaults)) keys.add(key);
    }
    for (const key of [...keys].sort()) {
      // The nearest spec in the chain (leaf wins) documents the parameter.
      const owner = [...chain].reverse().find(entry => entry.specs[key]);
      const spec = owner?.specs[key];
      const value = defaults[key];
      params.push({
        name: key,
        type: typeOfDefault(spec ? spec.default : value),
        default: value,
        doc: spec?.doc,
        min: spec?.min,
        max: spec?.max,
        options: spec?.options,
        declaredBy: owner?.name ?? name,
      });
    }
    const leaf = chain[chain.length - 1];
    return {
      name,
      doc: [...chain].reverse().find(entry => entry.doc)?.doc,
      extends: leaf.parent,
      chain: chain.map(entry => entry.name),
      builtin: leaf.builtin,
      reshapesLine: chain.some(entry => entry.geometry),
      params,
    };
  }

  render(name: string, line: BrushLine, options: Record<string, unknown>): void {
    const chain = this.chain(name); // root -> leaf
    const params = this.resolveParams(name, options);

    // 1. Geometry hooks (root -> leaf) may split or reshape the polyline into several segments.
    let segments: BrushSegment[] = [{ points: line.points, closed: line.closed }];
    for (const entry of chain) {
      if (!entry.geometry) continue;
      const hook = entry.geometry;
      segments = segments.flatMap(seg =>
        toSegments(
          hook({ points: seg.points as Point[], closed: seg.closed ?? false }, { ...params, closed: seg.closed, renderer: entry.name } as BrushParams<any>),
          seg.closed ?? false,
        ),
      );
    }

    // 2. Each segment goes through the nearest draw at or above the leaf.
    for (const seg of segments) {
      const segLine: BrushLine = { ctx: line.ctx, points: seg.points as Point[], closed: seg.closed ?? false };
      const segParams = { ...params, closed: segLine.closed };

      // Executes the nearest draw at or above chain[index]; `renderer` always names the brush that owns the draw.
      const run = (index: number, current: Record<string, unknown>): void => {
        let i = index;
        while (i >= 0 && !chain[i].draw) i--;
        if (i < 0) return;
        const owner = chain[i];
        const base: BrushBase = (overrides?: Record<string, unknown>) => run(i - 1, { ...current, ...(overrides ?? {}) });
        owner.draw!(segLine, { ...current, renderer: owner.name } as BrushParams<any>, base);
      };
      run(chain.length - 1, segParams);
    }
  }
}

/** The single process-wide registry. */
export const brushRegistry = new BrushRegistry();
export type { BrushRegistry };
