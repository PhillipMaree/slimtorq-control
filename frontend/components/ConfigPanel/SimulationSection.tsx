'use client';

import { NumberField } from './Field';
import { Section, Sub } from './Section';

export function TrajectorySection() {
  return (
    <Section title="Trajectory (load-torque step)">
      <NumberField name="t_end" label={<Sub stem="t" sub="end" />} step={1e-3} min={1e-3} max={1.0} suffix="s" />
      <NumberField name="t_step" label={<Sub stem="t" sub="step" />} step={1e-3} min={0} max={1.0} suffix="s" />
      <NumberField
        name="t_step_frac"
        label={
          <span>
            T<sub>L</sub>
            <sup>ref</sup> / T<sub>e</sub>
            <sup>peak</sup>
          </span>
        }
        step={0.05}
        min={0}
        max={1.5}
      />
      <NumberField name="Tf" label={<Sub stem="T" sub="f" />} step={1e-3} min={1e-3} max={5.0} suffix="s (blank=auto)" nullable />
    </Section>
  );
}

export function TimingSection() {
  return (
    <Section title="Timing">
      <NumberField
        name="dt_sim"
        label={
          <span>
            Δt<sub>sim</sub>
          </span>
        }
        step={1e-7}
        min={1e-7}
        max={1e-4}
        suffix="s (blank=T_pwm/20)"
        nullable
      />
    </Section>
  );
}
