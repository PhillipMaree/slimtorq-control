// Mirrors src/tuning.py + src/simulator.py:_auto_tune, so the ConfigPanel can
// preview Kp/Ki the same way the server will resolve them.

export function modulusOptimumTuning(R: number, L: number, fPwm: number): [number, number] {
  const Tsigma = 1.5 / fPwm;
  const Kp = L / (2 * Tsigma);
  const Ki = R / (2 * Tsigma);
  return [Kp, Ki];
}

export function skogestadTuning(R: number, L: number, fPwm: number, k1 = 1.44, Tc: number | null = null): [number, number] {
  const tauDelay = 1.5 / fPwm;
  const TcEff = Tc === null ? tauDelay : Tc;
  const tauE = L / R;
  const sumT = TcEff + tauDelay;
  const Kp = L / sumT;
  const Ti = Math.min(tauE, k1 * sumT);
  const Ki = Kp / Ti;
  return [Kp, Ki];
}

// Mirrors src/model.py FilterConfig.derive_components + LCLParams.resonance_frequency_rad_s
// for the UI's safe-Tc preview. L_f = L_s/4, C_f sized so 1/sqrt(L_f·C_f) = 2π·fc;
// the LCL resonance is omega_res = sqrt((L_f + L_s) / (L_f · L_s · C_f)).
export function lclResonanceRadS(Ls: number, fc: number): number {
  const Lf = Ls / 4.0;
  const Cf = 1.0 / Math.pow(2 * Math.PI * fc, 2) / Lf;
  return Math.sqrt((Lf + Ls) / (Lf * Ls * Cf));
}

// Mirrors src/simulator.py:_safe_lcl_tc. Picks Tc so omega_c <= omega_res / 6.25,
// i.e. 25% headroom over the active-damping margin (5).
const LCL_TC_SAFETY_HEADROOM = 1.25;
export function safeLclTc(Ls: number, fPwm: number, fc: number): number {
  const omegaRes = lclResonanceRadS(Ls, fc);
  const tauDelay = 1.5 / fPwm;
  const tcMin = (5.0 * LCL_TC_SAFETY_HEADROOM) / omegaRes - tauDelay;
  return Math.max(tcMin, tauDelay);
}

// Mirrors src/simulator.py:_auto_tune. When the LCL filter is on, MO is unsafe
// at typical fc, so we substitute Skogestad with a safe Tc against the
// active-damping plant — and never let user-supplied Tc go below the safe floor.
export function autoTune(
  R: number,
  L: number,
  fPwm: number,
  piMode: 'modulus_optimum' | 'skogestad',
  piK1: number,
  piTc: number | null,
  filterEnabled: boolean,
  filterFc: number,
): [number, number] {
  if (filterEnabled) {
    const tcSafe = safeLclTc(L, fPwm, filterFc);
    const tcUsed = piTc === null ? tcSafe : Math.max(piTc, tcSafe);
    return skogestadTuning(R, L, fPwm, piK1, tcUsed);
  }
  if (piMode === 'skogestad') return skogestadTuning(R, L, fPwm, piK1, piTc);
  return modulusOptimumTuning(R, L, fPwm);
}
