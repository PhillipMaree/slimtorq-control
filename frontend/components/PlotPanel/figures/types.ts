import type { Table } from 'apache-arrow';
import type { SimMeta } from '@/types/sim';
import type { FigureSpec } from '../FigureCard';

export interface FigureInput {
  table: Table;
  meta: SimMeta;
}

export type FigureBuilder = (input: FigureInput) => FigureSpec;

// Tracking-error % over the trailing 80% of the run (transient excluded).
// Normalised by max|ref| in that window so the % matches what the user sees
// on the plot. When |ref| is near zero (i_d_ref = 0), falls back to the
// motor-relative peak passed in so the d-axis badge stays meaningful.
import { col } from '@/lib/arrow';
export function refTrackingErrPct(table: Table, measCol: string, refCol: string, fallbackPeak: number): number {
  const meas = col(table, measCol);
  const ref = col(table, refCol);
  const n = meas.length;
  if (n < 4) return NaN;
  const start = Math.floor(0.8 * n);
  let sumE = 0;
  let cnt = 0;
  let refPeak = 0;
  for (let i = start; i < n; i++) {
    const e = meas[i] - ref[i];
    sumE += e * e;
    cnt++;
    const ar = Math.abs(ref[i]);
    if (ar > refPeak) refPeak = ar;
  }
  const errRms = Math.sqrt(sumE / cnt);
  const denom = refPeak > 0.01 * Math.abs(fallbackPeak) ? refPeak : fallbackPeak;
  if (!(denom > 0)) return NaN;
  return (100 * errRms) / denom;
}

export function metaNum(meta: SimMeta, key: string, fallback: number): number {
  const v = meta.parquet_meta[key];
  if (v === undefined || v === null || v === 'null') return fallback;
  const f = parseFloat(v);
  return Number.isFinite(f) ? f : fallback;
}

export function metaStr(meta: SimMeta, key: string, fallback = '?'): string {
  return meta.parquet_meta[key] ?? fallback;
}

export function titlePrefix(meta: SimMeta): string {
  return `${meta.motor_family} / ${meta.motor_name}`;
}
