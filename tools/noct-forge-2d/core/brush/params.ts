/**
 * NoctBrush - Declarative parameter specs shared by `defineBrush` and `definePrimitive`.
 *
 * A spec documents one parameter (type is inferred from its default) so catalogs can be generated and
 * agents can ask `describeBrush('chalk')` / `describePrimitive('gear')` instead of reading source code.
 */

/** Declaration of one parameter: its default plus optional documentation and valid range. */
export interface ParamSpec<T = unknown> {
  /** Value used when the caller does not pass the parameter. */
  default: T;
  /** One-line explanation shown in catalogs. State units and effect, e.g. "pixels; 0 disables". */
  doc?: string;
  /** Lower bound, for numeric parameters. */
  min?: number;
  /** Upper bound, for numeric parameters. */
  max?: number;
  /** Allowed values, for enumerations. */
  options?: readonly T[];
}

/** One spec per key of `P`. */
export type ParamSpecs<P extends object> = { [K in keyof P]-?: ParamSpec<P[K]> };

/** Flattened description of a parameter, as returned by `describeBrush` / `describePrimitive`. */
export interface ParamDescription {
  name: string;
  /** `number`, `string`, `boolean`, `function`, `object`, ... inferred from the default. */
  type: string;
  default: unknown;
  doc?: string;
  min?: number;
  max?: number;
  options?: readonly unknown[];
  /** Name of the brush / primitive that declared this parameter's documentation. */
  declaredBy: string;
}

/** @internal Extracts `{ key: default }` from a spec map. */
export function specDefaults(specs: Record<string, ParamSpec> | undefined): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  if (!specs) return out;
  for (const key of Object.keys(specs)) out[key] = specs[key].default;
  return out;
}

/** @internal */
export function typeOfDefault(value: unknown): string {
  if (value === null || value === undefined) return 'unknown';
  if (Array.isArray(value)) return 'array';
  return typeof value;
}

/** @internal Deterministic string used to detect "same definition registered twice". */
export function fingerprint(value: unknown): string {
  return JSON.stringify(value, (_key, v) => (typeof v === 'function' ? `fn:${v.toString()}` : v));
}
