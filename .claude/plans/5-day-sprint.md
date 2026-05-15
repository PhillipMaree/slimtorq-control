# Sprint Plan — Alva Interview

**Start:** Tue 2026-05-12 (today, partial) · **Interview:** Mon 2026-05-18
**Working days:** Tue (partial) → Wed/Thu/Fri (full) → Sat afternoon (parkrun in AM). Sun = full rest.
**Budget:** ~Tue (whatever's left) + 8 h × 3 + ~4 h Sat = **~28–34 h total**.

The extra Tuesday block converts this from "tight" to "comfortable" — Bode capture (the headline artifact) now lands on Day 3 with a buffer day after.

---

## Triage at this budget

**Must master (deep):**
- FOC block diagram + current-loop tuning math
- DS402 state machine + EtherCAT basics
- PMSM physics + torque equation
- Cascaded loop bandwidth reasoning

**Must demo:**
- PMSM sim with FOC current loop → **Bode plot screenshot** (headline)
- Speed-loop step response screenshot
- 5-min verbal walkthrough of architecture

**Must skim (vocabulary level only):**
- Encoder types, current sensing
- Induction motor (equivalent circuit + V/f vs IFOC)
- Sensorless techniques (BEMF / HFI / EKF + speed ranges)
- Lab equipment + HIL platforms (namedrop)
- MTPA / field weakening ("negative i_d above base speed")

**Cut entirely:**
- pysoem stub (DS402 verbal fluency is the bar)
- Three-shunt vs single-shunt math
- Notch filter design specifics
- Any hardware-flavored deep-dives

If you reach for a cut topic mid-sprint, **stop** — that's the rabbit hole that costs you the demo.

---

## Day 1 (Tue 5/12 — today, partial) — Theory power-skim + repo skeleton

Scale the block list to the hours you have left today. Start at the top; whatever doesn't fit rolls to Wed morning.

| Block | Topic | Module ref |
|---|---|---|
| 1 h | Three-phase AC + PMSM physics + Alva tech | [01-motors-and-alva.md](01-motors-and-alva.md) §1.1–1.3 |
| 1 h | Clarke/Park + d-q frame intuition | [02-control-foc.md](02-control-foc.md) §2.1–2.2 |
| 1 h | FOC block diagram (draw 5× from blank) + SVPWM concept | [02-control-foc.md](02-control-foc.md) §2.3–2.4 |
| 0.5 h | Repo skeleton (`sim/`, `control/`, `link/`, `ui/`, `docs/`) + first commit | [09-project.md](09-project.md) §9.2 |
| 0.5 h | Bench characterization checklist | [01-motors-and-alva.md](01-motors-and-alva.md) §1.5 |
| 1 h | Induction motor 30-min overview (V/f vs IFOC) | [01-motors-and-alva.md](01-motors-and-alva.md) §1.4 |

**Gate (end of today, blank-page test):** FOC block diagram from memory + PMSM torque equation.

---

## Day 2 (Wed 5/13) — Sim + current loop · 8 h

| Block | Topic | Module ref |
|---|---|---|
| 1 h | Mop up any Day 1 blocks that didn't fit | |
| 0.5 h | Current-loop math review (analytical gains) | [02-control-foc.md](02-control-foc.md) §2.5 |
| 2.5 h | `sim/pmsm.py` (d-q ODE) + unit tests | |
| 1.5 h | `control/transforms.py` (Clarke/Park/inverse) + tests | |
| 2 h | `control/foc.py` current loops + step response | |
| 0.5 h | Capture `docs/day2-current-step.png` | |

**Gate:** step on `i_q*` produces a first-order rise in sim that matches analytical τ.

---

## Day 3 (Thu 5/14) — Tuning depth + speed loop + Bode (headline) · 8 h

| Block | Topic | Module ref |
|---|---|---|
| 1 h | Cascaded BW rule + common pitfalls (anti-windup, deadtime, decoupling) | [02-control-foc.md](02-control-foc.md) §2.6–2.7 |
| 1.5 h | Speed loop in sim — inertia ID + analytical gains | [05-tuning.md](05-tuning.md) §5.5–5.6 |
| 0.5 h | Speed-step capture → `docs/day3-speed-step.png` | |
| 2.5 h | **Bode-sweep harness** — sinusoidal `i_q*` at log-spaced f → magnitude/phase | [09-project.md](09-project.md) §9.4 |
| 1.5 h | **Bode plot artifact** → `docs/day3-current-bode.png` (compare to theoretical 1st-order) | |
| 0.5 h | Tuning bench recipe — read & memorize | [05-tuning.md](05-tuning.md) §5.11 |
| 0.5 h | Sensorless overview namedrop | [02-control-foc.md](02-control-foc.md) §2.8 |

**Gate:** Bode plot matches theoretical first-order rolloff at design BW. **Interview headline.**

> *If Bode slips:* cut speed-step polish, ship the Bode. The Bode turns "how do you tune a current loop" from hand-waving into a screenshot.

---

## Day 4 (Fri 5/15) — EtherCAT/DS402 + UI/telemetry + skims · 8 h

| Block | Topic | Module ref |
|---|---|---|
| 2.5 h | EtherCAT frames/SM/FMMU/DC + PDO/SDO + DS402 state machine + modes | [04-communication.md](04-communication.md) §4.1–4.8 |
| 0.5 h | CANopen comparison + protocol-zoo namedrop | [04-communication.md](04-communication.md) §4.10–4.11 |
| 0.5 h | DS402 state-machine cheat sheet — write your own one-pager | |
| 0.5 h | `link/sim_link.py` + DS402 mode enums + state machine in code | [09-project.md](09-project.md) §9.3 |
| 2.5 h | UI (Streamlit) — gain sliders, mode selector, live i_d/i_q plot via WS | [09-project.md](09-project.md) Tier 1/2 |
| 0.5 h | Telemetry ring buffer + trigger capture | [08-architecture.md](08-architecture.md) §8.4 |
| 0.5 h | Sensors & current sensing skim | [03-sensors-feedback.md](03-sensors-feedback.md) §3.1–3.3 |
| 0.5 h | README polish + screenshot pass | |

**Gate:** DS402 state machine drawn from memory. UI runs, shows live current. README has screenshots.

> *If UI slips:* matplotlib live-plot + CLI sliders is fine. UI polish is not the bar; the conversation about it is.

---

## Day 5 (Sat 5/16 afternoon) — Rehearsal + polish · ~4 h

Parkrun in the AM (good — physical activity consolidates memory). Start work ~13:00.

| Block | Topic | Module ref |
|---|---|---|
| 0.5 h | Lab equipment + HIL namedrop skim | [06-lab-equipment.md](06-lab-equipment.md) + [07-simulation-hil.md](07-simulation-hil.md) §7.6 |
| 0.5 h | Architecture diagram — rehearse describing aloud | [08-architecture.md](08-architecture.md) §8.1 |
| 1 h | Whiteboard rehearsal bank: FOC, DS402, cascaded loops, IM equivalent circuit | [10-interview.md](10-interview.md) §10.2 |
| 1 h | Cheat sheet — read 10.1–10.6 aloud, write your <40 s self-pitch | [10-interview.md](10-interview.md) |
| 0.5 h | Fresh-shell demo dry run — does `make demo` (or equivalent) work cold? | [09-project.md](09-project.md) §9.5 |
| 0.5 h | Final README polish + commit final screenshots | |

**Gate:** demo runs on a cold shell. Self-pitch <40 s. Whiteboard topics all recallable.

---

## Sun 5/17 — REST (do not work)

- **No coding.** No new material.
- Optional, **only if anxious**: 20 min cheat-sheet read-through in the evening.
- Sleep 8+ h. Eat well, walk, see people, normal Sunday.

Rest is part of the plan. Memory consolidates during sleep; Sunday cramming correlates with worse interview performance.

---

## Mon 5/18 — Interview day

- Light cheat-sheet skim. Draw FOC block diagram once on paper.
- Open laptop, run demo cold, confirm it works.
- Arrive 15 min early.

---

## What you're explicitly not doing

| Skipped | Why it's OK |
|---|---|
| pysoem real-EtherCAT master | DS402 verbal fluency + `sim_link` abstraction is the bar |
| MTPA / FW math | "Negative i_d above base speed" one-liner suffices |
| Induction-motor FOC implementation | Equivalent circuit + V/f vs IFOC narrative covers it |
| HIL hands-on | Namedrop Typhoon/dSPACE/Speedgoat + workflow |
| Three-shunt sampling math | "Synchronized to PWM, mid-low-side" suffices |
| Sensorless implementation | Name BEMF/HFI/EKF + speed-range applicability |

---

## Hourly discipline

- 50/10 Pomodoro. Long break after 4 cycles.
- One topic per block — no syllabus/capstone multitasking inside a block.
- Every passing test → screenshot in `docs/`. These are interview artifacts.
- End each day: update [scorecard.md](scorecard.md). Any topic ≤2 → flag for next morning's first block.

---

## Daily gates (don't paper over failures)

| Day | Pass criterion |
|---|---|
| Tue | FOC block diagram from blank page. PMSM torque eqn. Repo skeleton committed. |
| Wed | Current step in sim matches analytical τ. |
| Thu | **Bode plot artifact captured.** Speed-step screenshot. |
| Fri | DS402 state machine on paper. UI shows live i_d/i_q. README screenshots. |
| Sat | 5-min demo rehearsed cold. Self-pitch <40 s. Cheat sheet refreshed. |

If a gate fails, **next morning's first block** is recovery — don't roll the failure forward silently.

---

## Risk register

- **Tuesday partial-day runs short** → Wed morning absorbs the shortfall; the buffer is built in.
- **Bode harness eats more than budget on Thu** → cut speed-step polish, ship Bode.
- **UI fights you on Fri** → matplotlib + CLI sliders fallback.
- **EtherCAT/DS402 feels shallow Fri morning** → re-read §4.5 (state machine) twice. Most-asked topic.
- **Energy crashes Sat after parkrun** → coffee + 20-min nap, then start. Rehearsal is the week's highest-leverage hour — don't skip.
