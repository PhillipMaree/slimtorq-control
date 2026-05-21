'use client';

import { useFormContext } from 'react-hook-form';
import type { SimParams, Variant } from '@/types/sim';
import { HelpHint } from '../HelpHint';
import { HELP } from '@/lib/helpContent';
import { Section } from './Section';

export function MotorSection({ variants }: { variants: Variant[] }) {
  const { register } = useFormContext<SimParams>();
  return (
    <Section title="Motor" helpKey="section:motor">
      <div className="alva-row">
        <label htmlFor="variant_name" className="flex items-center">
          <span>variant</span>
          <HelpHint content={HELP['field:variant_name']} />
        </label>
        <select id="variant_name" {...register('variant_name')}>
          {variants.map((v) => (
            <option key={v.name} value={v.name}>
              {v.name}
            </option>
          ))}
        </select>
      </div>
    </Section>
  );
}
