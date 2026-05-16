"""Pydantic data models + catalog loader for the FOC sim.

Two layers:
1. Catalog-parsing models mirror catalog.yaml exactly. They exist so
   `CatalogFile.model_validate(yaml.safe_load(...))` produces type-checked
   Python objects without ad-hoc dict-walking.
2. Simulation-facing models (PmsmModel, EncoderConfig, FocConfig, TLRef) are
   the flat shapes the runtime code consumes. PmsmModel is built by flattening
   one (family, variant, winding) triple from the catalog at load time.

The catalog loader (load_catalog, _build_pmsm_model, validate) lives at the
bottom of the file. `python -m model` runs the cross-check.

Catalog conversions
-------------------
- Pole pairs:           p     = common.pole_pairs           (already / 2 in catalog)
- Phase (line-to-neutral) impedance from line-to-line:
    R_s [Ohm] = R_LL / 2
    L_s [H]   = L_LL_uH * 1e-6 / 2
  Valid for both Y and Delta windings expressed in the equivalent-star form
  the dq model uses. (For Delta, the delta -> equivalent-Y transform gives
  R_Y = R_delta_branch/3 and R_delta_branch = 1.5*R_LL, so R_Y = R_LL/2.)
- PM flux linkage from Kt:
    psi_m = Kt / (1.5 * p * sqrt(2))
  Amplitude-invariant Clarke preserves phase peaks: iq_peak = sqrt(2)*i_arms,
  and Te = 1.5*p*psi_m*iq_peak = Kt*i_arms.
- Rotor inertia: J [kg.m^2] = inertia_gcm2 * 1e-7.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict


# ---------- Reusable cell shape (every {unit, value} in catalog.yaml) ----------
class ValueWithUnit(BaseModel):
    model_config = ConfigDict(frozen=True)
    unit: str
    value: float | int


# ---------- Catalog parsing layer (mirrors catalog.yaml) ----------
class AmbientRange(BaseModel):
    model_config = ConfigDict(frozen=True)
    min: ValueWithUnit
    max: ValueWithUnit
    reference: ValueWithUnit


class PowerCable(BaseModel):
    model_config = ConfigDict(frozen=True)
    length: ValueWithUnit
    size: str


class CommonSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    rated_voltage: ValueWithUnit
    poles: int
    pole_pairs: int
    cogging_torque: ValueWithUnit
    max_stator_temperature: ValueWithUnit
    max_rotor_temperature: ValueWithUnit
    ambient: AmbientRange
    power_cable: PowerCable


class _SpecWithTolerance(BaseModel):
    """A {unit, value, tolerance?} cell. Tolerance is informational; we ignore it."""
    model_config = ConfigDict(frozen=True, extra="allow")
    unit: str
    value: float | int


class MechanicalSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    stator_outer_diameter: _SpecWithTolerance
    rotor_inner_diameter: _SpecWithTolerance
    stator_axial_length: _SpecWithTolerance
    rotor_axial_length: _SpecWithTolerance
    rotational_inertia: ValueWithUnit
    stator_mass: ValueWithUnit
    rotor_mass: ValueWithUnit
    total_mass: ValueWithUnit


class ThermalSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    thermal_resistance: ValueWithUnit
    continuous_power_loss: ValueWithUnit


class PerformanceEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True)
    motor_constant: ValueWithUnit
    continuous_torque: ValueWithUnit
    peak_torque_1s: ValueWithUnit
    peak_torque_3s: ValueWithUnit
    peak_torque_5s: ValueWithUnit
    electrical_time_constant: ValueWithUnit
    spatial_harmonic_torque_ripple: ValueWithUnit  # value is in %


class WindingSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    winding_type: str
    torque_constant: ValueWithUnit
    voltage_constant: ValueWithUnit
    line_to_line_resistance: ValueWithUnit
    line_to_line_inductance: ValueWithUnit
    max_continuous_current: ValueWithUnit
    peak_current_1s: ValueWithUnit
    peak_current_3s: ValueWithUnit
    peak_current_5s: ValueWithUnit
    max_speed_at_max_voltage: ValueWithUnit


class VariantSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    sku: str
    type: str
    mechanical: MechanicalSpec
    thermal: ThermalSpec
    performance_envelope: PerformanceEnvelope
    windings: list[WindingSpec]


class FamilySpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    family: str
    description: str | None = None
    common: CommonSpec
    variants: list[VariantSpec]


class CatalogFile(BaseModel):
    model_config = ConfigDict(frozen=True)
    motors: list[FamilySpec]


# ---------- Simulation-facing flat model ----------
class PmsmModel(BaseModel):
    """One concrete motor (family + variant + winding flattened).

    The runtime sees only this shape. Built from CatalogFile by
    motor_catalog._build_pmsm_model().
    """
    model_config = ConfigDict(frozen=True)
    family: str              # family name from catalog, e.g. "SlimTorq 75-20"
    name: str                # composite: "<sku>-<winding_type>", e.g. "STM-75-20-L-4Y"
    R_s: float               # phase resistance [Ohm]
    L_s: float               # synchronous inductance [H]
    psi_m: float             # PM flux linkage [Wb]
    p: int                   # pole pairs
    J: float                 # rotor inertia [kg.m^2]
    rated_voltage: float     # [V]
    i_cont: float            # continuous line current [Arms] (validation only)
    te_cont_cat: float       # catalog continuous torque [Nm]
    torque_ripple_pct: float = 0.0  # spatial harmonic ripple [%], 0..100


# ---------- Controller / encoder / trajectory configs ----------
class EncoderConfig(BaseModel):
    """Flux-encoder parameters. Defaults = Zettlex IND-MAX-100 (22-bit)."""
    model_config = ConfigDict(frozen=True)
    n_bits: int = 22
    theta_offset: float = 0.0
    A1: float = 2.4e-5
    k1: int = 1
    phi1: float = 0.0
    A2: float = 5.0e-6
    k2: int = 2
    phi2: float = 0.0
    A3: float = 1.0e-6
    k3: int = 4
    phi3: float = 0.0
    Ts_enc: float = 1e-4


class FocConfig(BaseModel):
    """Current-loop controller tuning + limits.

    Kp / Ki override: when both are non-None the FOCController uses them
    verbatim. Otherwise the controller auto-derives gains from bw_hz via
    pole-zero cancellation against the plant.

    Vector saturation: |(v_d_ref, v_q_ref)| is clipped to V_max = Vdc / 2,
    the linear range of centered sinusoidal PWM. This pre-empts per-phase
    duty clamping (which would inject harmonics) by limiting in the dq
    frame instead.
    """
    model_config = ConfigDict(frozen=True)
    R_s: float
    L_s: float
    psi_m: float
    p: int
    Vdc: float                       # DC-link voltage [V]
    f_pwm: float                     # PWM carrier frequency [Hz]
    bw_hz: float = 1000.0            # auto-tune target bandwidth
    Kp: float | None = None
    Ki: float | None = None


class InverterConfig(BaseModel):
    """Three-phase voltage-source inverter parameters."""
    model_config = ConfigDict(frozen=True)
    Vdc: float                       # DC-link voltage [V]
    t_dead: float = 1.5e-6           # gate-driver blanking interval [s]; 0 disables


class TLRef(BaseModel):
    """Piecewise-constant load-torque trajectory.

    Each entry (ref[i], t[i]) defines a SEGMENT:
      - segment 0 spans [0,      t[0])  with value ref[0]
      - segment i spans [t[i-1], t[i])  with value ref[i]   (for i > 0)
      - t[i] is the END time of segment i (NOT the start).
      - Default simulation horizon T = t[-1].

    Example:
        TL_ref = TLRef(ref=np.array([1, 0, 2]), t=np.array([1, 3, 5]))
        # T_L = 1 for t in [0,1), 0 for t in [1,3), 2 for t in [3,5].
    """
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    ref: np.ndarray
    t:   np.ndarray


# ---------- Catalog loader ----------
SQRT2 = math.sqrt(2.0)
DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent.parent / "catalog.yaml"


def _build_pmsm_model(family: FamilySpec, variant: VariantSpec,
                      winding: WindingSpec) -> PmsmModel:
    """Flatten one (family, variant, winding) triple into a PmsmModel."""
    name  = f"{variant.sku}-{winding.winding_type}"
    p     = family.common.pole_pairs
    R_s   = winding.line_to_line_resistance.value / 2.0
    L_s   = winding.line_to_line_inductance.value * 1e-6 / 2.0
    psi_m = winding.torque_constant.value / (1.5 * p * SQRT2)
    J     = variant.mechanical.rotational_inertia.value * 1e-7
    return PmsmModel(
        family=family.family,
        name=name,
        R_s=R_s,
        L_s=L_s,
        psi_m=psi_m,
        p=p,
        J=J,
        rated_voltage=float(family.common.rated_voltage.value),
        i_cont=winding.max_continuous_current.value,
        te_cont_cat=variant.performance_envelope.continuous_torque.value,
        torque_ripple_pct=variant.performance_envelope.spatial_harmonic_torque_ripple.value,
    )


def load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> dict[str, PmsmModel]:
    """Parse catalog.yaml, return {sku-winding: PmsmModel}."""
    raw = yaml.safe_load(path.read_text())
    catalog_file = CatalogFile.model_validate(raw)
    return {
        f"{v.sku}-{w.winding_type}": _build_pmsm_model(family=f, variant=v, winding=w)
        for f in catalog_file.motors
        for v in f.variants
        for w in v.windings
    }


def predicted_continuous_torque(m: PmsmModel) -> float:
    """T_e = 1.5 * p * psi_m * (sqrt(2) * i_cont). Should match m.te_cont_cat."""
    iq_peak = SQRT2 * m.i_cont
    return 1.5 * m.p * m.psi_m * iq_peak


def validate() -> None:
    """Cross-check every loaded variant: predicted Kt*i_cont vs catalog Te.

    Tolerance is 15% because for the largest motors the catalog's Continuous
    Torque column is thermally derated below the electromagnetic Kt*i_cont
    product -- a real spec-sheet inconsistency, not a conversion bug.
    """
    catalog = load_catalog()
    print(f"Loaded {len(catalog)} variant(s) from {DEFAULT_CATALOG_PATH.name}\n")
    print(f"{'variant':22s}  {'predicted Te':>12s}  {'catalog Te':>10s}  {'err':>7s}")
    print("-" * 60)
    max_err = 0.0
    for name, m in sorted(catalog.items()):
        te_pred = predicted_continuous_torque(m)
        err = abs(te_pred - m.te_cont_cat) / m.te_cont_cat
        max_err = max(max_err, err)
        flag = " OK " if err < 0.05 else "warn"
        print(f"{name:22s}  {te_pred:12.4f}  {m.te_cont_cat:10.4f}  {100*err:6.2f}%  {flag}")
    print(f"\nMax relative error: {100*max_err:.2f}%")
    assert max_err < 0.15, f"Catalog conversion off by >15% ({100*max_err:.2f}%)"


if __name__ == "__main__":
    validate()
