"""Assembled closed-loop drive: motor + power stage + sensing + control.

A :class:`Drivetrain` bundles the four runtime components — FMU-backed
motor, FOC controller, inverter, encoder — plus an optional LCL output
filter, with every motor-aware derivation already resolved:

- ``Vdc`` from ``motor.rated_voltage``
- ``(L_f, C_f, R_d)`` from :func:`FilterConfig.derive_components`
- ``(Kp, Ki)`` from the chosen PI tuning rule (see :func:`_resolve_gains`)

The :meth:`Drivetrain.build` classmethod is the canonical factory; given
:class:`SimParams` and a :class:`PmsmModel` it materialises a fully-wired
drive ready to hand to :class:`Simulator`.

Drivetrain owns the FMU resource — it is the context manager around a
simulation::

    with Drivetrain.build(p, motor) as drive:
        sim = Simulator(drive)
        df = sim.run(TL_ref)
"""

from __future__ import annotations

import math
from types import TracebackType
from typing import Self

from src.controller import FOCController
from src.encoder import EncoderMeasurement, FluxEncoder
from src.model import (
    EncoderConfig,
    FilterConfig,
    FocConfig,
    InverterConfig,
    LCLParams,
    PiMode,
    PmsmModel,
    SimParams,
)
from src.switching import Inverter, LCLFilter, PMSMAbcModel
from src.tuning import PlantType, modulus_optimum_tuning, skogestad_tuning

# Headroom factor over the active-damping resonance margin (5). Tc is
# chosen so omega_c <= omega_res / (5 * SAFETY_HEADROOM); 1.25 leaves
# ~25% slack against the guard.
_LCL_TC_SAFETY_HEADROOM = 1.25


class Drivetrain:
    """The whole motor-side mechanism — assembled, pre-wired, ready to run.

    Instances hold already-instantiated runtime components rather than
    Pydantic configs: the components carry mutable per-step state (PWM
    dead-time tracking, PI integrators, FMU handle), so the Drivetrain
    is the right granularity for resource ownership — one ``with`` block
    scopes the whole drive.
    """

    def __init__(
        self,
        *,
        motor: PmsmModel,
        motor_fmu: PMSMAbcModel,
        controller: FOCController,
        inverter: Inverter,
        encoder: EncoderMeasurement,
        lcl_filter: LCLFilter | None,
        observer_pole_multiplier: float = 3.0,
    ) -> None:
        self.motor = motor
        self.motor_fmu = motor_fmu
        self.controller = controller
        self.inverter = inverter
        self.encoder = encoder
        self.lcl_filter = lcl_filter
        # Stored for the simulator to use when it constructs LCL observers
        # (lazily, only in switching mode). Observer poles will be placed
        # at this multiple of the LCL resonance frequency.
        self.observer_pole_multiplier = float(observer_pole_multiplier)

    # Default DC bus as a multiple of the motor's catalog rated voltage.
    # The catalog "rated_voltage" is the BEMF the motor produces at its top
    # speed — *not* the recommended bus. A real drive supplies roughly
    # 1.3-2* rated so the PI controller has headroom for the steady-state
    # R·i_q drop and the transient L·di_q/dt inside the linear PWM range
    # (|v_dq| ≤ Vdc/2). 1.5* is the middle of the band and matches
    # industrial servo-drive practice. See memo.md §1 for the worked
    # 72 V vs 108 V comparison.
    DEFAULT_VDC_OVER_RATED = 1.5

    @classmethod
    def build(cls, p: SimParams, motor: PmsmModel) -> Self:
        """Materialise a Drivetrain from :class:`SimParams` and a motor.

        Resolves every motor-aware derivation in one place:

        - **Vdc** from ``p.vdc`` if supplied, otherwise
          ``DEFAULT_VDC_OVER_RATED * motor.rated_voltage`` (see
          :func:`resolve_vdc`).
        - **LCL components** (when ``p.filter_enabled``) from the motor
          inductance via :meth:`FilterConfig.derive_components`.
        - **FOC gains** from the chosen PI mode (see :func:`_resolve_gains`).
        """
        Vdc = resolve_vdc(p, motor)
        Kp, Ki, Kd = _resolve_gains(p, motor)

        encoder_cfg = EncoderConfig(
            n_bits=p.n_bits,
            theta_offset=p.theta_offset,
            A1=p.A1,
            k1=p.k1,
            phi1=p.phi1,
            A2=p.A2,
            k2=p.k2,
            phi2=p.phi2,
            A3=p.A3,
            k3=p.k3,
            phi3=p.phi3,
            Ts_enc=p.ts_enc,
        )
        foc_cfg = FocConfig(
            R_s=motor.R_s,
            L_s=motor.L_s,
            lambda_PM=motor.lambda_PM,
            p=motor.p,
            Vdc=Vdc,
            f_pwm=p.f_pwm,
            Kp=Kp,
            Ki=Ki,
            Kd=Kd,
        )
        inverter_cfg = InverterConfig(
            Vdc=Vdc,
            f_pwm=p.f_pwm,
            t_dead=p.t_dead,
            pwm_mode=p.pwm_mode,
        )

        lcl_filter: LCLFilter | None = None
        if p.filter_enabled:
            L_f, C_f, R_d = FilterConfig.derive_components(motor.L_s, p.filter_fc)
            lcl_filter = LCLFilter(L_f=L_f, C_f=C_f, R_d=R_d)

        return cls(
            motor=motor,
            motor_fmu=PMSMAbcModel(motor),
            controller=FOCController(foc_cfg),
            inverter=Inverter(inverter_cfg),
            encoder=EncoderMeasurement(FluxEncoder(encoder_cfg), p=motor.p),
            lcl_filter=lcl_filter,
            observer_pole_multiplier=float(p.observer_pole_multiplier),
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # Release the FMU even if a caller raised. fmpy's terminate/free
        # raise if called twice, so swallow on the way out — a second
        # close here would mask the original exception.
        try:
            self.motor_fmu.close()
        except Exception:
            pass

    # ---- Derived quantities the Simulator needs every step ----

    @property
    def Vdc(self) -> float:
        return self.inverter.Vdc

    @property
    def kt_dq(self) -> float:
        # T_e = 1.5·p·λ_PM·i_q  =>  i_q_ref = T_e_ref / kt_dq.
        return 1.5 * self.motor.p * self.motor.lambda_PM

    @property
    def dt_ctrl(self) -> float:
        # One FOC tick per PWM cycle — standard digital-FOC convention.
        return 1.0 / self.controller.f_pwm


# ---------------------------------------------------------------------------
# Bus-voltage resolution.
# ---------------------------------------------------------------------------


def resolve_vdc(p: SimParams, motor: PmsmModel) -> float:
    """Return the DC bus voltage to use for this run.

    Uses ``p.vdc`` verbatim if supplied; otherwise scales the motor's
    catalog ``rated_voltage`` by :data:`Drivetrain.DEFAULT_VDC_OVER_RATED`.
    The catalog's "rated_voltage" is the BEMF the motor produces at its top
    speed — *not* the bus a real drive would supply. Scaling it up gives
    the PI controller realistic headroom inside the linear PWM range
    (``|v_dq| ≤ Vdc/2``).
    """
    return float(p.vdc) if p.vdc is not None else Drivetrain.DEFAULT_VDC_OVER_RATED * float(motor.rated_voltage)


# ---------------------------------------------------------------------------
# Gain-resolution policy.
#
# Lives here because the gains are part of the assembled drive — picking
# Kp / Ki is the last step before instantiating FOCController. The same
# helpers are exported for callers (e.g. the /defaults endpoint via
# simulator.gains_for_mode) that need a tuning answer without building a
# whole drive.
# ---------------------------------------------------------------------------


def _ts_for_tuning(f_pwm: float) -> float:
    """Mirror of Simulator.run()'s default ``T_s = T_pwm / 20`` so the
    :class:`LCLParams` used at tuning time matches the Ts the observer
    will actually see."""
    return 1.0 / (float(f_pwm) * 20.0)


def _plant_type_for(filter_enabled: bool) -> PlantType:
    """LR for no filter, ``lcl_with_active_damping`` when the LCL is on
    (the observer drives Kd · ic_hat, so the resonance is actively damped
    — margin 5 suffices instead of the conservative 10)."""
    return "lcl_with_active_damping" if filter_enabled else "lr"


def _safe_lcl_tc(motor: PmsmModel, f_pwm: float, filter_fc: float, margin: float = 5.0) -> float:
    """Skogestad ``Tc`` that keeps closed-loop bandwidth safely below the
    LCL resonance.

    Solves ``omega_c = 1/(Tc + tau_delay) <= omega_res / (margin * headroom)``
    for ``Tc``, where ``tau_delay = 1.5 / f_pwm`` is the controller-+-PWM
    dead-time used by Skogestad. ``margin`` matches the tuning rule's plant
    gate: 5 for ``lcl_with_active_damping``, 10 for ``lcl_conservative``.
    Floored at ``tau_delay`` so ``Tc`` is at least one dead-time.
    """
    lcl = LCLParams.from_filter_config(
        FilterConfig(enabled=True, f_c_target=filter_fc),
        motor,
        _ts_for_tuning(f_pwm),
    )
    omega_res = lcl.resonance_frequency_rad_s()
    tau_delay = 1.5 / float(f_pwm)
    tc_min = (float(margin) * _LCL_TC_SAFETY_HEADROOM) / omega_res - tau_delay
    return max(tc_min, tau_delay)


def _auto_tune(
    motor: PmsmModel,
    pi_mode: PiMode,
    f_pwm: float,
    pi_tc: float | None,
    pi_k1: float,
    filter_enabled: bool,
    filter_fc: float,
    zeta_target: float = 0.7,
) -> tuple[float, float, float | None]:
    """Resolve ``(Kp, Ki, Kd)``. ``Kd`` is ``None`` when LCL is not engaged.

    When the LCL filter is on the tuner routes through
    :func:`lcl_pole_placement_tuning`, which designs ``(Kp, Ki, Kd)``
    simultaneously by placing 3 closed-loop poles of the augmented 3rd-order
    LCL + integrator plant. ``pi_mode`` is ignored in that branch (pole
    placement is the only sensible choice once active damping is in play).

    Without the filter, the function defers to the user's ``pi_mode``
    (Modulus Optimum / Skogestad) on the LR plant.
    """
    if filter_enabled:
        # LCL plant. Two routes depending on whether the user wants active
        # damping (zeta_target > 0) or passive-only:
        #   - zeta_target > 0: Skogestad on (L_eq, R_eq) with the
        #     "lcl_with_active_damping" margin (5), plus analytic
        #         Kd = 2·ζ·√(L_total/Cf) − (R_1 + R_d_passive)
        #     to damp the resonance pole pair to ``zeta_target``. Kd floors
        #     at 0 — if passive damping already meets the target, AD is
        #     unnecessary.
        #   - zeta_target ≤ 0: AD is genuinely off (Kd = 0). Route through
        #     "lcl_conservative" (margin 10) so the PI bandwidth respects
        #     the *passive* damping budget; otherwise we'd tune as if AD
        #     were active and the undamped resonance would ring.
        lcl = LCLParams.from_filter_config(
            FilterConfig(enabled=True, f_c_target=filter_fc),
            motor,
            _ts_for_tuning(f_pwm),
        )
        _, _, R_d_passive = FilterConfig.derive_components(motor.L_s, filter_fc)
        ad_on = float(zeta_target) > 0.0
        tc_safe = _safe_lcl_tc(motor, f_pwm, filter_fc, margin=5.0 if ad_on else 10.0)
        tc_used = tc_safe if pi_tc is None else max(float(pi_tc), tc_safe)
        sk = skogestad_tuning(
            float(f_pwm),
            Rs=motor.R_s,
            Ls=motor.L_s,
            plant_type="lcl_with_active_damping" if ad_on else "lcl_conservative",
            lcl_params=lcl,
            k1=float(pi_k1),
            Tc=tc_used,
        )
        if ad_on:
            L_total = (lcl.L1 * lcl.Lload) / (lcl.L1 + lcl.Lload)
            Kd_target = 2.0 * float(zeta_target) * math.sqrt(L_total / lcl.Cf) - (lcl.R1 + R_d_passive)
            Kd = max(0.0, Kd_target)
        else:
            Kd = 0.0
        return sk.Kp, sk.Ki, Kd
    if pi_mode == "skogestad":
        r = skogestad_tuning(
            float(f_pwm),
            Rs=motor.R_s,
            Ls=motor.L_s,
            plant_type="lr",
            lcl_params=None,
            k1=float(pi_k1),
            Tc=pi_tc,
        )
        return r.Kp, r.Ki, None
    r = modulus_optimum_tuning(
        float(f_pwm),
        Rs=motor.R_s,
        Ls=motor.L_s,
        plant_type="lr",
        lcl_params=None,
    )
    return r.Kp, r.Ki, None


def _resolve_gains(p: SimParams, motor: PmsmModel) -> tuple[float, float, float | None]:
    if p.pi_mode == "manual" and p.Kp is not None and p.Ki is not None:
        return float(p.Kp), float(p.Ki), None
    return _auto_tune(
        motor,
        p.pi_mode,
        p.f_pwm,
        p.pi_tc,
        p.pi_k1,
        p.filter_enabled,
        p.filter_fc,
        p.zeta_target,
    )
