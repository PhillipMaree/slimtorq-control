"""Drive the SlotlessPMSMPlant FMU from a Python-side FOC current loop.

Workflow:
  1. Pick a SlimTorq variant from the catalog (`motor_catalog.CATALOG`).
  2. Load the FMU (built by `omc modelica/build_fmu.mos`).
  3. Override FMU parameters with the catalog values + encoder settings.
  4. At each control tick Ts: read i_a/b/c and theta_m_meas from the FMU,
     run the full Clarke -> Park -> PI -> InvPark -> InvClarke pipeline, write
     v_a/b/c back, step the FMU.
  5. Log everything and plot.
"""

import math
from pathlib import Path

import click
import matplotlib.pyplot as plt
import numpy as np
from fmpy import extract, read_model_description
from fmpy.fmi2 import FMU2Slave

from foc import CurrentLoopFOC, FocConfig
from motor_catalog import CATALOG, MotorVariant

REPO_ROOT = Path(__file__).resolve().parent.parent
FMU_PATH = REPO_ROOT / "modelica" / "Plant.fmu"
FIGURES_DIR = REPO_ROOT / "figures"

TWO_PI = 2.0 * math.pi


def load_fmu() -> tuple[FMU2Slave, dict[str, int]]:
    md = read_model_description(str(FMU_PATH))
    unzip_dir = extract(str(FMU_PATH))
    fmu = FMU2Slave(
        guid=md.guid,
        unzipDirectory=unzip_dir,
        modelIdentifier=md.coSimulation.modelIdentifier,
        instanceName="slotless_pmsm_plant",
    )
    vr = {v.name: v.valueReference for v in md.modelVariables}
    return fmu, vr


def apply_parameters(fmu: FMU2Slave, vr: dict[str, int], variant: MotorVariant,
                     n_bits: int, theta_offset: float,
                     a1: float, k1: int, phi1: float,
                     a2: float, k2: int, phi2: float,
                     a3: float, k3: int, phi3: float,
                     j_load: float, b_load: float) -> None:
    real_params = {
        "Rs":           variant.Rs,
        "Ls":           variant.Ls,
        "psi_m":        variant.psi_m,
        "J":            variant.J + j_load,
        "B":            b_load,
        "T_load":       0.0,
        "theta_offset": theta_offset,
        "A1":           a1,
        "phi1":         phi1,
        "A2":           a2,
        "phi2":         phi2,
        "A3":           a3,
        "phi3":         phi3,
    }
    int_params = {
        "p":            variant.p,
        "n_bits":       n_bits,
        "k1":           k1,
        "k2":           k2,
        "k3":           k3,
    }
    fmu.setReal([vr[k] for k in real_params], list(real_params.values()))
    fmu.setInteger([vr[k] for k in int_params], list(int_params.values()))


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
# ---- Motor variant ---------------------------------------------------------
@click.option("--variant", "variant_name", type=click.Choice(sorted(CATALOG.keys())),
              default="STM-105-17-L-4Y", show_default=True,
              help="SlimTorq catalog part number (see motor_catalog.CATALOG).")
# ---- Encoder error overrides (defaults: Zettlex IND-MAX-100 22-bit, 3-harmonic) ----
@click.option("--n-bits", type=click.IntRange(10, 26), default=22, show_default=True,
              help="Encoder resolution [bits]. Inductive encoders typically 12-24.")
@click.option("--theta-offset", type=click.FloatRange(-math.pi, math.pi),
              default=0.0, show_default=True,
              help="Fixed mounting offset [rad].")
# Cyclic angle error: theta_err = sum_i A_i * sin(k_i*theta + phi_i)
# H1 = eccentricity once-per-rev (dominant), H2 = coil/target asymmetry, H3 = residual.
@click.option("--a1", "a1", type=click.FloatRange(0.0, 1e-3),
              default=2.4e-5, show_default=True,
              help="Cyclic amplitude, harmonic 1 [rad] (~+/-5 arcsec spec).")
@click.option("--k1", "k1", type=click.IntRange(1, 100),
              default=1, show_default=True,
              help="Cyclic harmonic order 1 (1 = eccentricity once-per-rev).")
@click.option("--phi1", "phi1", type=click.FloatRange(0.0, TWO_PI),
              default=0.0, show_default=True,
              help="Cyclic phase, harmonic 1 [rad].")
@click.option("--a2", "a2", type=click.FloatRange(0.0, 1e-3),
              default=5.0e-6, show_default=True,
              help="Cyclic amplitude, harmonic 2 [rad].")
@click.option("--k2", "k2", type=click.IntRange(1, 100),
              default=2, show_default=True,
              help="Cyclic harmonic order 2.")
@click.option("--phi2", "phi2", type=click.FloatRange(0.0, TWO_PI),
              default=0.0, show_default=True,
              help="Cyclic phase, harmonic 2 [rad].")
@click.option("--a3", "a3", type=click.FloatRange(0.0, 1e-3),
              default=1.0e-6, show_default=True,
              help="Cyclic amplitude, harmonic 3 [rad].")
@click.option("--k3", "k3", type=click.IntRange(1, 100),
              default=4, show_default=True,
              help="Cyclic harmonic order 3.")
@click.option("--phi3", "phi3", type=click.FloatRange(0.0, TWO_PI),
              default=0.0, show_default=True,
              help="Cyclic phase, harmonic 3 [rad].")
# ---- Sim / control configuration -------------------------------------------
@click.option("--t-end", type=click.FloatRange(1e-3, 1.0),
              default=0.05, show_default=True,
              help="Simulated time [s].")
@click.option("--ts-max", type=click.FloatRange(1e-6, 1e-4),
              default=20e-6, show_default=True,
              help="Nominal control-period upper bound [s] (1 MHz - 10 kHz).")
@click.option("--ts-ratio", type=click.IntRange(3, 20),
              default=5, show_default=True,
              help="Require Ts <= tau_e / ts_ratio for stable discrete PI.")
@click.option("--bw-hz", type=click.FloatRange(100.0, 5000.0),
              default=1000.0, show_default=True,
              help="Current-loop closed-loop bandwidth target [Hz].")
@click.option("--t-step-time", type=click.FloatRange(0.0, 1.0),
              default=0.005, show_default=True,
              help="Torque-setpoint step time [s] (must be < --t-end).")
@click.option("--t-step-frac", type=click.FloatRange(0.0, 1.5),
              default=0.25, show_default=True,
              help="Torque setpoint as a fraction of variant.te_cont_cat.")
# ---- Mechanical load (added to variant rotor inertia / friction) -----------
@click.option("--j-load", type=click.FloatRange(0.0, 1e-1),
              default=1.0e-3, show_default=True,
              help="Load inertia added to rotor inertia [kg.m^2].")
@click.option("--b-load", type=click.FloatRange(0.0, 1e-1),
              default=5.0e-3, show_default=True,
              help="Viscous friction coefficient [N.m.s/rad].")
def main(variant_name: str, n_bits: int, theta_offset: float,
         a1: float, k1: int, phi1: float,
         a2: float, k2: int, phi2: float,
         a3: float, k3: int, phi3: float,
         t_end: float, ts_max: float, ts_ratio: int, bw_hz: float,
         t_step_time: float, t_step_frac: float,
         j_load: float, b_load: float) -> None:
    """Drive the SlotlessPMSMPlant FMU from a Python-side FOC current loop."""
    if not FMU_PATH.exists():
        raise SystemExit(
            f"FMU not found at {FMU_PATH}.\n"
            f"Build it first:  (cd modelica && omc build_fmu.mos)"
        )
    if t_step_time >= t_end:
        raise click.BadParameter(
            f"--t-step-time ({t_step_time}) must be < --t-end ({t_end}).")

    variant = CATALOG[variant_name]
    tau_e = variant.Ls / variant.Rs
    Ts = min(ts_max, tau_e / ts_ratio)
    print(f"Variant: {variant.name}")
    print(f"  Rs={variant.Rs:.4g} Ohm  Ls={variant.Ls*1e6:.2f} uH  "
          f"psi_m={variant.psi_m*1e3:.3f} mWb  p={variant.p}  "
          f"J={variant.J*1e7:.2f} gcm^2")
    print(f"  tau_e = Ls/Rs = {tau_e*1e6:.1f} us   "
          f"Ts = {Ts*1e6:.2f} us ({1.0/Ts/1e3:.1f} kHz)")

    fmu, vr = load_fmu()
    fmu.instantiate()
    fmu.setupExperiment(startTime=0.0)
    apply_parameters(fmu, vr, variant,
                     n_bits=n_bits, theta_offset=theta_offset,
                     a1=a1, k1=k1, phi1=phi1,
                     a2=a2, k2=k2, phi2=phi2,
                     a3=a3, k3=k3, phi3=phi3,
                     j_load=j_load, b_load=b_load)
    fmu.enterInitializationMode()
    fmu.exitInitializationMode()

    foc = CurrentLoopFOC(FocConfig(
        Ts=Ts, bw_hz=bw_hz, Rs=variant.Rs, Ls=variant.Ls, psi_m=variant.psi_m,
        u_max=variant.rated_voltage, p=variant.p,
    ))

    T_target = t_step_frac * variant.te_cont_cat

    n_steps = int(round(t_end / Ts))
    log = {k: np.zeros(n_steps) for k in
           ("t", "T_ref", "id_ref", "iq_ref",
            "i_a", "i_b", "i_c",
            "id_meas", "iq_meas",
            "v_d", "v_q", "v_a", "v_b", "v_c",
            "theta_m_meas", "theta_m_true",
            "omega_m_true", "torque_true")}

    vr_in  = [vr[n] for n in ("v_a", "v_b", "v_c")]
    vr_out = [vr[n] for n in ("i_a", "i_b", "i_c", "theta_m_meas",
                              "theta_m_true", "omega_m_true", "torque_true")]

    t = 0.0
    for k in range(n_steps):
        i_a, i_b, i_c, theta_m_meas, theta_m_true, omega_m_true, torque_true = fmu.getReal(vr_out)
        T_ref = T_target if t >= t_step_time else 0.0
        v_a, v_b, v_c = foc.step(i_a, i_b, i_c, theta_m_meas, T_ref)
        fmu.setReal(vr_in, [v_a, v_b, v_c])
        fmu.doStep(currentCommunicationPoint=t, communicationStepSize=Ts)

        log["t"][k]            = t
        log["T_ref"][k]        = T_ref
        log["id_ref"][k]       = foc.id_ref
        log["iq_ref"][k]       = foc.iq_ref
        log["i_a"][k]          = i_a
        log["i_b"][k]          = i_b
        log["i_c"][k]          = i_c
        log["id_meas"][k]      = foc.id_m
        log["iq_meas"][k]      = foc.iq_m
        log["v_d"][k]          = foc.v_d
        log["v_q"][k]          = foc.v_q
        log["v_a"][k]          = v_a
        log["v_b"][k]          = v_b
        log["v_c"][k]          = v_c
        log["theta_m_meas"][k] = theta_m_meas
        log["theta_m_true"][k] = theta_m_true
        log["omega_m_true"][k] = omega_m_true
        log["torque_true"][k]  = torque_true
        t += Ts

    fmu.terminate()
    fmu.freeInstance()

    print(f"Final  id = {log['id_meas'][-1]: .4f} A   "
          f"iq = {log['iq_meas'][-1]: .4f} A   "
          f"iq* = {log['iq_ref'][-1]: .4f} A")
    print(f"Final  Te = {log['torque_true'][-1]: .4f} N.m   "
          f"T* = {log['T_ref'][-1]: .4f} N.m   "
          f"omega_m = {log['omega_m_true'][-1]: .2f} rad/s")

    plot(log, variant)


def plot(log: dict[str, np.ndarray], variant: MotorVariant) -> None:
    t_ms = log["t"] * 1e3
    fig, ax = plt.subplots(4, 1, sharex=True, figsize=(10, 9))

    ax[0].plot(t_ms, log["i_a"], label="i_a")
    ax[0].plot(t_ms, log["i_b"], label="i_b")
    ax[0].plot(t_ms, log["i_c"], label="i_c")
    ax[0].set_ylabel("phase current [A]")
    ax[0].grid(True); ax[0].legend(loc="upper right", ncol=3)

    ax[1].plot(t_ms, log["iq_ref"], "--", label="iq*")
    ax[1].plot(t_ms, log["iq_meas"], label="iq")
    ax[1].plot(t_ms, log["id_ref"], "--", label="id*")
    ax[1].plot(t_ms, log["id_meas"], label="id")
    ax[1].set_ylabel("dq current [A]")
    ax[1].grid(True); ax[1].legend(loc="upper right", ncol=4)

    ax[2].plot(t_ms, log["theta_m_true"], label="theta_m true")
    ax[2].plot(t_ms, log["theta_m_meas"], "--", label="theta_m meas")
    ax[2].set_ylabel("mech angle [rad]")
    ax[2].grid(True); ax[2].legend(loc="upper left")

    ax[3].plot(t_ms, log["T_ref"], "--", label="T*")
    ax[3].plot(t_ms, log["torque_true"], label="Te")
    ax[3].set_ylabel("torque [N.m]")
    ax[3].set_xlabel("time [ms]")
    ax[3].grid(True); ax[3].legend(loc="upper right")

    fig.suptitle(f"{variant.name}  |  Python FOC (Clarke->Park->PI->InvPark->InvClarke)"
                 f"  <->  OpenModelica abc-frame plant")
    fig.tight_layout()
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out = FIGURES_DIR / f"sim_result_{variant.name}.png"
    fig.savefig(out, dpi=120)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
