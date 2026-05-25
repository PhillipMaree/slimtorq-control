'use client';

import { useEffect } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';
import type { SimParams, Variant } from '@/types/sim';

// Bus-voltage default = 1.5 × the catalog rated_voltage of the selected
// variant. Mirrors src/drivetrain.py:Drivetrain.DEFAULT_VDC_OVER_RATED and
// the resolve_vdc helper. Auto-populates whenever the variant changes —
// same pattern as SuggestPiGains. The catalog "rated_voltage" is the
// BEMF cap, not the bus; 1.5× gives the PI controller realistic headroom
// for R·i_q and L·di/dt inside the linear PWM range.
const VDC_OVER_RATED = 1.5;

export function SuggestVdc({ variants }: { variants: Variant[] }) {
  const { setValue } = useFormContext<SimParams>();
  const variantName = useWatch<SimParams, 'variant_name'>({ name: 'variant_name' });

  useEffect(() => {
    const m = variants.find((v) => v.name === variantName);
    if (!m) return;
    setValue('vdc', VDC_OVER_RATED * m.rated_voltage, { shouldDirty: false });
  }, [variantName, variants, setValue]);

  return null;
}
