"""PI current-loop tuning rules for a slotless PMSM.

Two rules ship here. Both target the per-axis dq plant

    G(s) = 1 / (L_s · s + R_s)   = (1/R_s) / (τ_e · s + 1),    τ_e = L_s / R_s

with the PI compensator in parallel form

    C(s) = K_p + K_i / s.

`auto_pi_gains_from_bw`
-----------------------
Pole-zero cancellation: choose `K_i/K_p = R_s/L_s` so the PI zero lands on the
plant pole. Open-loop collapses to `(K_p/L_s)/s`; closed-loop is exactly
first-order at `ω_bw = K_p/L_s`. Solving with `ω_bw = 2π·bw_hz`:

    K_p = L_s · ω_bw
    K_i = R_s · ω_bw

No overshoot in continuous time. Bandwidth is the only knob.

`modulus_optimum_tuning`
------------------------
Modulus Optimum (Leonhard / Schroeder). Models the unavoidable lag of the
power stage as a small time constant `T_σ = 1.5/f_pwm` — half a PWM period
for ZOH plus one full period for sampling/computation delay. The MO rule for
a first-order plant in series with one small lag gives

    K_p = L_s / (2·T_σ) = L_s · f_pwm / 3
    K_i = R_s / (2·T_σ) = R_s · f_pwm / 3

Result: optimal modulus (|T(jω)| ≈ 1 over the widest band), ~4.3 % overshoot,
faster than pole-zero cancellation when `bw_hz` was chosen conservatively
against the same `f_pwm`. Use this when the PWM frequency is the dominant
constraint and you want to push bandwidth to the physical ceiling.
"""

from __future__ import annotations

import math


def auto_pi_gains_from_bw(R: float, L: float, bw_hz: float) -> tuple[float, float]:
    """Pole-zero cancellation: Kp = L·ω_bw, Ki = R·ω_bw."""
    omega_bw = 2.0 * math.pi * bw_hz
    return L * omega_bw, R * omega_bw


def modulus_optimum_tuning(R: float, L: float, f_pwm: float) -> tuple[float, float]:
    """Modulus Optimum tuning with T_σ = 1.5/f_pwm.

    Returns (Kp, Ki) = (L·f_pwm/3, R·f_pwm/3).
    """
    T_sigma = 1.5 / f_pwm
    Kp = L / (2.0 * T_sigma)
    Ki = R / (2.0 * T_sigma)
    return Kp, Ki
