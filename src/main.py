"""Run a SlimTorq FOC + PWM + inverter simulation and write the results to parquet.

This is a thin driver: it builds the component pipeline (FOC, PWM, Inverter,
PMSM, Encoder), hands them to the `Simulator`, runs `n_steps = T_horizon/dt_sim`
ticks, and writes one parquet file at `out_path`.

The PMSM wrapper writes the FMU's outputs back through to the dataframe; the
parquet's key-value metadata records the canonical parameter hash + JSON so
the Dash app can cache-hit on identical reruns.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pyarrow.parquet as pq

from controller import FOCController
from encoder import EncoderMeasurement, FluxEncoder
from model import EncoderConfig, FocConfig, InverterConfig, PmsmModel, TLRef
from simulator import Simulator
from switching import Inverter, PMSMAbcModel, PWMModulator

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"

SCHEMA_VERSION = "2"

LOG_COLUMNS = (
    "t", "TL_ref", "T_e",
    "i_d_ref", "i_q_ref", "i_d_meas", "i_q_meas",
    "v_d_ref", "v_q_ref",
    "i_a", "i_b", "i_c",
    "theta_m_true", "theta_m_meas",
    "omega_m_true", "omega_m_meas",
    "v_a_ref", "v_b_ref", "v_c_ref",
    "d_a", "d_b", "d_c",
    "v_a", "v_b", "v_c",
)
BOOL_COLUMNS = ("sat_d", "sat_q")
INT_COLUMNS = ("s_a", "s_b", "s_c")


# ----------------------------------------------------------------------------
# Output path + parquet writer
# ----------------------------------------------------------------------------
def output_path_for(motor: PmsmModel) -> Path:
    """Canonical output path: output/data/<family>_<name>.parquet."""
    fname = f"{motor.family.replace(' ', '_')}_{motor.name}.parquet"
    return OUTPUT_DIR / fname


def _write_parquet(log: dict[str, np.ndarray],
                   motor: PmsmModel,
                   foc: FOCController,
                   Vdc: float,
                   f_pwm: float,
                   t_dead: float,
                   pi_mode: str,
                   b_est: float | None,
                   params_json: str,
                   params_hash: str,
                   out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    columns = {k: pl.Series(k, log[k]) for k in LOG_COLUMNS}
    for k in BOOL_COLUMNS:
        columns[k] = pl.Series(k, log[k].astype(bool))
    for k in INT_COLUMNS:
        columns[k] = pl.Series(k, log[k].astype(np.int8))
    df = pl.DataFrame(columns)

    table = df.to_arrow()
    meta = {
        b"slimtorq.schema_version":      SCHEMA_VERSION.encode(),
        b"slimtorq.params_hash":         params_hash.encode(),
        b"slimtorq.params_json":         params_json.encode(),
        b"slimtorq.foc_kp":              f"{foc.Kp:.10g}".encode(),
        b"slimtorq.foc_ki":              f"{foc.Ki:.10g}".encode(),
        b"slimtorq.pi_mode":             pi_mode.encode(),
        b"slimtorq.vdc":                 f"{Vdc:.10g}".encode(),
        b"slimtorq.f_pwm":               f"{f_pwm:.10g}".encode(),
        b"slimtorq.t_dead":              f"{t_dead:.10g}".encode(),
        b"slimtorq.b_est":               (b"null" if b_est is None
                                          else f"{b_est:.10g}".encode()),
        b"slimtorq.motor_family":        motor.family.encode(),
        b"slimtorq.motor_name":          motor.name.encode(),
        b"slimtorq.motor_rated_voltage": f"{motor.rated_voltage:.6g}".encode(),
    }
    table = table.replace_schema_metadata(meta)
    pq.write_table(table, str(out_path))


def read_metadata(path: Path) -> dict[str, str]:
    raw = pq.read_metadata(str(path)).metadata or {}
    return {k.decode(): v.decode() for k, v in raw.items()
            if k.decode().startswith("slimtorq.")}


# ----------------------------------------------------------------------------
# Trajectory helper (also used by the Dash callback)
# ----------------------------------------------------------------------------
def default_TL_ref(motor: PmsmModel, t_end: float, t_step: float,
                   frac: float) -> TLRef:
    """Default TL_ref: zero until t_step, then step to frac · te_peak_1s, hold to t_end.

    `frac` is interpreted against the catalog's 1-second peak torque so the
    user-facing knob has the meaning "fraction of max torque the motor can
    briefly produce." Defaults around 0.5-0.7 are realistic; values > 1.0 push
    past the catalog peak and will hit the FOC's vector-saturation limit.
    """
    amp = frac * motor.te_peak_1s
    return TLRef(ref=np.array([0.0, amp]), t=np.array([t_step, t_end]))


# ----------------------------------------------------------------------------
# Core simulation entry point
# ----------------------------------------------------------------------------
def run(*,
        motor: PmsmModel,
        encoder_cfg: EncoderConfig,
        TL_ref: TLRef,
        out_path: Path,
        params_json: str,
        params_hash: str,
        pi_mode: str,
        Vdc: float,
        f_pwm: float,
        t_dead: float,
        dt_sim: float | None = None,
        Tf: float | None = None,
        bw_hz: float = 1000.0,
        Kp: float | None = None,
        Ki: float | None = None) -> None:
    """Build the pipeline, run the inner loop, write a parquet file."""
    T_pwm = 1.0 / f_pwm
    dt_ctrl = T_pwm
    if dt_sim is None:
        dt_sim = T_pwm / 20.0
    tau_e = motor.L_s / motor.R_s
    if dt_sim > tau_e / 3.0:
        msg = (f"dt_sim ({dt_sim*1e6:.2f} us) too large for stable discrete PI; "
               f"require dt_sim <= tau_e/3 = {tau_e/3.0*1e6:.2f} us "
               f"(tau_e = L_s/R_s = {tau_e*1e6:.2f} us).")
        raise ValueError(msg)
    if dt_sim > T_pwm / 10.0:
        msg = (f"dt_sim ({dt_sim*1e6:.2f} us) too large to resolve PWM at "
               f"f_pwm={f_pwm:g} Hz; require dt_sim <= T_pwm/10 = {T_pwm/10*1e6:.2f} us.")
        raise ValueError(msg)

    T_horizon = float(Tf) if Tf is not None else float(TL_ref.t[-1])
    n_steps = round(T_horizon / dt_sim)

    foc_cfg = FocConfig(
        R_s=motor.R_s, L_s=motor.L_s, psi_m=motor.psi_m, p=motor.p,
        Vdc=Vdc, f_pwm=f_pwm, bw_hz=bw_hz,
        Kp=Kp, Ki=Ki,
    )
    foc = FOCController(foc_cfg)
    pwm = PWMModulator(f_pwm=f_pwm)
    inverter = Inverter(InverterConfig(Vdc=Vdc, t_dead=t_dead))
    pmsm = PMSMAbcModel(motor)
    encoder = EncoderMeasurement(FluxEncoder(encoder_cfg), p=motor.p)
    sim = Simulator(motor=motor, foc=foc, pwm=pwm, inverter=inverter,
                    pmsm=pmsm, encoder=encoder, TL=TL_ref,
                    dt_sim=dt_sim, dt_ctrl=dt_ctrl, Vdc=Vdc)

    print(f"Variant: {motor.name}  ({motor.family})")
    print(f"  R_s={motor.R_s:.4g} Ohm  L_s={motor.L_s*1e6:.2f} uH  "
          f"psi_m={motor.psi_m*1e3:.3f} mWb  p={motor.p}  "
          f"J={motor.J*1e7:.2f} gcm^2  ripple={motor.torque_ripple_pct:.2f}%")
    print(f"  Vdc={Vdc:g} V   f_pwm={f_pwm:g} Hz   t_dead={t_dead*1e6:.2f} us")
    print(f"  dt_sim={dt_sim*1e6:.2f} us ({1.0/dt_sim/1e3:.1f} kHz)   "
          f"dt_ctrl={dt_ctrl*1e6:.2f} us   horizon={T_horizon*1e3:.1f} ms")
    print(f"  PI gains [{pi_mode}]:  Kp={foc.Kp:.4g} V/A   Ki={foc.Ki:.4g} V/(A·s)")

    # Pre-allocate column buffers.
    all_cols = list(LOG_COLUMNS) + list(BOOL_COLUMNS) + list(INT_COLUMNS)
    log = {k: np.zeros(n_steps) for k in all_cols}

    try:
        for k in range(n_steps):
            row = sim.step(k * dt_sim)
            for col in all_cols:
                log[col][k] = row[col]
    finally:
        pmsm.close()

    # Steady-state B extraction over the trailing 20%.
    tail = slice(int(0.8 * n_steps), n_steps)
    mean_omega = float(np.mean(log["omega_m_true"][tail]))
    mean_dT = float(np.mean(log["T_e"][tail] - log["TL_ref"][tail]))
    b_est: float | None = mean_dT / mean_omega if abs(mean_omega) > 1e-3 else None
    b_str = f"{b_est:.3e} N·m·s/rad" if b_est is not None \
        else f"undetermined (|omega_m|={abs(mean_omega):.2e} too small)"
    print(f"Final  i_d={log['i_d_meas'][-1]: .4f} A   "
          f"i_q={log['i_q_meas'][-1]: .4f} A   "
          f"i_q*={log['i_q_ref'][-1]: .4f} A")
    print(f"Final  T_e={log['T_e'][-1]: .4f} N.m   "
          f"TL*={log['TL_ref'][-1]: .4f} N.m   "
          f"omega_m={log['omega_m_true'][-1]: .3f} rad/s")
    print(f"Steady-state B_est: {b_str}  (FMU B = 1.0e-5)")

    _write_parquet(log, motor=motor, foc=foc,
                   Vdc=Vdc, f_pwm=f_pwm, t_dead=t_dead, pi_mode=pi_mode,
                   b_est=b_est,
                   params_json=params_json, params_hash=params_hash,
                   out_path=out_path)
    print(f"Wrote {out_path}")
