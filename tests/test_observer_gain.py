"""Ackermann pole placement for the LCL observer gain.

``compute_observer_gain(A, C, pole)`` should produce an ``L`` such that
``A − L·C`` has all three eigenvalues at ``−pole``. The classic textbook
sanity check.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.model import LCLParams
from src.observer import _C_BY_MEASUREMENT, compute_observer_gain


def _A(lcl: LCLParams) -> np.ndarray:
    return np.array(
        [
            [-lcl.R1 / lcl.L1, -1.0 / lcl.L1, 0.0],
            [1.0 / lcl.Cf, 0.0, -1.0 / lcl.Cf],
            [0.0, 1.0 / lcl.Lload, -lcl.Rload / lcl.Lload],
        ]
    )


def _representative_lcl() -> LCLParams:
    """Plant that resembles 8D + matched-L LCL filter."""
    return LCLParams(L1=41.6e-6, R1=0.0, Cf=24.4e-6, Lload=41.6e-6, Rload=1.935, Ts=2.5e-6)


def test_compute_observer_gain_places_all_eigenvalues_at_minus_pole() -> None:
    lcl = _representative_lcl()
    A = _A(lcl)
    C = _C_BY_MEASUREMENT["motor_current"]
    pole = 3.0 * lcl.resonance_frequency_rad_s()
    L = compute_observer_gain(A, C, pole=pole)
    eig = np.sort(np.linalg.eigvals(A - np.outer(L, C)).real)
    # All three eigenvalues should sit at -pole within numerical tolerance.
    expected = -pole
    for e in eig:
        assert abs(e - expected) / abs(expected) < 1e-3, f"eigenvalues {eig}; expected all at {expected:.3g}"


def test_compute_observer_gain_returns_shape_3() -> None:
    lcl = _representative_lcl()
    L = compute_observer_gain(_A(lcl), _C_BY_MEASUREMENT["motor_current"], pole=1e5)
    assert L.shape == (3,)


@pytest.mark.parametrize("measurement_type", ["motor_current", "inverter_current", "capacitor_voltage"])
def test_compute_observer_gain_handles_each_measurement_type(measurement_type: str) -> None:
    lcl = _representative_lcl()
    A = _A(lcl)
    C = _C_BY_MEASUREMENT[measurement_type]
    pole = 2.0 * lcl.resonance_frequency_rad_s()
    L = compute_observer_gain(A, C, pole=pole)
    eig = np.linalg.eigvals(A - np.outer(L, C)).real
    # All eigenvalues stable + near the target.
    assert np.all(eig < 0.0), f"unstable eigenvalues for {measurement_type}: {eig}"
    assert all(abs(e + pole) / pole < 1e-3 for e in eig)


def test_compute_observer_gain_rejects_non_positive_pole() -> None:
    lcl = _representative_lcl()
    A = _A(lcl)
    C = _C_BY_MEASUREMENT["motor_current"]
    with pytest.raises(ValueError, match="pole must be positive"):
        compute_observer_gain(A, C, pole=0.0)
    with pytest.raises(ValueError, match="pole must be positive"):
        compute_observer_gain(A, C, pole=-1.0)
