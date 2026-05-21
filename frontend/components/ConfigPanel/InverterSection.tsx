'use client';

import { NumberField, RadioField } from './Field';
import { Section, Sub } from './Section';

export function InverterSection() {
  return (
    <Section title="Power stage" helpKey="section:power-stage">
      <NumberField name="f_pwm" label={<Sub stem="f" sub="pwm" />} step={1000} min={1000} max={100000} suffix="Hz" />
      <NumberField name="t_dead" label={<Sub stem="t" sub="dead" />} step={1e-8} min={0} max={5e-6} suffix="s" />
      <RadioField
        name="pwm_mode"
        label="PWM mode"
        options={[
          { value: 'sine', label: 'sine' },
          { value: 'svpwm', label: 'svpwm' },
          { value: 'dpwmmax', label: 'dpwmmax' },
          { value: 'dpwmmin', label: 'dpwmmin' },
          { value: 'dpwm1', label: 'dpwm1' },
          { value: 'auto', label: 'auto (svpwm ↔ dpwm1)' },
        ]}
      />
    </Section>
  );
}
