# Module 2 — Control Theory & Field-Oriented Control

**Goal:** Master FOC end-to-end so you can draw the block diagram, design each loop's gains analytically, and explain why every block exists.

**Time:** 8–12 hours
**Prereq:** Module 1. Comfort with Laplace transforms and Bode plots.

This is the highest-leverage module for the interview. Prioritize it.

---

## 2.1 Control fundamentals refresh

Make sure these are second nature:

- **First-order plant:** `G(s) = K / (τs + 1)`. Step response, time constant, bandwidth `ω_bw ≈ 1/τ`.
- **PI controller:** `C(s) = K_p + K_i/s = K_p · (τ_i s + 1) / (τ_i s)` where `τ_i = K_p / K_i`.
- **Pole-zero cancellation:** if plant pole is at `−1/τ_p`, set `τ_i = τ_p` and the closed loop becomes a single pole.
- **Closed-loop bandwidth:** for a unity-feedback system with open-loop crossover at `ω_c`, closed-loop bandwidth ≈ `ω_c`.
- **Phase margin:** 60° = well-damped, 45° = aggressive, <30° = ringing/instability risk.
- **Cascaded loops rule of thumb:** inner loop bandwidth should be 3–10× outer loop bandwidth so the inner appears "instantaneous" to the outer.

**Self-check:** for `G(s) = 1/(Ls + R)`, design a PI controller for closed-loop bandwidth `ω_bw`. Answer: `K_p = L · ω_bw`, `K_i = R · ω_bw`. Memorize this — it's the current loop design.

---

## 2.2 Reference frame transformations

The three transforms you must know cold:

### Clarke (a-b-c → α-β)
Maps three-phase AC to two-axis stationary AC.
```
i_α =  (2/3) · (i_a − 0.5·i_b − 0.5·i_c)
i_β =  (2/3) · (√3/2 · i_b − √3/2 · i_c)
```
With `i_a + i_b + i_c = 0`, you can use only two sensed phases.

### Park (α-β → d-q)
Maps stationary to rotor-synchronous (rotating) frame. Requires electrical angle `θ_e`.
```
i_d =  i_α·cos(θ_e) + i_β·sin(θ_e)
i_q = −i_α·sin(θ_e) + i_β·cos(θ_e)
```

### Inverse Park, Inverse Clarke
Same equations transposed. You apply these to your voltage commands `v_d, v_q` on the way to the modulator.

**Build intuition:**
- In steady state at constant torque, `i_d` and `i_q` are **DC values** — that's why PI works on them.
- `i_a, i_b, i_c` are sinusoids at electrical frequency.
- The Park transform is "literally just" stepping onto a merry-go-round spinning with the rotor.

**Exercise:** in Python, generate three-phase sinusoids, run them through Clarke→Park with a matching rotor angle, plot the d-q outputs. They should be constant. Then mismatch the angle by 10° and watch the cross-coupling appear.

---

## 2.3 The FOC block diagram

Sketch this from memory at least 10 times before the interview:

```
                                       i_q* ──►(−)──►[PI_q]──► v_q*
ω* ──►(−)──►[PI_ω]──► T*/Kt ──► i_q*         ▲              │
              ▲                              │              ▼
              │ω                          measured       [inv Park (θ_e)]
              │                            i_q              │
              │                                             ▼
                                                         v_α*, v_β*
                                       i_d* ──►(−)──►[PI_d]    │
                                       (often 0)    │          ▼
                                                    ▼      [SVPWM] ──► 6 PWM
                                       i_d measured                   │
                                                                       ▼
                                                              [Inverter] ──► Motor
                                                                                │
                                                            ┌────────[Park (θ_e)]
                                                            │              ▲
                                                            │              │
                                                            │       [Clarke]
                                                            │              ▲
                                                            ▼              │
                                                       i_d, i_q     i_a, i_b (sensed)
                                                                            ▲
                                                           θ_e ◄── [Encoder/observer]
```

Every block earns its place. In an interview, be ready to defend each one.

**The four cascaded loops in a position servo:**
1. Inner current loop (d and q independent) — fastest, ~1 kHz BW typical.
2. Speed loop — 100–300 Hz BW.
3. Position loop — 10–50 Hz BW.
4. (Optional) Trajectory generator on top.

---

## 2.4 Space Vector Modulation (SVM / SVPWM)

You don't have to derive it perfectly in an interview, but understand:

- **Why SVPWM:** ~15% better DC bus utilization than sine-triangle PWM, lower harmonic distortion.
- **Eight switching states:** six active vectors (V1–V6) at 60° intervals, two zero vectors (V0, V7).
- **Time decomposition:** any reference vector `V*` in a sector is the time-average of the two adjacent active vectors plus zero vector(s).
- **Dead time and its compensation:** non-zero turn-off vs turn-on time means both switches in a leg must be off briefly → distorts low-frequency output → tunable compensation.

**Self-check:** for `V_dc = 24 V`, what's the maximum line-to-line RMS output for sine-PWM vs SVPWM? (Roughly 14.7 V vs 17 V.)

---

## 2.5 Current loop design (the analytical sweet spot)

Plant per axis (after decoupling feedforward applied):
```
G(s) = i / v = 1 / (L_dq · s + R_s)
```

Goal: closed-loop bandwidth `ω_bw_i` (radians/sec). Typical target: 1/10 of switching frequency.

Use pole-zero cancellation:
- `K_p_i = L_dq · ω_bw_i`
- `K_i_i = R_s · ω_bw_i`

Closed loop becomes `G_cl(s) = ω_bw_i / (s + ω_bw_i)` — perfect first-order, no overshoot.

**Anti-windup:** when output saturates at `±V_dc/√3`, clamp integrator. Implementation: back-calculation or clamp-on-saturation.

**Decoupling feedforward (PMSM):**
- `v_d_ff = −ω_e · L_q · i_q`
- `v_q_ff = +ω_e · L_d · i_d + ω_e · λ_PM`

Adding these to the PI output removes the cross-coupling and the back-EMF term so the PI loop only fights the R-L impedance.

---

## 2.6 Speed and position loops

**Speed plant** (mechanical):
```
G_ω(s) = ω / T_e = 1 / (Js + B)
```
Since friction `B` is often tiny, the plant is effectively an integrator.

**Speed PI gains for damping ratio ζ = 0.707, natural freq `ω_n_s`:**
- `K_p_ω = 2 · ζ · ω_n_s · J`
- `K_i_ω = ω_n_s² · J`

Set `ω_n_s ≤ ω_bw_i / 5` for cascaded loop stability.

**Position loop:** typically P-only (or PD with velocity feedforward) feeding into the speed loop. P-only on an integrator plant gives first-order behavior:
- `K_p_θ = ω_bw_θ`
- Closed-loop bandwidth = `K_p_θ` (rad/s) — set 1/5 of speed loop BW.

**Feedforward you'll add later:**
- Velocity FF on position output (massive tracking improvement).
- Acceleration FF (torque feedforward `T_ff = J·α_ref`) for known trajectories.

---

## 2.7 Sensorless techniques (know the names)

- **Back-EMF observer** (Luenberger, SMO — sliding-mode observer): works above ~5–10% rated speed. Estimates flux from `v − R·i − L·di/dt`.
- **High-frequency injection (HFI):** works at and near zero speed. Injects a high-freq voltage on d-axis, measures the response on q-axis to find saliency. Requires `L_d ≠ L_q`, so harder on SPM motors.
- **Kalman filter / Extended Kalman:** model-based, computationally expensive, robust to noise.

For Alva's slotless PMSMs, sensorless is harder at low speed because saliency is minimal. Encoder-based control is the norm.

---

## 2.8 Common pitfalls (interview gold)

- **Sign convention:** d-axis aligned with rotor flux, q-axis leads d by +90° electrical. Inconsistent conventions are the #1 reason FOC implementations don't work.
- **Encoder zero offset:** even a correct FOC implementation produces no torque if `θ_e_offset` is wrong. Calibration procedures matter.
- **Inverter dead-time distortion:** causes torque ripple at low speed. Compensation needed.
- **Current-sensor bandwidth and noise:** filter delay introduces phase lag in the loop. Anti-alias filters must be designed jointly with the loop.
- **Sample timing:** sample current at the midpoint of the PWM low-side on-time to get the average. Botching this gives ripple-corrupted measurements.

---

## 2.9 Exercises

1. **Python sim:** model a PMSM in d-q (3 ODEs: `di_d/dt`, `di_q/dt`, `dω/dt`). Wrap current PI loops, run a torque step, plot.
2. **Tuning exercise:** given `R = 0.1 Ω`, `L = 0.2 mH`, target current BW = 2 kHz, compute `K_p, K_i`. Verify in sim that step response has no overshoot.
3. **Cross-coupling demo:** disable decoupling FF, command i_d step, watch i_q wiggle. Re-enable FF, watch it stop.
4. **Saturation:** command an `i_q` step that requires more voltage than `V_dc` allows. Show integrator windup without anti-windup, then fix it.

These become the seeds of [09-project.md](09-project.md).

---

## 2.10 Exit criteria

- [ ] Sketch FOC block diagram from memory, all signals labeled.
- [ ] Derive `K_p, K_i` for the current loop given R, L, and target bandwidth.
- [ ] Explain why d-q transformation makes PI control work on a 3-phase AC machine.
- [ ] Describe two sensorless techniques and the speed range each is valid in.
- [ ] List four ways a "correct" FOC implementation can still produce no torque (sign error, encoder offset, sensor wiring, dead-time).
