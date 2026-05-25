'use client';

import { useEffect } from 'react';
import { FormProvider, useForm, useWatch } from 'react-hook-form';
import type { SimParams, Variant } from '@/types/sim';
import { FORM_DEFAULTS } from '@/lib/formDefaults';
import { ControllerSection, DebugSection } from './ControllerSection';
import { EncoderSection } from './EncoderSection';
import { FilterSection } from './FilterSection';
import { InverterSection } from './InverterSection';
import { MotorSection } from './MotorSection';
import { TimingSection, TrajectorySection } from './SimulationSection';
import { SuggestPiGains } from './SuggestPiGains';
import { SuggestVdc } from './SuggestVdc';

interface ConfigPanelProps {
  variants: Variant[];
  onSubmit: (p: SimParams) => Promise<void>;
  loading: boolean;
}

export function ConfigPanel({ variants, onSubmit, loading }: ConfigPanelProps) {
  const methods = useForm<SimParams>({
    defaultValues: FORM_DEFAULTS,
    mode: 'onChange',
  });
  return (
    <FormProvider {...methods}>
      <form
        onSubmit={methods.handleSubmit(onSubmit)}
        className="w-[24rem] shrink-0 border-r border-alva-border bg-alva-panel h-full flex flex-col min-h-0"
      >
        <div className="flex-1 overflow-y-auto px-4 pt-4 pb-2">
          <MotorSection variants={variants} />
          <InverterSection />
          <FilterSection />
          <EncoderSection />
          <TrajectorySection />
          <TimingSection />
          <ControllerSection />
          <DebugSection />
          <SuggestPiGains variants={variants} />
          <SuggestVdc variants={variants} />
        </div>
        <div className="px-4 py-3 border-t border-alva-border bg-alva-panel">
          <button type="submit" className="alva-btn" disabled={loading}>
            {loading ? 'Simulating…' : 'Simulate'}
          </button>
        </div>
      </form>
    </FormProvider>
  );
}
