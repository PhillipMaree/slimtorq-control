'use client';

import { useWatch } from 'react-hook-form';
import type { SimParams } from '@/types/sim';
import { CheckboxField, NumberField } from './Field';
import { Section, Sub } from './Section';

const TWO_PI = 2 * Math.PI;

function FilterDerived() {
  // Mirror src/app.py:466-468: L_f = L_s/4, C_f from f_c, R_d from sqrt(L_f/C_f)/3.
  // We don't have L_s on the client until /catalog is fetched; show formula hint instead.
  const f_pwm = useWatch<SimParams, 'f_pwm'>({ name: 'f_pwm' });
  const fc = useWatch<SimParams, 'filter_fc'>({ name: 'filter_fc' });
  if (!f_pwm || !fc) return null;
  const f_BW = f_pwm / (3 * Math.PI);
  const f_c_typical = f_pwm / 10;
  const f_c_safe = 2 * f_BW;
  return (
    <div className="alva-status">
      loop BW ≈ {f_BW.toFixed(0)} Hz · typical f_c ≈ {f_c_typical.toFixed(0)} Hz (f_pwm/10) · loop-safe floor ≈ {f_c_safe.toFixed(0)} Hz (2·f_BW)
    </div>
  );
}

export function FilterSection() {
  const enabled = useWatch<SimParams, 'filter_enabled'>({ name: 'filter_enabled' });
  return (
    <Section title="Output filter (LCL)" helpKey="section:filter">
      <CheckboxField name="filter_enabled" label="Enable LCL filter between inverter and motor" />
      <NumberField name="filter_fc" label={<Sub stem="f" sub="c" />} step={500} min={500} max={20000} suffix="Hz" disabled={!enabled} />
      <FilterDerived />
    </Section>
  );
}

// Re-export TWO_PI so EncoderSection can use it without duplicating.
export { TWO_PI };
