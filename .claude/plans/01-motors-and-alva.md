# Module 1 — Motor Fundamentals & Alva's Technology

**Goal:** Understand the physical machines you'll be controlling and tuning, with specific focus on Alva's slotless PMSM technology and the induction motors you've flagged as a learning priority.

**Time:** 4–6 hours
**Prereq:** Comfort with basic EM (Lorentz force, Faraday's law) and three-phase AC.

---

## 1.1 Alva's motor technology

Alva's differentiator is **FiberPrinting** — an additive manufacturing process for the stator windings. Practical implications you should understand:

- **Slotless stator:** no iron teeth between windings → very low cogging torque, low torque ripple, smooth motion at low speeds. Ideal for precision applications.
- **Air-gap winding:** windings sit in the air gap, not in slots. Trade-off — higher copper losses per area, but lower iron losses and higher current density possible.
- **High power-to-weight:** typical claim is 2–5× industrial baselines.
- **Permanent-magnet rotor (PMSM):** typically surface-mounted PMs → roughly `L_d ≈ L_q`, so reluctance torque is small and the torque equation simplifies to `T_e = (3/2) * p * λ_PM * i_q`.
- **Targets:** drones, eVTOL, robotics, high-end industrial.

**Why this matters for tuning:**
- Low inductance (slotless) → fast current dynamics → you need higher PWM frequencies and faster current loops than a typical industrial servo.
- Low cogging → smoother sensorless operation possible at low speeds.
- High torque density → thermal management is the dominant constraint; current limits are thermal not electromagnetic.

**Action:** Spend 30 min on alvaindustries.com. Note their product families, target customers, and any whitepapers/datasheets. Bring informed questions to the interview.

---

## 1.2 Motor taxonomy you must know

| Type | Rotor | Commutation | Torque equation (steady) | Typical control |
|---|---|---|---|---|
| **DC brushed** | Wound | Mechanical (brushes) | `T = K_t · I` | Linear, easy |
| **BLDC** (trapezoidal back-EMF) | PM | Electronic (Hall-triggered 6-step) | `T ≈ K_t · I` (per phase pair) | Trapezoidal / 6-step |
| **PMSM** (sinusoidal back-EMF) | PM | Electronic (continuous, FOC) | `T_e = (3/2)·p·(λ_PM·i_q + (L_d−L_q)·i_d·i_q)` | FOC |
| **Induction (squirrel cage)** | Shorted bars, induced current | Slip-driven | `T ∝ (s·V²)/(R_r² + (s·X)²)` | V/f or vector (IFOC) |
| **Synchronous reluctance** | Salient iron, no PM | Electronic | `T_e = (3/2)·p·(L_d−L_q)·i_d·i_q` | FOC (different alignment) |

For Alva specifically you live in the **PMSM** row. But the job mentions induction motors, so the **induction** row is your other study target.

---

## 1.3 PMSM deep dive

Topics to internalize:

- **Two-pole equivalent and electrical angle:** `θ_e = p · θ_m` where p is pole pairs.
- **Back-EMF constant `K_e`** and **torque constant `K_t`** — same physical quantity in SI units, expressed differently.
- **d-q frame motivation:** rotor-aligned reference makes a 3-phase AC machine look like a DC machine. d-axis aligns with rotor flux; q-axis is 90° electrical ahead.
- **Voltage equations in d-q (steady-state):**
  - `v_d = R_s · i_d − ω_e · L_q · i_q`
  - `v_q = R_s · i_q + ω_e · L_d · i_d + ω_e · λ_PM`
- **Cross-coupling:** the `ω_e · L · i` terms couple d and q axes. Decoupling feedforward removes this so the two PI loops can be designed independently.
- **Field weakening:** when back-EMF saturates the inverter voltage, push negative `i_d` to reduce effective flux and extend speed range. Reduces available torque.
- **MTPA (Max Torque Per Amp):** for IPMs, optimal `i_d` is not zero — minimizes copper loss for a given torque.

**Self-check:**
1. Why does cogging torque exist in slotted motors but not in slotless?
2. For an SPM with `L_d = L_q`, what `i_d` setpoint minimizes copper loss below base speed? Above base speed?
3. Sketch the d-q voltage equations as a circuit.

---

## 1.4 Induction motor essentials

Why the job description leans here: 3rd-party drives Alva integrates with may drive induction motors, and customer applications often use them for cost/ruggedness reasons.

Topics:

- **Slip `s = (ω_s − ω_m) / ω_s`** — induction motors need slip to produce torque.
- **Equivalent circuit (per phase):** stator R/L, magnetizing branch, rotor R/L referred to stator. Know which branch dominates which behavior.
- **Torque-slip curve:** breakdown torque, pull-out, rated operating point near low slip.
- **Scalar V/f control:** maintain constant flux by keeping `V/f` ratio constant (with boost at low speed). Open-loop, cheap, no encoder. Performance: poor at low speed, sluggish dynamics. Common in pumps/fans.
- **Indirect FOC (IFOC):** estimate rotor flux angle from slip and stator currents → orient d-axis to estimated rotor flux → control torque via `i_q`, flux via `i_d`. Needs accurate rotor time constant `T_r = L_r / R_r`.
- **Direct FOC (DFOC):** measure flux (rare) or estimate from voltage model. Less common in practice.

**Small vs large induction motors — what changes?**

| Aspect | Small (<10 kW) | Large (>100 kW) |
|---|---|---|
| Switching freq | 8–20 kHz | 1–4 kHz |
| Sensorless feasibility | Hard at low speed | Easier (better signal-to-noise) |
| Dominant losses | Stator copper | Stator iron + rotor copper |
| Thermal time const | Seconds | Minutes |
| Starting strategy | Direct + ramp | Soft-starter / VFD ramp |
| Encoder use | Often closed-loop | Often open-loop (V/f) |

**Self-check:**
1. Why does an induction motor draw inrush current at startup and how does a VFD avoid that?
2. What's the rotor time constant `T_r` and why does FOC accuracy depend on it being right?
3. When would you choose V/f over FOC for an induction motor?

---

## 1.5 Motor parameters to characterize (bench skill)

When you walk up to an unknown motor, you'll need to measure or estimate:

- `R_s` (stator phase resistance) — DC current injection, V/I.
- `L_d`, `L_q` (PMSM) or `L_s` (induction) — AC injection at various angles / locked rotor tests.
- `λ_PM` (PM flux linkage) — back-EMF test, spin at known speed measure line-line voltage.
- `J` (rotor inertia) — coast-down test or step-response identification.
- `B` (viscous friction) — steady-state speed vs torque.
- Pole pairs `p` — sometimes from datasheet, sometimes from counting back-EMF cycles per mechanical revolution.

**Action:** write a 1-page "motor characterization checklist" you could hand to a junior engineer. This is exactly the kind of artifact an interviewer loves to see.

---

## 1.6 Resources

Pick one or two — don't try to consume all:

- **Book:** Krishnan, *Permanent Magnet Synchronous and Brushless DC Motor Drives* — the reference text for PMSM control. Chapter 9 on FOC is what you need.
- **Book:** Mohan, *Electric Drives — An Integrative Approach*. Approachable, good for induction motors.
- **Free:** Microchip AN1078 (Sensored FOC for PMSM), AN1162 (Sensorless FOC), AN1206 (induction motor V/f).
- **Free:** TI InstaSPIN documentation — practical FOC with auto-identification.
- **Video:** Mathworks "Understanding Motor Control" series on YouTube — short, well-illustrated.

---

## 1.7 Exit criteria for this module

You should be able to:

- [ ] Draw and label a slotless PMSM cross-section and explain why low inductance affects current loop design.
- [ ] State the PMSM torque equation including the reluctance term, and explain when each term dominates.
- [ ] Sketch the induction motor torque-slip curve and label rated, breakdown, and starting torque.
- [ ] Explain V/f vs IFOC trade-offs in one paragraph.
- [ ] List six motor parameters you'd characterize on the bench and the test for each.
