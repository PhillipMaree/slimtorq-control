"""Synchronous-sampling phase equivalence under sine PWM.

Production motor drives sample the phase currents synchronously with the PWM
carrier so the controller sees the cycle-average current instead of an
arbitrary instant on the triangular ripple. For a centered triangular carrier
with a *linear* in-period current ramp there are two equivalent
cycle-average sampling instants: the carrier valley (start of the period) and
the carrier peak (mid-period). Real drives pick either, or sometimes both
(double sampling).

These tests run the same step into the same drive under both sampling phases
and pin the equivalence:

  - the steady-state mean ``i_q_meas`` is identical (the loop converges to
    the same operating point regardless of phase);
  - the ripple seen by the controller (``i_q_meas`` std and peak-to-peak)
    differs by less than a small tolerance.

Where the equivalence *breaks* — when ``R · i_q`` becomes comparable to
``Vdc/2`` so the in-period ramp curves significantly, or when dead-time
breaks the rising/falling-edge symmetry — single-instant sampling stops
being a cycle-average estimator. The remaining ripple after either phase
choice is dominated by Park-transform rotation during the PWM period mixing
abc-frame ripple into the dq frame, *not* by sampling-instant placement.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from src.drivetrain import Drivetrain
from src.model import SimParams
from src.simulator import CATALOG, Simulator, default_tl_ref, resolve_t_step_frac


def _run_with_phase(variant: str, phase: str) -> pl.DataFrame:
    motor = CATALOG[variant]
    # Pin both the high-load step AND the undersized bus that exercise the
    # in-period current-ramp curvature this suite is measuring. With the
    # product default ``vdc = 1.5 * rated_voltage`` the 8D winding's
    # ``R*i_q`` drop sits comfortably inside the linear PWM range, the ramp
    # is essentially linear, and the peak-vs-valley samples agree — so
    # double sampling has nothing to cancel. Opting back into
    # ``vdc = rated_voltage`` reproduces the regime where the textbook
    # production gain shows up.
    p = SimParams(variant_name=variant, inverter_mode="switching", t_end=0.05, t_step=0.005, t_step_frac=2.0 / 3.0, vdc=72.0)
    TL = default_tl_ref(motor, t_end=p.t_end, t_step=p.t_step, frac=resolve_t_step_frac(p, motor))
    with Drivetrain.build(p, motor) as drive:
        sim = Simulator(drive)
        df = sim.run(TL, inverter_mode="switching", sampling_phase=phase)  # type: ignore[arg-type]
    return df


def _steady_state(df: pl.DataFrame) -> pl.DataFrame:
    """Last 25% of the trace — well past the load step at t_step = 5 ms."""
    n = df.height
    return df.slice(int(0.75 * n), n - int(0.75 * n))


def _ripple_stats(df: pl.DataFrame) -> tuple[float, float, float]:
    """(mean, std, peak-to-peak) of i_q_meas in the steady-state tail."""
    tail = _steady_state(df)
    iq = tail["i_q_meas"].to_numpy()
    return float(np.mean(iq)), float(np.std(iq)), float(iq.max() - iq.min())


def _assert_phase_equivalent(variant: str, ripple_tolerance: float) -> None:
    df_v = _run_with_phase(variant, "valley")
    df_m = _run_with_phase(variant, "midpoint")

    mean_v, std_v, pp_v = _ripple_stats(df_v)
    mean_m, std_m, pp_m = _ripple_stats(df_m)

    # Same operating point — the loop converges to the same i_q regardless of
    # which carrier instant we sample at.
    assert abs(mean_m - mean_v) / abs(mean_v) < 0.02, f"{variant}: mean i_q differs by more than 2% (valley={mean_v:.3f}, midpoint={mean_m:.3f})"

    # Ripple magnitude equivalent within tolerance. Tolerance is generous —
    # the point is *not* that one is meaningfully better; the point is that
    # phase choice is not the dominant factor.
    rel_std = abs(std_m - std_v) / max(std_v, 1e-6)
    rel_pp = abs(pp_m - pp_v) / max(pp_v, 1e-6)
    assert rel_std < ripple_tolerance, f"{variant}: i_q std diverges across sampling phase (valley={std_v:.3f}, midpoint={std_m:.3f}, rel={rel_std:.2%})"
    assert rel_pp < ripple_tolerance, f"{variant}: i_q pp diverges across sampling phase (valley={pp_v:.3f}, midpoint={pp_m:.3f}, rel={rel_pp:.2%})"


def test_low_R_winding_sampling_phase_equivalent() -> None:
    """2D winding (R_s = 0.12 Ω, L_s = 2.6 µH). IR drop at rated current is
    13 V — small relative to V_max = 36 V — so the in-period ramp is close to
    linear and both sampling phases land near the cycle-average."""
    _assert_phase_equivalent("STM-105-17-L-2D", ripple_tolerance=0.20)


def test_high_R_winding_sampling_phase_equivalent() -> None:
    """8D winding (R_s = 1.94 Ω, L_s = 41.6 µH). IR drop is comparable to
    V_max here, so the ramp is more curved and we expect slightly more
    divergence between phases — but still within tolerance."""
    _assert_phase_equivalent("STM-105-17-L-8D", ripple_tolerance=0.20)


def test_double_sampling_reduces_ripple_low_R() -> None:
    """2D winding: double sampling averages the peak and valley snapshots,
    cancelling the linear in-period ramp. Expect a measurable peak-to-peak
    drop in i_q ripple compared to single-sample valley."""
    df_v = _run_with_phase("STM-105-17-L-2D", "valley")
    df_d = _run_with_phase("STM-105-17-L-2D", "double")
    _, _, pp_v = _ripple_stats(df_v)
    _, _, pp_d = _ripple_stats(df_d)
    drop = (pp_v - pp_d) / pp_v
    # Measured improvement is ~26% on i_q_pp; 10% is a conservative floor.
    assert drop > 0.10, f"2D double sampling pp drop = {drop:.1%}; expected > 10% (valley_pp={pp_v:.3f}, double_pp={pp_d:.3f})"


def test_double_sampling_reduces_ripple_high_R() -> None:
    """8D winding: same in principle but the larger R·i causes a curved
    in-period ramp, so the absolute ripple level is lower and the *relative*
    improvement from double sampling is larger. Expect a substantial std
    reduction."""
    df_v = _run_with_phase("STM-105-17-L-8D", "valley")
    df_d = _run_with_phase("STM-105-17-L-8D", "double")
    _, std_v, _ = _ripple_stats(df_v)
    _, std_d, _ = _ripple_stats(df_d)
    drop = (std_v - std_d) / std_v
    # Measured improvement is ~33% on i_q std; 20% is a conservative floor.
    assert drop > 0.20, f"8D double sampling std drop = {drop:.1%}; expected > 20% (valley_std={std_v:.3f}, double_std={std_d:.3f})"


def test_double_sampling_preserves_operating_point() -> None:
    """Double sampling changes *what the controller sees*, not the physical
    drive. The closed loop still converges to the same i_q operating point
    as single-sample modes."""
    for variant in ("STM-105-17-L-2D", "STM-105-17-L-8D"):
        df_v = _run_with_phase(variant, "valley")
        df_d = _run_with_phase(variant, "double")
        mean_v, _, _ = _ripple_stats(df_v)
        mean_d, _, _ = _ripple_stats(df_d)
        assert abs(mean_d - mean_v) / abs(mean_v) < 0.02, f"{variant}: double sampling shifted mean i_q (valley={mean_v:.3f}, double={mean_d:.3f})"


def test_midpoint_first_tick_lands_at_carrier_peak() -> None:
    """Implementation sanity check: midpoint sampling shifts the first FOC
    tick from t = T_pwm (valley) to t = T_pwm/2 (peak). Detected by the
    first non-zero v_q_ref under a delayed-step trajectory."""
    motor = CATALOG["STM-105-17-L-8D"]
    p = SimParams(variant_name="STM-105-17-L-8D", t_end=0.0005, t_step=0.0001)
    TL = default_tl_ref(motor, t_end=p.t_end, t_step=p.t_step, frac=resolve_t_step_frac(p, motor))

    first_tick_us = {}
    for phase in ("valley", "midpoint"):
        with Drivetrain.build(p, motor) as drive:
            sim = Simulator(drive)
            df = sim.run(TL, sampling_phase=phase)  # type: ignore[arg-type]
        vq = df["v_q_ref"].to_numpy()
        t = df["t"].to_numpy()
        first = int(np.argmax(vq != 0.0))  # index of first non-zero
        first_tick_us[phase] = t[first] * 1e6

    # First non-zero v_q happens at the first FOC tick *after* TL_ref steps
    # to non-zero (t_step = 100 µs). Under valley sampling the next tick is
    # at 100 µs; under midpoint sampling it's at 125 µs.
    assert first_tick_us["valley"] == 100.0, f"valley first non-zero v_q at {first_tick_us['valley']} µs, expected 100.0"
    assert first_tick_us["midpoint"] == 125.0, f"midpoint first non-zero v_q at {first_tick_us['midpoint']} µs, expected 125.0"
