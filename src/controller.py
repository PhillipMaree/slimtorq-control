"""FOC current-loop controller for a slotless surface PMSM.

Signal flow per tick (one `step()` call):

    i_a, i_b, i_c           ──► Clarke ──► i_alpha, i_beta
    theta_e_meas            ──┘
    (i_alpha, i_beta, theta_e_meas) ──► Park ──► i_d, i_q
    (i_d_ref - i_d), dt     ──► PI(d) ──► v_d (raw)
    (i_q_ref - i_q), dt     ──► PI(q) ──► v_q (raw)
    (v_d, v_q)              ──► vector saturation to V_max = Vdc/2 ──► v_d_ref, v_q_ref
    (v_d_ref, v_q_ref, theta_e_meas) ──► inverse Park ──► v_alpha_ref, v_beta_ref
    inverse Clarke          ──► v_a_ref, v_b_ref, v_c_ref

The FOC outputs *continuous* abc voltage references. Conversion to duty cycles
and switch states happens in the PWMModulator + Inverter blocks downstream.

Decoupling and BEMF feedforward
===============================

The dq stator equations include cross-coupling and BEMF terms:

    v_d = R_s · i_d + L_s · di_d/dt − ω_e · L_s · i_q
    v_q = R_s · i_q + L_s · di_q/dt + ω_e · L_s · i_d + ω_e · ψ_m

The FOC injects the two cross-coupling and BEMF terms as feedforward so the
per-axis plant seen by each PI reduces to the first-order R/L circuit:

    ff_d = −ω_e · L_s · i_q_meas
    ff_q =  ω_e · L_s · i_d_meas + ω_e · ψ_m
    v_d_raw = PI_d + ff_d
    v_q_raw = PI_q + ff_q

Vector saturation acts on the combined (PI + FF) command, which is the
voltage actually requested from the inverter — the right physical bound.

Tuning rationale
================

Per-axis dq plant after decoupling/BEMF feedforward (each axis collapses to
a pure R/L circuit):

    v = R_s · i + L_s · di/dt   =>   G(s) = i(s)/v(s) = 1 / (L_s · s + R_s)

Equivalently G(s) = (1/R_s) / (τ_e·s + 1) with τ_e = L_s / R_s.

PI in parallel form:

    C(s) = K_p + K_i / s = K_p · (s + K_i/K_p) / s

This adds an integrator and one zero at s = -K_i/K_p.

Two tuning rules ship in `tuning.py` and either can drive K_p / K_i:

1. Pole-zero cancellation (auto_pi_gains_from_bw). Pick K_i/K_p = R_s/L_s so
   the PI zero cancels the plant pole at -R_s/L_s. The open loop collapses
   to a pure integrator L(s) = (K_p/L_s)/s; the closed loop is exactly
   first-order, T(s) = 1 / (1 + s·L_s/K_p), with bandwidth ω_bw = K_p/L_s.
   Solving:   K_p = L_s · ω_bw,   K_i = R_s · ω_bw   (ω_bw = 2π · bw_hz).
   No overshoot. Bandwidth is the only knob.

2. Modulus Optimum (modulus_optimum_tuning). Models the unavoidable lag of
   the power stage as a small time constant T_σ = 1.5 / f_pwm — half a PWM
   period for ZOH plus one period for sampling/compute delay. The MO rule
   for a first-order plant in series with one small lag gives:
       K_p = L_s / (2·T_σ) = L_s · f_pwm / 3
       K_i = R_s / (2·T_σ) = R_s · f_pwm / 3
   Result: optimal modulus, ~4.3 % overshoot, pushes bandwidth to roughly
   f_pwm / (3·2π) ≈ 1.06 kHz at 20 kHz PWM — the physical ceiling set by
   the modulator.

Discrete-time validity. Forward-Euler PI is stable when Ts ≪ τ_e. The
Simulator enforces Ts ≤ τ_e/3 as a conservative bound; for bandwidths near
1/Ts the continuous analysis breaks down — keep at least ~5× margin between
bw_hz and 1/Ts.

Vector saturation. With centered duty conversion d = 0.5 + v_ref/Vdc, each
phase saturates when |v_phase| > Vdc/2 — the sinusoidal-PWM linear range.
Letting the duty clamp injects low-order harmonic content into v_abc, so
instead we clip the dq voltage vector to magnitude V_max = Vdc/2 *before*
inverse Park. With amplitude-invariant Clarke the peak phase voltage equals
|v_dq_vec|, so a circular limit in dq is the right physical bound. (SVPWM
would extend this to Vdc/√3 by injecting a zero-sequence offset — not
implemented yet.) When the vector limit fires both PI integrators stop
accumulating to prevent windup.

The catalog stores line-to-line R and L; the loader in model.py applies
R_s = R_LL/2 and L_s = L_LL/2 so the values used here are per-phase
(line-to-neutral) — the correct sign-convention for the dq voltage equations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from model import FocConfig
from transform import abc_to_dq, dq_to_abc
from tuning import auto_pi_gains_from_bw


@dataclass
class PIController:
    """Parallel-form PI with conditional anti-windup (clamping).

    Saturation is *external*: the caller computes the saturated output,
    then either calls `integrate(err, dt)` to advance the integrator, or
    `freeze()` to leave it alone (anti-windup). This split is needed by
    FOCController's vector saturation, where both axes must freeze together
    when the dq voltage vector exceeds V_max.
    """

    Kp: float
    Ki: float
    integ: float = 0.0

    def reset(self) -> None:
        self.integ = 0.0

    def unsaturated(self, ref: float, meas: float) -> tuple[float, float]:
        """Return (u_raw, err). Caller decides whether to integrate or freeze."""
        err = ref - meas
        u_raw = self.Kp * err + self.Ki * self.integ
        return u_raw, err

    def integrate(self, err: float, dt: float) -> None:
        """Advance the integrator by err·dt."""
        self.integ += err * dt


class FOCController:
    """Full FOC current-loop pipeline. One `step()` call = one control tick."""

    def __init__(self, cfg: FocConfig) -> None:
        self.cfg = cfg
        if cfg.Kp is not None and cfg.Ki is not None:
            self.Kp = cfg.Kp
            self.Ki = cfg.Ki
        else:
            # Auto-tune: pole-zero cancellation. See module docstring.
            self.Kp, self.Ki = auto_pi_gains_from_bw(cfg.R_s, cfg.L_s, cfg.bw_hz)
        self.pi_d = PIController(Kp=self.Kp, Ki=self.Ki)
        self.pi_q = PIController(Kp=self.Kp, Ki=self.Ki)
        # Sinusoidal-PWM linear range: |v_dq_vec| ≤ Vdc/2.
        self.V_max = cfg.Vdc / 2.0
        # Plant params needed for dq decoupling and BEMF feedforward.
        self.L_s = cfg.L_s
        self.psi_m = cfg.psi_m
        # Last-step internals exposed for logging.
        self.i_d_meas: float = 0.0
        self.i_q_meas: float = 0.0
        self.v_d: float = 0.0
        self.v_q: float = 0.0
        self.ff_d: float = 0.0
        self.ff_q: float = 0.0
        self.sat_d: bool = False
        self.sat_q: bool = False

    @property
    def f_pwm(self) -> float:
        # Exposed so the Simulator can derive dt_ctrl = 1/f_pwm (one FOC tick
        # per PWM cycle — standard digital-FOC convention).
        return self.cfg.f_pwm

    def step(self, i_a: float, i_b: float, i_c: float, theta_e_meas: float, omega_e_meas: float, i_d_ref: float, i_q_ref: float, dt: float) -> tuple[float, float, float]:
        """One FOC tick.

        Inputs:
            i_a, i_b, i_c     measured phase currents [A]
            theta_e_meas      measured electrical angle [rad]
            omega_e_meas      measured electrical speed [rad/s] (= p · ω_m_meas)
            i_d_ref, i_q_ref  current references [A]
            dt                control tick period [s]

        Returns continuous (v_a_ref, v_b_ref, v_c_ref) for the modulator.
        """
        # Forward: abc -> dq currents.
        i_d_meas, i_q_meas = abc_to_dq(i_a, i_b, i_c, theta_e_meas)

        # PI on each axis (unsaturated).
        v_d_pi, err_d = self.pi_d.unsaturated(i_d_ref, i_d_meas)
        v_q_pi, err_q = self.pi_q.unsaturated(i_q_ref, i_q_meas)

        # Decoupling + BEMF feedforward (matches the dq plant equations).
        ff_d = -omega_e_meas * self.L_s * i_q_meas
        ff_q = omega_e_meas * self.L_s * i_d_meas + omega_e_meas * self.psi_m

        v_d_raw = v_d_pi + ff_d
        v_q_raw = v_q_pi + ff_q

        # Vector saturation in the dq frame.
        mag = math.sqrt(v_d_raw * v_d_raw + v_q_raw * v_q_raw)
        if mag > self.V_max:
            scale = self.V_max / mag
            v_d = v_d_raw * scale
            v_q = v_q_raw * scale
            sat = True
        else:
            v_d = v_d_raw
            v_q = v_q_raw
            sat = False

        # Anti-windup: integrate only when not saturated, or when the error
        # would pull the vector back into the linear range.
        if not sat:
            self.pi_d.integrate(err_d, dt)
            self.pi_q.integrate(err_q, dt)
        else:
            # Project (err_d, err_q) onto the inward normal of the saturation
            # boundary (-v_d_raw, -v_q_raw)/mag. If the projection is positive,
            # the error is trying to pull |v| back down, so allow integration.
            proj = -(err_d * v_d_raw + err_q * v_q_raw) / mag
            if proj > 0.0:
                self.pi_d.integrate(err_d, dt)
                self.pi_q.integrate(err_q, dt)

        # Inverse: dq -> abc voltage references.
        v_a_ref, v_b_ref, v_c_ref = dq_to_abc(v_d, v_q, theta_e_meas)

        # Stash for logging.
        self.i_d_meas, self.i_q_meas = i_d_meas, i_q_meas
        self.v_d, self.v_q = v_d, v_q
        self.ff_d, self.ff_q = ff_d, ff_q
        self.sat_d = self.sat_q = sat
        return v_a_ref, v_b_ref, v_c_ref
