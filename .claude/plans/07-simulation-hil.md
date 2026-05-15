# Module 7 — Simulation & HIL (Standing in for Real Motors)

**Goal:** Since you won't have access to real Alva motors before the interview, build a simulation that's good enough to demo control loops, tuning workflows, and protocol interactions. The slimtorq-control capstone hinges on this.

**Time:** 6–10 hours
**Prereq:** Modules 1, 2.

---

## 7.1 Levels of motor modeling

| Level | Captures | When to use |
|---|---|---|
| **Ideal d-q electrical** | R, L, λ_PM, J, B. No PWM, no current sensors, no nonlinearities. | Algorithm development, gain math. |
| **PWM + inverter** | Adds switching, dead time, DC bus sag. | Validating digital controller. |
| **Saturation & cross-coupling** | L(i_d, i_q) maps, saturation tables. | High-fidelity at high current. |
| **Thermal** | Loss models, thermal RC network. | Long-duration / derating studies. |
| **Mechanical** | Multi-body, compliant couplings, gearbox backlash. | Resonance and FF design. |
| **Acoustic / vibration** | NVH considerations. | Premium products. |

For your prep, build levels 1 and 2 in Python. Level 3 is a stretch goal.

---

## 7.2 d-q PMSM model (the workhorse)

State variables: `i_d, i_q, ω_m, θ_m`.

ODEs (per-unit or SI):
```
di_d/dt = (v_d − R_s·i_d + ω_e·L_q·i_q) / L_d
di_q/dt = (v_q − R_s·i_q − ω_e·L_d·i_d − ω_e·λ_PM) / L_q
dω_m/dt = (T_e − T_load − B·ω_m) / J
dθ_m/dt = ω_m
T_e = (3/2) · p · (λ_PM·i_q + (L_d − L_q)·i_d·i_q)
ω_e = p · ω_m
```

Discretize with forward Euler at `Δt = 1/f_sim`, where `f_sim ≥ 10 × f_sw`.

**Numerical tip:** if you simulate a high-bandwidth current loop, Euler is fine. For long thermal runs, use RK4 or scipy's `solve_ivp`.

---

## 7.3 Induction motor model

State variables: `i_sd, i_sq, ψ_rd, ψ_rq, ω_m, θ_m`. Rotor-flux-oriented d-q form is the cleanest.

(Defer until after PMSM is working — induction model is the most common interview "do you understand the difference" probe rather than something you need running in sim.)

---

## 7.4 Inverter + PWM model

Two options:

- **Average model:** assume the inverter output equals the commanded voltage. Fast simulation, no switching ripple, no dead-time effects. Use this for control loop development.
- **Switched model:** simulate the six switching states explicitly with `f_sw = 10–20 kHz`. Captures ripple and dead time. Use to validate sampling timing and dead-time compensation.

For your slimtorq prototype, start with average. Add switched later if you want to demo dead-time effects.

---

## 7.5 The simulation/control loop separation

A real drive runs the control loop on a microcontroller at fixed cadence (say 10 kHz). Your Python sim should mimic this:

```
for k in range(N):
    # 1. Sample feedback (with optional noise/quantization)
    θ_meas = encoder_model(θ)
    i_abc_meas = sensor_model(i_abc, noise, offset)

    # 2. Control update (called every Ts_ctrl)
    if k % (Ts_ctrl / Ts_sim) == 0:
        v_d_cmd, v_q_cmd = foc_step(i_d_meas, i_q_meas, ω_meas, θ_meas, refs)

    # 3. Plant update (every Ts_sim)
    v_abc = inverse_park_clarke(v_d_cmd, v_q_cmd, θ_e)
    di_dt = motor_ode(i, v, ω, θ)
    i += di_dt * Ts_sim
    ω += dω_dt * Ts_sim
    θ += ω * Ts_sim
```

This decoupling is what makes the sim "feel like" a drive and forces you to think about sampling, jitter, computational delay — exactly the skills tested in the interview.

---

## 7.6 HIL platforms — namedrop & understand at high level

You probably won't use these in prep, but you should be able to discuss them.

- **Typhoon HIL:** GPU/FPGA-based, motor-control-specialized, microsecond switching simulation. Industry favorite for drive testing.
- **dSPACE SCALEXIO:** automotive-leaning, broad ecosystem.
- **OPAL-RT:** academic + industrial, very flexible.
- **Speedgoat:** integrates with Simulink Real-Time.
- **NI VeriStand + PXI:** general-purpose RT testing platform.

**HIL workflow:**
1. Build motor + power-electronics model in vendor tooling.
2. Compile to real-time target (FPGA or RT CPU).
3. Connect actual drive's analog/digital I/O to the HIL I/O.
4. Drive thinks it's connected to a real motor; HIL provides feedback in real time.
5. Run automated test suites — fault injection, parameter sweeps, regression on every firmware build.

**Why a startup like Alva might use HIL:** test new firmware versions against a battery of motor variants without burning hardware, run faults you can't safely run on a bench, scale CI/CD into firmware deployment.

---

## 7.7 Co-simulation possibility

If you want extra credit: drive your Python motor sim from an external master via a fake EtherCAT-like UDP interface. The master sends torque commands; the sim returns position/velocity/current. This is the architecture for [09-project.md](09-project.md).

This essentially makes your Python sim a poor-man's HIL — useful for the slimtorq capstone.

---

## 7.8 Verification: does the sim believe its own physics?

Sanity checks before trusting any tuning result:

- **Torque-speed consistency:** at steady state with no load, `T_e − B·ω = 0` → `ω = T_e / B`. Check.
- **Back-EMF:** at constant ω with `i_d = i_q = 0`, `v_q` should equal `ω_e · λ_PM`. Plot to confirm.
- **Cross-coupling:** disable FF decoupling. Step `i_d`, watch `i_q` perturb. Re-enable, watch it stop.
- **Closed-loop bandwidth:** sweep frequency on `i_q*`, plot Bode. Should match design `ω_bw_i`.

---

## 7.9 Tooling suggestions

- **Python:** numpy + scipy for math, matplotlib for offline plots, **PyQt5/6** or **Plotly Dash** for live UI, **asyncio** for I/O.
- **MATLAB/Simulink:** if you have a license, Motor Control Blockset is the industry tool. Worth a few hours' familiarity even if you build the prototype in Python.
- **Modelica / OpenModelica:** free, equation-based, great for multi-physics. Overkill for prep.
- **PLECS:** drive-engineering favorite, license needed. Free for academic use.

Pick **Python** for slimtorq — interviewers will look at the code.

---

## 7.10 Exit criteria

- [ ] Have a working PMSM d-q sim in Python.
- [ ] FOC current loop running in sim, with measurable bandwidth.
- [ ] Speed loop on top, with verified inertia-based gains.
- [ ] Can demonstrate cross-coupling on/off and FW kicking in.
- [ ] Can discuss HIL platforms and the workflow they enable.
