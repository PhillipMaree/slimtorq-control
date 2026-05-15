# Motion Control Systems Engineer — Interview Prep Syllabus

**Target role:** Motion Control Systems Engineer, Alva Industries
**Reference:** https://www.alvaindustries.com/
**Repo project:** `slimtorq-control` — companion tool to operationalize the learning (UI + backend engine + simulated motor interface)

---

## 1. Strategic framing

Alva Industries builds high-power-density **slotless PMSM** motors using their proprietary **FiberPrinting** stator manufacturing process. Their target markets are aerospace/drones, robotics, and high-performance industrial applications where torque-to-weight matters.

The job description signals that the role splits roughly into three tracks:

| Track | What you'll do | What you must know |
|---|---|---|
| **Bench / lab** | Tune controllers, characterize motors, integrate 3rd-party drives | FOC, PID, scopes, power analyzers, encoders |
| **Integration** | Make motors talk to customer systems | EtherCAT (CoE/DS402), CANopen, schematics |
| **Tooling** | Automate tests, build tuning workflows | Python/C#, frontends, data pipelines |

**The interview narrative you want to land:** *"I can show up on day one, plug into a motor on the bench, characterize it, design a control loop around it, validate over a protocol like EtherCAT, and wrap the whole workflow in a repeatable automated test."*

---

## 2. Honest gap assessment (do this first)

Before opening any module, score yourself 1–5 on each topic. Anything ≤3 becomes a study priority. Anything ≥4 just needs a refresher.

- [2] Three-phase AC fundamentals (phasors, balanced systems)
- [1] PMSM vs BLDC vs induction motor construction & physics
- [1] Park / Clarke transforms; d-q frame intuition
- [1] Field-Oriented Control (FOC) block diagram from memory
- [3] Current/speed/position cascaded loop tuning
- [3] PID variants (anti-windup, feedforward, 2-DOF)
- [1] Encoder types (incremental, absolute, SinCos, resolver, Hall)
- [2] Current sensing topologies (shunt vs Hall, single vs three-shunt)
- [1] Space Vector Modulation (SVM/SVPWM)
- [1] EtherCAT frame structure, DC sync, CoE/DS402
- [2] CANopen basics
- [2] Reading schematics, IGBT/MOSFET gate drives, dead-time
- [3] Oscilloscope use on a switched system (probes, grounding, math channels)
- [2] Power analyzer measurements (efficiency, η, THD)
- [1] Induction motor scalar (V/f) vs vector control
- [1] HIL concepts and platforms (Typhoon HIL, dSPACE, Speedgoat)
- [4] Python data viz / real-time UI (PyQt, Plotly Dash, Streamlit)

Write your scores into [scorecard.md](scorecard.md) (create as you go).

---

## 3. Module roadmap

Each module is in its own file. Suggested order is top-down; later modules assume earlier ones.

| # | Module | File | Time est. |
|---|---|---|---|
| 1 | Motor fundamentals & Alva's technology | [01-motors-and-alva.md](01-motors-and-alva.md) | 4–6 h |
| 2 | Control theory & FOC | [02-control-foc.md](02-control-foc.md) | 8–12 h |
| 3 | Sensors, encoders, current sensing | [03-sensors-feedback.md](03-sensors-feedback.md) | 4–6 h |
| 4 | Communication: EtherCAT (primary) + CANopen | [04-communication.md](04-communication.md) | 6–10 h |
| 5 | Tuning strategies (current/speed/position) | [05-tuning.md](05-tuning.md) | 6–8 h |
| 6 | Lab equipment & measurement | [06-lab-equipment.md](06-lab-equipment.md) | 2–4 h |
| 7 | Simulation & HIL (since no real motor) | [07-simulation-hil.md](07-simulation-hil.md) | 6–10 h |
| 8 | System architecture (UI + backend engine) | [08-architecture.md](08-architecture.md) | 4–6 h |
| 9 | `slimtorq-control` capstone project | [09-project.md](09-project.md) | open-ended |
| 10 | Interview-day cheat sheet | [10-interview.md](10-interview.md) | 2 h |

**Total focused study time: ~50–70 hours.** Front-load 2 and 4 — they carry the most interview weight.

---

## 4. Pacing recommendation

- **5-day sprint:** see [5-day-sprint.md](5-day-sprint.md) — concrete day-by-day plan tailored to your baseline scores. **This is the active plan.**
- **Sprint mode (1 week):** Modules 1, 2, 4, 10 + light skim of others. Build a minimal FOC simulation in [09-project.md](09-project.md).
- **Standard (3 weeks):** All modules in order. Capstone target: working FOC sim + a tuning UI that streams currents/speed and lets you adjust gains live.
- **Thorough (6 weeks):** All modules + induction motor module deep dive + EtherCAT slave simulator + automated tuning routine.

---

## 5. The capstone — `slimtorq-control`

The repo this syllabus lives in is your sandbox. The end goal is a tool you can demo or describe in the interview:

> *"I built a tuning environment that simulates a PMSM under FOC, exposes the control loop over a fake EtherCAT-like interface, and lets you tune current/speed/position loops from a web UI with live scope traces."*

Architecture sketch (details in [08-architecture.md](08-architecture.md) and [09-project.md](09-project.md)):

```
┌─────────────────┐    ws/http     ┌──────────────────┐    ─── stub ───►  ┌──────────────┐
│  Frontend UI    │ ◄────────────► │  Backend engine  │  (EtherCAT-like)  │ Motor + load │
│  (gains, plots) │                │  (FOC, scheduler)│  ◄────────────►   │  simulator   │
└─────────────────┘                └──────────────────┘                   └──────────────┘
```

The simulator stands in for the HIL/motor you don't have. The protocol stub is deliberately abstracted so it can later be swapped for a real EtherCAT master (SOEM bindings) without rewriting the engine.

---

## 6. Daily/weekly study ritual

- Start each session by re-reading your scorecard.
- Pick **one** module, **one** subsection. Read → take notes in your own words → answer the self-check.
- End each session by updating your scorecard score for that subsection.
- Once a week, do a "blank page test": close everything, sketch the FOC block diagram, label every signal. If you can't, you don't know it yet.

---

## 7. What success looks like

You should be able to whiteboard, in the interview, without notes:

1. The FOC block diagram for a PMSM, including Clarke/Park, current PI loops, SVM, and the inverse transforms.
2. How you'd tune the current loop given motor R, L (analytical pole-zero cancellation).
3. How an EtherCAT cyclic frame moves target torque from a master to a drive and brings back actual current/position.
4. How you'd characterize an unknown motor on the bench (R, L_d, L_q, λ_PM, J, B).
5. The differences (and tuning implications) between controlling a PMSM and a squirrel-cage induction motor.
6. How you'd architect a tuning tool that needs hard-real-time control plus a soft-real-time UI.

If you can do all six unaided, you're ready.
