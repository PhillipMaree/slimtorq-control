# Module 5 — Tuning Strategies

**Goal:** Turn theory from Module 2 into a repeatable bench procedure. Walk into a lab, pick up an unknown motor + drive combo, and have a method that converges to good gains in under an hour.

**Time:** 6–8 hours
**Prereq:** Modules 1, 2, 3.

---

## 5.1 The tuning hierarchy (always inside-out)

1. **Inverter and current sensing checked** — dead time configured, current offsets calibrated, scaling verified.
2. **Encoder calibrated** — direction and electrical offset locked.
3. **Current loop tuned** — analytical first, then verified with steps.
4. **Speed loop tuned** — analytical first, then ID inertia, refine.
5. **Position loop tuned** — usually P-only or PD with FF.
6. **Trajectory & FF** — velocity FF, then acceleration FF, then jerk-limited profile.
7. **Disturbance rejection refined** — notch filters, observer-based disturbance, friction comp.

Never tune outer before inner. Never tune position before speed is solid.

---

## 5.2 Pre-tune sanity checks (the 5-minute checklist)

Before touching any gain:

- [ ] Bus voltage matches drive rating.
- [ ] Phase order matches expectation (swap two phases reverses direction).
- [ ] Encoder direction matches motor rotation direction (otherwise positive feedback → runaway).
- [ ] At rest with zero current command, measured currents are near zero (offset calibration).
- [ ] STO not active.
- [ ] Thermal sensors reading sane values.
- [ ] Estop accessible and tested.

---

## 5.3 Encoder zero-offset calibration

The most common reason a textbook-correct FOC implementation produces no torque.

**Method 1 (open-loop alignment):**
1. Disable closed-loop control.
2. Inject `i_α = I_align, i_β = 0` (i.e., command the stator field to point at electrical angle 0).
3. Wait for rotor to align (no load).
4. Read encoder. Store as `θ_offset`.
5. Henceforth, `θ_e = (encoder − θ_offset) · p`.

**Method 2 (auto-id with locked rotor):** inject low-frequency signal, find the phase relationship between command and response. Used by InstaSPIN and similar.

---

## 5.4 Current loop tuning

**Analytical (start here):**

Given motor `R_s, L_d, L_q` and desired current loop bandwidth `ω_bw_i` (rad/s):
- `K_p_d = L_d · ω_bw_i`, `K_i_d = R_s · ω_bw_i`
- `K_p_q = L_q · ω_bw_i`, `K_i_q = R_s · ω_bw_i`

**Choosing `ω_bw_i`:**
- Rule of thumb: `ω_bw_i ≤ 2π · f_sw / 10`. For `f_sw = 20 kHz`, that's ~12 kHz angular = ~2 kHz Hz.
- Also limited by current sensor BW and ADC anti-alias filter.

**Verify with a step:**
- Hold rotor locked (or low inertia loaded).
- Step `i_q*` from 0 to a small value (say 10% rated).
- Capture `i_q` actual on the scope or via streaming telemetry.
- Look for: rise time matches `2.2 / ω_bw_i`, no overshoot, no steady-state error.

**Common problems:**
- Overshoot → integrator too aggressive or inductance estimate too low.
- Slow rise → inductance estimate too high, or voltage saturating.
- Oscillation → sampling delay not accounted for, or computational delay >25% of sample period.

---

## 5.5 Inertia identification

You need `J` (combined rotor + load) for the speed loop math.

**Methods:**

- **Step torque, measure acceleration:** with no load other than friction, command `T*`, measure `α = dω/dt` over a short window. `J ≈ T* / α`. Subtract friction torque.
- **Sinusoidal injection:** inject a small sinusoidal torque, measure the speed response amplitude. From the magnitude of the transfer function `1/(Js + B)` at a chosen frequency, solve for J.
- **Coast-down:** spin up, kill drive, log `ω(t)`. Slope at high speed dominated by friction; integrate energy balance to extract J.

**Online identification:** more advanced — recursive least-squares on the speed-torque equation. Many commercial drives include "auto-tuning" routines that do exactly this.

---

## 5.6 Speed loop tuning

**Analytical:**
- Pick speed loop bandwidth `ω_n_s` ≤ `ω_bw_i / 5` (often ω_bw_i/10 for safety).
- With ζ = 0.707:
  - `K_p_ω = 2 · ζ · ω_n_s · J = 1.414 · ω_n_s · J`
  - `K_i_ω = ω_n_s² · J`

**Iterate with steps:**
- Start at lower gains than analytical (×0.5).
- Command a speed step (small relative to rated).
- If sluggish → increase Kp.
- If overshoot/ringing → decrease Kp or add filter on ω_meas.
- If steady-state error → increase Ki (rare with cascaded structure since inner loop kills it).

**Speed measurement filter:** almost always needed. A 1st-order LPF at ~3× `ω_n_s` is a good start. Be aware it adds phase lag and you must include it in the bandwidth budget.

---

## 5.7 Position loop tuning

Plant is a pure integrator (`ω → θ` via `1/s`).

- P-only is sufficient for most servos: `K_p_θ = ω_bw_θ` where `ω_bw_θ ≤ ω_n_s / 5`.
- Add **velocity feedforward**: `ω_ff = dθ_ref/dt`. Eliminates following error during constant-velocity moves.
- Add **acceleration feedforward** to the torque setpoint: `T_ff = J · d²θ_ref/dt²`. Eliminates following error during accel/decel phases.

**Result with both FFs:** following error during a smooth trajectory ≈ 0 in theory, limited by disturbance + uncompensated nonlinearities in practice.

---

## 5.8 Notch filters for mechanical resonance

If you tune the speed loop aggressively and hear a whine or see ringing at a fixed frequency in the speed-loop output:
1. FFT the speed signal during step response → identify peak.
2. Insert a notch filter at that frequency in the speed-loop output (before torque command).
3. Re-tune speed loop higher than before, since the resonance is suppressed.

Multiple resonances → multiple notches. Be aware of compliant couplings — they introduce a torsional pole around `√(K_t_couple / J_load)`.

---

## 5.9 Friction and disturbance compensation

- **Coulomb + viscous friction model:** `T_fric = T_c · sign(ω) + B · ω`. Add the estimated friction as a feedforward in the torque command. Identify by ramping speed and recording torque at steady state.
- **Stiction:** breakaway torque at zero speed. Often handled with a dither or special low-speed mode.
- **Cogging torque (slotted motors):** position-dependent. Map by spinning slowly and measuring torque ripple; play back as a function of θ.
- **Observer-based disturbance:** Luenberger or DOB (disturbance observer) estimates external torque online and adds it as feedforward.

For Alva slotless motors cogging is negligible — one of your differentiator talking points in the interview.

---

## 5.10 Field weakening (FW)

When `√(v_d² + v_q²) ≥ V_dc / √3` (SVPWM limit), you can't raise speed without reducing flux.

**Simple scheme:** PI controller on voltage magnitude. Reference = max usable voltage. Error = ref − actual. Output = negative `i_d*` setpoint, clamped to a safety limit (`|i_d*| ≤ I_max`).

**Better scheme:** lookup table indexed by speed and torque, computed offline from MTPA/MTPV solving.

For an SPM with `L_d = L_q`, field weakening reduces available torque proportionally. For an IPM with `L_d < L_q`, FW also unlocks reluctance torque → more useful FW range. Alva's slotless are typically SPM-like.

---

## 5.11 An "unknown motor" tuning recipe (interview-ready)

Walk through this in the interview when asked "how would you tune our drives":

1. **Read the datasheet:** pole pairs, rated current, rated speed, R, L if listed.
2. **Visual + electrical check:** wiring, encoder type, STO.
3. **DC R measurement:** Inject 10% rated current via two phases at zero speed. `R_phase = V/I × 1/2`.
4. **AC L measurement:** inject low-amplitude AC, fit impedance. Or use drive's auto-id if available.
5. **Back-EMF / λ_PM:** spin the motor open-circuit with a dyno or by hand, measure line-line peak.
6. **Encoder zero offset:** alignment procedure (Section 5.3).
7. **Current loop:** compute Kp, Ki from `ω_bw_i = 2π · 1 kHz` (start). Step test, verify.
8. **Inertia ID:** torque step, measure α.
9. **Speed loop:** compute Kp, Ki for ω_n_s = ω_bw_i / 5. Step test.
10. **Position loop:** Kp = ω_n_s / 5. Move test.
11. **Feedforward:** add velocity FF, then acceleration FF.
12. **Stress test:** trajectory under load, capture following error and tune further.
13. **Document:** all final gains, identified parameters, scope captures.

---

## 5.12 Exit criteria

- [ ] Walk through the unknown-motor recipe (5.11) from memory.
- [ ] Derive Kp, Ki for current loop with R = 50 mΩ, L = 100 µH, BW = 2 kHz.
- [ ] Explain why you can't raise speed loop gain beyond ~1/5 of current loop bandwidth.
- [ ] Describe how to identify J on the bench.
- [ ] Identify whether overshoot in a step response is from too much Kp or too much Ki, and how to tell the difference.
