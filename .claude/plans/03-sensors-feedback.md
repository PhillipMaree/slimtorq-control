# Module 3 — Sensors, Encoders, Current Sensing

**Goal:** Know every feedback element you'll wire up on a motor bench: what each one outputs, its bandwidth and noise floor, how it interfaces electrically, and how it fails.

**Time:** 4–6 hours
**Prereq:** Module 1.

---

## 3.1 Position / angle sensors

### Hall sensors
- Three digital switches at 120° electrical spacing → six valid states per electrical revolution.
- Resolution: 60° electrical. Fine for trapezoidal BLDC, **too coarse for FOC by itself**.
- Used in FOC during startup before encoder homing, then handed off.
- Failure modes: misaligned magnet, single Hall dropout (one of six states missing → torque dip).

### Incremental encoders (quadrature)
- Two channels A, B in quadrature → 4× edge counting → counts per revolution = 4·PPR.
- Z (index) pulse once per revolution → absolute reference after a homing move.
- Interface: differential (RS-422) for noise immunity, or single-ended for short runs.
- Limitations: no absolute position at power-on; need homing.

### Absolute encoders
- **Single-turn:** unique code per position within one revolution.
- **Multi-turn:** also tracks revolution count via gear train or battery-backed counter.
- Interfaces: **SSI**, **BiSS-C** (open), **EnDat 2.2** (Heidenhain), **Hiperface DSL** (SICK), **Tamagawa**.
- Resolution: 17–25 bits typical.
- Latency matters for high-bandwidth FOC — BiSS-C at 10 MHz gives ~10 µs round trip for a single-turn read.

### SinCos encoders
- Analog sine and cosine outputs (often 1 Vpp) over one period.
- Interpolation in the drive ASIC extends resolution well beyond the line count.
- Common in high-end servos.

### Resolvers
- Rotary transformer: excited primary on rotor, two secondaries on stator outputting `sin(θ)` and `cos(θ)` modulated by the excitation carrier.
- Demodulated by an RDC (resolver-to-digital converter) like the AD2S1210.
- Pros: rugged, high temperature, no electronics on rotor.
- Cons: more expensive front-end, requires excitation signal generation.

**Decision table for the interview:**

| Application | Best choice | Why |
|---|---|---|
| Low-cost BLDC fan | Hall | Cheap, sufficient |
| Industrial servo | Absolute (BiSS/EnDat) | No homing, multi-turn |
| Harsh environment (aerospace, drone) | Resolver | Robust, no electronics on rotor |
| Precision machine tool | SinCos w/ interpolation | Sub-arc-second possible |
| Hobbyist / prototype | Incremental quadrature | Cheap, ubiquitous |

---

## 3.2 Speed estimation from position

- **Backward difference:** `ω ≈ (θ[k] − θ[k−1]) / T_s`. Noisy at low speed and high resolution.
- **Frequency measurement (M-method):** count pulses per fixed window. Good at high speed, poor at low speed.
- **Period measurement (T-method):** time between pulses. Good at low speed, poor at high speed.
- **M/T method:** hybrid, switches based on speed.
- **Observer (Luenberger):** model-based, filters noise; often used when also estimating position for sensorless modes.

---

## 3.3 Current sensing

The current sensor IS your control feedback. Its bandwidth, accuracy, and noise determine your loop performance.

### Topologies

| Type | How | BW | Isolation | Notes |
|---|---|---|---|---|
| Inline shunt + diff amp | Low-side or in-phase, R drops V | High (>1 MHz possible) | None unless isolated amp | Cheap, accurate, needs careful PCB |
| Low-side shunt only | Below each MOSFET source | High | None | Sample timing constraint (current valid only when low-side is on) |
| Hall-based (open-loop) | Magnetic field around conductor | ~100 kHz | Inherent | Low cost, drift |
| Hall-based (closed-loop / LEM) | Compensated by feedback coil | ~200 kHz | Inherent | Industrial standard, expensive |
| Fluxgate | Like closed-loop Hall but better | High | Inherent | Premium |
| Rogowski coil | di/dt → integrate | Very high | Inherent | AC only, integrator drift |

### Single-shunt vs three-shunt vs two-shunt

- **Single-shunt** (DC bus): cheapest, reconstructs phase currents from DC bus current within a PWM period using switching state. Requires minimum vector dwell time → distorts low-modulation operation.
- **Two-shunt:** measure two phases, compute the third from Kirchhoff (`i_a + i_b + i_c = 0`).
- **Three-shunt:** redundant, allows error detection. Premium.

### Sampling

Sample synchronized to PWM, typically at the midpoint of the low-side on-time (current ripple is symmetric there → you get the average). Modern motor-control MCUs (STM32 G4/H7, TI C2000) have ADC triggers tied to PWM timer to make this automatic.

---

## 3.4 Voltage and temperature

- **DC bus voltage:** divide down, ADC. Used for SVM scaling and overvoltage protection.
- **Phase voltages:** if measured (rare in drives), used by sensorless observers.
- **Motor temperature:** NTC or PT100 in the windings; communicated via separate ADC channel. Some encoders (BiSS-C) embed temperature on the same line.

---

## 3.5 Practical bench skills

- Identify encoder type from a connector pinout.
- Verify Hall sequence by spinning the motor by hand and watching three GPIO with a scope.
- Calibrate encoder zero offset for FOC: lock the rotor by injecting `i_d = I_nom, i_q = 0` from electrical angle = 0; the rotor will align to d-axis; record encoder reading as offset.
- Identify current sensor scaling and offset: with motor disconnected, ADC should read midscale (zero current). Calibrate gain by injecting known DC through a phase with a bench supply.

---

## 3.6 Exit criteria

- [ ] Name five encoder types and the right application for each.
- [ ] Explain why FOC needs higher angle resolution than trapezoidal commutation.
- [ ] Describe the difference between M-method and T-method speed estimation.
- [ ] Sketch a three-shunt current-sensing topology and explain when to sample.
- [ ] Walk through an encoder zero-offset calibration procedure.
