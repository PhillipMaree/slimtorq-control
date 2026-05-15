"""FOC building blocks: Clarke/Park transforms + dq current loop.

The plant (slotless PMSM in the abc frame) lives inside the OpenModelica FMU
and exposes phase currents + measured rotor angle. This module is what would
run on the MCU in a real drive: read i_abc and theta_m_meas, do
Clarke -> Park -> two PI loops on (id, iq) -> InvPark -> InvClarke, and write
v_abc back to the inverter.
"""

import math
from dataclasses import dataclass

SQRT3 = math.sqrt(3.0)


def clarke(a: float, b: float, c: float) -> tuple[float, float]:
    """Amplitude-invariant 3 -> 2 Clarke transform."""
    alpha = (2.0/3.0) * (a - 0.5*b - 0.5*c)
    beta  = (b - c) / SQRT3
    return alpha, beta


def inv_clarke(alpha: float, beta: float) -> tuple[float, float, float]:
    """Amplitude-invariant 2 -> 3 inverse Clarke transform."""
    a =  alpha
    b = -0.5*alpha + (SQRT3/2.0)*beta
    c = -0.5*alpha - (SQRT3/2.0)*beta
    return a, b, c


def park(alpha: float, beta: float, theta_e: float) -> tuple[float, float]:
    """Stationary alpha-beta -> rotating d-q using electrical angle."""
    cos_t = math.cos(theta_e)
    sin_t = math.sin(theta_e)
    d =  alpha*cos_t + beta*sin_t
    q = -alpha*sin_t + beta*cos_t
    return d, q


def inv_park(d: float, q: float, theta_e: float) -> tuple[float, float]:
    """Rotating d-q -> stationary alpha-beta."""
    cos_t = math.cos(theta_e)
    sin_t = math.sin(theta_e)
    alpha = d*cos_t - q*sin_t
    beta  = d*sin_t + q*cos_t
    return alpha, beta


@dataclass
class PIController:
    """Parallel-form PI controller with output saturation and conditional
    anti-windup (clamping). One step = one control tick."""

    Kp: float
    Ki: float
    u_max: float = float("inf")
    u_min: float = float("-inf")

    integ: float = 0.0

    def reset(self) -> None:
        self.integ = 0.0

    def step(self, ref: float, meas: float, Ts: float) -> float:
        err = ref - meas
        u_unsat = self.Kp * err + self.Ki * self.integ
        u = max(self.u_min, min(self.u_max, u_unsat))
        saturated = u != u_unsat
        if not saturated or err * u_unsat < 0.0:
            self.integ += err * Ts
        return u


@dataclass
class FocConfig:
    """Tuning + limits for the dq current loop."""

    Ts: float          # control period [s]
    bw_hz: float       # closed-loop current bandwidth target [Hz]
    Rs: float          # phase resistance [Ohm]
    Ls: float          # synchronous inductance [H]
    psi_m: float       # PM flux linkage [Wb], used for torque <-> iq conversion
    u_max: float       # per-axis voltage limit [V]
    p: int             # pole pairs (electrical angle = p * mech angle)


class CurrentLoopFOC:
    """Full FOC pipeline: i_abc + theta_m_meas in -> v_abc out.

    Tuning uses pole-zero cancellation against the plant 1/(Ls*s + Rs):
        Kp = Ls * w_bw,  Ki = Rs * w_bw
    -> first-order closed loop at w_bw rad/s on each axis.

    Cross-coupling decoupling (omega_e*Ls*iq and omega_e*Ls*id + omega_e*psi_m)
    is intentionally omitted; obvious next addition once the bare loop is solid.
    """

    def __init__(self, cfg: FocConfig) -> None:
        self.cfg = cfg
        w_bw = 2.0 * math.pi * cfg.bw_hz
        Kp = cfg.Ls * w_bw
        Ki = cfg.Rs * w_bw
        self.pi_d = PIController(Kp=Kp, Ki=Ki, u_max=cfg.u_max, u_min=-cfg.u_max)
        self.pi_q = PIController(Kp=Kp, Ki=Ki, u_max=cfg.u_max, u_min=-cfg.u_max)
        # Te = 1.5 * p * psi_m * iq  =>  iq* = T*/(1.5 * p * psi_m).
        self.kt_dq = 1.5 * cfg.p * cfg.psi_m
        # last-step internals exposed for logging
        self.id_ref = 0.0
        self.iq_ref = 0.0
        self.id_m   = 0.0
        self.iq_m   = 0.0
        self.v_d    = 0.0
        self.v_q    = 0.0
        self.theta_e = 0.0

    def iq_ref_from_torque(self, T_ref: float) -> float:
        """Convert a desired electromagnetic torque [N.m] to a q-axis current
        reference [A] for a non-salient PMSM (Ld = Lq). id is kept at zero, so
        all torque comes from iq."""
        return T_ref / self.kt_dq

    def step(self, i_a: float, i_b: float, i_c: float, theta_m_meas: float,
             T_ref: float) -> tuple[float, float, float]:
        """One FOC tick.

        Pipeline:  i_abc + theta_m_meas
                   -> Clarke -> Park (theta_e = p*theta_m_meas) -> (id, iq)
                   -> PI on id (ref = 0) and iq (ref = T_ref / kt_dq) -> (v_d, v_q)
                   -> InvPark -> InvClarke -> v_abc
        """
        id_ref = 0.0                          # surface-PM: zero d-axis current
        iq_ref = self.iq_ref_from_torque(T_ref)

        theta_e = self.cfg.p * theta_m_meas
        alpha, beta = clarke(i_a, i_b, i_c)
        id_m, iq_m = park(alpha, beta, theta_e)
        v_d = self.pi_d.step(id_ref, id_m, self.cfg.Ts)
        v_q = self.pi_q.step(iq_ref, iq_m, self.cfg.Ts)
        v_alpha, v_beta = inv_park(v_d, v_q, theta_e)
        v_a, v_b, v_c = inv_clarke(v_alpha, v_beta)

        (self.id_ref, self.iq_ref, self.id_m, self.iq_m,
         self.v_d, self.v_q, self.theta_e) = (
            id_ref, iq_ref, id_m, iq_m, v_d, v_q, theta_e)
        return v_a, v_b, v_c


if __name__ == "__main__":
    # Round-trip sanity: Clarke -> InvClarke is identity on balanced triples;
    # Park -> InvPark is identity on any (d, q).
    import random
    random.seed(0)
    for _ in range(100):
        a = random.uniform(-10, 10)
        b = random.uniform(-10, 10)
        c = -(a + b)  # balanced
        alpha, beta = clarke(a, b, c)
        a2, b2, c2 = inv_clarke(alpha, beta)
        assert abs(a - a2) < 1e-9, (a, a2)
        assert abs(b - b2) < 1e-9, (b, b2)
        assert abs(c - c2) < 1e-9, (c, c2)

        theta = random.uniform(-10, 10)
        d, q = park(alpha, beta, theta)
        alpha2, beta2 = inv_park(d, q, theta)
        assert abs(alpha - alpha2) < 1e-9, (alpha, alpha2)
        assert abs(beta - beta2) < 1e-9, (beta, beta2)
    print("foc.py: transform round-trips OK")
