"""Switching power stage: inverter (PWM + dead-time) and PMSM FMU wrapper.

PWMModulator: centered duty conversion + triangular-carrier comparison.
              Lives inside `Inverter` — kept as a standalone class for unit
              tests and direct inspection.
Inverter:     Power stage = PWM modulator + 2-level VSI with gate-driver
              dead-time emulation. One `step()` call does both.
PMSMAbcModel: thin wrapper around the OpenModelica SlotlessPMSM_abc FMU.

The signal chain is

    v_a_ref, v_b_ref, v_c_ref, i_abc, t, dt  ──► Inverter ──►
        d_abc, s_abc, v_a, v_b, v_c (post-inverter)
    v_a, v_b, v_c, T_L, dt                   ──► PMSMAbcModel ──► (FMU step)

so the FOC's continuous voltage refs are converted to switching phase voltages
that the PMSM integrates. Phase currents acquire the textbook triangular ripple
Δi_pp ≈ Vdc · T_pwm / (8 · L_s) at the carrier frequency.
"""

from __future__ import annotations

import math
from pathlib import Path

from fmpy import extract, read_model_description
from fmpy.fmi2 import FMU2Slave

from src.model import InverterConfig, PmsmModel

# ---------------------------------------------------------------------------
# PWM modulator
# ---------------------------------------------------------------------------
_MODE_CODE = {"sine": 0, "svpwm": 1, "dpwmmax": 2, "dpwmmin": 3, "dpwm1": 4}
_AUTO_HYST_LOW = 0.45
_AUTO_HYST_HIGH = 0.55


class PWMModulator:
    """Centered triangular-carrier PWM with selectable zero-sequence injection.

    Duty conversion per phase:
        d_k = clip(0.5 + (v_k_ref + v_z) / Vdc, 0, 1)

    where `v_z` is a per-tick common-mode offset that depends on `mode`:
      sine    : v_z = 0                              (no injection — original behaviour)
      svpwm   : v_z = -(max(v_abc) + min(v_abc)) / 2 (extends linear range by 15%)
      dpwmmax : v_z = Vdc/2 - max(v_abc)             (top phase clamped to +Vdc/2)
      dpwmmin : v_z = -Vdc/2 - min(v_abc)            (bottom phase clamped to -Vdc/2)
      dpwm1   : dpwmmax if |max| >= |min| else dpwmmin (canonical DSVPWM, alternating)
      auto    : svpwm when m_index < 0.45, dpwm1 when m_index > 0.55 (hysteretic switch)

    Common-mode injection is invisible to the motor's dq currents because
    the FMU's Clarke transform rejects it; only the duty pattern (and
    therefore switching-loss profile) changes.

    Carrier: a triangle of period T_pwm = 1/f_pwm rising 0 → 1 over [0, T/2)
    and falling 1 → 0 over [T/2, T). Switch state s_k = 1 iff d_k > carrier.

    The modulator is stateless across `step()` calls except for the
    auto-mode hysteresis latch and per-tick diagnostic readouts
    (`last_active_mode`, `last_m_index`).
    """

    def __init__(self, f_pwm: float, mode: str = "sine") -> None:
        if mode not in {*_MODE_CODE.keys(), "auto"}:
            msg = f"PWMModulator: unknown mode {mode!r}"
            raise ValueError(msg)
        self.f_pwm = f_pwm
        self.T_pwm = 1.0 / f_pwm
        self.mode = mode
        # Auto-mode latch starts in continuous; flips to dpwm1 above the
        # high threshold and back below the low threshold.
        self._auto_active: str = "svpwm"
        self.last_active_mode: str = mode if mode != "auto" else "svpwm"
        self.last_m_index: float = 0.0

    def _carrier(self, t: float) -> float:
        phase = (t / self.T_pwm) % 1.0  # in [0, 1)
        # Triangle peak=1 at phase=0.5, valley=0 at phase=0 and 1.
        return 1.0 - 2.0 * abs(phase - 0.5)

    def _resolve_active_mode(self, m_index: float) -> str:
        if self.mode != "auto":
            return self.mode
        # Hysteresis: only flip when crossing the far threshold from the
        # other side, so noise around 0.5 doesn't chatter.
        if self._auto_active == "svpwm" and m_index > _AUTO_HYST_HIGH:
            self._auto_active = "dpwm1"
        elif self._auto_active == "dpwm1" and m_index < _AUTO_HYST_LOW:
            self._auto_active = "svpwm"
        return self._auto_active

    @staticmethod
    def _v_z(active_mode: str, v_a: float, v_b: float, v_c: float, Vdc: float) -> float:
        if active_mode == "sine":
            return 0.0
        v_max = max(v_a, v_b, v_c)
        v_min = min(v_a, v_b, v_c)
        if active_mode == "svpwm":
            return -0.5 * (v_max + v_min)
        if active_mode == "dpwmmax":
            return 0.5 * Vdc - v_max
        if active_mode == "dpwmmin":
            return -0.5 * Vdc - v_min
        # dpwm1 — clamp whichever rail is closer to the current peak.
        return 0.5 * Vdc - v_max if abs(v_max) >= abs(v_min) else -0.5 * Vdc - v_min

    def step(self, v_a_ref: float, v_b_ref: float, v_c_ref: float, Vdc: float, t: float, dt: float) -> tuple[float, float, float, int, int, int]:
        # Modulation index for the auto-mode switch (and for diagnostic logging).
        # With centered Clarke the peak phase ref equals |v_dq|.
        v_peak = max(abs(v_a_ref), abs(v_b_ref), abs(v_c_ref))
        m_index = v_peak / (0.5 * Vdc) if Vdc > 0.0 else 0.0
        active = self._resolve_active_mode(m_index)
        v_z = self._v_z(active, v_a_ref, v_b_ref, v_c_ref, Vdc)
        self.last_active_mode = active
        self.last_m_index = m_index
        d_a = max(0.0, min(1.0, 0.5 + (v_a_ref + v_z) / Vdc))
        d_b = max(0.0, min(1.0, 0.5 + (v_b_ref + v_z) / Vdc))
        d_c = max(0.0, min(1.0, 0.5 + (v_c_ref + v_z) / Vdc))
        c = self._carrier(t)
        s_a = 1 if d_a > c else 0
        s_b = 1 if d_b > c else 0
        s_c = 1 if d_c > c else 0
        return d_a, d_b, d_c, s_a, s_b, s_c


# ---------------------------------------------------------------------------
# Inverter (PWM modulator + 2-level VSI with dead-time emulation)
# ---------------------------------------------------------------------------
class Inverter:
    """Power stage: PWM modulator + 2-level VSI with dead-time emulation.

    Outside the dead-time window, each phase voltage relative to the DC-link
    midpoint is

        v_k = (s_k - 0.5) · Vdc           (i.e. ±Vdc/2)

    During the t_dead window following a switch transition both top and
    bottom transistors are off (shoot-through prevention). With both off,
    the only current path is through the anti-parallel freewheel diodes,
    which clamp the phase voltage based on the current direction:

        v_k = -sign(i_k) · Vdc/2

    Positive i_k (current flowing out of the half-bridge) forces the bottom
    diode to conduct, pulling v_k to -Vdc/2; negative i_k turns on the top
    diode and pulls v_k to +Vdc/2. The result is a small, sign-dependent
    voltage error per phase that produces the textbook 5th and 7th harmonic
    distortion in i_abc and a low-amplitude torque ripple FOC's integrator
    eventually absorbs.

    State per leg: time elapsed since the most recent switch-state edge.
    """

    def __init__(self, cfg: InverterConfig) -> None:
        self.cfg = cfg
        self.Vdc = float(cfg.Vdc)
        self.t_dead = float(cfg.t_dead)
        self._pwm = PWMModulator(f_pwm=cfg.f_pwm, mode=cfg.pwm_mode)
        self._prev_s = [-1, -1, -1]  # force "edge" on first call
        self._t_since_edge = [math.inf, math.inf, math.inf]

    def step(
        self,
        v_a_ref: float,
        v_b_ref: float,
        v_c_ref: float,
        i_a: float,
        i_b: float,
        i_c: float,
        t: float,
        dt: float,
    ) -> tuple[float, float, float, int, int, int, float, float, float]:
        """One power-stage tick: PWM compare + dead-time-aware leg voltages.

        Returns (d_a, d_b, d_c, s_a, s_b, s_c, v_a, v_b, v_c).
        """
        d_a, d_b, d_c, s_a, s_b, s_c = self._pwm.step(v_a_ref, v_b_ref, v_c_ref, self.Vdc, t, dt)
        v_a, v_b, v_c = self._dead_time_step(s_a, s_b, s_c, i_a, i_b, i_c, dt)
        return d_a, d_b, d_c, s_a, s_b, s_c, v_a, v_b, v_c

    def _dead_time_step(self, s_a: int, s_b: int, s_c: int, i_a: float, i_b: float, i_c: float, dt: float) -> tuple[float, float, float]:
        s = (s_a, s_b, s_c)
        i = (i_a, i_b, i_c)
        v = [0.0, 0.0, 0.0]
        for k in range(3):
            if s[k] != self._prev_s[k]:
                self._t_since_edge[k] = 0.0
                self._prev_s[k] = s[k]
            if self.t_dead > 0.0 and self._t_since_edge[k] < self.t_dead:
                sign_i = 1.0 if i[k] > 0.0 else (-1.0 if i[k] < 0.0 else 0.0)
                v[k] = -sign_i * self.Vdc * 0.5
            else:
                v[k] = (s[k] - 0.5) * self.Vdc
            self._t_since_edge[k] += dt
        return v[0], v[1], v[2]


# ---------------------------------------------------------------------------
# LCL output filter (Python-side, between inverter terminals and motor)
# ---------------------------------------------------------------------------
class LCLFilter:
    """Per-phase LCL low-pass between inverter terminals and motor.

    Topology per phase (the motor's L_s is the LCL's second-stage inductor;
    we only add the inverter-side L_f + shunt C_f branch with series R_d
    for passive damping):

        v_inv ──L_f──┬── v_motor ──L_s── motor back-EMF
              i_1    │      i_motor
                    C_f
                     │
                    R_d
                     │
                     ─── (3-phase common; CM is rejected by the FMU's Clarke)

    Two state variables per phase: inductor current `i_Lf` (≡ ``i_1``, the
    inverter-side current) and capacitor voltage `v_Cf`. ODE (per phase):

        i_Lf' = (v_inv - v_Cf - R_d * (i_Lf - i_motor)) / L_f
        v_Cf' = (i_Lf - i_motor) / C_f
        v_motor = v_Cf + R_d * (i_Lf - i_motor)

    Integrated by forward Euler at the simulator's inner step `dt`. Stable
    at the default dt_sim = T_pwm / 20 = 1 µs (50 kHz carrier) for cutoffs
    >= a few kHz.

    Inverter-side current exposure (``i_1``). The state ``_i_Lf`` is the
    current flowing through ``L_f`` — equivalent to what a current sensor
    physically placed between the inverter FETs and the LCL would measure.
    In real industrial LCL drives that is the **standard sensor placement**
    and the **standard feedback signal for the inner current loop** (see
    Liserre et al., IEEE TIA 2005 — "inverter-side current control" / ICC).
    Exposed here as :py:attr:`i_Lf` so the :class:`Simulator` can hand it
    to the FOC controller in place of the motor-side current. Doing so
    eliminates the LCL resonance from the closed-loop transfer function and
    in particular eliminates the discrete-time anti-damping ``f_pwm/2``
    limit cycle that observer-driven AD produced (see memo.md §4).
    """

    def __init__(self, L_f: float, C_f: float, R_d: float) -> None:
        self.L_f = float(L_f)
        self.C_f = float(C_f)
        self.R_d = float(R_d)
        self._i_Lf = [0.0, 0.0, 0.0]
        self._v_Cf = [0.0, 0.0, 0.0]

    def reset(self) -> None:
        self._i_Lf = [0.0, 0.0, 0.0]
        self._v_Cf = [0.0, 0.0, 0.0]

    @property
    def i_Lf(self) -> tuple[float, float, float]:
        """Three-phase inverter-side current (= ``i_1`` in the LCL topology).

        Equivalent to the value a physical current sensor placed between the
        inverter and ``L_f`` would read. The simulator uses this as the FOC
        feedback signal when LCL is engaged, in place of the motor-side
        current. See class docstring for the architectural rationale.
        """
        return self._i_Lf[0], self._i_Lf[1], self._i_Lf[2]

    def step(self, v_inv_abc: tuple[float, float, float], i_motor_abc: tuple[float, float, float], dt: float) -> tuple[float, float, float]:
        v_motor = [0.0, 0.0, 0.0]
        for k in range(3):
            i_Lf = self._i_Lf[k]
            v_Cf = self._v_Cf[k]
            i_diff = i_Lf - i_motor_abc[k]
            v_drop = self.R_d * i_diff
            di_dt = (v_inv_abc[k] - v_Cf - v_drop) / self.L_f
            dv_dt = i_diff / self.C_f
            self._i_Lf[k] = i_Lf + di_dt * dt
            self._v_Cf[k] = v_Cf + dv_dt * dt
            v_motor[k] = v_Cf + v_drop
        return v_motor[0], v_motor[1], v_motor[2]


# ---------------------------------------------------------------------------
# PMSM abc model (FMU wrapper)
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
FMU_PATH = REPO_ROOT / "modelica" / "SlotlessPMSM_abc.fmu"


class PMSMAbcModel:
    """Thin wrapper around the OpenModelica SlotlessPMSM_abc.fmu.

    The FMU accepts (v_a, v_b, v_c, T_L) and exposes (i_a, i_b, i_c, theta_m,
    omega_m, T_e). Internally the model integrates in dq, driven by the true
    rotor angle — switching abc inputs are handled correctly as long as the
    co-simulation step dt is small enough (dt ≤ T_pwm/10 is the rule of thumb).

    `measure()` reads the FMU outputs at the current time.
    `step(v_a, v_b, v_c, T_L, dt)` writes inputs and advances one co-sim step.
    Call `close()` to release the FMU instance.
    """

    def __init__(self, motor: PmsmModel) -> None:
        if not FMU_PATH.exists():
            msg = f"FMU not found at {FMU_PATH}.\nBuild it first:  (cd modelica && omc build_fmu.mos)"
            raise SystemExit(msg)
        md = read_model_description(str(FMU_PATH))
        unzip_dir = extract(str(FMU_PATH))
        self.fmu = FMU2Slave(
            guid=md.guid,
            unzipDirectory=unzip_dir,
            modelIdentifier=md.coSimulation.modelIdentifier,
            instanceName="slotless_pmsm_abc",
        )
        self._vr = {v.name: v.valueReference for v in md.modelVariables}
        self.motor = motor
        self.p = motor.p

        self.fmu.instantiate()
        self.fmu.setupExperiment(startTime=0.0)
        self._apply_parameters()
        self.fmu.enterInitializationMode()
        self.fmu.exitInitializationMode()

        self._vr_in = [self._vr[n] for n in ("v_a", "v_b", "v_c", "T_L")]
        self._vr_out = [self._vr[n] for n in ("i_a", "i_b", "i_c", "theta_m", "omega_m", "T_e")]
        self._t = 0.0

    def _apply_parameters(self) -> None:
        m = self.motor
        real_params = {
            "R_s": m.R_s,
            "L_s": m.L_s,
            # FMU parameter name "psi_m" is fixed at the Modelica level
            # (see modelica/Alva.mo); the Python identifier is lambda_PM.
            "psi_m": m.lambda_PM,
            "J": m.J,
            "B": 1.0e-5,
            "torque_ripple_pct": m.torque_ripple_pct / 100.0,
            "torque_ripple_phase": 0.0,
        }
        int_params = {
            "p": m.p,
            "torque_ripple_order": 6,
        }
        self.fmu.setReal([self._vr[k] for k in real_params], list(real_params.values()))
        self.fmu.setInteger([self._vr[k] for k in int_params], list(int_params.values()))

    def measure(self) -> tuple[float, float, float, float, float, float]:
        """Returns (i_a, i_b, i_c, theta_m, omega_m, T_e) at the current time."""
        i_a, i_b, i_c, theta_m, omega_m, T_e = self.fmu.getReal(self._vr_out)
        return i_a, i_b, i_c, theta_m, omega_m, T_e

    def step(self, v_a: float, v_b: float, v_c: float, T_L: float, dt: float) -> None:
        self.fmu.setReal(self._vr_in, [v_a, v_b, v_c, T_L])
        self.fmu.doStep(currentCommunicationPoint=self._t, communicationStepSize=dt)
        self._t += dt

    def close(self) -> None:
        try:
            self.fmu.terminate()
        finally:
            self.fmu.freeInstance()
