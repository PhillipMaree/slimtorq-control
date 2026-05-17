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

from model import InverterConfig, PmsmModel


# ---------------------------------------------------------------------------
# PWM modulator
# ---------------------------------------------------------------------------
class PWMModulator:
    """Centered sinusoidal PWM with a unipolar triangular carrier.

    Duty conversion:
        d_k = clip(0.5 + v_k_ref / Vdc, 0, 1)

    Carrier: a triangle of period T_pwm = 1/f_pwm rising 0 → 1 over [0, T/2)
    and falling 1 → 0 over [T/2, T). Switch state s_k = 1 iff d_k > carrier.

    The modulator is stateless across `step()` calls — it derives the carrier
    phase from absolute time `t` so the simulator can call it at any dt_sim.
    """

    def __init__(self, f_pwm: float) -> None:
        self.f_pwm = f_pwm
        self.T_pwm = 1.0 / f_pwm

    def _carrier(self, t: float) -> float:
        phase = (t / self.T_pwm) % 1.0  # in [0, 1)
        # Triangle peak=1 at phase=0.5, valley=0 at phase=0 and 1.
        return 1.0 - 2.0 * abs(phase - 0.5)

    def step(self, v_a_ref: float, v_b_ref: float, v_c_ref: float, Vdc: float, t: float, dt: float) -> tuple[float, float, float, int, int, int]:
        d_a = max(0.0, min(1.0, 0.5 + v_a_ref / Vdc))
        d_b = max(0.0, min(1.0, 0.5 + v_b_ref / Vdc))
        d_c = max(0.0, min(1.0, 0.5 + v_c_ref / Vdc))
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
        self._pwm = PWMModulator(f_pwm=cfg.f_pwm)
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
            "psi_m": m.psi_m,
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
