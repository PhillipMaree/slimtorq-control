"""Flux encoder model: true mechanical rotor angle -> noisy/quantized measurement.

Replaces the previous Modelica `FluxEncoder` block. The motor model now exposes
the true mechanical angle; this Python class emulates a Zettlex-style inductive
encoder with:
  - fixed mounting offset
  - three-harmonic cyclic angle error: theta_err = sum_i A_i * sin(k_i*theta + phi_i)
  - N-bit absolute quantization
  - sample-and-hold at Ts_enc (independent of the inner control tick)

Measured speed is the wrapped finite difference of consecutive samples / Ts_enc.
"""

from __future__ import annotations

import math

from src.model import EncoderConfig

TWO_PI = 2.0 * math.pi


class FluxEncoder:
    """Inductive flux encoder. Call `step(theta_m_true, t)` each control tick.

    Internally the encoder re-samples only when `t` crosses the next encoder
    boundary `_next_sample_t`; between boundaries the most recent measured
    angle and speed are held (zero-order hold).
    """

    def __init__(self, cfg: EncoderConfig) -> None:
        self.cfg = cfg
        self._dtheta = TWO_PI / (1 << cfg.n_bits)
        self._theta_sampled: float = 0.0
        self._theta_prev: float = 0.0
        self._omega_sampled: float = 0.0
        self._next_sample_t: float = 0.0

    def _measure(self, theta_m_true: float) -> float:
        c = self.cfg
        cyclic = c.A1 * math.sin(c.k1 * theta_m_true + c.phi1) + c.A2 * math.sin(c.k2 * theta_m_true + c.phi2) + c.A3 * math.sin(c.k3 * theta_m_true + c.phi3)
        raw = theta_m_true + c.theta_offset + cyclic
        # Symmetric (mid-tread) quantization, then wrap to [0, 2*pi).
        q = self._dtheta * math.floor(raw / self._dtheta + 0.5)
        return q % TWO_PI

    def step(self, theta_m_true: float, t: float) -> tuple[float, float]:
        """Return (theta_m_meas, omega_m_meas) for time `t`.

        At each encoder sample boundary, re-measure and recompute omega from
        the wrapped angle difference / Ts_enc. Otherwise hold previous values.
        """
        if t >= self._next_sample_t:
            theta_now = self._measure(theta_m_true)
            # Wrap the angle delta into [-pi, pi) so we don't see a 2*pi jump
            # when the encoder rolls over once per mechanical revolution.
            dtheta = ((theta_now - self._theta_sampled + math.pi) % TWO_PI) - math.pi
            self._omega_sampled = dtheta / self.cfg.Ts_enc
            self._theta_prev = self._theta_sampled
            self._theta_sampled = theta_now
            self._next_sample_t += self.cfg.Ts_enc
            # Guard against drift if the caller skips multiple encoder ticks.
            while self._next_sample_t <= t:
                self._next_sample_t += self.cfg.Ts_enc
        return self._theta_sampled, self._omega_sampled


class EncoderMeasurement:
    """Composite measurement block: FluxEncoder + theta_e_meas + i_abc pass-through.

    The Simulator calls this once per inner tick. The internal FluxEncoder
    re-samples only at its own Ts_enc grid; between samples the held values
    are returned unchanged. theta_e_meas = (p · theta_m_meas) mod 2π.
    """

    def __init__(self, encoder: FluxEncoder, p: int) -> None:
        self.encoder = encoder
        self.p = p

    def step(self, theta_m_true: float, omega_m_true: float, i_abc: tuple[float, float, float], t: float) -> tuple[float, float, float, float, float, float]:
        """Returns (theta_m_meas, omega_m_meas, theta_e_meas, i_a_meas, i_b_meas, i_c_meas).

        i_abc currently passes through verbatim; this is the natural insertion
        point for current-sensor bandwidth / noise / offset effects later.
        """
        theta_m_meas, omega_m_meas = self.encoder.step(theta_m_true, t)
        theta_e_meas = (self.p * theta_m_meas) % TWO_PI
        i_a, i_b, i_c = i_abc
        return theta_m_meas, omega_m_meas, theta_e_meas, i_a, i_b, i_c


if __name__ == "__main__":
    # Sanity: a linear-ramp theta with no harmonics + zero offset should give
    # quantized theta_meas at the LSB resolution, and omega_meas ~ true omega.
    import numpy as np

    cfg = EncoderConfig(n_bits=22, A1=0.0, A2=0.0, A3=0.0, Ts_enc=2e-4)
    enc = FluxEncoder(cfg)
    omega_true = 10.0  # rad/s
    Ts = 1e-5
    measured_omegas = []
    last_meas = None
    for k in range(2000):
        t = k * Ts
        theta_true = omega_true * t
        meas, om = enc.step(theta_true, t)
        if last_meas != meas:
            measured_omegas.append(om)
            last_meas = meas

    lsb = 2 * math.pi / (1 << cfg.n_bits)
    avg = np.mean(measured_omegas[5:]) if len(measured_omegas) > 5 else float("nan")
    print(f"encoder.py: LSB = 2*pi/2^{cfg.n_bits} = {lsb:.3e} rad ({math.degrees(lsb) * 3600:.3f} arcsec)")
    print(f"encoder.py: omega_true = {omega_true} rad/s, mean measured = {avg:.3f} rad/s")
    assert abs(avg - omega_true) < 0.5, f"omega tracking off: {avg} vs {omega_true}"
    print("encoder.py: linear-ramp omega tracking OK")
