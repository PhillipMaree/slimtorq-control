"""Tests for the plant-aware PI tuning module.

Covers the 13 cases enumerated in the implementation brief.
"""

from __future__ import annotations

import math

import pytest

from src.model import LCLParams
from src.tuning import (
    auto_pi_gains_from_bw,
    equivalent_lcl_low_frequency_lr,
    lcl_resonance_frequency_hz,
    lcl_resonance_frequency_rad_s,
    modulus_optimum_tuning,
    skogestad_tuning,
)

# Reference numbers shared by several cases.
RS = 0.2
LS = 50e-6
F_PWM = 50_000.0
BW_HZ = 500.0


def _lcl_safe() -> LCLParams:
    """An LCL plant whose resonance is comfortably above any tuning we'll run."""
    return LCLParams(L1=100e-6, R1=0.02, Cf=2e-6, Lload=70e-6, Rload=0.25, Ts=1e-6)


def _lcl_low_res() -> LCLParams:
    """An LCL plant deliberately picked to fail the MO/Skogestad resonance gate."""
    return LCLParams(L1=200e-6, R1=0.0, Cf=20e-6, Lload=200e-6, Rload=0.1, Ts=1e-6)


# 1. LR bandwidth tuning gives the textbook gains.
def test_lr_bandwidth_matches_textbook() -> None:
    r = auto_pi_gains_from_bw(BW_HZ, Rs=RS, Ls=LS, plant_type="lr")
    omega = 2.0 * math.pi * BW_HZ
    assert math.isclose(r.Kp, LS * omega)
    assert math.isclose(r.Ki, RS * omega)
    assert r.plant_type == "lr"
    assert r.method == "bandwidth"


# 2. LR Modulus Optimum matches the f_pwm/3 formula.
def test_lr_modulus_optimum_matches_textbook() -> None:
    r = modulus_optimum_tuning(F_PWM, Rs=RS, Ls=LS, plant_type="lr")
    assert math.isclose(r.Kp, LS * F_PWM / 3.0)
    assert math.isclose(r.Ki, RS * F_PWM / 3.0)


# 3. LR Skogestad reproduces the pre-change gains.
def test_lr_skogestad_matches_pre_change() -> None:
    r = skogestad_tuning(F_PWM, Rs=RS, Ls=LS, plant_type="lr")
    # tau = 1.5/f_pwm; Tc=tau; sum=2*tau; Kp = L/sum = L*f_pwm/3.
    tau = 1.5 / F_PWM
    sum_T = 2.0 * tau
    expected_kp = LS / sum_T
    tau_e = LS / RS
    expected_ti = min(tau_e, 1.44 * sum_T)
    assert math.isclose(r.Kp, expected_kp)
    assert math.isclose(r.Ki, expected_kp / expected_ti)


# 4. LCL resonance frequency uses the standard formula.
def test_lcl_resonance_formula() -> None:
    p = _lcl_safe()
    omega_expected = math.sqrt((p.L1 + p.Lload) / (p.L1 * p.Lload * p.Cf))
    assert math.isclose(lcl_resonance_frequency_rad_s(p), omega_expected)
    assert math.isclose(lcl_resonance_frequency_hz(p), omega_expected / (2.0 * math.pi))


# 5. Equivalent low-frequency LR is (L1+Lload, R1+Rload).
def test_equivalent_lcl_lr() -> None:
    p = _lcl_safe()
    L_eq, R_eq = equivalent_lcl_low_frequency_lr(p)
    assert math.isclose(L_eq, p.L1 + p.Lload)
    assert math.isclose(R_eq, p.R1 + p.Rload)


# 6. LCL conservative bandwidth tuning returns L_eq·ω, R_eq·ω.
def test_lcl_conservative_bandwidth() -> None:
    p = _lcl_safe()
    # Pick a bandwidth comfortably below resonance/10.
    bw = p.resonance_frequency_hz() / 20.0
    r = auto_pi_gains_from_bw(bw, plant_type="lcl_conservative", lcl_params=p)
    omega = 2.0 * math.pi * bw
    L_eq, R_eq = equivalent_lcl_low_frequency_lr(p)
    assert math.isclose(r.Kp, L_eq * omega)
    assert math.isclose(r.Ki, R_eq * omega)
    assert r.bandwidth_to_resonance_ratio == pytest.approx(omega / p.resonance_frequency_rad_s())


# 7. LCL conservative raises when ω_bw > ω_res / 10.
def test_lcl_conservative_rejects_high_bandwidth() -> None:
    p = _lcl_safe()
    bw_too_high = p.resonance_frequency_hz() / 5.0  # ratio 0.2, well above 0.1
    with pytest.raises(ValueError, match="LCL resonance"):
        auto_pi_gains_from_bw(bw_too_high, plant_type="lcl_conservative", lcl_params=p)


# 8. Active-damping path accepts a bandwidth the conservative path rejects.
def test_active_damping_relaxes_resonance_margin() -> None:
    p = _lcl_safe()
    # Pick a bandwidth between ω_res/10 and ω_res/5 — fails conservative, passes AD.
    bw = p.resonance_frequency_hz() / 7.0
    with pytest.raises(ValueError):
        auto_pi_gains_from_bw(bw, plant_type="lcl_conservative", lcl_params=p)
    r = auto_pi_gains_from_bw(bw, plant_type="lcl_with_active_damping", lcl_params=p)
    assert r.plant_type == "lcl_with_active_damping"
    assert "active" in r.notes[0].lower()


# 9. MO raises on an unsafe LCL resonance ratio with the specific message.
def test_lcl_modulus_optimum_unsafe_raises() -> None:
    p = _lcl_low_res()  # f_res low enough to make ω_mo > ω_res/10 at F_PWM
    with pytest.raises(ValueError, match="Modulus optimum first-order tuning is unsafe"):
        modulus_optimum_tuning(F_PWM, Rs=RS, Ls=LS, plant_type="lcl_conservative", lcl_params=p)


# 10. Skogestad raises on an unsafe LCL resonance ratio.
def test_lcl_skogestad_unsafe_raises() -> None:
    p = _lcl_low_res()
    with pytest.raises(ValueError, match="LCL resonance"):
        skogestad_tuning(F_PWM, Rs=RS, Ls=LS, plant_type="lcl_conservative", lcl_params=p)


# 11. Invalid LCLParams raise at construction time.
@pytest.mark.parametrize(
    "kwargs",
    [
        {"L1": -1.0},
        {"Cf": 0.0},
        {"Lload": -1e-6},
        {"R1": -0.1},
        {"Rload": -0.1},
        {"Ts": 0.0},
        {"L1": float("inf")},
    ],
)
def test_invalid_lcl_params_raise(kwargs: dict[str, float]) -> None:
    base = {"L1": 1e-4, "R1": 0.01, "Cf": 1e-6, "Lload": 1e-4, "Rload": 0.1, "Ts": 1e-6}
    base.update(kwargs)
    with pytest.raises(ValueError):
        LCLParams(**base)


# 12. plant_type="lr" without Rs/Ls raises.
def test_lr_requires_rs_ls() -> None:
    with pytest.raises(ValueError, match="requires Rs and Ls"):
        auto_pi_gains_from_bw(BW_HZ, plant_type="lr")
    with pytest.raises(ValueError, match="requires Rs and Ls"):
        modulus_optimum_tuning(F_PWM, plant_type="lr")
    with pytest.raises(ValueError, match="requires Rs and Ls"):
        skogestad_tuning(F_PWM, plant_type="lr")


# 13. LCL plant types without lcl_params raise.
def test_lcl_requires_lcl_params() -> None:
    with pytest.raises(ValueError, match="requires lcl_params"):
        auto_pi_gains_from_bw(BW_HZ, plant_type="lcl_conservative")
    with pytest.raises(ValueError, match="requires lcl_params"):
        modulus_optimum_tuning(F_PWM, plant_type="lcl_conservative")
    with pytest.raises(ValueError, match="requires lcl_params"):
        skogestad_tuning(F_PWM, plant_type="lcl_with_active_damping")
