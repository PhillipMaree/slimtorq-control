import type { Table } from 'apache-arrow';

// Polars writes columns as Float64. Vector#toArray() returns a typed array
// when available; we cast to Float64Array for ECharts series consumption.

export function col(table: Table, name: string): Float64Array {
  const v = table.getChild(name);
  if (!v) {
    throw new Error(`column not found: ${name}`);
  }
  // toArray on a Float64 vector returns Float64Array directly; otherwise we copy.
  const arr = v.toArray();
  return arr instanceof Float64Array ? arr : Float64Array.from(arr as Iterable<number>);
}

export function boolCol(table: Table, name: string): Uint8Array {
  const v = table.getChild(name);
  if (!v) {
    throw new Error(`column not found: ${name}`);
  }
  const out = new Uint8Array(v.length);
  for (let i = 0; i < v.length; i++) {
    out[i] = v.get(i) ? 1 : 0;
  }
  return out;
}

// Pair the time column with another for ECharts [x, y] series format.
export function xyPairs(x: Float64Array, y: Float64Array): [number, number][] {
  const n = Math.min(x.length, y.length);
  const out = new Array(n) as [number, number][];
  for (let i = 0; i < n; i++) {
    out[i] = [x[i], y[i]];
  }
  return out;
}
