'use client';

import { IntField, NumberField } from './Field';
import { Section, Sub } from './Section';

const TWO_PI = 2 * Math.PI;

export function EncoderSection() {
  return (
    <Section title="Encoder">
      <IntField name="n_bits" label={<Sub stem="N" sub="bits" />} step={1} min={10} max={26} />
      <NumberField name="theta_offset" label={<Sub stem="θ" sub="offset" />} step={1e-3} min={-Math.PI} max={Math.PI} suffix="rad" />
      <NumberField name="A1" label={<Sub stem="A" sub="1" />} step={1e-6} min={0} max={1e-3} suffix="rad" />
      <IntField name="k1" label={<Sub stem="k" sub="1" />} step={1} min={1} max={100} />
      <NumberField name="phi1" label={<Sub stem="φ" sub="1" />} step={1e-3} min={0} max={TWO_PI} suffix="rad" />
      <NumberField name="A2" label={<Sub stem="A" sub="2" />} step={1e-6} min={0} max={1e-3} suffix="rad" />
      <IntField name="k2" label={<Sub stem="k" sub="2" />} step={1} min={1} max={100} />
      <NumberField name="phi2" label={<Sub stem="φ" sub="2" />} step={1e-3} min={0} max={TWO_PI} suffix="rad" />
      <NumberField name="A3" label={<Sub stem="A" sub="3" />} step={1e-6} min={0} max={1e-3} suffix="rad" />
      <IntField name="k3" label={<Sub stem="k" sub="3" />} step={1} min={1} max={100} />
      <NumberField name="phi3" label={<Sub stem="φ" sub="3" />} step={1e-3} min={0} max={TWO_PI} suffix="rad" />
      <NumberField name="ts_enc" label={<Sub stem="T" sub="s,enc" />} step={1e-5} min={1e-6} max={1e-2} suffix="s" />
    </Section>
  );
}
