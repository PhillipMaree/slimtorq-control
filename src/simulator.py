"""Multi-rate orchestrator for the FOC → Inverter → PMSM → Encoder loop.

The Simulator wires together the four physical components — motor, encoder,
controller, inverter — and drives them with three clocks:

- T_s     inner simulation step (FMU doStep, PWM carrier comparison, inverter
          dead-time tracking). Default = T_pwm / 20.
- dt_ctrl FOC current-loop update period. Derived as 1 / controller.f_pwm
          — one FOC tick per PWM cycle, the standard digital-FOC convention.
- Ts_enc  encoder sample period (lives inside FluxEncoder, queried by
          EncoderMeasurement; independent of the above two).

Between FOC ticks the FOC's last v_abc_ref output is held by ZOH and fed into
the Inverter every T_s.

Use as a context manager so the FMU is always released:

    with Simulator(motor, encoder, controller, inverter) as sim:
        df = sim.run(TL_ref, T_s, T_f)
"""

from __future__ import annotations

from types import TracebackType

import numpy as np
import polars as pl

from controller import FOCController
from encoder import EncoderMeasurement
from model import TLRef
from switching import Inverter, PMSMAbcModel

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
)
BOOL_COLUMNS = ("sat_d", "sat_q")
INT_COLUMNS = ("s_a", "s_b", "s_c")


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

    def __init__(self, motor: PMSMAbcModel, encoder: EncoderMeasurement, controller: FOCController, inverter: Inverter) -> None:
        self.motor = motor
        self.encoder = encoder
        self.controller = controller
        self.inverter = inverter

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
        bypass_pwm: bool = False,
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
            bypass_pwm        if True, FOC's v_abc_ref bypass the inverter
                              and feed the FMU directly (diagnostic only).
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

            # (c) Power stage: PWM + inverter, or bypass.
            if bypass_pwm:
                # Ideal-voltage path: FOC refs go straight to the FMU. Duty is
                # logged for inspection but the switch states are not used.
                d_a = 0.5 + v_a_ref / self.Vdc
                d_b = 0.5 + v_b_ref / self.Vdc
                d_c = 0.5 + v_c_ref / self.Vdc
                s_a = s_b = s_c = 0
                v_a, v_b, v_c = v_a_ref, v_b_ref, v_c_ref
            else:
                d_a, d_b, d_c, s_a, s_b, s_c, v_a, v_b, v_c = self.inverter.step(v_a_ref, v_b_ref, v_c_ref, i_a, i_b, i_c, t, T_s)

            # (d) PMSM advance.
            T_L = T_L_override if T_L_override is not None else T_e_ref
            self.motor.step(v_a, v_b, v_c, T_L, T_s)

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
            log["sat_d"][k] = self.controller.sat_d
            log["sat_q"][k] = self.controller.sat_q

        columns: dict[str, pl.Series] = {col: pl.Series(col, log[col]) for col in LOG_COLUMNS}
        for col in BOOL_COLUMNS:
            columns[col] = pl.Series(col, log[col].astype(bool))
        for col in INT_COLUMNS:
            columns[col] = pl.Series(col, log[col].astype(np.int8))
        return pl.DataFrame(columns)
