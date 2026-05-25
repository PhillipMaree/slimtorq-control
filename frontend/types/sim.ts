// Mirrors src/sim_service.py SimParams (28 inputs) and SimMeta.

export type PiMode = 'modulus_optimum' | 'skogestad' | 'manual';
export type InverterMode = 'ideal' | 'average' | 'switching';
export type PwmMode = 'sine' | 'svpwm' | 'dpwmmax' | 'dpwmmin' | 'dpwm1' | 'auto';

export interface SimParams {
  variant_name: string;
  f_pwm: number;
  t_dead: number;
  n_bits: number;
  theta_offset: number;
  A1: number;
  k1: number;
  phi1: number;
  A2: number;
  k2: number;
  phi2: number;
  A3: number;
  k3: number;
  phi3: number;
  ts_enc: number;
  dt_sim: number | null;
  t_end: number;
  t_step: number;
  t_step_frac: number | null;
  Tf: number | null;
  pi_mode: PiMode;
  Kp: number | null;
  Ki: number | null;
  pi_tc: number | null;
  pi_k1: number;
  inverter_mode: InverterMode;
  pwm_mode: PwmMode;
  filter_enabled: boolean;
  filter_fc: number;
  vdc: number | null;
  zeta_target: number;
  observer_pole_multiplier: number;
}

export interface RippleStats {
  delta_pp: number;
  pct_rated: number;
  pct_cmd: number | null;
}

export interface SimMeta {
  params_hash: string;
  rows: number;
  err_pct: number;
  artifact_name: string;
  foc_kp: number;
  foc_ki: number;
  pi_mode: string;
  motor_family: string;
  motor_name: string;
  rated_voltage: number;
  iq_ripple: RippleStats;
  te_ripple: RippleStats;
  ia_ripple: RippleStats;
  parquet_meta: Record<string, string>;
}

export interface Variant {
  name: string;
  family: string;
  p: number;
  R_s: number;
  L_s: number;
  lambda_PM: number;
  J: number;
  rated_voltage: number;
  i_cont: number;
  te_cont_cat: number;
  te_peak_1s: number;
}

export interface CatalogResponse {
  variants: Variant[];
}
