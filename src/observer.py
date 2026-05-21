"""Single-axis LCL state observer (Luenberger form).

Estimates the three LCL filter states from a single measurement:

    x_hat = [i1_hat, vc_hat, im_hat]^T

with:

    i1_hat  inverter-side current  [A]
    vc_hat  capacitor voltage      [V]
    im_hat  motor-side current     [A]

The estimated capacitor current

    ic_hat = i1_hat - im_hat

is the load-bearing signal for future active LCL damping:

    v_damp = -Kd * ic_hat

This module is intentionally standalone — it implements only the observer.
FOC, Park/Clarke, SVPWM, inverter switching, and motor dynamics live
elsewhere. Two instances are used in dq-frame FOC, one per axis:

    obs_d = LCLObserver(params, measurement_type="motor_current")
    obs_q = LCLObserver(params, measurement_type="motor_current")
    d_est = obs_d.predict_update(v_inv=vd_inv_est, y_meas=id_meas, e=0.0)
    q_est = obs_q.predict_update(v_inv=vq_inv_est, y_meas=iq_meas, e=omega_e * lambda_pm)
    ic_d_hat = d_est["ic_hat"]
    ic_q_hat = q_est["ic_hat"]

Continuous-time state space (single axis):

    A = [[-R1/L1,   -1/L1,            0],
         [  1/Cf,       0,        -1/Cf],
         [     0, 1/Lload, -Rload/Lload]]

    B = [1/L1, 0, 0]^T
    E = [0, 0, -1/Lload]^T

Observer:

    x_hat_dot = A x_hat + B v_inv + E e + L (y_meas - C x_hat)
    x_hat[k+1] = x_hat[k] + Ts * x_hat_dot[k]      (forward Euler)

TODO: replace forward Euler with exact ZOH discretisation if the inner step
makes Euler marginal at high resonance frequencies. As a rule of thumb the
forward-Euler step on the (undamped) LCL plant is marginally stable when
``Ts · ω_res ≈ 1``; keep ``Ts · ω_res ≲ 0.05`` for headroom. With the
simulator's default ``Ts = T_pwm / 20`` this means ``ω_res ≲ f_pwm`` (in
radians, with a healthy safety factor) — fine at the project default
``f_pwm = 50 kHz`` and ``f_c_target = 5 kHz``.
"""

from __future__ import annotations

import math
from typing import Literal

import numpy as np

from src.model import LCLParams

MeasurementType = Literal["motor_current", "inverter_current", "capacitor_voltage"]

_C_BY_MEASUREMENT: dict[str, np.ndarray] = {
    "motor_current": np.array([0.0, 0.0, 1.0]),
    "inverter_current": np.array([1.0, 0.0, 0.0]),
    "capacitor_voltage": np.array([0.0, 1.0, 0.0]),
}

# Conservative default observer gains. Starting points only — not tuned.
# Picked so the gain pushes the corresponding measured state toward the
# innovation. Real designs should pole-place L against (A - L C).
_DEFAULT_GAIN: dict[str, np.ndarray] = {
    "motor_current": np.array([0.0, 0.0, 500.0]),
    "inverter_current": np.array([500.0, 0.0, 0.0]),
    "capacitor_voltage": np.array([0.0, 500.0, 0.0]),
}


def _flatten_3(name: str, arr: np.ndarray) -> np.ndarray:
    a = np.asarray(arr, dtype=float)
    if a.shape == (3,):
        out = a
    elif a.shape == (3, 1):
        out = a.reshape(3)
    else:
        msg = f"{name} must have shape (3,) or (3, 1); got {a.shape}"
        raise ValueError(msg)
    if not np.all(np.isfinite(out)):
        msg = f"{name} contains non-finite values: {out!r}"
        raise ValueError(msg)
    return out


class LCLObserver:
    """Luenberger observer for the single-axis LCL plant.

    Parameters
    ----------
    params : LCLParams
        Plant + sample-period.
    measurement_type : {"motor_current", "inverter_current", "capacitor_voltage"}
        Which scalar is measured each step.
    observer_gain : np.ndarray, optional
        Shape (3,) or (3, 1). Defaults to a conservative starting gain that
        only acts on the measured state. Tune for production use.
    initial_state : np.ndarray, optional
        Shape (3,) or (3, 1). Defaults to zeros.
    max_abs_state : float, optional
        Simulation safeguard. If set, the state is clipped element-wise to
        [-max_abs_state, max_abs_state] after every update. Not part of the
        physical observer.
    """

    def __init__(
        self,
        params: LCLParams,
        measurement_type: MeasurementType = "motor_current",
        observer_gain: np.ndarray | None = None,
        initial_state: np.ndarray | None = None,
        max_abs_state: float | None = None,
    ) -> None:
        if measurement_type not in _C_BY_MEASUREMENT:
            msg = f"measurement_type must be one of {sorted(_C_BY_MEASUREMENT)}; got {measurement_type!r}"
            raise ValueError(msg)
        if max_abs_state is not None and not (math.isfinite(max_abs_state) and max_abs_state > 0.0):
            msg = f"max_abs_state must be positive and finite (got {max_abs_state!r})"
            raise ValueError(msg)

        self.params = params
        self.measurement_type: MeasurementType = measurement_type
        self.Ts = float(params.Ts)
        self.max_abs_state = None if max_abs_state is None else float(max_abs_state)

        # Continuous-time plant matrices.
        self.A = np.array(
            [
                [-params.R1 / params.L1, -1.0 / params.L1, 0.0],
                [1.0 / params.Cf, 0.0, -1.0 / params.Cf],
                [0.0, 1.0 / params.Lload, -params.Rload / params.Lload],
            ]
        )
        self.B = np.array([1.0 / params.L1, 0.0, 0.0])
        self.E = np.array([0.0, 0.0, -1.0 / params.Lload])
        self.C = _C_BY_MEASUREMENT[measurement_type].copy()

        if observer_gain is None:
            self.L = _DEFAULT_GAIN[measurement_type].copy()
        else:
            self.L = _flatten_3("observer_gain", observer_gain)

        if initial_state is None:
            self.x_hat = np.zeros(3)
        else:
            self.x_hat = _flatten_3("initial_state", initial_state).copy()

    def reset(self, initial_state: np.ndarray | None = None) -> None:
        if initial_state is None:
            self.x_hat = np.zeros(3)
        else:
            self.x_hat = _flatten_3("initial_state", initial_state).copy()

    def predict_update(self, v_inv: float, y_meas: float, e: float = 0.0) -> dict[str, float]:
        """One discrete observer step (forward Euler).

        Inputs are scalars in SI units: v_inv [V], y_meas [A or V depending on
        measurement_type], e [V] motor-side disturbance/back-EMF.
        """
        v_inv = float(v_inv)
        y_meas = float(y_meas)
        e = float(e)
        if not (math.isfinite(v_inv) and math.isfinite(y_meas) and math.isfinite(e)):
            msg = f"v_inv, y_meas, e must be finite (got {v_inv!r}, {y_meas!r}, {e!r})"
            raise ValueError(msg)

        y_hat = float(self.C @ self.x_hat)
        innovation = y_meas - y_hat
        x_dot = self.A @ self.x_hat + self.B * v_inv + self.E * e + self.L * innovation
        self.x_hat = self.x_hat + self.Ts * x_dot

        if self.max_abs_state is not None:
            np.clip(self.x_hat, -self.max_abs_state, self.max_abs_state, out=self.x_hat)

        i1_hat = float(self.x_hat[0])
        vc_hat = float(self.x_hat[1])
        im_hat = float(self.x_hat[2])
        return {
            "i1_hat": i1_hat,
            "vc_hat": vc_hat,
            "im_hat": im_hat,
            "ic_hat": i1_hat - im_hat,
            "innovation": float(innovation),
            "y_hat": y_hat,
        }

    def get_state(self) -> np.ndarray:
        return self.x_hat.copy()

    def get_capacitor_current(self) -> float:
        return float(self.x_hat[0] - self.x_hat[2])

    def resonance_frequency_hz(self) -> float:
        return self.params.resonance_frequency_hz()

    def matrices(self) -> dict[str, np.ndarray]:
        """Copies of A, B, E, C, L for debugging / pole-placement design."""
        return {
            "A": self.A.copy(),
            "B": self.B.copy(),
            "E": self.E.copy(),
            "C": self.C.copy(),
            "L": self.L.copy(),
        }


if __name__ == "__main__":
    # Smoke test: plausible LCL + motor for a slotless PMSM.
    L_s = 7.7e-6
    R_s = 0.2285
    L_f = L_s / 4.0
    C_f = 1.0 / ((2.0 * math.pi * 5000.0) ** 2 * L_f)
    params = LCLParams(L1=L_f, R1=0.0, Cf=C_f, Lload=L_s, Rload=R_s, Ts=1e-6)
    print(f"Resonance: f_res = {params.resonance_frequency_hz():.1f} Hz")

    obs = LCLObserver(params, measurement_type="motor_current")
    v_inv = 24.0  # constant inverter voltage
    y_meas = 0.0  # pretend motor current measurement is zero (worst innovation)
    for k in range(20):
        est = obs.predict_update(v_inv=v_inv, y_meas=y_meas)
        if k % 4 == 0 or k == 19:
            print(f"k={k:2d}  i1={est['i1_hat']:+9.4f}  vc={est['vc_hat']:+9.4f}  im={est['im_hat']:+9.4f}  ic={est['ic_hat']:+9.4f}  innov={est['innovation']:+9.4f}")
