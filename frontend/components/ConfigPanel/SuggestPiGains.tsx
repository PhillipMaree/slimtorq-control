'use client';

import { useEffect } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';
import type { SimParams, Variant } from '@/types/sim';
import { modulusOptimumTuning, skogestadTuning } from '@/lib/tuning';

const round6 = (x: number) => Math.round(x * 1e6) / 1e6;

// Mirrors src/app.py:494-510 `suggest_pi_gains`: auto-populate Kp / Ki
// whenever variant, f_pwm, pi_mode, or Skogestad knobs change — except in
// manual mode where the user's values are kept verbatim.
export function SuggestPiGains({ variants }: { variants: Variant[] }) {
  const { setValue } = useFormContext<SimParams>();
  const variantName = useWatch<SimParams, 'variant_name'>({ name: 'variant_name' });
  const fPwm = useWatch<SimParams, 'f_pwm'>({ name: 'f_pwm' });
  const piMode = useWatch<SimParams, 'pi_mode'>({ name: 'pi_mode' });
  const piTc = useWatch<SimParams, 'pi_tc'>({ name: 'pi_tc' });
  const piK1 = useWatch<SimParams, 'pi_k1'>({ name: 'pi_k1' });

  useEffect(() => {
    if (piMode === 'manual') return;
    const m = variants.find((v) => v.name === variantName);
    if (!m || !fPwm || Number.isNaN(fPwm)) return;
    let kp: number;
    let ki: number;
    if (piMode === 'skogestad') {
      [kp, ki] = skogestadTuning(m.R_s, m.L_s, fPwm, piK1 ?? 1.44, piTc ?? null);
    } else {
      [kp, ki] = modulusOptimumTuning(m.R_s, m.L_s, fPwm);
    }
    setValue('Kp', round6(kp), { shouldDirty: false });
    setValue('Ki', round6(ki), { shouldDirty: false });
  }, [variantName, fPwm, piMode, piTc, piK1, variants, setValue]);

  return null;
}
