'use client';

import { useCallback, useEffect, useState } from 'react';
import type { Table } from 'apache-arrow';
import { ConfigPanel } from '@/components/ConfigPanel';
import { Header } from '@/components/Header';
import { PlotPanel } from '@/components/PlotPanel';
import { getCatalog, simulate } from '@/lib/api';
import type { SimMeta, SimParams, Variant } from '@/types/sim';

export default function Page() {
  const [variants, setVariants] = useState<Variant[]>([]);
  const [meta, setMeta] = useState<SimMeta | null>(null);
  const [table, setTable] = useState<Table | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getCatalog()
      .then((c) => setVariants(c.variants))
      .catch((e) => setError(String(e)));
  }, []);

  const onSubmit = useCallback(async (p: SimParams) => {
    setError(null);
    setLoading(true);
    try {
      const { meta: m, table: t } = await simulate(p);
      setMeta(m);
      setTable(t);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <main className="h-screen flex flex-col overflow-hidden">
      <Header meta={meta} />
      {error ? <div className="bg-red-50 text-red-700 px-4 py-2 text-sm">{error}</div> : null}
      <div className="flex flex-1 min-h-0">
        <ConfigPanel variants={variants} onSubmit={onSubmit} loading={loading} />
        <PlotPanel table={table} meta={meta} />
      </div>
    </main>
  );
}
