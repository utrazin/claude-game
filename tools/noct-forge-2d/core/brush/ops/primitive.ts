/**
 * NoctBrush - definePrimitive: register parametric polygon / shape generators (gear, leaf, gem, buckle, etc.).
 *
 * Supports typed parameters, parameter specs (for documentation and discovery), default merging,
 * holes / compound shapes, and introspection via `listPrimitives()` and `describePrimitive()`.
 */

import type { Point, PolygonOptions } from '../types.js';
import type { ParamDescription, ParamSpecs } from '../params.js';
import { specDefaults, typeOfDefault, fingerprint } from '../params.js';
import { Polygon } from '../shapes/polygon.js';
import { CompoundShape, Shape } from '../shapes/shape.js';

/** Placement and finishing options accepted by every primitive. */
export type PrimitivePlacement = Partial<Pick<PolygonOptions, 'cx' | 'cy' | 'center' | 'rotation' | 'roundness' | 'wobble' | 'seed'>>;

/** What a primitive generator returns: a point list, or an outer contour with holes. */
export type PrimitivePointsResult = Point[] | { outer: Point[]; holes?: Point[][] };

/** Function that returns the points of a primitive from its parameters. */
export type PrimitiveGenerator<P extends object> = (params: P) => PrimitivePointsResult;

/** Definition of a custom primitive, passed to `definePrimitive`. */
export interface PrimitiveDefinition<P extends object> {
  name: string;
  doc?: string;
  /** Parent primitive to inherit defaults and generator from. */
  extends?: string;
  params?: ParamSpecs<P>;
  defaults?: Partial<P>;
  generate?: PrimitiveGenerator<P>;
  override?: boolean;
}

/** Introspection result of a primitive, returned by `describePrimitive`. */
export interface PrimitiveDescription {
  name: string;
  doc?: string;
  extends?: string;
  chain: string[];
  params: ParamDescription[];
}

/** A factory created by `definePrimitive`. Call it with parameters and placement options. */
export type PrimitiveFactory<P extends object> = ((params?: Partial<P>, placement?: PrimitivePlacement) => Shape) & {
  readonly primitiveName: string;
};

interface PrimitiveEntry {
  name: string;
  doc?: string;
  parent?: string;
  specs: Record<string, any>;
  defaults: Record<string, unknown>;
  generate?: PrimitiveGenerator<any>;
  fingerprint: string;
}

class PrimitiveRegistry {
  private readonly entries = new Map<string, PrimitiveEntry>();

  define(def: PrimitiveDefinition<any>): void {
    if (!def.name) throw new Error('definePrimitive: "name" is required.');
    if (!def.generate && !def.extends) {
      throw new Error(`definePrimitive("${def.name}"): provide "generate" or "extends".`);
    }
    if (def.extends) {
      if (def.extends === def.name) throw new Error(`definePrimitive("${def.name}"): a primitive cannot extend itself.`);
      if (!this.entries.has(def.extends)) {
        throw new Error(`definePrimitive("${def.name}"): parent primitive "${def.extends}" is not defined. Registered: ${this.names().join(', ')}.`);
      }
    }

    const specs = (def.params ?? {}) as Record<string, any>;
    const defaults = { ...specDefaults(specs), ...(def.defaults ?? {}) };
    const entry: PrimitiveEntry = {
      name: def.name,
      doc: def.doc,
      parent: def.extends,
      specs,
      defaults,
      generate: def.generate,
      fingerprint: fingerprint([def.extends, def.doc, specs, defaults, def.generate?.toString()]),
    };

    const existing = this.entries.get(def.name);
    if (existing) {
      if (existing.fingerprint === entry.fingerprint) return;
      if (!def.override) {
        throw new Error(`definePrimitive("${def.name}"): already registered. Pass { override: true } to replace it.`);
      }
    }
    this.entries.set(def.name, entry);
  }

  names(): string[] {
    return [...this.entries.keys()].sort();
  }

  private chain(name: string): PrimitiveEntry[] {
    const out: PrimitiveEntry[] = [];
    let current: string | undefined = name;
    const seen = new Set<string>();
    while (current) {
      if (seen.has(current)) throw new Error(`Primitive inheritance cycle at "${current}".`);
      seen.add(current);
      const entry = this.entries.get(current);
      if (!entry) throw new Error(`Unknown primitive "${current}".`);
      out.unshift(entry);
      current = entry.parent;
    }
    return out;
  }

  resolveParams(name: string, explicit: Record<string, unknown> = {}): Record<string, unknown> {
    const params: Record<string, unknown> = {};
    for (const entry of this.chain(name)) {
      for (const k of Object.keys(entry.defaults)) {
        if (entry.defaults[k] !== undefined) params[k] = entry.defaults[k];
      }
    }
    for (const k of Object.keys(explicit)) {
      if (explicit[k] !== undefined) params[k] = explicit[k];
    }
    return params;
  }

  getGenerator(name: string): PrimitiveGenerator<any> {
    const chain = this.chain(name);
    for (let i = chain.length - 1; i >= 0; i--) {
      if (chain[i].generate) return chain[i].generate!;
    }
    throw new Error(`Primitive "${name}" has no generator.`);
  }

  describe(name: string): PrimitiveDescription {
    const chain = this.chain(name);
    const defaults = this.resolveParams(name, {});
    const params: ParamDescription[] = [];
    const keys = new Set<string>();
    for (const entry of chain) {
      for (const key of Object.keys(entry.specs)) keys.add(key);
      for (const key of Object.keys(entry.defaults)) keys.add(key);
    }
    for (const key of [...keys].sort()) {
      const owner = [...chain].reverse().find(entry => entry.specs[key]);
      const spec = owner?.specs[key];
      const val = defaults[key];
      params.push({
        name: key,
        type: typeOfDefault(spec ? spec.default : val),
        default: val,
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
      chain: chain.map(e => e.name),
      params,
    };
  }
}

const primitiveRegistry = new PrimitiveRegistry();

/**
 * Wraps a point generator into a parametric polygon/shape factory.
 * Accepts either:
 * - Simple signature: `definePrimitive('gear', (params) => [...points])`
 * - Full definition: `definePrimitive({ name: 'gear', doc: '...', params: { ... }, generate: (p) => ... })`
 */
export function definePrimitive<P extends object>(
  nameOrDef: string | PrimitiveDefinition<P>,
  generator?: PrimitiveGenerator<P>,
): PrimitiveFactory<P> {
  const def: PrimitiveDefinition<P> = typeof nameOrDef === 'string'
    ? { name: nameOrDef, generate: generator }
    : nameOrDef;

  primitiveRegistry.define(def);

  const build = (params: Partial<P> = {}, placement: PrimitivePlacement = {}): Shape => {
    const resolved = primitiveRegistry.resolveParams(def.name, params as Record<string, unknown>) as P;
    const gen = primitiveRegistry.getGenerator(def.name);
    const result = gen(resolved);

    if (Array.isArray(result)) {
      if (result.length < 3) throw new Error(`Primitive "${def.name}" must return at least 3 points.`);
      return Polygon.fromPoints(result, placement);
    }

    if (result && typeof result === 'object' && Array.isArray(result.outer)) {
      if (result.outer.length < 3) throw new Error(`Primitive "${def.name}" outer contour must have >= 3 points.`);
      const poly = Polygon.fromPoints(result.outer, placement);
      if (result.holes && result.holes.length > 0) {
        return new CompoundShape(poly.toPoints(), result.holes);
      }
      return poly;
    }

    throw new Error(`Primitive "${def.name}" returned invalid geometry.`);
  };

  return Object.assign(build, { primitiveName: def.name });
}

/** Names of all registered custom primitives. */
export function listPrimitives(): string[] {
  return primitiveRegistry.names();
}

/** Introspection for a primitive's parameters, defaults and documentation. */
export function describePrimitive(name: string): PrimitiveDescription {
  return primitiveRegistry.describe(name);
}
