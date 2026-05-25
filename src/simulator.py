"""Multi-rate FOC simulation pipeline.

Two layers in one module:

1. :class:`Simulator` — the multi-rate orchestrator. Given a fully-built
   :class:`Drivetrain` (see :mod:`src.drivetrain`) it routes signals
   through three clocks:

   - T_s     inner simulation step (FMU doStep, PWM carrier comparison,
             inverter dead-time tracking). Default = T_pwm / 20.
   - dt_ctrl FOC current-loop update period. Derived as 1 / controller.f_pwm
             — one FOC tick per PWM cycle, the standard digital-FOC convention.
   - Ts_enc  encoder sample period (lives inside FluxEncoder, queried by
             EncoderMeasurement; independent of the above two).

   Between FOC ticks the FOC's last v_abc_ref output is held by ZOH and
   fed into the Inverter every T_s. The Drivetrain owns the FMU lifecycle::

       with Drivetrain.build(p, motor) as drive:
           sim = Simulator(drive)
           df = sim.run(TL_ref, T_s, T_f)

2. :func:`run_simulation` — headless pipeline that turns a
   :class:`SimParams` request into a polars DataFrame + parquet artifact
   (with ``slimtorq.*`` metadata) and a :class:`SimMeta` summary. Consumed
   by the FastAPI server. The 28-field `SimParams` shape mirrors the dict
   that the old Dash callback built at app.py:648-678 verbatim, so
   ``params_hash`` is bit-stable across the refactor.

The Inverter has three operating modes selected per ``run()`` call:
- "ideal"     : v_abc_ref straight to FMU (smooth voltage source).
- "average"   : compute PWM duty as in switching mode but emit cycle-average
                voltages (d - 0.5)*Vdc, skip dead-time. Isolates "scaling /
                duty bug?" from "switching ripple problem?".
- "switching" : real carrier compare + dead-time. Default.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Literal

import numpy as np
import polars as pl
import pyarrow.parquet as pq

from src import get_config
from src.controller import FOCController
from src.drivetrain import Drivetrain, _auto_tune, resolve_vdc
from src.model import (
    FilterConfig,
    LCLParams,
    PiMode,
    PmsmModel,
    RippleStats,
    SimMeta,
    SimParams,
    TLRef,
    load_catalog,
)
from src.observer import LCLObserver, compute_observer_gain
from src.transform import abc_to_dq

SCHEMA_VERSION = "8"
TWO_PI = 2.0 * math.pi

CATALOG: dict[str, PmsmModel] = load_catalog(get_config().catalog.file_path)


LOG_COLUMNS = (
    "t",
    "TL_ref",
    "T_e",
    "i_d_ref",
    "i_q_ref",
    "i_d_meas",
    "i_q_meas",
    "v_d_ref",
    "v_q_ref",
    "i_a",
    "i_b",
    "i_c",
    "theta_m_true",
    "theta_m_meas",
    "theta_e_true",
    "theta_e_meas",
    "omega_m_true",
    "omega_m_meas",
    "v_a_ref",
    "v_b_ref",
    "v_c_ref",
    "d_a",
    "d_b",
    "d_c",
    "v_a",
    "v_b",
    "v_c",
    "v_a_motor",
    "v_b_motor",
    "v_c_motor",
    "m_index",
    "i1_d_hat",
    "vc_d_hat",
    "im_d_hat",
    "ic_d_hat",
    "i1_q_hat",
    "vc_q_hat",
    "im_q_hat",
    "ic_q_hat",
    "ad_d",
    "ad_q",
)
# Columns initialised to NaN instead of zero — observer estimates are only
# meaningful when the LCL filter runs in switching mode, otherwise the LCL
# states don't exist and a zero-line would be misleading.
NAN_INIT_COLUMNS = (
    "i1_d_hat",
    "vc_d_hat",
    "im_d_hat",
    "ic_d_hat",
    "i1_q_hat",
    "vc_q_hat",
    "im_q_hat",
    "ic_q_hat",
)
BOOL_COLUMNS = ("sat_d", "sat_q")
INT_COLUMNS = ("s_a", "s_b", "s_c", "pwm_mode_active")

# pwm_mode_active codes — keep in sync with switching._MODE_CODE.
_PWM_MODE_CODE = {"sine": 0, "svpwm": 1, "dpwmmax": 2, "dpwmmin": 3, "dpwm1": 4}


def _tl_value_at(TL: TLRef, t: float) -> float:
    """Look up the active load-torque value at time t.

    TLRef has t[i] = END of segment i. searchsorted with side='right' gives the
    segment index whose t-boundary first exceeds t.
    """
    i = int(np.searchsorted(TL.t, t, side="right"))
    return float(TL.ref[min(i, len(TL.t) - 1)])


class Simulator:
    """Multi-rate orchestrator over a fully-assembled :class:`Drivetrain`.

    The Simulator owns only the clock logic and per-step signal routing.
    Resource ownership (in particular the FMU) lives on the Drivetrain,
    which is the context manager around a run.
    """

    def __init__(self, drive: Drivetrain) -> None:
        self.drive = drive
        # Cached for the inner loop. Keep them on the Simulator so the hot
        # path doesn't reach back through the drive on every step.
        self.Vdc = drive.Vdc
        self.p = drive.motor.p
        self.kt_dq = drive.kt_dq
        self.dt_ctrl = drive.dt_ctrl

    def run(
        self,
        TL_ref: TLRef,
        T_s: float | None = None,
        T_f: float | None = None,
        *,
        i_q_ref_override: float | None = None,
        i_d_ref_override: float | None = None,
        T_L_override: float | None = None,
        inverter_mode: Literal["ideal", "average", "switching"] = "switching",
        sampling_phase: Literal["valley", "midpoint", "double"] = "valley",
    ) -> pl.DataFrame:
        """Run the closed-loop simulation and return a polars DataFrame of the log.

        Arguments:
            TL_ref            piecewise-constant load-torque trajectory.
            T_s               inner sim step [s]. Default = T_pwm/20.
            T_f               horizon [s]. Default = TL_ref.t[-1].
            i_q_ref_override  if not None, used in place of TL_ref/kt_dq.
            i_d_ref_override  if not None, used in place of 0.0.
            T_L_override      if not None, used in place of TL_ref(t) as the
                              mechanical load fed to the FMU.
            inverter_mode     "ideal"     : v_abc_ref straight to FMU.
                              "average"   : duty as in switching, but emit
                                            cycle-average (d-0.5)*Vdc, no
                                            dead-time. Diagnostic.
                              "switching" : real PWM compare + dead-time
                                            (default).
            sampling_phase    Where in the PWM cycle the FOC samples and ticks:
                              "valley"   : single sample at every carrier
                                           valley (t = T_pwm, 2·T_pwm, …).
                                           Default.
                              "midpoint" : single sample at every carrier
                                           peak (t = T_pwm/2, 3·T_pwm/2, …).
                                           Equivalent to valley for sine PWM
                                           with a linear ramp.
                              "double"   : two abc-frame samples per period
                                           (one at the carrier peak, one at
                                           the valley), averaged before the
                                           FOC tick. Cancels the in-period
                                           ramp exactly when it is linear,
                                           and rejects dead-time-induced
                                           edge asymmetry — the textbook
                                           production technique.
        """
        T_pwm = 1.0 / self.drive.controller.f_pwm
        if T_s is None:
            # 20x oversampling of the PWM carrier — the floor below enforces
            # the >10x minimum.
            T_s = T_pwm / 20.0
        tau_e = self.drive.motor.L_s / self.drive.motor.R_s
        if T_s > tau_e / 3.0:
            msg = f"T_s ({T_s * 1e6:.2f} us) too large for stable discrete PI; require T_s <= tau_e/3 = {tau_e / 3.0 * 1e6:.2f} us (tau_e = L_s/R_s = {tau_e * 1e6:.2f} us)."
            raise ValueError(msg)
        if T_s > T_pwm / 10.0:
            msg = f"T_s ({T_s * 1e6:.2f} us) too large to resolve PWM at f_pwm={self.drive.controller.f_pwm:g} Hz; require T_s <= T_pwm/10 = {T_pwm / 10.0 * 1e6:.2f} us."
            raise ValueError(msg)

        T_horizon = float(T_f) if T_f is not None else float(TL_ref.t[-1])
        n_steps = round(T_horizon / T_s)

        all_cols = list(LOG_COLUMNS) + list(BOOL_COLUMNS) + list(INT_COLUMNS)
        log = {k: (np.full(n_steps, np.nan) if k in NAN_INIT_COLUMNS else np.zeros(n_steps)) for k in all_cols}

        # ZOH state for v_abc_ref between FOC ticks.
        v_a_ref = 0.0
        v_b_ref = 0.0
        v_c_ref = 0.0
        # Initial ctrl_phase places the first FOC tick at either the carrier
        # valley (t = dt_ctrl) or the carrier peak (t = dt_ctrl / 2). Double
        # sampling fires the FOC at the valley but takes an intermediate
        # snapshot at the peak — same phase initialisation as valley mode.
        ctrl_phase = 0.5 * self.dt_ctrl if sampling_phase == "midpoint" else 0.0
        # Double-sampling: the midpoint-snapshot bookkeeping. The snapshot is
        # taken once per period (between FOC ticks), then averaged with the
        # valley sample at the next FOC tick.
        half_dt_ctrl = 0.5 * self.dt_ctrl
        mid_snap = (0.0, 0.0, 0.0)
        mid_snap_due = sampling_phase == "double"
        # LCL state observers (d, q axes). Constructed lazily only when the
        # filter is engaged in switching mode — otherwise the LCL states are
        # not part of the plant and the estimates are left as NaN.
        lcl_filter = self.drive.lcl_filter
        observers_active = lcl_filter is not None and inverter_mode == "switching"
        obs_d: LCLObserver | None = None
        obs_q: LCLObserver | None = None
        if observers_active:
            assert lcl_filter is not None
            params = LCLParams.from_runtime(L_f=lcl_filter.L_f, C_f=lcl_filter.C_f, motor=self.drive.motor, Ts=T_s)
            # Place observer poles at α · ω_res via Ackermann; α from
            # SimParams.observer_pole_multiplier (default 3). Both d and q
            # axes share the same plant matrices (LCL is axis-symmetric)
            # so the gain is computed once and reused.
            A_obs = np.array(
                [
                    [-params.R1 / params.L1, -1.0 / params.L1, 0.0],
                    [1.0 / params.Cf, 0.0, -1.0 / params.Cf],
                    [0.0, 1.0 / params.Lload, -params.Rload / params.Lload],
                ]
            )
            C_obs = np.array([0.0, 0.0, 1.0])  # motor_current measurement
            pole = self.drive.observer_pole_multiplier * params.resonance_frequency_rad_s()
            L_obs = compute_observer_gain(A_obs, C_obs, pole=pole)
            obs_d = LCLObserver(params, measurement_type="motor_current", observer_gain=L_obs)
            obs_q = LCLObserver(params, measurement_type="motor_current", observer_gain=L_obs)

        # Local aliases for the hot inner loop.
        motor_fmu = self.drive.motor_fmu
        encoder = self.drive.encoder
        controller = self.drive.controller
        inverter = self.drive.inverter

        for k in range(n_steps):
            t = k * T_s

            # (a) PMSM measurements + encoder.
            i_a, i_b, i_c, theta_m_true, omega_m_true, T_e = motor_fmu.measure()
            (theta_m_meas, omega_m_meas, theta_e_meas, i_a_meas, i_b_meas, i_c_meas) = encoder.step(theta_m_true, omega_m_true, (i_a, i_b, i_c), t)
            omega_e_meas = self.p * omega_m_meas

            # (a2) LCL state observers — advance one T_s using the inverter
            # voltage that has been driving the plant since the last update
            # (controller.v_d from the prior FOC tick, ZOH-held) and the
            # current dq-frame measurement. Done BEFORE the FOC tick so the
            # active-damping signal ic_hat is in-phase with the resonance
            # rather than one-cycle delayed.
            if obs_d is not None and obs_q is not None:
                i_d_now, i_q_now = abc_to_dq(i_a_meas, i_b_meas, i_c_meas, theta_e_meas)
                e_q = omega_e_meas * self.drive.motor.lambda_PM
                d_est = obs_d.predict_update(v_inv=controller.v_d, y_meas=i_d_now, e=0.0)
                q_est = obs_q.predict_update(v_inv=controller.v_q, y_meas=i_q_now, e=e_q)
                ic_d_hat = d_est["ic_hat"]
                ic_q_hat = q_est["ic_hat"]
                log["i1_d_hat"][k] = d_est["i1_hat"]
                log["vc_d_hat"][k] = d_est["vc_hat"]
                log["im_d_hat"][k] = d_est["im_hat"]
                log["ic_d_hat"][k] = ic_d_hat
                log["i1_q_hat"][k] = q_est["i1_hat"]
                log["vc_q_hat"][k] = q_est["vc_hat"]
                log["im_q_hat"][k] = q_est["im_hat"]
                log["ic_q_hat"][k] = ic_q_hat
            else:
                ic_d_hat = 0.0
                ic_q_hat = 0.0

            # (b) FOC tick once per dt_ctrl.
            T_e_ref = _tl_value_at(TL_ref, t)
            i_q_ref = i_q_ref_override if i_q_ref_override is not None else T_e_ref / self.kt_dq
            i_d_ref = i_d_ref_override if i_d_ref_override is not None else 0.0
            # Double sampling: take an intermediate snapshot at the carrier
            # peak (mid-period). One per period; cleared at each FOC tick.
            if sampling_phase == "double" and mid_snap_due and ctrl_phase >= half_dt_ctrl - 1e-15:
                mid_snap = (i_a_meas, i_b_meas, i_c_meas)
                mid_snap_due = False
            if ctrl_phase >= self.dt_ctrl - 1e-15:
                ctrl_phase -= self.dt_ctrl
                if sampling_phase == "double":
                    # Average the peak and valley snapshots in abc-frame
                    # before handing to the FOC. Park-transform uses
                    # theta_e_meas at the valley instant; the ~T_pwm/2 phase
                    # delay against the peak snapshot is a known and small
                    # error term in production drives.
                    i_a_in = 0.5 * (mid_snap[0] + i_a_meas)
                    i_b_in = 0.5 * (mid_snap[1] + i_b_meas)
                    i_c_in = 0.5 * (mid_snap[2] + i_c_meas)
                    mid_snap_due = True
                else:
                    i_a_in, i_b_in, i_c_in = i_a_meas, i_b_meas, i_c_meas
                v_a_ref, v_b_ref, v_c_ref = controller.step(
                    i_a_in,
                    i_b_in,
                    i_c_in,
                    theta_e_meas,
                    omega_e_meas,
                    i_d_ref=i_d_ref,
                    i_q_ref=i_q_ref,
                    dt=self.dt_ctrl,
                    ic_d_hat=ic_d_hat,
                    ic_q_hat=ic_q_hat,
                )
            ctrl_phase += T_s

            # (c) Power stage: ideal voltage source / cycle-averaged PWM / real switching.
            if inverter_mode == "ideal":
                # Ideal-voltage path: FOC refs go straight to the FMU.
                d_a = max(0.0, min(1.0, 0.5 + v_a_ref / self.Vdc))
                d_b = max(0.0, min(1.0, 0.5 + v_b_ref / self.Vdc))
                d_c = max(0.0, min(1.0, 0.5 + v_c_ref / self.Vdc))
                s_a = s_b = s_c = 0
                v_a, v_b, v_c = v_a_ref, v_b_ref, v_c_ref
            elif inverter_mode == "average":
                # Same duty calculation as switching mode (clip + 0.5 + v/Vdc),
                # but feed the FMU the cycle-average voltage (d-0.5)*Vdc. No
                # dead-time. Isolates duty / scaling bugs from switching ripple.
                d_a, d_b, d_c, _, _, _ = inverter._pwm.step(v_a_ref, v_b_ref, v_c_ref, self.Vdc, t, T_s)
                v_a = (d_a - 0.5) * self.Vdc
                v_b = (d_b - 0.5) * self.Vdc
                v_c = (d_c - 0.5) * self.Vdc
                s_a = s_b = s_c = 0
            else:
                d_a, d_b, d_c, s_a, s_b, s_c, v_a, v_b, v_c = inverter.step(v_a_ref, v_b_ref, v_c_ref, i_a, i_b, i_c, t, T_s)

            # (c2) Optional LCL output filter — only meaningful with real
            # switching; ideal/average already produce smooth voltages so we
            # pass through to keep the diagnostic intent of those modes intact.
            if lcl_filter is not None and inverter_mode == "switching":
                v_a_motor, v_b_motor, v_c_motor = lcl_filter.step((v_a, v_b, v_c), (i_a, i_b, i_c), T_s)
            else:
                v_a_motor, v_b_motor, v_c_motor = v_a, v_b, v_c

            # (d) PMSM advance — fed the filtered voltage when the filter is on.
            T_L = T_L_override if T_L_override is not None else T_e_ref
            motor_fmu.step(v_a_motor, v_b_motor, v_c_motor, T_L, T_s)

            log["t"][k] = t
            log["TL_ref"][k] = T_L
            log["T_e"][k] = T_e
            log["i_d_ref"][k] = i_d_ref
            log["i_q_ref"][k] = i_q_ref
            log["i_d_meas"][k] = controller.i_d_meas
            log["i_q_meas"][k] = controller.i_q_meas
            log["v_d_ref"][k] = controller.v_d
            log["v_q_ref"][k] = controller.v_q
            log["i_a"][k] = i_a
            log["i_b"][k] = i_b
            log["i_c"][k] = i_c
            log["theta_m_true"][k] = theta_m_true
            log["theta_m_meas"][k] = theta_m_meas
            log["theta_e_true"][k] = (self.p * theta_m_true) % TWO_PI
            log["theta_e_meas"][k] = theta_e_meas
            log["omega_m_true"][k] = omega_m_true
            log["omega_m_meas"][k] = omega_m_meas
            log["v_a_ref"][k] = v_a_ref
            log["v_b_ref"][k] = v_b_ref
            log["v_c_ref"][k] = v_c_ref
            log["d_a"][k] = d_a
            log["d_b"][k] = d_b
            log["d_c"][k] = d_c
            log["s_a"][k] = s_a
            log["s_b"][k] = s_b
            log["s_c"][k] = s_c
            log["v_a"][k] = v_a
            log["v_b"][k] = v_b
            log["v_c"][k] = v_c
            log["v_a_motor"][k] = v_a_motor
            log["v_b_motor"][k] = v_b_motor
            log["v_c_motor"][k] = v_c_motor
            log["m_index"][k] = inverter._pwm.last_m_index
            log["pwm_mode_active"][k] = _PWM_MODE_CODE.get(inverter._pwm.last_active_mode, 0)
            log["sat_d"][k] = controller.sat_d
            log["sat_q"][k] = controller.sat_q
            log["ad_d"][k] = controller.ad_d
            log["ad_q"][k] = controller.ad_q

        columns: dict[str, pl.Series] = {col: pl.Series(col, log[col]) for col in LOG_COLUMNS}
        for col in BOOL_COLUMNS:
            columns[col] = pl.Series(col, log[col].astype(bool))
        for col in INT_COLUMNS:
            columns[col] = pl.Series(col, log[col].astype(np.int8))
        return pl.DataFrame(columns)


# ---------------------------------------------------------------------------
# Headless run pipeline (SimParams -> DataFrame + parquet + SimMeta).
# ---------------------------------------------------------------------------


def _artifacts_dir() -> Path:
    return get_config().artifacts.path


def canonical_params_json(params: dict) -> str:
    norm = {k: (round(float(v), 12) if isinstance(v, float) else v) for k, v in sorted(params.items())}
    return json.dumps(norm, separators=(",", ":"), sort_keys=True)


def params_hash(json_str: str) -> str:
    return hashlib.blake2b(json_str.encode(), digest_size=8).hexdigest()


def output_path_for(motor: PmsmModel) -> Path:
    fname = f"{motor.family.replace(' ', '_')}_{motor.name}.parquet"
    return _artifacts_dir() / fname


def artifact_by_hash(hash_str: str) -> Path | None:
    """Look up the parquet artifact whose slimtorq.params_hash matches.

    The output filename is keyed by motor name, not hash, so we have to scan
    metadata. Cheap — pyarrow reads only the footer.
    """
    root = _artifacts_dir()
    if not root.exists():
        return None
    for p in root.glob("*.parquet"):
        try:
            md = pq.read_metadata(str(p)).metadata or {}
        except Exception:
            continue
        if md.get(b"slimtorq.params_hash") == hash_str.encode():
            return p
    return None


def read_metadata(path: Path) -> dict[str, str]:
    raw = pq.read_metadata(str(path)).metadata or {}
    return {k.decode(): v.decode() for k, v in raw.items() if k.decode().startswith("slimtorq.")}


def default_tl_ref(motor: PmsmModel, t_end: float, t_step: float, frac: float) -> TLRef:
    """Zero until t_step, then step to frac · te_peak_1s, hold to t_end."""
    amp = frac * motor.te_peak_1s
    return TLRef(ref=np.array([0.0, amp]), t=np.array([t_step, t_end]))


# Headroom against the steady-state R·i_q bound — leaves room for the
# transient overshoot during the current ramp and the back-EMF term
# ω_e·λ_PM as the rotor accelerates over t_end.
_SAFE_FRAC_MARGIN = 0.75


def max_safe_step_frac(motor: PmsmModel) -> float:
    """Largest TL_ref / Te_peak (rounded down to 0.1) that keeps the
    closed-loop |v_dq| within the sinusoidal-PWM linear range V_max = Vdc/2.

    Derived from the steady-state q-axis voltage bound at zero speed:

        v_q ≈ R_s · i_q   with   i_q = frac · te_peak_1s / (1.5·p·λ_PM)

    Solving ``v_q <= margin · V_max`` for frac and flooring to the nearest
    0.1 yields a per-motor default that doesn't saturate out of the box.
    High-resistance windings (e.g. 8-turn variants at 72 V) clamp at 0.1.
    """
    V_max = 0.5 * float(motor.rated_voltage)
    kt_dq = 1.5 * motor.p * motor.lambda_PM
    frac_max = _SAFE_FRAC_MARGIN * V_max * kt_dq / (motor.R_s * motor.te_peak_1s)
    return max(0.1, min(1.0, math.floor(frac_max * 10.0) / 10.0))


def resolve_t_step_frac(p: SimParams, motor: PmsmModel) -> float:
    """Return ``p.t_step_frac`` if the user supplied one, otherwise the
    per-motor safe default from :func:`max_safe_step_frac`."""
    return float(p.t_step_frac) if p.t_step_frac is not None else max_safe_step_frac(motor)


def write_parquet(
    df: pl.DataFrame,
    *,
    motor: PmsmModel,
    controller: FOCController,
    Vdc: float,
    f_pwm: float,
    t_dead: float,
    ts_enc: float,
    inverter_mode: str,
    pwm_mode: str,
    filter_enabled: bool,
    filter_fc: float,
    L_f: float,
    C_f: float,
    R_d: float,
    pi_mode: str,
    pi_tc: float | None,
    pi_k1: float,
    params_json: str,
    params_hash_str: str,
    out_path: Path,
) -> None:
    """Persist a Simulator.run() DataFrame as parquet with slimtorq.* metadata.

    b_est (steady-state viscous-friction estimate) is derived inline from the
    trailing 20% of the run: B ~= mean(T_e - TL_ref) / mean(omega_m_true).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n = df.height
    tail = df.slice(int(0.8 * n), n - int(0.8 * n))
    mean_omega = float(tail["omega_m_true"].mean())
    mean_dT = float((tail["T_e"] - tail["TL_ref"]).mean())
    b_est: float | None = mean_dT / mean_omega if abs(mean_omega) > 1e-3 else None

    table = df.to_arrow()
    meta = {
        b"slimtorq.schema_version": SCHEMA_VERSION.encode(),
        b"slimtorq.params_hash": params_hash_str.encode(),
        b"slimtorq.params_json": params_json.encode(),
        b"slimtorq.foc_kp": f"{controller.Kp:.10g}".encode(),
        b"slimtorq.foc_ki": f"{controller.Ki:.10g}".encode(),
        b"slimtorq.pi_mode": pi_mode.encode(),
        b"slimtorq.pi_tc": (b"null" if pi_tc is None else f"{pi_tc:.10g}".encode()),
        b"slimtorq.pi_k1": f"{pi_k1:.10g}".encode(),
        b"slimtorq.vdc": f"{Vdc:.10g}".encode(),
        b"slimtorq.f_pwm": f"{f_pwm:.10g}".encode(),
        b"slimtorq.t_dead": f"{t_dead:.10g}".encode(),
        b"slimtorq.ts_enc": f"{ts_enc:.10g}".encode(),
        b"slimtorq.inverter_mode": inverter_mode.encode(),
        b"slimtorq.pwm_mode": pwm_mode.encode(),
        b"slimtorq.filter_enabled": (b"1" if filter_enabled else b"0"),
        b"slimtorq.filter_fc": f"{filter_fc:.10g}".encode(),
        b"slimtorq.filter_lf": f"{L_f:.10g}".encode(),
        b"slimtorq.filter_cf": f"{C_f:.10g}".encode(),
        b"slimtorq.filter_rd": f"{R_d:.10g}".encode(),
        b"slimtorq.b_est": (b"null" if b_est is None else f"{b_est:.10g}".encode()),
        b"slimtorq.motor_family": motor.family.encode(),
        b"slimtorq.motor_name": motor.name.encode(),
        b"slimtorq.motor_rated_voltage": f"{motor.rated_voltage:.6g}".encode(),
        b"slimtorq.r_s": f"{motor.R_s:.10g}".encode(),
        b"slimtorq.l_s": f"{motor.L_s:.10g}".encode(),
        b"slimtorq.pole_pairs": str(motor.p).encode(),
        b"slimtorq.i_q_peak": f"{i_q_peak_of(motor):.10g}".encode(),
        b"slimtorq.te_peak_1s": f"{motor.te_peak_1s:.10g}".encode(),
    }
    table = table.replace_schema_metadata(meta)
    pq.write_table(table, str(out_path))


def gains_for_mode(
    variant: str,
    pi_mode: PiMode,
    f_pwm: float,
    pi_tc: float | None = None,
    pi_k1: float = 1.44,
    *,
    filter_enabled: bool = False,
    filter_fc: float = 5000.0,
) -> tuple[float, float] | None:
    """Auto-suggested (Kp, Ki) for variant + mode. ``None`` for manual.

    Wraps :func:`src.drivetrain._auto_tune` with catalog lookup so callers
    only need a variant name. The tuning algorithm itself lives with the
    drivetrain because picking gains is the last step of drive assembly.
    """
    if pi_mode == "manual":
        return None
    kp, ki, _kd = _auto_tune(CATALOG[variant], pi_mode, float(f_pwm), pi_tc, float(pi_k1), filter_enabled, float(filter_fc))
    return kp, ki


def _params_dict_for_hash(p: SimParams, t_step_frac: float, vdc: float) -> dict:
    """The dict the old Dash callback hashed at app.py:648-678. ``t_step_frac``
    and ``vdc`` are passed in resolved so the hash reflects the actual sim
    (per-motor auto default vs explicit user value)."""
    return {
        "variant_name": p.variant_name,
        "f_pwm": float(p.f_pwm),
        "t_dead": float(p.t_dead),
        "n_bits": int(p.n_bits),
        "theta_offset": float(p.theta_offset),
        "A1": float(p.A1),
        "k1": int(p.k1),
        "phi1": float(p.phi1),
        "A2": float(p.A2),
        "k2": int(p.k2),
        "phi2": float(p.phi2),
        "A3": float(p.A3),
        "k3": int(p.k3),
        "phi3": float(p.phi3),
        "ts_enc": float(p.ts_enc),
        "dt_sim": None if p.dt_sim is None else float(p.dt_sim),
        "t_end": float(p.t_end),
        "t_step": float(p.t_step),
        "t_step_frac": float(t_step_frac),
        "Tf": None if p.Tf is None else float(p.Tf),
        "pi_mode": p.pi_mode,
        "Kp": float(p.Kp) if p.Kp is not None else None,
        "Ki": float(p.Ki) if p.Ki is not None else None,
        "pi_tc": None if p.pi_tc is None else float(p.pi_tc),
        "pi_k1": float(p.pi_k1) if p.pi_k1 is not None else 1.44,
        "inverter_mode": p.inverter_mode,
        "pwm_mode": p.pwm_mode,
        "filter_enabled": bool(p.filter_enabled),
        "filter_fc": float(p.filter_fc),
        "vdc": float(vdc),
        "zeta_target": float(p.zeta_target),
        "observer_pole_multiplier": float(p.observer_pole_multiplier),
    }


def i_q_peak_of(motor: PmsmModel) -> float:
    """Peak of rated continuous q-axis current [A]. Amplitude-invariant Clarke gives
    i_peak = sqrt(2) * I_rms, so i_q_peak = sqrt(2) * i_cont."""
    return math.sqrt(2.0) * motor.i_cont


def _tracking_err_pct(df: pl.DataFrame, motor: PmsmModel) -> float:
    """RMS(i_q_meas - i_q_ref) / i_q_peak over trailing 80%, as percent.

    Motor-relative normalization — stable across operating points and reused
    for the d-axis badge (where i_d_ref = 0 makes a ref-relative percentage
    meaningless).
    """
    tail = df.slice(int(0.8 * df.height), df.height - int(0.8 * df.height))
    err = (tail["i_q_meas"] - tail["i_q_ref"]).to_numpy()
    err_rms = float(np.sqrt(np.mean(err * err)))
    return 100.0 * err_rms / i_q_peak_of(motor)


def run_simulation(p: SimParams) -> tuple[pl.DataFrame, SimMeta]:
    """Run one sim end-to-end. Writes parquet, returns DataFrame + metadata.

    Raises ValueError on invalid inputs (unknown variant, t_step >= t_end).
    Anything else (FMU faults, numerical blow-ups) propagates.
    """
    if p.variant_name not in CATALOG:
        msg = f"unknown variant: {p.variant_name!r}"
        raise ValueError(msg)
    if p.t_step >= p.t_end:
        msg = f"t_step ({p.t_step}) must be < t_end ({p.t_end})"
        raise ValueError(msg)

    motor = CATALOG[p.variant_name]
    t_step_frac = resolve_t_step_frac(p, motor)
    vdc = resolve_vdc(p, motor)
    params_json = canonical_params_json(_params_dict_for_hash(p, t_step_frac, vdc))
    h = params_hash(params_json)
    out_path = output_path_for(motor)
    TL = default_tl_ref(motor, t_end=p.t_end, t_step=p.t_step, frac=t_step_frac)
    # Derive (L_f, C_f, R_d) unconditionally for parquet metadata — the
    # Drivetrain only instantiates an LCLFilter when filter_enabled is true,
    # but the metadata always records what the filter would have been.
    L_f, C_f, R_d = FilterConfig.derive_components(motor.L_s, p.filter_fc)

    with Drivetrain.build(p, motor) as drive:
        sim = Simulator(drive)
        df = sim.run(TL, T_s=p.dt_sim, T_f=p.Tf, inverter_mode=p.inverter_mode)

        write_parquet(
            df,
            motor=motor,
            controller=drive.controller,
            Vdc=drive.Vdc,
            f_pwm=p.f_pwm,
            t_dead=p.t_dead,
            ts_enc=p.ts_enc,
            inverter_mode=p.inverter_mode,
            pwm_mode=p.pwm_mode,
            filter_enabled=p.filter_enabled,
            filter_fc=p.filter_fc,
            L_f=L_f,
            C_f=C_f,
            R_d=R_d,
            pi_mode=p.pi_mode,
            pi_tc=p.pi_tc,
            pi_k1=p.pi_k1,
            params_json=params_json,
            params_hash_str=h,
            out_path=out_path,
        )
        parquet_meta = read_metadata(out_path)
        n = df.height
        tail = df.slice(int(0.75 * n), n - int(0.75 * n))
        i_peak_rated = i_q_peak_of(motor)
        # Window of ~2 PWM periods for the abc-frame ripple metric. Short
        # enough that the rotating fundamental at ω_e can't swing across it,
        # so the windowed peak-to-peak isolates PWM-band content from the
        # fundamental sinusoid. T_s is the simulator's inner step; default
        # T_s = T_pwm / 20 ⇒ window ≈ 40 samples.
        T_pwm = 1.0 / p.f_pwm
        T_s_default = float(p.dt_sim) if p.dt_sim is not None else T_pwm / 20.0
        ia_window = max(4, int(2.0 * T_pwm / T_s_default))
        meta = SimMeta(
            params_hash=h,
            rows=df.height,
            err_pct=_tracking_err_pct(df, motor),
            artifact_name=out_path.name,
            foc_kp=drive.controller.Kp,
            foc_ki=drive.controller.Ki,
            pi_mode=p.pi_mode,
            motor_family=motor.family,
            motor_name=motor.name,
            rated_voltage=drive.Vdc,
            iq_ripple=RippleStats.from_signal(tail["i_q_meas"].to_numpy(), rated=i_peak_rated, cmd=float(tail["i_q_ref"].mean())),
            te_ripple=RippleStats.from_signal(tail["T_e"].to_numpy(), rated=motor.te_cont_cat, cmd=float(tail["TL_ref"].mean())),
            ia_ripple=RippleStats.from_signal(tail["i_a"].to_numpy(), rated=i_peak_rated, cmd=None, window_samples=ia_window),
            parquet_meta=parquet_meta,
        )
    return df, meta
