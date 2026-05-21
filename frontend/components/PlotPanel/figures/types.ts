import type { Table } from 'apache-arrow';
import type { SimMeta } from '@/types/sim';
import type { FigureSpec } from '../FigureCard';

export interface FigureInput {
  table: Table;
  meta: SimMeta;
}

export type FigureBuilder = (input: FigureInput) => FigureSpec;

// Tracking-error % normalized by a motor-relative peak (i_q_peak for currents,
// te_peak_1s for torque). Computed over the trailing 80% of the run so the
// transient doesn't dominate. Peak normalization keeps the d-axis badge
// meaningful (i_d_ref = 0) and makes errors comparable across operating points.
import { col } from '@/lib/arrow';
export function refTrackingErrPct(table: Table, measCol: string, refCol: string, peak: number): number {
  const meas = col(table, measCol);
  const ref = col(table, refCol);
  const n = meas.length;
  if (n < 4 || !(peak > 0)) return NaN;
  const start = Math.floor(0.8 * n);
  let sumE = 0;
  let cnt = 0;
  for (let i = start; i < n; i++) {
    const e = meas[i] - ref[i];
    sumE += e * e;
    cnt++;
  }
  const errRms = Math.sqrt(sumE / cnt);
  return (100 * errRms) / peak;
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
