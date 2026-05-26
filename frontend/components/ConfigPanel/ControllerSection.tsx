'use client';

import { useWatch } from 'react-hook-form';
import type { SimParams } from '@/types/sim';
import { NumberField, RadioField } from './Field';
import { Section, Sub } from './Section';

export function ControllerSection() {
  const piMode = useWatch<SimParams, 'pi_mode'>({ name: 'pi_mode' });
  const manual = piMode === 'manual';
  const skogestad = piMode === 'skogestad';

  return (
    <Section title="Current loop" helpKey="section:current-loop">
      <RadioField
        name="pi_mode"
        label="PI tuning"
        options={[
          { value: 'modulus_optimum', label: 'Modulus Optimum (f_pwm)' },
          { value: 'skogestad', label: 'Skogestad (T_c, k1)' },
          { value: 'manual', label: 'Manual (Kp, Ki)' },
        ]}
      />
      <NumberField name="pi_tc" label={<Sub stem="T" sub="c" />} step={1e-7} min={1e-7} max={1e-3} suffix="s (blank=1.5/f_pwm)" disabled={!skogestad} nullable />
      <NumberField name="pi_k1" label={<Sub stem="k" sub="1" />} step={0.01} min={0.5} max={8.0} disabled={!skogestad} />
      <NumberField name="Kp" label={<Sub stem="K" sub="p" />} step={1e-3} min={0} suffix="V/A" disabled={!manual} nullable />
      <NumberField name="Ki" label={<Sub stem="K" sub="i" />} step={1e-3} min={0} suffix="V/(A·s)" disabled={!manual} nullable />
    </Section>
  );
}

export function DebugSection() {
  return (
    <details className="alva-section">
      <summary className="cursor-pointer text-sm text-alva-muted uppercase tracking-wider mb-2">Debug</summary>
      <RadioField
        name="inverter_mode"
        label="Inverter mode"
        options={[
          { value: 'ideal', label: 'ideal (v_abc_ref straight to FMU)' },
          { value: 'average', label: 'average (cycle-averaged PWM, no dead-time)' },
          { value: 'switching', label: 'switching (real PWM compare + dead-time)' },
        ]}
      />
    </details>
  );
}
