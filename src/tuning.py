"""PI current-loop tuning rules for the slotless PMSM, with optional LCL plant.

Two plant shapes are supported, selected by `plant_type`:

1. **LR motor plant** (``plant_type="lr"``). Per-axis dq plant after FOC's
   decoupling/BEMF feedforward collapses to a first-order R/L circuit:

        G_LR(s) = 1 / (L_s · s + R_s),   τ_e = L_s / R_s

   PI in parallel form `C(s) = K_p + K_i/s` adds a pole at origin and a zero
   at `-K_i/K_p`. The three rules in this module pick (K_p, K_i) from
   different design objectives below.

2. **LCL-filtered plant** (``plant_type="lcl_conservative"`` /
   ``"lcl_with_active_damping"``). Adding the inverter-side LCL filter turns
   the loop's plant into a third-order resonant system

        v_inv → L1/R1 → Cf → Lload/Rload → i_m

   with state equations

        L1   · di1/dt = v_inv - vc - R1   · i1
        Cf   · dvc/dt = i1   - im
        Lload· dim/dt = vc   - Rload· im

   Approximate (lossless) transfer function

        G_LCL(s) ≈ 1 / (L1·Lload·Cf · s³ + (L1 + Lload) · s)

   has a resonance at

        ω_res = sqrt((L1 + Lload) / (L1 · Lload · Cf))

   For closed-loop bandwidth well below resonance, the LCL plant is well
   approximated by an equivalent LR plant

        L_eq = L1 + Lload,   R_eq = R1 + Rload

   and the same PI rules apply with `(L_s, R_s) ↦ (L_eq, R_eq)`. A
   ``ValueError`` is raised if the implied closed-loop bandwidth gets too
   close to resonance or to the PWM frequency — silently tuning into the
   resonance is a footgun.

Hard guard-rails:

- ``omega_bw <= omega_res / resonance_margin`` —
  default margin 10 for ``lcl_conservative``, 5 for ``lcl_with_active_damping``.
  Active damping (separate ``Kd · ic_hat`` injection, observer-driven) reduces
  the resonance peak but does not eliminate it; relax with care.
- ``f_bw_est <= f_pwm / pwm_margin`` — default margin 20. Applies to every
  plant_type, even LR.

All three tuning functions return ``PITuningResult`` with the gains plus
diagnostic metadata for inspection and logging.

The runtime PI block (parallel form ``C(s) = K_p + K_i/s``) is unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from src.model import LCLParams

PlantType = Literal["lr", "lcl_conservative", "lcl_with_active_damping"]
TuningMethod = Literal["bandwidth", "modulus_optimum", "skogestad"]

_DEFAULT_RESONANCE_MARGIN: dict[PlantType, float] = {
    "lcl_conservative": 10.0,
    "lcl_with_active_damping": 5.0,
}
# Default PWM margin: bandwidth must be at least one decade below f_pwm.
# Modulus Optimum sits at f_pwm/(6π) ≈ f_pwm/18.85 by construction, so any
# stricter default would reject the project's own MO tuning at every f_pwm.
_DEFAULT_PWM_MARGIN = 10.0

_ACTIVE_DAMPING_NOTE = "This tuning assumes the LCL resonance is actively damped. If active damping is disabled or poorly tuned, reduce bandwidth."


@dataclass(frozen=True)
class PITuningResult:
    """Gains + diagnostics from one tuning call.

    `Kp`, `Ki` are the only fields the runtime PI needs; everything else is
    metadata for logging, UI display, and post-hoc analysis.
    """

    Kp: float
    Ki: float
    Ti: float
    plant_type: PlantType
    method: TuningMethod
    omega_bw: float | None = None
    bw_hz: float | None = None
    omega_res: float | None = None
    f_res_hz: float | None = None
    resonance_margin: float | None = None
    bandwidth_to_resonance_ratio: float | None = None
    L_used: float | None = None
    R_used: float | None = None
    T_sigma: float | None = None
    tau_e_eq: float | None = None
    f_pwm: float | None = None
    # Active-damping gain on capacitor current. Set by callers that have
    # an LCL plant + a damping-ratio target; ``None`` when no LCL or when
    # active damping is not engaged.
    Kd: float | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)


def lcl_resonance_frequency_rad_s(p: LCLParams) -> float:
    return p.resonance_frequency_rad_s()


def lcl_resonance_frequency_hz(p: LCLParams) -> float:
    return p.resonance_frequency_hz()


def equivalent_lcl_low_frequency_lr(p: LCLParams) -> tuple[float, float]:
    """Low-frequency equivalent LR of the LCL plant: (L_eq, R_eq)."""
    return p.L1 + p.Lload, p.R1 + p.Rload


def _resonance_margin_for(plant_type: PlantType, override: float | None) -> float:
    if override is not None:
        if not (math.isfinite(override) and override > 0.0):
            msg = f"resonance_margin must be positive and finite (got {override!r})"
            raise ValueError(msg)
        return override
    return _DEFAULT_RESONANCE_MARGIN[plant_type]


def _resolve_lr(plant_type: PlantType, Rs: float | None, Ls: float | None, lcl: LCLParams | None) -> tuple[float, float, float | None]:
    """Return (L_used, R_used, omega_res). `omega_res` is None for LR."""
    if plant_type == "lr":
        if Rs is None or Ls is None:
            msg = "plant_type='lr' requires Rs and Ls."
            raise ValueError(msg)
        return float(Ls), float(Rs), None
    if lcl is None:
        msg = f"plant_type={plant_type!r} requires lcl_params."
        raise ValueError(msg)
    L_eq, R_eq = equivalent_lcl_low_frequency_lr(lcl)
    return L_eq, R_eq, lcl_resonance_frequency_rad_s(lcl)


def _check_safety(
    *,
    plant_type: PlantType,
    method: TuningMethod,
    omega_implied: float,
    omega_res: float | None,
    resonance_margin: float | None,
    f_pwm: float | None,
    pwm_margin: float,
) -> tuple[float | None, list[str]]:
    """Validate the implied closed-loop bandwidth against LCL resonance and PWM.

    Returns ``(bw_to_res_ratio, notes)``. Raises ``ValueError`` on violation.
    """
    notes: list[str] = []

    ratio: float | None = None
    if plant_type != "lr":
        assert omega_res is not None  # set by _resolve_lr for LCL paths
        margin = resonance_margin if resonance_margin is not None else _DEFAULT_RESONANCE_MARGIN[plant_type]
        ratio = omega_implied / omega_res
        max_ratio = 1.0 / margin
        if ratio > max_ratio:
            if method == "modulus_optimum":
                msg = (
                    "Modulus optimum first-order tuning is unsafe for this LCL plant "
                    "at the requested PWM frequency. Use lower bandwidth tuning, "
                    "active damping, or redesign the LCL resonance. "
                    f"(omega_mo/omega_res={ratio:.3f} > 1/{margin:g})"
                )
            else:
                msg = (
                    f"PI bandwidth too close to LCL resonance: "
                    f"omega_implied/omega_res = {ratio:.3f} > 1/{margin:g} "
                    f"(method={method}, plant_type={plant_type}). "
                    "Lower the bandwidth, enable active damping, or move the LCL resonance."
                )
            raise ValueError(msg)
        if plant_type == "lcl_with_active_damping":
            notes.append(_ACTIVE_DAMPING_NOTE)

    if f_pwm is not None and pwm_margin > 0.0:
        f_bw_est = omega_implied / (2.0 * math.pi)
        max_f_bw = f_pwm / pwm_margin
        if f_bw_est > max_f_bw:
            msg = (
                f"PI implied bandwidth too close to PWM frequency: "
                f"f_bw_est = {f_bw_est:.2f} Hz > f_pwm/{pwm_margin:g} = {max_f_bw:.2f} Hz "
                f"(method={method}, plant_type={plant_type}). "
                "Lower the bandwidth or raise f_pwm."
            )
            raise ValueError(msg)

    return ratio, notes


def auto_pi_gains_from_bw(
    bw_hz: float,
    *,
    Rs: float | None = None,
    Ls: float | None = None,
    plant_type: PlantType = "lr",
    lcl_params: LCLParams | None = None,
    resonance_margin: float | None = None,
    f_pwm: float | None = None,
    pwm_margin: float = _DEFAULT_PWM_MARGIN,
) -> PITuningResult:
    """Pole-zero cancellation: K_p = L·ω_bw, K_i = R·ω_bw.

    For LCL plants the equivalent low-frequency (L_eq, R_eq) is used; raises
    ``ValueError`` if ω_bw is too close to LCL resonance or to f_pwm.
    """
    bw_hz = float(bw_hz)
    if not (math.isfinite(bw_hz) and bw_hz > 0.0):
        msg = f"bw_hz must be positive and finite (got {bw_hz!r})"
        raise ValueError(msg)

    omega_bw = 2.0 * math.pi * bw_hz
    L_used, R_used, omega_res = _resolve_lr(plant_type, Rs, Ls, lcl_params)
    margin = _resonance_margin_for(plant_type, resonance_margin) if plant_type != "lr" else None

    ratio, notes = _check_safety(
        plant_type=plant_type,
        method="bandwidth",
        omega_implied=omega_bw,
        omega_res=omega_res,
        resonance_margin=margin,
        f_pwm=f_pwm,
        pwm_margin=pwm_margin,
    )

    Kp = L_used * omega_bw
    Ki = R_used * omega_bw
    Ti = (Kp / Ki) if Ki > 0.0 else math.inf

    return PITuningResult(
        Kp=Kp,
        Ki=Ki,
        Ti=Ti,
        plant_type=plant_type,
        method="bandwidth",
        omega_bw=omega_bw,
        bw_hz=bw_hz,
        omega_res=omega_res,
        f_res_hz=(None if omega_res is None else omega_res / (2.0 * math.pi)),
        resonance_margin=margin,
        bandwidth_to_resonance_ratio=ratio,
        L_used=L_used,
        R_used=R_used,
        tau_e_eq=(L_used / R_used) if R_used > 0.0 else math.inf,
        f_pwm=f_pwm,
        notes=tuple(notes),
    )


def modulus_optimum_tuning(
    f_pwm: float,
    *,
    Rs: float | None = None,
    Ls: float | None = None,
    plant_type: PlantType = "lr",
    lcl_params: LCLParams | None = None,
    resonance_margin: float | None = None,
    pwm_margin: float = _DEFAULT_PWM_MARGIN,
) -> PITuningResult:
    """Modulus Optimum tuning. T_σ = 1.5/f_pwm; K_p = L/(2·T_σ), K_i = R/(2·T_σ)."""
    f_pwm = float(f_pwm)
    if not (math.isfinite(f_pwm) and f_pwm > 0.0):
        msg = f"f_pwm must be positive and finite (got {f_pwm!r})"
        raise ValueError(msg)

    T_sigma = 1.5 / f_pwm
    omega_mo = 1.0 / (2.0 * T_sigma)  # implied closed-loop bandwidth
    L_used, R_used, omega_res = _resolve_lr(plant_type, Rs, Ls, lcl_params)
    margin = _resonance_margin_for(plant_type, resonance_margin) if plant_type != "lr" else None

    ratio, notes = _check_safety(
        plant_type=plant_type,
        method="modulus_optimum",
        omega_implied=omega_mo,
        omega_res=omega_res,
        resonance_margin=margin,
        f_pwm=f_pwm,
        pwm_margin=pwm_margin,
    )

    Kp = L_used / (2.0 * T_sigma)
    Ki = R_used / (2.0 * T_sigma)
    Ti = (Kp / Ki) if Ki > 0.0 else math.inf

    return PITuningResult(
        Kp=Kp,
        Ki=Ki,
        Ti=Ti,
        plant_type=plant_type,
        method="modulus_optimum",
        omega_bw=omega_mo,
        bw_hz=omega_mo / (2.0 * math.pi),
        omega_res=omega_res,
        f_res_hz=(None if omega_res is None else omega_res / (2.0 * math.pi)),
        resonance_margin=margin,
        bandwidth_to_resonance_ratio=ratio,
        L_used=L_used,
        R_used=R_used,
        T_sigma=T_sigma,
        tau_e_eq=(L_used / R_used) if R_used > 0.0 else math.inf,
        f_pwm=f_pwm,
        notes=tuple(notes),
    )


def skogestad_tuning(
    f_pwm: float,
    *,
    Rs: float | None = None,
    Ls: float | None = None,
    plant_type: PlantType = "lr",
    lcl_params: LCLParams | None = None,
    k1: float = 1.44,
    Tc: float | None = None,
    resonance_margin: float | None = None,
    pwm_margin: float = _DEFAULT_PWM_MARGIN,
) -> PITuningResult:
    """Skogestad SIMC for first-order plant with dead-time τ = 1.5/f_pwm.

    K_p = L / (T_c + τ);  T_i = min(L/R, k1·(T_c+τ));  K_i = K_p/T_i.
    """
    f_pwm = float(f_pwm)
    if not (math.isfinite(f_pwm) and f_pwm > 0.0):
        msg = f"f_pwm must be positive and finite (got {f_pwm!r})"
        raise ValueError(msg)

    tau_delay = 1.5 / f_pwm
    Tc_used = tau_delay if Tc is None else float(Tc)
    sum_T = Tc_used + tau_delay
    omega_c = 1.0 / sum_T  # approximate closed-loop bandwidth

    L_used, R_used, omega_res = _resolve_lr(plant_type, Rs, Ls, lcl_params)
    margin = _resonance_margin_for(plant_type, resonance_margin) if plant_type != "lr" else None

    ratio, notes = _check_safety(
        plant_type=plant_type,
        method="skogestad",
        omega_implied=omega_c,
        omega_res=omega_res,
        resonance_margin=margin,
        f_pwm=f_pwm,
        pwm_margin=pwm_margin,
    )

    Kp = L_used / sum_T
    tau_e_eq = L_used / R_used if R_used > 0.0 else math.inf
    Ti = min(tau_e_eq, k1 * sum_T)
    Ki = Kp / Ti if Ti > 0.0 else 0.0

    return PITuningResult(
        Kp=Kp,
        Ki=Ki,
        Ti=Ti,
        plant_type=plant_type,
        method="skogestad",
        omega_bw=omega_c,
        bw_hz=omega_c / (2.0 * math.pi),
        omega_res=omega_res,
        f_res_hz=(None if omega_res is None else omega_res / (2.0 * math.pi)),
        resonance_margin=margin,
        bandwidth_to_resonance_ratio=ratio,
        L_used=L_used,
        R_used=R_used,
        T_sigma=tau_delay,
        tau_e_eq=tau_e_eq,
        f_pwm=f_pwm,
        notes=tuple(notes),
    )
