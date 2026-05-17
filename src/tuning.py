"""PI current-loop tuning rules for a slotless PMSM.

Three rules ship here. All target the per-axis dq plant

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

`skogestad_tuning`
------------------
Skogestad's SIMC rule for a first-order plant with time delay (Haugen,
"PID Control", §7.5, Table 7.1, row 2). Models the PWM/sample delay as a
pure dead-time τ = 1.5/f_pwm (identical to MO's `T_σ`), specifies a
desired closed-loop time constant `T_c`, and gives

    K_p = L_s / (T_c + τ)
    T_i = min(τ_e, k1 · (T_c + τ))
    K_i = K_p / T_i

Defaults are `T_c = τ` (Skogestad, eq. 7.91) and `k1 = 1.44` (Haugen's
suggestion for ~60° phase margin and ~3× faster disturbance rejection
than the textbook `k1 = 4`, footnote 11). With `T_c = τ`, the resulting
`K_p` matches MO exactly; what differs is `T_i` — Skogestad with k1=1.44
gives a substantially smaller integral time than MO's pole-cancellation
choice (T_i = τ_e), trading some setpoint overshoot for sharper load-step
rejection.
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


def skogestad_tuning(R: float, L: float, f_pwm: float, k1: float = 1.44, Tc: float | None = None) -> tuple[float, float]:
    """Skogestad SIMC for a first-order plant with dead-time τ = 1.5/f_pwm.

    Kp = L / (Tc + τ);  Ti = min(L/R, k1·(Tc + τ));  Ki = Kp / Ti.
    Tc=None falls back to the canonical Tc = τ.
    """
    tau_delay = 1.5 / f_pwm
    if Tc is None:
        Tc = tau_delay
    tau_e = L / R
    sum_T = Tc + tau_delay
    Kp = L / sum_T
    Ti = min(tau_e, k1 * sum_T)
    Ki = Kp / Ti
    return Kp, Ki
