import { tableFromIPC, Table } from 'apache-arrow';
import type { CatalogResponse, SimMeta, SimParams } from '@/types/sim';

// Production: FastAPI serves the static export on the same origin, so /api is
// relative. Development: NEXT_PUBLIC_API_BASE in .env.local points at the
// uvicorn dev server (e.g. http://localhost:8000/api).
const BASE = process.env.NEXT_PUBLIC_API_BASE || '/api';

async function jsonOrThrow<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const body = await r.text();
    throw new Error(`${r.status} ${r.statusText}: ${body}`);
  }
  return (await r.json()) as T;
}

export async function getCatalog(): Promise<CatalogResponse> {
  return jsonOrThrow(await fetch(`${BASE}/catalog`, { cache: 'no-store' }));
}

export async function getDefaults(): Promise<SimParams> {
  return jsonOrThrow(await fetch(`${BASE}/defaults`, { cache: 'no-store' }));
}

export async function simulate(params: SimParams): Promise<{ meta: SimMeta; table: Table }> {
  const metaRes = await fetch(`${BASE}/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  const meta = await jsonOrThrow<SimMeta>(metaRes);
  const dataRes = await fetch(`${BASE}/simulate/${meta.params_hash}/data`, { cache: 'no-store' });
  if (!dataRes.ok) {
    throw new Error(`Failed to fetch simulation data: ${dataRes.status} ${dataRes.statusText}`);
  }
  const buf = await dataRes.arrayBuffer();
  const table = tableFromIPC(new Uint8Array(buf));
  return { meta, table };
}

export function artifactUrl(hash: string): string {
  return `${BASE}/artifacts/${hash}.parquet`;
}
