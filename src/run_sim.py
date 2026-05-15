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

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from fmpy import extract, read_model_description
from fmpy.fmi2 import FMU2Slave

from foc import CurrentLoopFOC, FocConfig
from motor_catalog import CATALOG, MotorVariant

REPO_ROOT = Path(__file__).resolve().parent.parent
FMU_PATH = REPO_ROOT / "modelica" / "SlotlessPMSMPlant.fmu"
FIGURES_DIR = REPO_ROOT / "figures"

# ---- Configuration ----------------------------------------------------------
VARIANT_NAME = "STM-105-17-L-4Y"      # see motor_catalog.CATALOG for options

# Encoder error overrides (defaults: ideal 22-bit, no offset, no cyclic error).
N_BITS        = 22
THETA_OFFSET  = 0.0     # rad
CYCLIC_AMP    = 0.0     # rad  (Zettlex IND-MAX-100: ~2.4e-5 for +/-5 arcsec)
CYCLIC_ORDER  = 1       # 1: eccentricity once-per-rev; p: per electrical cycle
CYCLIC_PHASE  = 0.0     # rad

# Sim / control configuration
T_END    = 0.05         # simulated time [s]
TS_MAX   = 20e-6        # nominal control period upper bound [s] (50 kHz)
TS_RATIO = 5            # require Ts <= tau_e / TS_RATIO for stable discrete PI
                        # (SlimTorq motors have tau_e ~ 9-60 us, so the actual
                        # Ts may need to drop to <5 us for the smallest variants)
BW_HZ  = 1000.0         # current-loop bandwidth target [Hz]
ID_REF = 0.0            # surface-PM: id* = 0
IQ_STEP_TIME = 0.005    # iq* step at t = 5 ms
IQ_STEP_FRAC = 0.25     # iq* step as a fraction of variant.i_cont

# Mechanical load (added to rotor inertia / friction). Without these the
# rotor accelerates ballistically and the iq step looks like an open-loop
# spin-up. Pick values that keep the mechanical bandwidth well below the
# current-loop bandwidth so the current loop is the visible dynamic.
J_LOAD = 1.0e-3         # kg.m^2  (a typical load -- dominates rotor inertia)
B_LOAD = 5.0e-3         # N.m.s/rad  viscous friction


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


def apply_parameters(fmu: FMU2Slave, vr: dict[str, int],
                     variant: MotorVariant) -> None:
    real_params = {
        "Rs":           variant.Rs,
        "Ls":           variant.Ls,
        "psi_m":        variant.psi_m,
        "J":            variant.J + J_LOAD,
        "B":            B_LOAD,
        "T_load":       0.0,
        "theta_offset": THETA_OFFSET,
        "cyclic_amp":   CYCLIC_AMP,
        "cyclic_phase": CYCLIC_PHASE,
    }
    int_params = {
        "p":            variant.p,
        "n_bits":       N_BITS,
        "cyclic_order": CYCLIC_ORDER,
    }
    fmu.setReal([vr[k] for k in real_params], list(real_params.values()))
    fmu.setInteger([vr[k] for k in int_params], list(int_params.values()))


def main() -> None:
    if not FMU_PATH.exists():
        raise SystemExit(
            f"FMU not found at {FMU_PATH}.\n"
            f"Build it first:  (cd modelica && omc build_fmu.mos)"
        )

    variant = CATALOG[VARIANT_NAME]
    tau_e = variant.Ls / variant.Rs
    Ts = min(TS_MAX, tau_e / TS_RATIO)
    print(f"Variant: {variant.name}")
    print(f"  Rs={variant.Rs:.4g} Ohm  Ls={variant.Ls*1e6:.2f} uH  "
          f"psi_m={variant.psi_m*1e3:.3f} mWb  p={variant.p}  "
          f"J={variant.J*1e7:.2f} gcm^2")
    print(f"  tau_e = Ls/Rs = {tau_e*1e6:.1f} us   "
          f"Ts = {Ts*1e6:.2f} us ({1.0/Ts/1e3:.1f} kHz)")

    fmu, vr = load_fmu()
    fmu.instantiate()
    fmu.setupExperiment(startTime=0.0)
    apply_parameters(fmu, vr, variant)
    fmu.enterInitializationMode()
    fmu.exitInitializationMode()

    foc = CurrentLoopFOC(FocConfig(
        Ts=Ts, bw_hz=BW_HZ, Rs=variant.Rs, Ls=variant.Ls,
        u_max=variant.rated_voltage, p=variant.p,
    ))

    iq_target = IQ_STEP_FRAC * variant.i_cont

    n_steps = int(round(T_END / Ts))
    log = {k: np.zeros(n_steps) for k in
           ("t", "id_ref", "iq_ref",
            "i_a", "i_b", "i_c",
            "id_meas", "iq_meas",
            "ud", "uq", "v_a", "v_b", "v_c",
            "theta_m_meas", "theta_m_true",
            "omega_m", "Te")}

    vr_in  = [vr[n] for n in ("v_a", "v_b", "v_c")]
    vr_out = [vr[n] for n in ("i_a", "i_b", "i_c", "theta_m_meas",
                              "theta_m_true", "omega_m", "Te")]

    t = 0.0
    for k in range(n_steps):
        i_a, i_b, i_c, theta_m_meas, theta_m_true, omega_m, Te = fmu.getReal(vr_out)
        iq_ref = iq_target if t >= IQ_STEP_TIME else 0.0
        v_a, v_b, v_c = foc.step(i_a, i_b, i_c, theta_m_meas, ID_REF, iq_ref)
        fmu.setReal(vr_in, [v_a, v_b, v_c])
        fmu.doStep(currentCommunicationPoint=t, communicationStepSize=Ts)

        log["t"][k]            = t
        log["id_ref"][k]       = ID_REF
        log["iq_ref"][k]       = iq_ref
        log["i_a"][k]          = i_a
        log["i_b"][k]          = i_b
        log["i_c"][k]          = i_c
        log["id_meas"][k]      = foc.id_m
        log["iq_meas"][k]      = foc.iq_m
        log["ud"][k]           = foc.ud
        log["uq"][k]           = foc.uq
        log["v_a"][k]          = v_a
        log["v_b"][k]          = v_b
        log["v_c"][k]          = v_c
        log["theta_m_meas"][k] = theta_m_meas
        log["theta_m_true"][k] = theta_m_true
        log["omega_m"][k]      = omega_m
        log["Te"][k]           = Te
        t += Ts

    fmu.terminate()
    fmu.freeInstance()

    print(f"Final  id = {log['id_meas'][-1]: .4f} A   "
          f"iq = {log['iq_meas'][-1]: .4f} A")
    print(f"Final  Te = {log['Te'][-1]: .4f} N.m   "
          f"omega_m = {log['omega_m'][-1]: .2f} rad/s")

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

    ax[3].plot(t_ms, log["Te"], label="Te")
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
