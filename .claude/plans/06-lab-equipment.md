# Module 6 — Lab Equipment & Measurement

**Goal:** Be the engineer who knows which probe to pick up and what to look at on the screen. The job description specifically calls out oscilloscopes and power analyzers — be ready to discuss both.

**Time:** 2–4 hours
**Prereq:** None.

---

## 6.1 Oscilloscope on switched power systems

### Probes — pick the right one

| Signal | Probe | Why |
|---|---|---|
| Logic / gate drive | 10× passive | Cheap, fine for <100 MHz, single-ended |
| Floating gate (high-side) | Differential active | Avoids shorting via scope ground |
| Phase-to-phase / bus | Differential active or HV diff | No common reference; ground would short |
| AC line voltage | High-voltage differential (1000 V CAT III) | Safety + isolation |
| Phase current | Current probe (Hall, AC/DC) or Rogowski | Non-contact; Rogowski for very high BW AC |
| Logic timing | MSO digital channels or 10× passive | Capture state machine events |

**Never** put a ground-referenced passive probe across an inverter phase or bus — you will short the bus through scope earth.

### Settings checklist
- 12-bit mode (HD/HiRes) for analog if scope supports it — much better for low-amplitude current.
- High-Z input for differential probes; 50 Ω only for matched RF.
- Trigger on a unique event (PWM update, controlword bit, fault flag) rather than free-running.
- Use **scope math channels:** `V_ab = V_a − V_b`, `P = V·I`, FFT for harmonics.
- Persistence + infinite color for catching intermittent glitches.

### Measurements you'll do often
- PWM duty cycle and dead time.
- Phase current shape (look for distortion at zero crossings → dead-time effect or current sensor offset).
- Back-EMF on a free-spinning motor.
- Encoder A/B/Z signal integrity.
- Bus ripple under load (sizing DC link cap).
- IGBT/MOSFET turn-on/turn-off slope (dv/dt, di/dt).

### Common gotchas
- **Ground loops** between scope earth and DUT earth → kill them by using differential probes or by floating one side (carefully, with isolation transformer or battery scope; never just lift safety ground).
- **Common-mode rejection** of differential probes drops at high frequency — read the datasheet.
- **Current probe bandwidth** is often much lower than voltage probe BW. Don't expect a 100 MHz current probe.
- **Skin effect / probe loop area:** large loop in your current sense lead picks up dv/dt noise.

---

## 6.2 Power analyzer

What sets a power analyzer apart from a scope-with-math:
- Wide dynamic range (mW to kW) with calibrated accuracy.
- Direct measurement of harmonics, true RMS, power factor, efficiency.
- Multi-input (3-phase voltage + 3-phase current + DC bus = 6+ channels) with simultaneous sampling.
- Typically integrates over a configurable window aligned to fundamental period.

### Typical measurements

- **Motor efficiency:** `η = P_mech / P_elec` where P_mech = `T · ω` (need a dyno or torque transducer) and P_elec is computed by the analyzer from V,I on the motor side.
- **Drive efficiency:** `P_motor / P_dc_bus`. Reveals inverter losses (conduction, switching, gate-drive).
- **THD (total harmonic distortion)** on phase current — sanity check on SVM and dead-time compensation.
- **Power factor and displacement angle** — relevant for line-side analysis or PFC stages.
- **dq decomposition** if the analyzer supports it (some Yokogawa WT5000s do).

### Brands / models you should namedrop
- **Yokogawa WT-series** (WT1800, WT5000) — industry standard.
- **HIOKI PW3390 / PW8001** — competitive Japanese alternative.
- **Tektronix PA3000 / PA1000** — entry-level.

---

## 6.3 Dynamometer (dyno) basics

Even if not a current focus, know the concept:

- **Load type:**
  - Eddy-current brake — absorbs power, easy.
  - Hysteresis brake — smoother, lower torque ranges.
  - **Active dyno** (back-to-back motor as generator) — bidirectional, captures torque/speed, lets DUT motor regenerate. Standard for serious testing.
- **Torque transducer:** in-line on the shaft, strain-gauge based. Reports torque to a DAQ or to the analyzer.
- **Speed measurement:** encoder on the dyno shaft or DUT shaft.

For tuning purposes, a dyno gives you:
- Torque vs current curves (verify `K_t`).
- Speed-torque envelope (find FW corner).
- Efficiency map (η vs torque × speed grid).
- Step-load disturbance for controller tuning.

---

## 6.4 Bench equipment beyond scope/PA

- **Programmable DC supply** (bus voltage source): 0–600 V, current limit, bidirectional (sources and sinks) for regen testing.
- **DC electronic load:** simulates bus loads for testing power stages.
- **Multimeter, bench-grade:** DC R measurements, insulation resistance.
- **Insulation tester (megger):** before powering an unknown motor, check phase-to-frame insulation.
- **LCR meter:** measure L_d, L_q, phase-to-phase L.
- **Thermal camera or T-couples + DAQ:** thermal characterization.

---

## 6.5 Safety culture (talk about this in the interview)

- Lockout/tagout before re-wiring.
- Discharge bus caps before touching (stored energy `½CV²` is lethal at >50 V).
- One-handed work, isolating mats, eye protection at the bench when running high power.
- Estop reachable; software estop is **not** a substitute for a hardware-wired contactor that drops bus or enables STO.
- Spinning shafts: keys, set-screws, couplings can launch. Guards on.

---

## 6.6 Exit criteria

- [ ] Pick the right probe for any signal on a 3-phase drive system.
- [ ] Set up a scope to capture a clean phase-current waveform.
- [ ] Explain why a power analyzer beats `V_rms · I_rms · cos(φ)` from scope math.
- [ ] Walk through how a dyno measures motor efficiency.
- [ ] List four safety practices on a high-power bench.
