"""Multi-rate orchestrator for the FOC → PWM → Inverter → PMSM → Encoder loop.

The Simulator owns three clocks:
- dt_sim   inner simulation step (FMU `doStep`, PWM carrier comparison, Inverter
           dead-time tracking). Default = T_pwm/20.
- dt_ctrl  FOC current-loop update period. Default = T_pwm (one FOC tick per
           PWM cycle, sampled synchronous with the carrier).
- Ts_enc   encoder sample period (lives inside FluxEncoder, queried by
           EncoderMeasurement; independent of the above two).

Between FOC ticks the FOC's last v_abc_ref output is held by ZOH and fed into
the PWMModulator every dt_sim. This is the standard digital-FOC convention.
"""

from __future__ import annotations

import numpy as np

from controller import FOCController
from encoder import EncoderMeasurement
from model import PmsmModel, TLRef
from switching import Inverter, PMSMAbcModel, PWMModulator


def _tl_value_at(TL: TLRef, t: float) -> float:
    """Look up the active load-torque value at time t.

    TLRef has t[i] = END of segment i. searchsorted with side='right' gives the
    segment index whose t-boundary first exceeds t.
    """
    i = int(np.searchsorted(TL.t, t, side="right"))
    return float(TL.ref[min(i, len(TL.t) - 1)])


class Simulator:
    """Owns the inner sim loop. One `step(t)` call advances time by dt_sim."""

    def __init__(self, *,
                 motor: PmsmModel,
                 foc: FOCController,
                 pwm: PWMModulator,
                 inverter: Inverter,
                 pmsm: PMSMAbcModel,
                 encoder: EncoderMeasurement,
                 TL: TLRef,
                 dt_sim: float,
                 dt_ctrl: float,
                 Vdc: float) -> None:
        self.motor = motor
        self.foc = foc
        self.pwm = pwm
        self.inverter = inverter
        self.pmsm = pmsm
        self.encoder = encoder
        self.TL = TL
        self.dt_sim = dt_sim
        self.dt_ctrl = dt_ctrl
        self.Vdc = Vdc
        # T_e = 1.5·p·ψ_m·i_q  =>  i_q_ref = T_e_ref / kt_dq.
        self.kt_dq = 1.5 * motor.p * motor.psi_m
        # ZOH state for v_abc_ref between FOC ticks.
        self.v_a_ref = 0.0
        self.v_b_ref = 0.0
        self.v_c_ref = 0.0
        self._ctrl_phase = 0.0
        # Cached references for logging.
        self.i_d_ref = 0.0
        self.i_q_ref = 0.0

    def step(self, t: float) -> dict:
        """Advance one dt_sim step. Returns a log row."""
        # (a) PMSM measurements + encoder.
        i_a, i_b, i_c, theta_m_true, omega_m_true, T_e = self.pmsm.measure()
        (theta_m_meas, omega_m_meas, theta_e_meas,
         i_a_meas, i_b_meas, i_c_meas) = self.encoder.step(
            theta_m_true, omega_m_true, (i_a, i_b, i_c), t)

        # (b) FOC tick once per dt_ctrl.
        T_e_ref = _tl_value_at(self.TL, t)
        self.i_q_ref = T_e_ref / self.kt_dq
        self.i_d_ref = 0.0
        if self._ctrl_phase >= self.dt_ctrl - 1e-15:
            self._ctrl_phase -= self.dt_ctrl
            self.v_a_ref, self.v_b_ref, self.v_c_ref = self.foc.step(
                i_a_meas, i_b_meas, i_c_meas, theta_e_meas,
                i_d_ref=self.i_d_ref, i_q_ref=self.i_q_ref, dt=self.dt_ctrl)
        self._ctrl_phase += self.dt_sim

        # (c) PWM every sim tick.
        d_a, d_b, d_c, s_a, s_b, s_c = self.pwm.step(
            self.v_a_ref, self.v_b_ref, self.v_c_ref, self.Vdc, t, self.dt_sim)

        # (d) Inverter — dead-time emulation uses measured i_abc sign.
        v_a, v_b, v_c = self.inverter.step(
            s_a, s_b, s_c, i_a, i_b, i_c, self.Vdc, self.dt_sim)

        # (e) PMSM advance.
        T_L = T_e_ref
        self.pmsm.step(v_a, v_b, v_c, T_L, self.dt_sim)

        return {
            "t": t, "TL_ref": T_L, "T_e": T_e,
            "i_d_ref": self.i_d_ref, "i_q_ref": self.i_q_ref,
            "i_d_meas": self.foc.i_d_meas, "i_q_meas": self.foc.i_q_meas,
            "v_d_ref": self.foc.v_d, "v_q_ref": self.foc.v_q,
            "i_a": i_a, "i_b": i_b, "i_c": i_c,
            "theta_m_true": theta_m_true, "theta_m_meas": theta_m_meas,
            "omega_m_true": omega_m_true, "omega_m_meas": omega_m_meas,
            "v_a_ref": self.v_a_ref, "v_b_ref": self.v_b_ref, "v_c_ref": self.v_c_ref,
            "d_a": d_a, "d_b": d_b, "d_c": d_c,
            "s_a": s_a, "s_b": s_b, "s_c": s_c,
            "v_a": v_a, "v_b": v_b, "v_c": v_c,
            "sat_d": self.foc.sat_d, "sat_q": self.foc.sat_q,
        }
