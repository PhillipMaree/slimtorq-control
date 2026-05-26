'use client';

import { useEffect } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';
import type { SimParams, Variant } from '@/types/sim';
import { autoTune } from '@/lib/tuning';

const round6 = (x: number) => Math.round(x * 1e6) / 1e6;

// Mirrors src/simulator.py:_auto_tune: auto-populate Kp / Ki whenever variant,
// f_pwm, pi_mode, filter, or Skogestad knobs change — except in manual mode
// where the user's values are kept verbatim. When the LCL filter is on the
// preview switches to Skogestad with a safe Tc so the user sees the same gains
// the server will use.
export function SuggestPiGains({ variants }: { variants: Variant[] }) {
  const { setValue } = useFormContext<SimParams>();
  const variantName = useWatch<SimParams, 'variant_name'>({ name: 'variant_name' });
  const fPwm = useWatch<SimParams, 'f_pwm'>({ name: 'f_pwm' });
  const piMode = useWatch<SimParams, 'pi_mode'>({ name: 'pi_mode' });
  const piTc = useWatch<SimParams, 'pi_tc'>({ name: 'pi_tc' });
  const piK1 = useWatch<SimParams, 'pi_k1'>({ name: 'pi_k1' });
  const filterEnabled = useWatch<SimParams, 'filter_enabled'>({ name: 'filter_enabled' });
  const filterFc = useWatch<SimParams, 'filter_fc'>({ name: 'filter_fc' });

  useEffect(() => {
    if (piMode === 'manual') return;
    const m = variants.find((v) => v.name === variantName);
    if (!m || !fPwm || Number.isNaN(fPwm)) return;
    const [kp, ki] = autoTune(m.R_s, m.L_s, fPwm, piMode, piK1 ?? 1.44, piTc ?? null, !!filterEnabled, filterFc ?? 5000.0);
    setValue('Kp', round6(kp), { shouldDirty: false });
    setValue('Ki', round6(ki), { shouldDirty: false });
  }, [variantName, fPwm, piMode, piTc, piK1, filterEnabled, filterFc, variants, setValue]);

  return null;
}
