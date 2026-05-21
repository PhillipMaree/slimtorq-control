'use client';

import { useFormContext } from 'react-hook-form';
import type { SimParams } from '@/types/sim';
import { HelpHint } from '../HelpHint';
import { HELP } from '@/lib/helpContent';

interface NumberFieldProps {
  name: keyof SimParams;
  label: React.ReactNode;
  step?: number;
  min?: number;
  max?: number;
  disabled?: boolean;
  suffix?: string;
  nullable?: boolean;
  helpKey?: string;
}

// Resolve helpKey: explicit prop wins, otherwise default to "field:<name>".
const helpFor = (name: string, override?: string) => HELP[override ?? `field:${name}`];

// step="any" disables the browser's grid-validity check ((value - min) % step === 0),
// which would otherwise reject defaults like theta_offset=0 with min=-π,
// ts_enc=1e-4 with min=1e-6, etc. min/max still constrain the range. The
// `step` prop is accepted for documentation but not bound to the input.
export function NumberField({ name, label, step: _step, min, max, disabled, suffix, nullable, helpKey }: NumberFieldProps) {
  const { register } = useFormContext<SimParams>();
  return (
    <div className="alva-row">
      <label htmlFor={String(name)} className="flex items-center">
        <span>{label}</span>
        {suffix ? <span className="ml-1 text-alva-muted"> [{suffix}]</span> : null}
        <HelpHint content={helpFor(String(name), helpKey)} />
      </label>
      <input
        id={String(name)}
        type="number"
        step="any"
        min={min}
        max={max}
        disabled={disabled}
        {...register(name, {
          setValueAs: (v) => {
            if (v === '' || v === null || v === undefined) return nullable ? null : NaN;
            const f = typeof v === 'number' ? v : parseFloat(v as string);
            return Number.isNaN(f) ? (nullable ? null : NaN) : f;
          },
        })}
      />
    </div>
  );
}

interface IntFieldProps extends Omit<NumberFieldProps, 'nullable'> {}

export function IntField({ name, label, step = 1, min, max, disabled, suffix, helpKey }: IntFieldProps) {
  const { register } = useFormContext<SimParams>();
  return (
    <div className="alva-row">
      <label htmlFor={String(name)} className="flex items-center">
        <span>{label}</span>
        {suffix ? <span className="ml-1 text-alva-muted"> [{suffix}]</span> : null}
        <HelpHint content={helpFor(String(name), helpKey)} />
      </label>
      <input
        id={String(name)}
        type="number"
        step={step}
        min={min}
        max={max}
        disabled={disabled}
        {...register(name, {
          setValueAs: (v) => {
            if (v === '' || v === null || v === undefined) return NaN;
            const n = typeof v === 'number' ? v : parseInt(v as string, 10);
            return Number.isNaN(n) ? NaN : n;
          },
        })}
      />
    </div>
  );
}

interface SelectFieldProps {
  name: keyof SimParams;
  label: React.ReactNode;
  options: { value: string; label: string }[];
  disabled?: boolean;
  helpKey?: string;
}

export function SelectField({ name, label, options, disabled, helpKey }: SelectFieldProps) {
  const { register } = useFormContext<SimParams>();
  return (
    <div className="alva-row">
      <label htmlFor={String(name)} className="flex items-center">
        <span>{label}</span>
        <HelpHint content={helpFor(String(name), helpKey)} />
      </label>
      <select id={String(name)} disabled={disabled} {...register(name)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

interface RadioFieldProps {
  name: keyof SimParams;
  label: React.ReactNode;
  options: { value: string; label: string }[];
  helpKey?: string;
}

export function RadioField({ name, label, options, helpKey }: RadioFieldProps) {
  const { register } = useFormContext<SimParams>();
  return (
    <div className="py-1">
      <div className="text-sm text-alva-muted mb-1 flex items-center">
        <span>{label}</span>
        <HelpHint content={helpFor(String(name), helpKey)} />
      </div>
      <div className="flex flex-col gap-1 pl-2">
        {options.map((o) => (
          <label key={o.value} className="flex items-center gap-2 text-sm">
            <input type="radio" value={o.value} {...register(name)} />
            <span>{o.label}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

interface CheckboxFieldProps {
  name: keyof SimParams;
  label: React.ReactNode;
  helpKey?: string;
}

export function CheckboxField({ name, label, helpKey }: CheckboxFieldProps) {
  const { register } = useFormContext<SimParams>();
  return (
    <label className="flex items-center gap-2 text-sm py-1">
      <input type="checkbox" {...register(name)} />
      <span>{label}</span>
      <HelpHint content={helpFor(String(name), helpKey)} />
    </label>
  );
}
