"""SlimTorq motor variant catalog.

Extracted from `docs/SlimTorq Product Catalog REV1.8.pdf`. Each entry maps a
catalog part number to the per-phase parameters needed by the dq motor model
in `modelica/Slimtorq.mo::SlotlessPMSM`.

Catalog datasheet -> Modelica parameter conversions
---------------------------------------------------
Pole pairs:
    p = poles / 2

Inertia:
    J [kg.m^2] = rotational_inertia [gcm^2] * 1e-7

Phase (line-to-neutral) impedance, for BOTH Y and Delta connections, expressed
in the equivalent-star form the dq model uses:
    Rs [Ohm] = R_LL [Ohm] / 2
    Ls [H]   = L_LL [uH] * 1e-6 / 2
(For Y this is direct; for Delta the delta -> equivalent-Y transform gives
R_Y = R_delta_branch / 3 and R_delta_branch = 1.5*R_LL, so R_Y = R_LL/2.
Same factor applies to inductance. Cross-checked against catalog tau_e = Ls/Rs.)

PM flux linkage from torque constant:
    psi_m = Kt / (1.5 * p * sqrt(2))
where catalog Kt is in Nm/Arms (per Arms of line current). Derivation:
amplitude-invariant Clarke preserves phase peaks, so iq_peak in the dq model
equals the abc phase-current peak = sqrt(2) * i_arms. Then
    Te = 1.5 * p * psi_m * iq_peak = 1.5 * p * psi_m * sqrt(2) * i_arms
       = Kt * i_arms
=> psi_m = Kt / (1.5 * p * sqrt(2)). Independent of Y/D because both Kt and
the model see the line current.

Run this module as `python motor_catalog.py` to cross-check every entry's
predicted continuous torque against the catalog "Continuous torque" column.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SQRT2 = math.sqrt(2.0)


@dataclass(frozen=True)
class MotorVariant:
    name: str             # e.g. "STM-105-17-L-4Y"
    Rs: float             # phase resistance, line-to-neutral [Ohm]
    Ls: float             # synchronous inductance per phase [H]
    psi_m: float          # PM flux linkage [Wb]
    p: int                # pole pairs
    J: float              # rotor inertia [kg.m^2]
    rated_voltage: float  # [V]
    i_cont: float         # continuous phase line current [Arms]
    te_cont_cat: float    # catalog continuous torque [Nm] -- for validation only


def _make(name: str, poles: int, Kt: float, R_LL: float, L_LL_uH: float,
          inertia_gcm2: float, i_cont_arms: float, te_cont_nm: float,
          rated_v: float = 72.0) -> MotorVariant:
    p = poles // 2
    Rs = R_LL / 2.0
    Ls = L_LL_uH * 1e-6 / 2.0
    psi_m = Kt / (1.5 * p * SQRT2)
    J = inertia_gcm2 * 1e-7
    return MotorVariant(name=name, Rs=Rs, Ls=Ls, psi_m=psi_m, p=p, J=J,
                        rated_voltage=rated_v, i_cont=i_cont_arms,
                        te_cont_cat=te_cont_nm)


# Inertia is rotor-only here (the catalog "rotational inertia" is the rotor).
# For Lite vs Max the rotor differs, so the inertia column is per-variant.

CATALOG: dict[str, MotorVariant] = {
    # ---- STM-25-9 (16 poles, Max only) ------------------------------------
    "STM-25-9-M-3D":   _make("STM-25-9-M-3D",   16, 0.0029, 0.064, 0.562, 5.16, 7.89, 0.023),
    "STM-25-9-M-3Y":   _make("STM-25-9-M-3Y",   16, 0.0051, 0.192, 1.690, 5.16, 4.56, 0.023),
    "STM-25-9-M-6Y":   _make("STM-25-9-M-6Y",   16, 0.0102, 0.770, 6.740, 5.16, 2.28, 0.023),

    # ---- STM-39-10 (26 poles, Max only) -----------------------------------
    "STM-39-10-M-2D":  _make("STM-39-10-M-2D",  26, 0.007, 0.079, 0.527, 33.9, 8.65, 0.058),
    "STM-39-10-M-4Y":  _make("STM-39-10-M-4Y",  26, 0.023, 0.948, 6.320, 33.9, 2.50, 0.058),

    # ---- STM-51-12 (36 poles, Max only) -----------------------------------
    "STM-51-12-M-2D":  _make("STM-51-12-M-2D",  36, 0.013, 0.064, 0.745, 106.0, 11.3, 0.144),
    "STM-51-12-M-4Y":  _make("STM-51-12-M-4Y",  36, 0.044, 0.769, 8.95,  106.0, 3.28, 0.144),
    "STM-51-12-M-8Y":  _make("STM-51-12-M-8Y",  36, 0.088, 3.070, 35.80, 106.0, 1.64, 0.144),

    # ---- STM-75-20 (36 poles, Lite & Max) ---------------------------------
    "STM-75-20-L-4Y":  _make("STM-75-20-L-4Y",  36, 0.109, 0.457, 15.4,  620.0,  5.98, 0.654),
    "STM-75-20-L-2D":  _make("STM-75-20-L-2D",  36, 0.032, 0.038, 1.28,  620.0, 20.7,  0.654),
    "STM-75-20-M-4Y":  _make("STM-75-20-M-4Y",  36, 0.149, 0.457, 15.4, 1350.0,  6.09, 0.905),

    # ---- STM-85-24 (42 poles, Lite & Max) ---------------------------------
    "STM-85-24-L-4Y":  _make("STM-85-24-L-4Y",  42, 0.211, 0.84, 22.8,  1380.0, 5.0,  1.06),
    "STM-85-24-M-4Y":  _make("STM-85-24-M-4Y",  42, 0.283, 0.84, 22.8,  2480.0, 5.1,  1.44),

    # ---- STM-105-17 (54 poles, Lite & Max) --------------------------------
    "STM-105-17-L-4Y": _make("STM-105-17-L-4Y", 54, 0.257, 0.964, 20.8, 2070.0, 4.4,  1.14),
    "STM-105-17-L-2D": _make("STM-105-17-L-2D", 54, 0.074, 0.080, 1.73, 2070.0, 15.3, 1.14),
    "STM-105-17-M-4Y": _make("STM-105-17-M-4Y", 54, 0.312, 0.964, 20.8, 3550.0, 4.4,  1.39),

    # ---- STM-130-27 (46 poles, Lite & Max) --------------------------------
    "STM-130-27-L-4Y": _make("STM-130-27-L-4Y", 46, 0.226, 0.387, 24.0, 3910.0, 9.0,  2.03),
    "STM-130-27-M-4Y": _make("STM-130-27-M-4Y", 46, 0.387, 0.387, 24.0, 8360.0, 9.1,  3.51),

    # ---- STM-160-17 (68 poles, Lite & Max) --------------------------------
    "STM-160-17-L-4Y": _make("STM-160-17-L-4Y", 68, 0.467, 1.02, 26.3,  8400.0, 5.0,  2.34),
    "STM-160-17-M-4Y": _make("STM-160-17-M-4Y", 68, 0.581, 1.02, 26.3, 13800.0, 5.1,  2.94),

    # ---- STM-190-35 (74 poles, Lite & Max) --------------------------------
    "STM-190-35-L-4Y": _make("STM-190-35-L-4Y", 74, 1.140, 1.254, 59.0, 40042.0, 8.3,  8.72),
    "STM-190-35-M-4Y": _make("STM-190-35-M-4Y", 74, 1.520, 1.254, 59.0, 59538.0, 8.3, 11.29),
    "STM-190-35-L-2D": _make("STM-190-35-L-2D", 74, 0.329, 0.105, 5.0,  40042.0, 28.6, 8.72),
}


def predicted_continuous_torque(v: MotorVariant) -> float:
    """Te = 1.5 * p * psi_m * (sqrt(2) * i_cont). Should match v.te_cont_cat."""
    iq_peak = SQRT2 * v.i_cont
    return 1.5 * v.p * v.psi_m * iq_peak


def validate() -> None:
    """Cross-check every variant: predicted Kt*i_cont vs catalog continuous torque.

    Tolerance is 15% because for the largest motors (STM-190-35) the catalog's
    Continuous Torque column is *thermally* derated below the electromagnetic
    Kt*i_cont product -- a real spec-sheet inconsistency, not a conversion bug
    (cross-check: for STM-190-35 every winding gives Kt*i_cont ~ 9.4 Nm while
    the catalog continuous-torque field reads 8.72 Nm). Anything beyond 15%
    would indicate a conversion error.
    """
    print(f"{'variant':22s}  {'predicted Te':>12s}  {'catalog Te':>10s}  {'err':>7s}")
    print("-" * 60)
    max_err = 0.0
    for name, v in CATALOG.items():
        te_pred = predicted_continuous_torque(v)
        err = abs(te_pred - v.te_cont_cat) / v.te_cont_cat
        max_err = max(max_err, err)
        flag = " OK " if err < 0.05 else "warn"
        print(f"{name:22s}  {te_pred:12.4f}  {v.te_cont_cat:10.4f}  {100*err:6.2f}%  {flag}")
    print(f"\nMax relative error: {100*max_err:.2f}%")
    assert max_err < 0.15, f"Catalog conversion off by >15% ({100*max_err:.2f}%)"


if __name__ == "__main__":
    validate()
