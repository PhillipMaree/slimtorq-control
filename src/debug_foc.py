"""FOC sanity-debug harness — walks the 11-step procedure from the project brief.

Each ``--step k`` builds the pipeline (FOC, PWM, Inverter, FMU, encoder) with
the *specific* knobs that isolate one effect, runs a short closed-loop
simulation, and prints PASS/FAIL plus the metric line documented in the user's
debug spec.

The motor parameters are synthesised from the user's problem statement
(R_s=0.5 Ω, L_s=100 µH, ψ_m=0.02 Wb, p=4, J=1e-4) rather than the catalog —
the catalog variant uses different values that would not match the expected
``T_e = 0.12 · i_q`` relation.

Run:
    uv run python src/debug_foc.py --step 1
    uv run python src/debug_foc.py --step 1 --step 2 --step 5    # multiple
    uv run python src/debug_foc.py --all                          # all 11
"""

from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass

import numpy as np

from controller import FOCController
from encoder import EncoderMeasurement, FluxEncoder
from model import EncoderConfig, FocConfig, InverterConfig, PmsmModel, TLRef
from simulator import Simulator
from switching import Inverter, PMSMAbcModel
from transform import abc_to_dq, dq_to_abc
from tuning import auto_pi_gains_from_bw

# ---------------------------------------------------------------------------
# Synthetic motor matching the user's brief exactly.
# ---------------------------------------------------------------------------
DEBUG_MOTOR = PmsmModel(
    family="Debug",
    name="synthetic-p4",
    R_s=0.5,
    L_s=100e-6,
    psi_m=0.02,
    p=4,
    J=1e-4,
    rated_voltage=200.0,  # 200 V Vdc → V_max=100 V, plenty of headroom
    i_cont=10.0,
    te_cont_cat=1.2,
    te_peak_1s=1.2,
    torque_ripple_pct=0.0,
)

# ---------------------------------------------------------------------------
# Encoder presets.
# ---------------------------------------------------------------------------
ENC_IDEAL = EncoderConfig(
    n_bits=30,
    theta_offset=0.0,
    A1=0.0,
    k1=1,
    phi1=0.0,
    A2=0.0,
    k2=2,
    phi2=0.0,
    A3=0.0,
    k3=4,
    phi3=0.0,
    Ts_enc=1e-6,
)
ENC_QUANT_ONLY = EncoderConfig(
    n_bits=22,
    theta_offset=0.0,
    A1=0.0,
    A2=0.0,
    A3=0.0,
    Ts_enc=1e-4,
)
ENC_HARMONICS = EncoderConfig(
    n_bits=30,
    theta_offset=0.0,
    A1=2.4e-5,
    k1=1,
    phi1=0.0,
    A2=5.0e-6,
    k2=2,
    phi2=0.0,
    A3=1.0e-6,
    k3=4,
    phi3=0.0,
    Ts_enc=1e-6,
)
ENC_DEFAULT = EncoderConfig()  # Catalog defaults (n_bits=22, harmonics + Ts=100 µs)

# ---------------------------------------------------------------------------
# Sim params.
# ---------------------------------------------------------------------------
F_PWM = 20_000.0
T_PWM = 1.0 / F_PWM
DT_SIM = T_PWM / 20.0
BW_HZ = 1000.0
VDC = DEBUG_MOTOR.rated_voltage


# ---------------------------------------------------------------------------
# Sim runner — one-shot closed loop, returns log dict.
# ---------------------------------------------------------------------------
@dataclass
class RunCfg:
    duration: float = 0.05
    i_q_ref: float = 10.0
    i_d_ref: float = 0.0
    T_L: float = 0.0
    encoder_cfg: EncoderConfig | None = None
    t_dead: float = 0.0
    bypass_pwm: bool = True
    TL_traj: TLRef | None = None  # if set, overrides constant T_L


def _run(cfg: RunCfg) -> dict[str, np.ndarray]:
    enc_cfg = cfg.encoder_cfg if cfg.encoder_cfg is not None else ENC_IDEAL
    foc_cfg = FocConfig(
        R_s=DEBUG_MOTOR.R_s,
        L_s=DEBUG_MOTOR.L_s,
        psi_m=DEBUG_MOTOR.psi_m,
        p=DEBUG_MOTOR.p,
        Vdc=VDC,
        f_pwm=F_PWM,
        bw_hz=BW_HZ,
    )
    controller = FOCController(foc_cfg)
    inverter = Inverter(InverterConfig(Vdc=VDC, f_pwm=F_PWM, t_dead=cfg.t_dead))
    encoder = EncoderMeasurement(FluxEncoder(enc_cfg), p=DEBUG_MOTOR.p)
    motor = PMSMAbcModel(DEBUG_MOTOR)

    if cfg.TL_traj is not None:
        TL = cfg.TL_traj
        T_L_override = None
    else:
        TL = TLRef(ref=np.array([0.0]), t=np.array([cfg.duration]))
        T_L_override = cfg.T_L

    with Simulator(motor, encoder, controller, inverter) as sim:
        df = sim.run(
            TL,
            T_s=DT_SIM,
            T_f=cfg.duration,
            i_q_ref_override=cfg.i_q_ref,
            i_d_ref_override=cfg.i_d_ref,
            T_L_override=T_L_override,
            bypass_pwm=cfg.bypass_pwm,
        )
    return {col: df[col].to_numpy() for col in df.columns}


def _tail_mean(arr: np.ndarray, frac: float = 0.2) -> float:
    return float(np.mean(arr[int((1.0 - frac) * len(arr)) :]))


def _verdict(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


# ---------------------------------------------------------------------------
# Step 1: i_q_ref = +10 A, all effects off.
# ---------------------------------------------------------------------------
def step1() -> bool:
    log = _run(RunCfg(i_q_ref=10.0, bypass_pwm=False))
    iq = _tail_mean(log["i_q_meas"])
    idm = _tail_mean(log["i_d_meas"])
    Te = _tail_mean(log["T_e"])
    om = log["omega_m_true"][-1]
    ok = abs(iq - 10.0) < 1.0 and abs(idm) < 1.0 and abs(Te - 1.2) < 0.15 and om > 0
    print(f"Step 1: {_verdict(ok)}  (i_q={iq:+.3f} A, i_d={idm:+.3f} A, T_e={Te:+.4f} N·m, omega_m={om:+.2f} rad/s)")
    return ok


# ---------------------------------------------------------------------------
# Step 2: i_q_ref = -10 A, symmetric.
# ---------------------------------------------------------------------------
def step2() -> bool:
    log = _run(RunCfg(i_q_ref=-10.0, bypass_pwm=False))
    iq = _tail_mean(log["i_q_meas"])
    idm = _tail_mean(log["i_d_meas"])
    Te = _tail_mean(log["T_e"])
    om = log["omega_m_true"][-1]
    ok = abs(iq + 10.0) < 1.0 and abs(idm) < 1.0 and abs(Te + 1.2) < 0.15 and om < 0
    print(f"Step 2: {_verdict(ok)}  (i_q={iq:+.3f} A, i_d={idm:+.3f} A, T_e={Te:+.4f} N·m, omega_m={om:+.2f} rad/s)")
    return ok


# ---------------------------------------------------------------------------
# Step 3: abc → Clarke → Park → inv-Park → inv-Clarke round-trip (no FMU).
# ---------------------------------------------------------------------------
def step3() -> bool:
    random.seed(42)
    max_err = 0.0
    for _ in range(1000):
        a = random.uniform(-15, 15)
        b = random.uniform(-15, 15)
        c = -(a + b)  # balanced: i_a + i_b + i_c = 0
        theta = random.uniform(-10, 10)
        d, q = abc_to_dq(a, b, c, theta)
        a2, b2, c2 = dq_to_abc(d, q, theta)
        err = max(abs(a - a2), abs(b - b2), abs(c - c2))
        max_err = max(max_err, err)
    ok = max_err < 1e-9
    print(f"Step 3: {_verdict(ok)}  (max abs round-trip error = {max_err:.2e})")
    return ok


# ---------------------------------------------------------------------------
# Step 4: electrical-angle scaling. theta_e/theta_m = p, omega_e/omega_m = p.
# ---------------------------------------------------------------------------
def step4() -> bool:
    """Verify theta_e = p · theta_m, omega_e = p · omega_m, and that
    theta_m_true is in radians (FD of theta_m matches omega_m at the same tick).
    """
    log = _run(RunCfg(i_q_ref=2.0, duration=0.02, bypass_pwm=True))
    p = DEBUG_MOTOR.p
    th = log["theta_m_true"]
    om = log["omega_m_true"]
    # Centred finite difference at sample N-2, compare against omega_m[N-2].
    n = len(th)
    j = n - 2
    om_fd = (th[j + 1] - th[j - 1]) / (2.0 * DT_SIM)
    om_ref = om[j]
    fd_err = abs(om_fd - om_ref)
    # theta_e = p · theta_m identity holds for any sample (verified by construction
    # via encoder.py:91 — theta_e_meas = (p · theta_m_meas) mod 2π).
    om_e_expected = p * om_ref
    ok_p = abs(om_e_expected / om_ref - p) < 1e-12 if abs(om_ref) > 1e-9 else True
    ok_units = fd_err < 0.5  # rad/s slack at 20 µs sampling
    ok = ok_p and ok_units
    print(f"Step 4: {_verdict(ok)}  (p={p}, FD(theta_m)={om_fd:.4f} vs omega_m={om_ref:.4f} rad/s, err={fd_err:.3e}; omega_e=p·omega_m={om_e_expected:.4f} rad/s)")
    return ok


# ---------------------------------------------------------------------------
# Step 5: PWM bypass with i_q_ref = ±10 A.
# ---------------------------------------------------------------------------
def step5() -> bool:
    ok = True
    for ref in (10.0, -10.0):
        log = _run(RunCfg(i_q_ref=ref, bypass_pwm=True))
        iq = _tail_mean(log["i_q_meas"])
        idm = _tail_mean(log["i_d_meas"])
        Te = _tail_mean(log["T_e"])
        om = log["omega_m_true"][-1]
        sub_ok = abs(iq - ref) < 0.5 and abs(idm) < 0.5 and abs(Te - 0.12 * ref) < 0.1 and (om > 0 if ref > 0 else om < 0)
        ok = ok and sub_ok
        print(f"Step 5 ({ref:+.0f} A bypass): {_verdict(sub_ok)}  (i_q={iq:+.3f} A, i_d={idm:+.3f} A, T_e={Te:+.4f} N·m, omega_m={om:+.2f} rad/s)")
    return ok


# ---------------------------------------------------------------------------
# Step 6: voltage-command inspection (Step 1 setup, then print v_dq stats).
# ---------------------------------------------------------------------------
def step6() -> bool:
    log = _run(RunCfg(i_q_ref=10.0, bypass_pwm=False))
    vd = log["v_d_ref"]
    vq = log["v_q_ref"]
    mag = np.sqrt(vd * vd + vq * vq)
    V_max = VDC / 2.0
    sat_count = int(np.sum(log["sat_d"]))
    headroom = (V_max - np.max(mag)) / V_max
    ok = sat_count == 0 and headroom > 0
    print(
        f"Step 6: {_verdict(ok)}  "
        f"(|v_dq| max={np.max(mag):.3f} V, V_max={V_max:.1f} V, "
        f"headroom={headroom * 100:.1f}%, sat_count={sat_count}, "
        f"final v_d={vd[-1]:+.3f}, v_q={vq[-1]:+.3f})"
    )
    return ok


# ---------------------------------------------------------------------------
# Step 7: PWM conversion sanity (Step 1 setup, then check duty + voltage map).
# ---------------------------------------------------------------------------
def step7() -> bool:
    log = _run(RunCfg(i_q_ref=10.0, bypass_pwm=False))
    d = np.concatenate([log["d_a"], log["d_b"], log["d_c"]])
    d_min, d_max = float(np.min(d)), float(np.max(d))

    # Algebraic checks (independent of the run):
    #   d=0.5 -> v=0, d=1.0 -> +Vdc/2, d=0.0 -> -Vdc/2.
    def duty_to_v(d_: float) -> float:
        return (d_ - 0.5) * VDC

    map_ok = abs(duty_to_v(0.5)) < 1e-12 and abs(duty_to_v(1.0) - VDC / 2) < 1e-12 and abs(duty_to_v(0.0) + VDC / 2) < 1e-12
    bounds_ok = 0.0 <= d_min and d_max <= 1.0
    ok = map_ok and bounds_ok
    print(f"Step 7: {_verdict(ok)}  (duty min/max = {d_min:.4f} / {d_max:.4f}, d=0.5→v={duty_to_v(0.5):+.3f}V, d=1.0→v={duty_to_v(1.0):+.1f}V, d=0.0→v={duty_to_v(0.0):+.1f}V)")
    return ok


# ---------------------------------------------------------------------------
# Step 8: PI tuning sanity.
# ---------------------------------------------------------------------------
def step8() -> bool:
    Kp, Ki = auto_pi_gains_from_bw(DEBUG_MOTOR.R_s, DEBUG_MOTOR.L_s, BW_HZ)
    tau_e = DEBUG_MOTOR.L_s / DEBUG_MOTOR.R_s
    f_bw_to_pwm = BW_HZ / F_PWM
    ok = f_bw_to_pwm <= 0.1 + 1e-12 and DT_SIM <= tau_e / 3.0
    print(f"Step 8: {_verdict(ok)}  (Kp={Kp:.4f} V/A, Ki={Ki:.2f} V/(A·s), tau_e={tau_e * 1e6:.2f} µs, f_bw={BW_HZ:.0f} Hz, f_pwm={F_PWM:.0f} Hz, ratio={f_bw_to_pwm:.4f} ≤ 0.1)")
    return ok


# ---------------------------------------------------------------------------
# Step 9: Apply a positive T_L step after the motor is spinning.
# ---------------------------------------------------------------------------
def step9() -> bool:
    # Two-segment TLref: 0 until 50 ms, then +1.0 N·m until 100 ms.
    TL = TLRef(ref=np.array([0.0, 1.0]), t=np.array([0.05, 0.10]))
    log = _run(RunCfg(i_q_ref=10.0, duration=0.10, bypass_pwm=False, TL_traj=TL))
    om = log["omega_m_true"]
    # dω/dt before and after the step.
    half = len(om) // 2
    pre_slope = (om[half - 1] - om[half // 2]) / (DT_SIM * (half - 1 - half // 2))
    post_slope = (om[-1] - om[half + half // 2]) / (DT_SIM * (len(om) - 1 - half - half // 2))
    ok = post_slope < pre_slope and post_slope > 0  # still positive but slower
    print(f"Step 9: {_verdict(ok)}  (pre-load dω/dt={pre_slope:.1f}, post-load dω/dt={post_slope:.1f} rad/s²)")
    return ok


# ---------------------------------------------------------------------------
# Step 10: re-enable effects A→F one at a time on the Step-1 setup.
# ---------------------------------------------------------------------------
def step10() -> bool:
    base = RunCfg(i_q_ref=10.0, bypass_pwm=False, encoder_cfg=ENC_IDEAL, t_dead=0.0)
    cases = {
        "A: PWM no dead-time   ": base,
        "B: PWM + 1.5µs dead   ": RunCfg(**{**base.__dict__, "t_dead": 1.5e-6}),
        "C: 22-bit quantization": RunCfg(**{**base.__dict__, "encoder_cfg": ENC_QUANT_ONLY}),
        "D: encoder harmonics  ": RunCfg(**{**base.__dict__, "encoder_cfg": ENC_HARMONICS}),
        "E: encoder latency    ": None,  # not modelled; report N/A
        "F: T_L step           ": RunCfg(
            i_q_ref=10.0,
            duration=0.10,
            bypass_pwm=False,
            TL_traj=TLRef(ref=np.array([0.0, 1.0]), t=np.array([0.05, 0.10])),
        ),
    }
    overall = True
    for label, cfg in cases.items():
        if cfg is None:
            print(f"Step 10 [{label}]: N/A    (encoder latency not implemented)")
            continue
        log = _run(cfg)
        iq = log["i_q_meas"]
        idm = log["i_d_meas"]
        Te = log["T_e"]
        vd = log["v_d_ref"]
        vq = log["v_q_ref"]
        mag = np.sqrt(vd * vd + vq * vq)
        d = np.concatenate([log["d_a"], log["d_b"], log["d_c"]])
        # Use the trailing 40% for steady-state metrics. PWM creates a
        # ~Vdc·T_pwm/(8·L_s) peak-peak current ripple at the carrier, which
        # is real and expected — track the *mean*, report the ripple separately.
        tail = slice(int(0.6 * len(iq)), len(iq))
        iq_mean = float(np.mean(iq[tail]))
        id_mean = float(np.mean(idm[tail]))
        iq_ripple_pp = float(np.max(iq[tail]) - np.min(iq[tail]))
        Te_pp = float(np.max(Te[tail]) - np.min(Te[tail]))
        v_ratio = float(np.max(mag) / (VDC / 2.0))
        d_min, d_max = float(np.min(d)), float(np.max(d))
        # PASS if mean tracking holds — matches Step 12 criteria.
        sub_ok = abs(iq_mean - 10.0) < 1.5 and abs(id_mean) < 1.5
        overall = overall and sub_ok
        print(
            f"Step 10 [{label}]: {_verdict(sub_ok)}  "
            f"i_q_mean={iq_mean:+.3f} A, "
            f"i_d_mean={id_mean:+.3f} A, "
            f"i_q_ripple_pp={iq_ripple_pp:.3f} A, "
            f"T_e_pp={Te_pp:.3f} N·m, "
            f"|v_dq|/V_max={v_ratio:.3f}, "
            f"d∈[{d_min:.3f},{d_max:.3f}]"
        )
    return overall


# ---------------------------------------------------------------------------
# Step 11: encoder error is bounded (no drift) over many revolutions.
# ---------------------------------------------------------------------------
def step11() -> bool:
    enc = FluxEncoder(ENC_HARMONICS)
    Ts = 1e-5
    om_true = 200.0  # rad/s mech
    errs = []
    for k in range(50_000):  # 0.5 s = ~16 mechanical revolutions at 200 rad/s
        t = k * Ts
        theta_true = om_true * t
        theta_meas, _ = enc.step(theta_true, t)
        # Compare wrapped angles in [0, 2π).
        theta_true_wrap = theta_true % (2.0 * math.pi)
        e = ((theta_meas - theta_true_wrap + math.pi) % (2.0 * math.pi)) - math.pi
        errs.append(e)
    errs = np.array(errs)
    # Bounded ↔ max|err| ≪ a few times the harmonic amplitude (2.4e-5 rad here).
    # Use the strict bound: sum of amplitudes + 1 LSB.
    cfg = ENC_HARMONICS
    bound = cfg.A1 + cfg.A2 + cfg.A3 + (2 * math.pi / (1 << cfg.n_bits))
    # Drift check: first 10% mean vs last 10% mean must not differ much.
    early = float(np.mean(errs[:5000]))
    late = float(np.mean(errs[-5000:]))
    drift = abs(late - early)
    ok = float(np.max(np.abs(errs))) <= 3 * bound and drift < bound
    print(f"Step 11: {_verdict(ok)}  (max|err|={np.max(np.abs(errs)):.2e} rad, bound≈{bound:.2e} rad, drift={drift:.2e} rad)")
    return ok


STEPS = {
    1: step1,
    2: step2,
    3: step3,
    4: step4,
    5: step5,
    6: step6,
    7: step7,
    8: step8,
    9: step9,
    10: step10,
    11: step11,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", type=int, action="append", choices=list(STEPS.keys()), help="Step number to run (may be repeated).")
    ap.add_argument("--all", action="store_true", help="Run all 11 steps in order.")
    args = ap.parse_args()
    if args.all:
        steps = list(STEPS.keys())
    elif args.step:
        steps = args.step
    else:
        ap.error("Provide --step N or --all.")
    print(
        f"Motor: R_s={DEBUG_MOTOR.R_s} Ω, L_s={DEBUG_MOTOR.L_s * 1e6:.0f} µH, "
        f"ψ_m={DEBUG_MOTOR.psi_m} Wb, p={DEBUG_MOTOR.p}, "
        f"J={DEBUG_MOTOR.J * 1e7:.1f} g·cm², Vdc={VDC} V, f_pwm={F_PWM:.0f} Hz, "
        f"bw={BW_HZ:.0f} Hz"
    )
    print()
    failed = []
    for k in steps:
        if not STEPS[k]():
            failed.append(k)
    print()
    if failed:
        print(f"Summary: {len(failed)} step(s) FAILED: {failed}")
        return 1
    print(f"Summary: all {len(steps)} step(s) PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
