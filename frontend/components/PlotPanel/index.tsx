'use client';

import { useEffect, useMemo, useState } from 'react';
import type { Table } from 'apache-arrow';
import type { SimMeta } from '@/types/sim';
import { FigureCard } from './FigureCard';
import { Tabs } from './Tabs';
import type { TabDef, TabKey } from './Tabs';
import { buildControlFft, buildControlTime } from './figures/control';
import { buildMechanicalFft, buildMechanicalTime } from './figures/mechanical';
import { buildPowerFft, buildPowerTime } from './figures/power';
import { buildSignalProcessingFft, buildSignalProcessingTime } from './figures/signalProcessing';
import { buildTrackingFft, buildTrackingTime } from './figures/tracking';
import type { FigureBuilder } from './figures/types';

const TAB_BUILDERS: Record<TabKey, FigureBuilder[]> = {
  tracking: [buildTrackingTime, buildTrackingFft],
  control: [buildControlTime, buildControlFft],
  mechanical: [buildMechanicalTime, buildMechanicalFft],
  power: [buildPowerTime, buildPowerFft],
  'signal-processing': [buildSignalProcessingTime, buildSignalProcessingFft],
};

export function PlotPanel({ table, meta }: { table: Table | null; meta: SimMeta | null }) {
  const [active, setActive] = useState<TabKey>('tracking');

  // Hide the Power tab when the inverter runs in "ideal" mode — there's no
  // real PWM switching to inspect. Hide the Signal-Processing tab when the
  // LCL filter is off — the v_*_motor columns are pass-throughs of v_a/b/c.
  const inverterMode = meta?.parquet_meta['slimtorq.inverter_mode'] ?? 'switching';
  const pwmEnabled = inverterMode !== 'ideal';
  const filterEnabled = meta?.parquet_meta['slimtorq.filter_enabled'] === '1';

  const tabs: TabDef[] = useMemo(() => {
    const out: TabDef[] = [
      { key: 'tracking', label: 'Tracking' },
      { key: 'control', label: 'Control' },
      { key: 'mechanical', label: 'Mechanical' },
    ];
    if (pwmEnabled) out.push({ key: 'power', label: 'Power' });
    if (filterEnabled) out.push({ key: 'signal-processing', label: 'Signal Processing' });
    return out;
  }, [pwmEnabled, filterEnabled]);

  // If the user was on a tab that just disappeared (e.g. they re-ran the sim
  // with PWM or the LCL filter turned off), fall back to Tracking.
  useEffect(() => {
    if (!tabs.some((t) => t.key === active)) setActive('tracking');
  }, [tabs, active]);

  const figures = useMemo(() => {
    if (!table || !meta) return [];
    if (!tabs.some((t) => t.key === active)) return [];
    return TAB_BUILDERS[active].map((b) => b({ table, meta }));
  }, [active, table, meta, tabs]);

  if (!table || !meta) {
    return (
      <div className="flex-1 flex flex-col min-h-0">
        <Tabs tabs={tabs} active={active} onChange={setActive} />
        <div className="flex-1 p-6 text-alva-muted">
          <p>Pick a motor variant and click <span className="font-semibold">Simulate</span> to render the diagnostic plots.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <Tabs tabs={tabs} active={active} onChange={setActive} />
      <div className="flex-1 p-4 flex flex-col gap-4 overflow-y-auto">
        {figures.map((fig, i) => (
          <FigureCard key={`${active}-${i}`} figure={fig} />
        ))}
      </div>
    </div>
  );
}
