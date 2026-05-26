"""Step-response voltage-saturation diagnostics for STM-105-17-L variants.

The textbook current-loop analysis says that for two windings with the same
``tau_e = L_s / R_s`` and a PI tuned by pole-zero cancellation, the closed-loop
step response is identical *under ideal PWM* — both reach
``i(t) = i_ref (1 - exp(-omega_bw t))`` with the same bandwidth.

That equivalence breaks the moment the controller leaves its linear range. For
the SlimTorq 105-17 Lite family at the cataloged rated voltage (72 V), the 8D
winding's IR drop alone for the catalog-default torque step already exceeds the
sinusoidal-PWM envelope ``V_max = Vdc / 2``. The 2D winding has plenty of
headroom.

These tests pin that asymmetry by running an ideal-PWM step into each variant
and inspecting the saturation diagnostics the simulator already logs
(``sat_q``, ``v_q_ref``). If the rated voltage or default torque step changes
such that one variant moves across the envelope, these tests will tell us.
"""

from __future__ import annotations

import polars as pl
import pytest

from src.model import SimParams
from src.simulator import run_simulation

VARIANT_2D = "STM-105-17-L-2D"
VARIANT_8D = "STM-105-17-L-8D"


def _post_step_tail(df: pl.DataFrame) -> pl.DataFrame:
    """Trailing 50% of the run — past the load-step boundary at t_step."""
    n = df.height
    return df.slice(n // 2, n - n // 2)


def _run(variant: str) -> tuple[pl.DataFrame, float]:
    """Run an ideal-PWM step for ``variant`` and return (df, V_max).

    Opts into two non-default settings that together reproduce the
    "undersized-drive" scenario this suite is documenting:

    - ``vdc = 72.0`` (= the catalog ``rated_voltage`` for the 105-17 L
      chassis). The product default is ``1.5 × rated_voltage`` which
      gives 8D enough headroom to *not* saturate; this test forces the
      bus down to the BEMF cap to expose the saturation asymmetry.
    - ``t_step_frac = 2/3``. The product default is ``None`` which lets
      ``resolve_t_step_frac`` clamp 8D to ~0.1; we want the aggressive
      original step so the IR drop alone breaches the linear range.
    """
    df, meta = run_simulation(SimParams(variant_name=variant, inverter_mode="ideal", vdc=72.0, t_step_frac=2.0 / 3.0))
    v_max = meta.rated_voltage / 2.0
    return df, v_max


def test_2d_runs_inside_voltage_envelope() -> None:
    """The 2D winding's IR drop for the catalog torque step is ~13 V at 110 A_peak;
    the linear envelope is 36 V. Expect no vector saturation and large headroom."""
    df, v_max = _run(VARIANT_2D)
    tail = _post_step_tail(df)

    sat_duty = float(tail["sat_q"].cast(int).sum()) / tail.height
    vq_peak = float(df["v_q_ref"].abs().max())

    assert sat_duty < 0.01, f"2D saturated {sat_duty:.1%} of post-step ticks; expected ~0"
    assert vq_peak < 0.6 * v_max, f"2D |v_q|_max = {vq_peak:.2f} V exceeded 0.6·V_max = {0.6 * v_max:.2f} V"


def test_8d_saturates_at_rated_bus() -> None:
    """The 8D winding needs R·i_q ≈ 52 V just for the steady-state IR drop on the
    catalog torque step, which already exceeds V_max = 36 V. Expect persistent
    vector saturation and v_q_ref pinned to the envelope."""
    df, v_max = _run(VARIANT_8D)
    tail = _post_step_tail(df)

    sat_duty = float(tail["sat_q"].cast(int).sum()) / tail.height
    vq_peak = float(df["v_q_ref"].abs().max())

    assert sat_duty > 0.5, f"8D sat_q duty {sat_duty:.1%} did not exceed 50%; voltage envelope no longer binds"
    assert vq_peak == pytest.approx(v_max, rel=1e-3), f"8D |v_q|_max = {vq_peak:.4f} V did not pin to V_max = {v_max:.4f} V"


def test_textbook_equivalence_breaks_on_voltage_envelope() -> None:
    """Asymmetry test: both windings share ``tau_e ≈ 21.6 us``, so unsaturated PI
    cancellation predicts identical normalized step responses. The asymmetry
    you actually see comes from one variant breaching V_max and the other not."""
    df_2d, v_max_2d = _run(VARIANT_2D)
    df_8d, v_max_8d = _run(VARIANT_8D)
    assert v_max_2d == v_max_8d, "Both variants share a chassis Vdc — sanity check"

    sat_2d = float(_post_step_tail(df_2d)["sat_q"].cast(int).sum()) / _post_step_tail(df_2d).height
    sat_8d = float(_post_step_tail(df_8d)["sat_q"].cast(int).sum()) / _post_step_tail(df_8d).height
    # An order of magnitude is conservative — measured asymmetry is ~∞ vs 0.78.
    assert sat_8d > 10.0 * max(sat_2d, 1e-3), (
        f"Expected 8D saturation duty (got {sat_8d:.3f}) to dwarf 2D's (got {sat_2d:.3f}); the textbook equivalence only holds inside the linear PWM range."
    )
