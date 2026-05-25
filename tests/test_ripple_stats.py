"""Windowed peak-to-peak isolates PWM ripple from the rotating fundamental.

The motor's abc-frame current is ``i_a(t) = I_mag · cos(ω_e·t + φ) +
ripple(t)``. A global ``max − min`` over the steady-state tail captures
the full ``2·I_mag`` fundamental swing, not the PWM-band ripple. The
windowed form takes ``pp`` over short sliding windows (a few PWM periods
each, much shorter than the electrical period) so the fundamental can't
swing within a window and what's left is the PWM-band content.
"""

from __future__ import annotations

import numpy as np

from src.model import RippleStats


def _synthetic_signal() -> tuple[np.ndarray, float, float, float, float]:
    """Returns (signal, dt, f_fund, f_pwm, fund_amplitude, ripple_amplitude)
    representing a steady-state phase current at ω_e = 2π·100 rad/s plus
    PWM-band ripple at 5 kHz."""
    dt = 5e-6  # 200 kHz inner step
    T = 0.05
    t = np.arange(0.0, T, dt)
    f_fund = 100.0
    f_pwm = 5000.0
    fund_amplitude = 5.0
    ripple_amplitude = 0.5  # peak ⇒ peak-to-peak = 1.0
    signal = fund_amplitude * np.cos(2.0 * np.pi * f_fund * t) + ripple_amplitude * np.cos(2.0 * np.pi * f_pwm * t)
    return signal, dt, f_fund, f_pwm


def test_unwindowed_pp_captures_full_fundamental_swing() -> None:
    """Default behaviour is unchanged: pp over the whole signal includes the
    fundamental, which dominates."""
    signal, _dt, _f_fund, _f_pwm = _synthetic_signal()
    r = RippleStats.from_signal(signal, rated=10.0, cmd=None)
    # Fundamental amplitude 5 ⇒ pp ≈ 10 (+ ~1 ripple); should be > 9.
    assert r.delta_pp > 9.0, f"unwindowed pp = {r.delta_pp}; expected ≥ 9 (captures fundamental swing)"


def test_windowed_pp_isolates_pwm_ripple() -> None:
    """With a window ~2 PWM periods long, the fundamental can't swing across
    the window, so pp reflects ripple amplitude (~1.0 pp), not the
    fundamental (~10 pp)."""
    signal, dt, _f_fund, f_pwm = _synthetic_signal()
    window = max(4, int(2.0 / f_pwm / dt))  # ~2 PWM periods of samples
    r = RippleStats.from_signal(signal, rated=10.0, cmd=None, window_samples=window)
    # Ripple peak-to-peak ≈ 1.0 (with small contribution from the
    # fundamental's slope over the short window). Allow generous margin.
    assert r.delta_pp < 2.0, f"windowed pp = {r.delta_pp}; expected ~1, well below 2"
    assert r.delta_pp > 0.5, f"windowed pp = {r.delta_pp}; expected near the ripple amplitude (~1)"
