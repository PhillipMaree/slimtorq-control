// Mirrors src/tuning.py modulus_optimum_tuning + skogestad_tuning, so the
// ConfigPanel can preview Kp/Ki the same way the old Dash callback did.

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
