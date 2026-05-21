'use client';

import { useMemo } from 'react';
import type { Table } from 'apache-arrow';
import type { SimMeta } from '@/types/sim';
import { FigureCard } from './FigureCard';
import { buildDuties } from './figures/duties';
import { buildEncoderError } from './figures/encoderError';
import { buildIabcFft } from './figures/iabcFft';
import { buildIqFft } from './figures/iqFft';
import { buildIqZoom } from './figures/iqZoom';
import { buildOmegaFft } from './figures/omegaFft';
import { buildPhaseCurrents } from './figures/phaseCurrents';
import { buildPhaseVoltages } from './figures/phaseVoltages';
import { buildPiPerformance } from './figures/piPerformance';
import { buildSpeedAndSaturation } from './figures/speedAndSaturation';
import { buildTracking } from './figures/tracking';
import { buildVdqRoundtrip } from './figures/vdqRoundtrip';

const BUILDERS = [
  buildTracking,
  buildPiPerformance,
  buildVdqRoundtrip,
  buildIqZoom,
  buildIqFft,
  buildOmegaFft,
  buildPhaseCurrents,
  buildIabcFft,
  buildPhaseVoltages,
  buildDuties,
  buildEncoderError,
  buildSpeedAndSaturation,
];

export function PlotPanel({ table, meta }: { table: Table | null; meta: SimMeta | null }) {
  const figures = useMemo(() => {
    if (!table || !meta) return [];
    return BUILDERS.map((build) => build({ table, meta }));
  }, [table, meta]);

  if (!table || !meta) {
    return (
      <div className="flex-1 p-6 text-alva-muted">
        <p>Pick a motor variant and click <span className="font-semibold">Simulate</span> to render the 12 diagnostic plots.</p>
      </div>
    );
  }

  return (
    <div className="flex-1 p-4 grid grid-cols-1 gap-4 overflow-y-auto">
      {figures.map((fig, i) => (
        <FigureCard key={i} figure={fig} />
      ))}
    </div>
  );
}
