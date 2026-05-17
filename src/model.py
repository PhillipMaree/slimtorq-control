"""Pydantic data models + catalog loader for the FOC sim.

Three layers:

1. Catalog-parsing models (CatalogFile, FamilySpec, VariantSpec, WindingSpec,
   ...) mirror catalog.yaml exactly so `CatalogFile.model_validate(...)`
   yields type-checked Python without dict-walking.
2. MotorSku decodes a SlimTorq serial number per catalog REV1.8 page 28.
   CatalogMotor takes raw catalog values + a decoded SKU and derives the
   electrical / mechanical phase-domain parameters via @computed_field, each
   one carrying its catalog page-35 formula in its docstring.
3. PmsmModel is the flat sim-facing shape consumed by the runtime
   (controller, simulator, debug scripts). For catalog motors it is produced
   by CatalogMotor.to_pmsm_model(); for synthetic motors (debug_foc.py) it
   is constructed directly with explicit R_s / L_s / psi_m / J.

The catalog loader (load_catalog, _build_pmsm_model, validate) lives at the
bottom of the file. `python -m model` runs the cross-check.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Literal

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field, computed_field


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


# ---------- Serial-number decoder (catalog REV1.8 page 28) ----------
#
# A full SlimTorq serial decomposes into nine segments:
#
#     STM-130-27-L-4Y-A-18A-A0-001
#     |   |   |  |  |  |  |   |  |
#     |   |   |  |  |  |  |   |  +-- Unique Identifier         (3 digits)
#     |   |   |  |  |  |  |   +----- Sensor Options            (Temp+Position, 2 chars; "0" = none)
#     |   |   |  |  |  |  +--------- Cable Gauge & Type        (AWG(1-99) + Type(A-Z))
#     |   |   |  |  |  +------------ Terminal Option           (A = Axial, R = Radial)
#     |   |   |  |  +--------------- Winding Option            (Series Turns + Star(Y)/Delta(D))
#     |   |   |  +------------------ Motor Variant             (L = Lite, M = Max)
#     |   |   +--------------------- Axial Length / Stator Length (mm)
#     |   +------------------------- Diameter / Stator OD     (mm)
#     +----------------------------- Motor Series              (STM = SlimTorq Motor)
#
# The short form `STM-75-20-L-4Y` (first five segments) is accepted; the
# trailing four segments are optional and default to None when absent.

_SKU_PATTERN = re.compile(
    r"^STM-(\d+)-(\d+)-([LM])-(\d+)([YD])"
    r"(?:-([AR])-(\d+[A-Z])-([A-Z0-9]{2})-(\d{3}))?$"
)


class MotorSku(BaseModel):
    """Structured form of a SlimTorq serial number (catalog REV1.8 page 28)."""

    model_config = ConfigDict(frozen=True)

    series: Literal["STM"]
    stator_od_mm: int = Field(gt=0)
    axial_length_mm: int = Field(gt=0)
    variant: Literal["L", "M"]
    series_turns: int = Field(gt=0)
    connection: Literal["Y", "D"]
    terminal: Literal["A", "R"] | None = None
    cable: str | None = None
    sensor: str | None = None
    unique_id: str | None = None

    @property
    def family_name(self) -> str:
        """Catalog family name, e.g. "SlimTorq 75-20"."""
        return f"SlimTorq {self.stator_od_mm}-{self.axial_length_mm}"

    @property
    def variant_sku(self) -> str:
        """Variant SKU as stored in catalog.yaml, e.g. "STM-75-20-L"."""
        return f"{self.series}-{self.stator_od_mm}-{self.axial_length_mm}-{self.variant}"

    @property
    def winding_code(self) -> str:
        """Winding code as stored in catalog.yaml, e.g. "4Y"."""
        return f"{self.series_turns}{self.connection}"

    @property
    def canonical_name(self) -> str:
        """Catalog dict key, e.g. "STM-75-20-L-4Y" — also used as filename stem."""
        return f"{self.variant_sku}-{self.winding_code}"


def decode_sku(s: str) -> MotorSku:
    """Parse a SlimTorq SKU string into a MotorSku.

    Accepts either the short five-segment form (STM-75-20-L-4Y) or the full
    nine-segment serial (STM-130-27-L-4Y-A-18A-A0-001).
    """
    m = _SKU_PATTERN.match(s.strip())
    if m is None:
        msg = f"unrecognised SlimTorq SKU: {s!r}"
        raise ValueError(msg)
    od, ax, var, turns, conn, term, cable, sensor, uid = m.groups()
    return MotorSku(
        series="STM",
        stator_od_mm=int(od),
        axial_length_mm=int(ax),
        variant=var,
        series_turns=int(turns),
        connection=conn,
        terminal=term,
        cable=cable,
        sensor=sensor,
        unique_id=uid,
    )


# ---------- Catalog-input model with page-35 derivations ----------
SQRT2 = math.sqrt(2.0)
UH_TO_H = 1e-6  # micro-henries -> henries
GCM2_TO_KGM2 = 1e-7  # g·cm^2 -> kg·m^2 (1e-3 kg * 1e-4 m^2)


class CatalogMotor(BaseModel):
    """Raw catalog inputs + decoded SKU; derives phase-domain parameters.

    All derivations (R_s, L_s, psi_m, J) live below as @computed_field
    properties whose docstrings cite the formula in catalog REV1.8 page 35.
    Call `.to_pmsm_model()` to obtain the flat PmsmModel the runtime expects.
    """

    model_config = ConfigDict(frozen=True)

    sku: MotorSku
    # Raw catalog values, units exactly as stored in catalog.yaml
    R_LL: float  # line-to-line resistance     [Ohm]
    L_LL_uH: float  # line-to-line inductance     [uH]
    K_T: float  # torque constant             [Nm / Arms]
    p: int  # pole pairs                  [-]
    J_gcm2: float  # rotor inertia               [g·cm^2]
    rated_voltage: float  # [V]
    i_cont: float  # [Arms]
    te_cont_cat: float  # [Nm]
    te_peak_1s: float  # [Nm]
    torque_ripple_pct: float = 0.0  # [%]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def R_s(self) -> float:
        """Phase resistance [Ohm].

        Catalog REV1.8 page 35 — the line-to-line measurement decomposes
        by winding connection:

            Star  (Y):  R_phase = 0.5 * R_LL
            Delta (D):  R_phase = 1.5 * R_LL
        """
        factor = 1.5 if self.sku.connection == "D" else 0.5
        return factor * self.R_LL

    @computed_field  # type: ignore[prop-decorator]
    @property
    def L_s(self) -> float:
        """Phase inductance [H].

        Same star/delta decomposition as R_s (catalog page 35), with an
        additional μH -> H unit conversion (factor 1e-6).
        """
        factor = 1.5 if self.sku.connection == "D" else 0.5
        return factor * self.L_LL_uH * UH_TO_H

    @computed_field  # type: ignore[prop-decorator]
    @property
    def psi_m(self) -> float:
        """Permanent-magnet flux linkage [Wb].

        Derivation from the PMSM torque equation in the amplitude-invariant
        dq frame:

            T_e = (3/2) * p * psi_m * i_q_peak                            (1)

        The catalog torque constant K_T (page 35) is defined per RMS current:

            K_T  =  T_e / I_q_rms      [Nm / Arms]                        (2)

        Amplitude-invariant Clarke gives i_q_peak = sqrt(2) * I_q_rms, so
        substituting into (1) and combining with (2):

            psi_m = K_T / (1.5 * p * sqrt(2)).
        """
        return self.K_T / (1.5 * self.p * SQRT2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def J(self) -> float:
        """Rotor inertia [kg·m^2].

        Catalog stores rotational_inertia in g·cm^2.
        1 g·cm^2 = 1e-3 kg * 1e-4 m^2 = 1e-7 kg·m^2.
        """
        return self.J_gcm2 * GCM2_TO_KGM2

    def to_pmsm_model(self) -> PmsmModel:
        """Materialise the flat sim-facing PmsmModel."""
        return PmsmModel(
            family=self.sku.family_name,
            name=self.sku.canonical_name,
            R_s=self.R_s,
            L_s=self.L_s,
            psi_m=self.psi_m,
            p=self.p,
            J=self.J,
            rated_voltage=self.rated_voltage,
            i_cont=self.i_cont,
            te_cont_cat=self.te_cont_cat,
            te_peak_1s=self.te_peak_1s,
            torque_ripple_pct=self.torque_ripple_pct,
        )


# ---------- Simulation-facing flat model ----------
class PmsmModel(BaseModel):
    """One concrete motor (family + variant + winding flattened).

    The runtime sees only this shape. Built from CatalogFile by
    motor_catalog._build_pmsm_model().
    """

    model_config = ConfigDict(frozen=True)
    family: str  # family name from catalog, e.g. "SlimTorq 75-20"
    name: str  # composite: "<sku>-<winding_type>", e.g. "STM-75-20-L-4Y"
    R_s: float  # phase resistance [Ohm]
    L_s: float  # synchronous inductance [H]
    psi_m: float  # PM flux linkage [Wb]
    p: int  # pole pairs
    J: float  # rotor inertia [kg.m^2]
    rated_voltage: float  # [V]
    i_cont: float  # continuous line current [Arms] (validation only)
    te_cont_cat: float  # catalog continuous torque [Nm]
    te_peak_1s: float  # catalog 1-second peak torque [Nm]
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
    Vdc: float  # DC-link voltage [V]
    f_pwm: float  # PWM carrier frequency [Hz]
    bw_hz: float = 1000.0  # auto-tune target bandwidth
    Kp: float | None = None
    Ki: float | None = None


class InverterConfig(BaseModel):
    """Three-phase voltage-source inverter parameters.

    f_pwm lives here (not just on FocConfig) because the inverter owns the
    PWM modulator — the modulator's carrier frequency is a power-stage trait.
    """

    model_config = ConfigDict(frozen=True)
    Vdc: float  # DC-link voltage [V]
    f_pwm: float  # PWM carrier frequency [Hz]
    t_dead: float = 1.5e-6  # gate-driver blanking interval [s]; 0 disables


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
    t: np.ndarray


# ---------- Catalog loader ----------
DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent.parent / "config" / "catalog.yaml"


def _build_pmsm_model(family: FamilySpec, variant: VariantSpec, winding: WindingSpec) -> PmsmModel:
    """Flatten one (family, variant, winding) triple into a PmsmModel.

    The serial number `f"{variant.sku}-{winding.winding_type}"` is decoded
    into a MotorSku; raw catalog values are copied into a CatalogMotor,
    which derives R_s / L_s / psi_m / J per catalog REV1.8 page 35 via its
    @computed_field properties; the result is then converted to the flat
    PmsmModel the runtime consumes.
    """
    sku = decode_sku(f"{variant.sku}-{winding.winding_type}")
    return CatalogMotor(
        sku=sku,
        R_LL=winding.line_to_line_resistance.value,
        L_LL_uH=winding.line_to_line_inductance.value,
        K_T=winding.torque_constant.value,
        p=family.common.pole_pairs,
        J_gcm2=variant.mechanical.rotational_inertia.value,
        rated_voltage=float(family.common.rated_voltage.value),
        i_cont=winding.max_continuous_current.value,
        te_cont_cat=variant.performance_envelope.continuous_torque.value,
        te_peak_1s=variant.performance_envelope.peak_torque_1s.value,
        torque_ripple_pct=variant.performance_envelope.spatial_harmonic_torque_ripple.value,
    ).to_pmsm_model()


def load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> dict[str, PmsmModel]:
    """Parse catalog.yaml, return {sku-winding: PmsmModel}."""
    raw = yaml.safe_load(path.read_text())
    catalog_file = CatalogFile.model_validate(raw)
    return {f"{v.sku}-{w.winding_type}": _build_pmsm_model(family=f, variant=v, winding=w) for f in catalog_file.motors for v in f.variants for w in v.windings}


def predicted_continuous_torque(m: PmsmModel) -> float:
    """T_e = 1.5 * p * psi_m * (sqrt(2) * i_cont). Should match m.te_cont_cat."""
    iq_peak = SQRT2 * m.i_cont
    return 1.5 * m.p * m.psi_m * iq_peak


def _validate_decoder() -> None:
    """Smoke-test the SKU decoder on a few representative serial numbers."""
    cases: list[tuple[str, dict[str, object]]] = [
        ("STM-75-20-L-4Y", {"connection": "Y", "series_turns": 4, "variant": "L", "stator_od_mm": 75, "axial_length_mm": 20}),
        ("STM-75-20-L-8D", {"connection": "D", "series_turns": 8, "variant": "L"}),
        ("STM-130-27-M-2Y", {"connection": "Y", "series_turns": 2, "variant": "M", "stator_od_mm": 130}),
        ("STM-130-27-L-4Y-A-18A-A0-001", {"terminal": "A", "cable": "18A", "sensor": "A0", "unique_id": "001"}),
    ]
    print("Decoder round-trip:")
    for raw, expected in cases:
        decoded = decode_sku(raw)
        for k, v in expected.items():
            actual = getattr(decoded, k)
            assert actual == v, f"{raw}: expected {k}={v!r}, got {actual!r}"
        canonical_expected = "-".join(raw.split("-")[:5])
        assert decoded.canonical_name == canonical_expected, f"canonical_name mismatch for {raw}"
        print(f"  OK  {raw:32s}  -> {decoded.canonical_name}")

    rejects = ("foo", "STM-75-20-L", "STM-75-20-X-4Y", "stm-75-20-l-4y")
    for bad in rejects:
        try:
            decode_sku(bad)
        except ValueError:
            print(f"  OK  rejected {bad!r}")
        else:
            msg = f"expected ValueError for {bad!r}"
            raise AssertionError(msg)
    print()


def _validate_worked_example() -> None:
    """Print derived parameters for STM-75-20-L-4Y and assert numerics.

    Reference values come from catalog REV1.8:
      - family common block (rated_voltage, pole_pairs) for SlimTorq 75-20
      - mechanical block (rotational_inertia) for STM-75-20-L
      - winding block (R_LL, L_LL, K_T, i_cont) for the 4Y winding
    Derivations follow page 35.
    """
    motor = load_catalog()["STM-75-20-L-4Y"]
    print("Worked example: STM-75-20-L-4Y (Star, 4 series turns, Lite variant)")
    print(f"  p              = {motor.p}")
    print(f"  R_s            = {motor.R_s:.4f}  Ohm        (= 0.5 * R_LL,            Star,  p.35)")
    print(f"  L_s            = {motor.L_s * 1e6:.2f}    uH         (= 0.5 * L_LL * 1e-6,     Star,  p.35)")
    print(f"  psi_m          = {motor.psi_m * 1e3:.4f}  mWb        (= K_T / (1.5 * p * sqrt(2)))")
    print(f"  J              = {motor.J:.3e} kg.m^2     (= J_gcm2 * 1e-7)")
    print(f"  rated_voltage  = {motor.rated_voltage}    V")
    print(f"  i_cont         = {motor.i_cont}   Arms")

    assert math.isclose(motor.R_s, 0.5 * 0.457, rel_tol=1e-9), motor.R_s
    assert math.isclose(motor.L_s, 0.5 * 15.4e-6, rel_tol=1e-9), motor.L_s
    assert math.isclose(motor.psi_m, 0.109 / (1.5 * 18 * SQRT2), rel_tol=1e-9), motor.psi_m
    assert math.isclose(motor.J, 620 * GCM2_TO_KGM2, rel_tol=1e-9), motor.J
    print("  all derivations match catalog REV1.8 p.35\n")


def validate() -> None:
    """End-to-end self-check: decoder, worked example, full catalog cross-check.

    The catalog cross-check tolerance is 15% because for the largest motors
    the catalog's Continuous Torque column is thermally derated below the
    electromagnetic Kt*i_cont product -- a real spec-sheet inconsistency,
    not a conversion bug.
    """
    _validate_decoder()
    _validate_worked_example()

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
        print(f"{name:22s}  {te_pred:12.4f}  {m.te_cont_cat:10.4f}  {100 * err:6.2f}%  {flag}")
    print(f"\nMax relative error: {100 * max_err:.2f}%")
    assert max_err < 0.15, f"Catalog conversion off by >15% ({100 * max_err:.2f}%)"


if __name__ == "__main__":
    validate()
