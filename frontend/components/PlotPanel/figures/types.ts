import type { Table } from 'apache-arrow';
import type { SimMeta } from '@/types/sim';
import type { FigureSpec } from '../FigureCard';

export interface FigureInput {
  table: Table;
  meta: SimMeta;
}

export type FigureBuilder = (input: FigureInput) => FigureSpec;

// Tracking-error % over trailing 80% of meas vs ref.
import { col } from '@/lib/arrow';
export function refTrackingErrPct(table: Table, measCol: string, refCol: string): number {
  const meas = col(table, measCol);
  const ref = col(table, refCol);
  const n = meas.length;
  if (n < 4) return NaN;
  const start = Math.floor(0.8 * n);
  let sumE = 0;
  let sumR = 0;
  let sumRm = 0;
  let cnt = 0;
  for (let i = start; i < n; i++) {
    const e = meas[i] - ref[i];
    sumE += e * e;
    sumR += ref[i] * ref[i];
    sumRm += ref[i];
    cnt++;
  }
  const errRms = Math.sqrt(sumE / cnt);
  const refRms = Math.sqrt(sumR / cnt);
  const refMean = Math.abs(sumRm / cnt);
  const floor = Math.max(refRms, refMean, 1e-9);
  return (100 * errRms) / floor;
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
