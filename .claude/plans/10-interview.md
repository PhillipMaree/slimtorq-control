# Module 10 — Interview-Day Cheat Sheet

**Goal:** Refresh the night before. Crisp, recallable. Not a study guide — a recall sheet.

---

## 10.1 30-second self-pitch

> *"I'm an engineer comfortable across the stack — control theory, embedded interfaces, and host-side tooling. For this role I've focused on three things: FOC end-to-end for PMSM and induction machines, EtherCAT/DS402 because that's how your drives integrate, and a tuning-tool prototype I built to make the workflow repeatable. I'm most excited about Alva because slotless PMSMs let you push current-loop bandwidths most industrial drives can't touch, which makes tuning genuinely interesting."*

Personalize and shorten.

---

## 10.2 Whiteboard-on-demand bank

You should be able to draw any of these without prep:

1. FOC block diagram (PMSM, with decoupling and SVM).
2. DS402 state machine.
3. Cascaded loop structure: position → velocity → current.
4. Park / Clarke transforms as equations.
5. Equivalent circuit of an induction motor (per phase).
6. EtherCAT topology with master + 3 slaves and a working-counter explanation.
7. Three-shunt current sensing with sampling timing relative to PWM.

---

## 10.3 Killer numbers to remember

- Current loop BW rule: `ω_bw_i ≈ 2π · f_sw / 10`.
- Cascaded BW separation: 5× minimum between adjacent loops.
- SVPWM gain over SinPWM: ~15% more usable bus voltage.
- DC sync jitter: < 100 ns achievable in EtherCAT.
- Typical motion cycle time: 250 µs–1 ms.
- Encoder bits: 17–25 for absolute, 1000–10000 PPR × 4 for incremental.
- PMSM torque equation simplified (SPM): `T_e = (3/2)·p·λ_PM·i_q`.

---

## 10.4 Likely questions + skeleton answers

**"Walk me through FOC."**
→ Goal: rotor-aligned reference frame turns AC machine into DC machine. Three steps: (1) measure 2-3 phase currents, Clarke→Park into d-q using rotor angle from encoder. (2) Two PI loops, one for `i_d` (often 0 for SPM), one for `i_q` (drives torque). (3) Invert: `v_d, v_q` → inverse Park → α-β → SVM → 6 PWM signals → inverter → motor.

**"How would you tune our current loop given motor R and L?"**
→ Pole-zero cancellation. `K_p = L · ω_bw`, `K_i = R · ω_bw`. Choose `ω_bw` ≤ switching freq × 2π/10. Verify with a step — first-order rise, no overshoot. Add decoupling FF.

**"What's the difference controlling a PMSM vs an induction motor?"**
→ PMSM has rotor flux from PMs — you can directly orient to it from encoder. Induction motor flux is induced via slip; you must either measure (rare) or estimate the rotor flux angle from a model that depends on the rotor time constant `T_r = L_r / R_r`. PMSM is easier and more efficient; induction is more rugged and PM-free.

**"Why EtherCAT over CANopen?"**
→ Determinism + bandwidth + sync. EtherCAT does 100 Mbps line-rate with <100 ns sync via DC, vs CANopen's 1 Mbps and ~10 µs SYNC jitter. For >16 axes or anything needing simultaneous setpoint application, EtherCAT wins.

**"How do you handle a motor whose parameters you don't know?"**
→ Walk through the unknown-motor recipe in [05-tuning.md](05-tuning.md) §5.11.

**"Tell me about a time you debugged a tricky control issue."**
→ Have one real story prepared. If you don't have one yet, your slimtorq project's encoder-offset / sign-convention bug counts — every FOC implementation hits this.

**"What if the customer's drive isn't responding after Op transition?"**
→ Common DS402 trap: bus state is Op but DS402 state machine is still in `Switched On` — need to walk controlword through shutdown → switch on → enable. Other suspects: SDO config (mode of operation), STO active, fault latched.

**"How would you architect a tuning tool for our drives?"**
→ Three-tier (UI, engine, protocol). Protocol abstraction so sim and real are interchangeable. Telemetry ring buffer with trigger-capture. DS402 object dictionary mirror. (Show your slimtorq diagram.)

**"What's a power analyzer better at than a scope with math?"**
→ Calibrated power across multi-phase, period-aligned RMS, harmonics. Drive-level efficiency without integration drift.

---

## 10.5 Questions YOU should ask

Always have 3–5 prepared. Suggestions:

- "What does your current tuning workflow look like? What hurts?"
- "How much of motor characterization is automated today?"
- "Do you use HIL in CI, or only bench testing?"
- "What customer integrations have you seen go best vs go worst, and what was the difference?"
- "Where on the firmware/host split does the control IP live, and how is that evolving?"
- "Do you ship the drive's firmware or does the customer bring their own controller and you ship the motor?"
- "How do you handle field-tuning at customer sites — remote tooling, on-site engineers?"

---

## 10.6 Things to flag honestly

If asked about a gap, don't oversell. Better:
- *"I haven't worked with EtherCAT on real hardware — I've worked with pysoem against a simulator and read SOEM enough to be useful from day one, but I'll have a real-hardware learning curve."*
- *"My induction-motor work has been theoretical — I'd want to spend bench time before signing off on customer integrations there."*

Calibrated honesty reads as senior. Overselling reads as risk.

---

## 10.7 The 10-minute morning-of refresher

1. Re-read [00-overview.md](00-overview.md) §7 (success criteria).
2. Sketch FOC block diagram on a sheet of paper, from memory.
3. Re-read 10.4 question skeletons aloud.
4. Open your slimtorq demo, click through it once.
5. Close everything and breathe.

You're ready.
