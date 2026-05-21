"""Multi-rate FOC simulation pipeline.

Two layers in one module:

1. :class:`Simulator` — the multi-rate orchestrator that wires the four
   physical components (motor, encoder, controller, inverter) together
   and steps them with three clocks:

   - T_s     inner simulation step (FMU doStep, PWM carrier comparison,
             inverter dead-time tracking). Default = T_pwm / 20.
   - dt_ctrl FOC current-loop update period. Derived as 1 / controller.f_pwm
             — one FOC tick per PWM cycle, the standard digital-FOC convention.
   - Ts_enc  encoder sample period (lives inside FluxEncoder, queried by
             EncoderMeasurement; independent of the above two).

   Between FOC ticks the FOC's last v_abc_ref output is held by ZOH and
   fed into the Inverter every T_s. Use as a context manager so the FMU is
   always released::

       with Simulator(motor, encoder, controller, inverter) as sim:
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
from types import TracebackType
from typing import Literal

import numpy as np
import polars as pl
import pyarrow.parquet as pq

from src import get_config
from src.controller import FOCController
from src.encoder import EncoderMeasurement, FluxEncoder
from src.model import (
    EncoderConfig,
    FilterConfig,
    FocConfig,
    InverterConfig,
    PiMode,
    PmsmModel,
    SimMeta,
    SimParams,
    TLRef,
    load_catalog,
)
from src.switching import Inverter, LCLFilter, PMSMAbcModel
from src.tuning import modulus_optimum_tuning, skogestad_tuning

SCHEMA_VERSION = "7"
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
    """Orchestrator for the four-component pipeline.

    Arguments are fully-built component wrappers; the Simulator only owns the
    multi-rate clock logic and the per-step signal routing. Lifecycle (in
    particular the FMU) is released on __exit__.
    """

    def __init__(self, motor: PMSMAbcModel, encoder: EncoderMeasurement, controller: FOCController, inverter: Inverter, filter: LCLFilter | None = None) -> None:
        self.motor = motor
        self.encoder = encoder
        self.controller = controller
        self.inverter = inverter
        # Optional LCL low-pass between inverter terminals and motor.
        # Engaged only in switching mode; ideal/average bypass the filter
        # because their voltage is already smooth.
        self.filter = filter

        self.Vdc = inverter.Vdc
        self.p = motor.p
        # T_e = 1.5·p·ψ_m·i_q  =>  i_q_ref = T_e_ref / kt_dq.
        self.kt_dq = 1.5 * motor.p * motor.motor.psi_m
        # One FOC tick per PWM cycle — standard digital-FOC convention.
        self.dt_ctrl = 1.0 / controller.f_pwm

    def __enter__(self) -> Simulator:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        # Why: release the FMU even if run() raised. fmpy's terminate/free
        # raise if called twice, so swallow on the way out — a second close
        # here would mask the original exception.
        try:
            self.motor.close()
        except Exception:
            pass

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
        """
        T_pwm = 1.0 / self.controller.f_pwm
        if T_s is None:
            # 20x oversampling of the PWM carrier — the floor below enforces
            # the >10x minimum.
            T_s = T_pwm / 20.0
        tau_e = self.motor.motor.L_s / self.motor.motor.R_s
        if T_s > tau_e / 3.0:
            msg = f"T_s ({T_s * 1e6:.2f} us) too large for stable discrete PI; require T_s <= tau_e/3 = {tau_e / 3.0 * 1e6:.2f} us (tau_e = L_s/R_s = {tau_e * 1e6:.2f} us)."
            raise ValueError(msg)
        if T_s > T_pwm / 10.0:
            msg = f"T_s ({T_s * 1e6:.2f} us) too large to resolve PWM at f_pwm={self.controller.f_pwm:g} Hz; require T_s <= T_pwm/10 = {T_pwm / 10.0 * 1e6:.2f} us."
            raise ValueError(msg)

        T_horizon = float(T_f) if T_f is not None else float(TL_ref.t[-1])
        n_steps = round(T_horizon / T_s)

        all_cols = list(LOG_COLUMNS) + list(BOOL_COLUMNS) + list(INT_COLUMNS)
        log = {k: np.zeros(n_steps) for k in all_cols}

        # ZOH state for v_abc_ref between FOC ticks.
        v_a_ref = 0.0
        v_b_ref = 0.0
        v_c_ref = 0.0
        ctrl_phase = 0.0

        for k in range(n_steps):
            t = k * T_s

            # (a) PMSM measurements + encoder.
            i_a, i_b, i_c, theta_m_true, omega_m_true, T_e = self.motor.measure()
            (theta_m_meas, omega_m_meas, theta_e_meas, i_a_meas, i_b_meas, i_c_meas) = self.encoder.step(theta_m_true, omega_m_true, (i_a, i_b, i_c), t)
            omega_e_meas = self.p * omega_m_meas

            # (b) FOC tick once per dt_ctrl.
            T_e_ref = _tl_value_at(TL_ref, t)
            i_q_ref = i_q_ref_override if i_q_ref_override is not None else T_e_ref / self.kt_dq
            i_d_ref = i_d_ref_override if i_d_ref_override is not None else 0.0
            if ctrl_phase >= self.dt_ctrl - 1e-15:
                ctrl_phase -= self.dt_ctrl
                v_a_ref, v_b_ref, v_c_ref = self.controller.step(i_a_meas, i_b_meas, i_c_meas, theta_e_meas, omega_e_meas, i_d_ref=i_d_ref, i_q_ref=i_q_ref, dt=self.dt_ctrl)
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
                d_a, d_b, d_c, _, _, _ = self.inverter._pwm.step(v_a_ref, v_b_ref, v_c_ref, self.Vdc, t, T_s)
                v_a = (d_a - 0.5) * self.Vdc
                v_b = (d_b - 0.5) * self.Vdc
                v_c = (d_c - 0.5) * self.Vdc
                s_a = s_b = s_c = 0
            else:
                d_a, d_b, d_c, s_a, s_b, s_c, v_a, v_b, v_c = self.inverter.step(v_a_ref, v_b_ref, v_c_ref, i_a, i_b, i_c, t, T_s)

            # (c2) Optional LCL output filter — only meaningful with real
            # switching; ideal/average already produce smooth voltages so we
            # pass through to keep the diagnostic intent of those modes intact.
            if self.filter is not None and inverter_mode == "switching":
                v_a_motor, v_b_motor, v_c_motor = self.filter.step((v_a, v_b, v_c), (i_a, i_b, i_c), T_s)
            else:
                v_a_motor, v_b_motor, v_c_motor = v_a, v_b, v_c

            # (d) PMSM advance — fed the filtered voltage when the filter is on.
            T_L = T_L_override if T_L_override is not None else T_e_ref
            self.motor.step(v_a_motor, v_b_motor, v_c_motor, T_L, T_s)

            log["t"][k] = t
            log["TL_ref"][k] = T_L
            log["T_e"][k] = T_e
            log["i_d_ref"][k] = i_d_ref
            log["i_q_ref"][k] = i_q_ref
            log["i_d_meas"][k] = self.controller.i_d_meas
            log["i_q_meas"][k] = self.controller.i_q_meas
            log["v_d_ref"][k] = self.controller.v_d
            log["v_q_ref"][k] = self.controller.v_q
            log["i_a"][k] = i_a
            log["i_b"][k] = i_b
            log["i_c"][k] = i_c
            log["theta_m_true"][k] = theta_m_true
            log["theta_m_meas"][k] = theta_m_meas
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
            log["m_index"][k] = self.inverter._pwm.last_m_index
            log["pwm_mode_active"][k] = _PWM_MODE_CODE.get(self.inverter._pwm.last_active_mode, 0)
            log["sat_d"][k] = self.controller.sat_d
            log["sat_q"][k] = self.controller.sat_q

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
    }
    table = table.replace_schema_metadata(meta)
    pq.write_table(table, str(out_path))


def gains_for_mode(variant: str, pi_mode: PiMode, f_pwm: float, pi_tc: float | None = None, pi_k1: float = 1.44) -> tuple[float, float] | None:
    """Auto-suggested (Kp, Ki) for variant + mode. None for manual."""
    m = CATALOG[variant]
    if pi_mode == "modulus_optimum":
        return modulus_optimum_tuning(m.R_s, m.L_s, float(f_pwm))
    if pi_mode == "skogestad":
        return skogestad_tuning(m.R_s, m.L_s, float(f_pwm), k1=float(pi_k1), Tc=pi_tc)
    return None


def _resolve_gains(p: SimParams, motor: PmsmModel) -> tuple[float, float]:
    if p.pi_mode == "manual" and p.Kp is not None and p.Ki is not None:
        return float(p.Kp), float(p.Ki)
    if p.pi_mode == "skogestad":
        return skogestad_tuning(motor.R_s, motor.L_s, p.f_pwm, k1=p.pi_k1, Tc=p.pi_tc)
    return modulus_optimum_tuning(motor.R_s, motor.L_s, p.f_pwm)


def _params_dict_for_hash(p: SimParams) -> dict:
    """The dict the old Dash callback hashed at app.py:648-678."""
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
        "t_step_frac": float(p.t_step_frac),
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
    }


def _tracking_err_pct(df: pl.DataFrame) -> float:
    """RMS(i_q - i_q_ref) / RMS(i_q_ref) over trailing 80%, as percent."""
    tail = df.slice(int(0.8 * df.height), df.height - int(0.8 * df.height))
    err = (tail["i_q_meas"] - tail["i_q_ref"]).to_numpy()
    ref = tail["i_q_ref"].to_numpy()
    err_rms = float(np.sqrt(np.mean(err * err)))
    ref_floor = max(float(np.sqrt(np.mean(ref * ref))), float(abs(ref.mean())), 1e-9)
    return 100.0 * err_rms / ref_floor


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
    Vdc = float(motor.rated_voltage)
    params_for_hash = _params_dict_for_hash(p)
    params_json = canonical_params_json(params_for_hash)
    h = params_hash(params_json)
    out_path = output_path_for(motor)

    L_f, C_f, R_d = FilterConfig.derive_components(motor.L_s, p.filter_fc)
    encoder_cfg = EncoderConfig(
        n_bits=p.n_bits,
        theta_offset=p.theta_offset,
        A1=p.A1,
        k1=p.k1,
        phi1=p.phi1,
        A2=p.A2,
        k2=p.k2,
        phi2=p.phi2,
        A3=p.A3,
        k3=p.k3,
        phi3=p.phi3,
        Ts_enc=p.ts_enc,
    )
    TL = default_tl_ref(motor, t_end=p.t_end, t_step=p.t_step, frac=p.t_step_frac)
    Kp_used, Ki_used = _resolve_gains(p, motor)

    foc_cfg = FocConfig(
        R_s=motor.R_s,
        L_s=motor.L_s,
        psi_m=motor.psi_m,
        p=motor.p,
        Vdc=Vdc,
        f_pwm=p.f_pwm,
        Kp=Kp_used,
        Ki=Ki_used,
    )
    controller = FOCController(foc_cfg)
    inverter = Inverter(InverterConfig(Vdc=Vdc, f_pwm=p.f_pwm, t_dead=p.t_dead, pwm_mode=p.pwm_mode))
    encoder = EncoderMeasurement(FluxEncoder(encoder_cfg), p=motor.p)
    motor_fmu = PMSMAbcModel(motor)
    lcl_filter = LCLFilter(L_f=L_f, C_f=C_f, R_d=R_d) if p.filter_enabled else None

    with Simulator(motor_fmu, encoder, controller, inverter, filter=lcl_filter) as sim:
        df = sim.run(TL, T_s=p.dt_sim, T_f=p.Tf, inverter_mode=p.inverter_mode)

    write_parquet(
        df,
        motor=motor,
        controller=controller,
        Vdc=Vdc,
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
    meta = SimMeta(
        params_hash=h,
        rows=df.height,
        err_pct=_tracking_err_pct(df),
        artifact_name=out_path.name,
        foc_kp=controller.Kp,
        foc_ki=controller.Ki,
        pi_mode=p.pi_mode,
        motor_family=motor.family,
        motor_name=motor.name,
        rated_voltage=Vdc,
        parquet_meta=parquet_meta,
    )
    return df, meta
