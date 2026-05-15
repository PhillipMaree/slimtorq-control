# Module 9 — Capstone: `slimtorq-control`

**Goal:** Build a runnable demo you can screen-share or describe in detail. Show that you've not just read about FOC but lived through tuning loops in a simulator.

**Time:** open-ended, but a useful MVP is reachable in 15–25 focused hours.
**Prereq:** Modules 2, 4, 7, 8.

---

## 9.1 Scope tiers

Pick a scope based on the time you have. Don't bite off more than you can finish.

### Tier 0 (≈4 h) — Minimum viable
- Python PMSM d-q simulator.
- FOC current loop running in sim.
- Matplotlib plots of step responses.
- README explaining what's there.

### Tier 1 (≈10 h) — Adds speed/position + simple UI
- Speed and position loops on top of FOC.
- Streamlit or Dash UI with sliders for gains + live plot.
- Saveable parameter profiles (JSON).

### Tier 2 (≈20 h) — Adds protocol abstraction
- `DriveLink` interface with `SimDriveLink` implementation.
- DS402-style object dictionary mirror.
- CST mode for torque, CSV for velocity, CSP for position.
- Capture-on-trigger.
- WebSocket telemetry streaming.

### Tier 3 (stretch) — Adds an EtherCAT-like fake transport
- UDP "fake EtherCAT" between host and sim process.
- Or: `pysoem` integration scaffolded so it would talk to a real slave (without actually having one).
- Auto-tuning routine: motor parameter ID + analytical gain computation.

**Aim for Tier 2.** Demo-ready, shows breadth, doesn't require more than two weekends.

---

## 9.2 Suggested repo layout

```
slimtorq-control/
├── pyproject.toml
├── README.md
├── src/
│   └── slimtorq/
│       ├── __init__.py
│       ├── sim/
│       │   ├── pmsm.py          # d-q model + ODE step
│       │   ├── inverter.py      # avg/switched
│       │   └── load.py          # T_load(ω) models
│       ├── control/
│       │   ├── foc.py           # current/speed/position loops
│       │   ├── transforms.py    # clarke/park, inverses
│       │   ├── tuning.py        # analytical gain formulas
│       │   └── modes.py         # DS402 mode enums + state machine
│       ├── link/
│       │   ├── base.py          # DriveLink protocol
│       │   ├── sim_link.py      # in-process sim
│       │   └── ecat_link.py     # pysoem stub
│       ├── engine/
│       │   ├── service.py       # FastAPI app
│       │   ├── telemetry.py     # ring buffer, downsampler
│       │   └── tests/           # step/sweep/etc.
│       └── ui/
│           ├── dash_app.py      # or react/, whatever
│           └── ...
└── tests/
    └── test_*.py
```

---

## 9.3 Build order (this is the actual recipe)

1. **`sim/pmsm.py`** — d-q ODE, parameterizable. Unit test: zero input → zero state; step v_q → exponential current rise matching `τ = L_q / R_s`.
2. **`control/transforms.py`** — Clarke, Park, and inverses. Unit test: round-trip identity.
3. **`control/foc.py`** — current PI loops, decoupling FF. Test: step `i_q*` in sim, measure rise time and overshoot.
4. **`control/tuning.py`** — given (R, L, BW) return (Kp, Ki). Plug into 3 and verify match.
5. Speed loop. Step ω*, measure rise time. Identify J from a torque step in sim.
6. Position loop. Move test.
7. **`link/base.py` + `link/sim_link.py`** — wrap the sim as a DS402-shaped interface.
8. **`engine/service.py`** — FastAPI app exposing `/parameters`, `/captures`, `/ws`.
9. **`engine/telemetry.py`** — ring buffer + downsample + trigger capture.
10. **`engine/tests/`** — step, sweep (frequency response), trajectory.
11. UI: at minimum a page with gain inputs, mode selector, live plot, capture viewer.
12. Stretch: `link/ecat_link.py` skeleton with pysoem — connect, scan, dump OD. Even without a slave, the scaffolding tells the interviewer you know what's involved.

---

## 9.4 The "Bode plot" demo (worth doing for the interview)

Few things land harder in a motor-control interview than showing a measured-from-sim Bode plot of your current loop matching the designed transfer function.

Procedure:
1. With `i_q_ref` driven by `A·sin(ω·t)` at varying ω, capture `i_q_meas`.
2. Compute magnitude and phase at each ω.
3. Plot vs. theoretical first-order at `ω_bw_i`.
4. Show that increasing Kp by 10× without changing Ki shifts the phase margin and produces overshoot.

This single artifact proves you can connect theory → implementation → measurement.

---

## 9.5 Demo script (for the interview)

Have a 5-minute walkthrough rehearsed:

1. *"Here's the architecture — UI, engine, protocol layer, sim."*
2. *"I'll connect to the sim, dump the object dictionary like a real DS402 drive."*
3. *"Switch to CST mode, command a torque step. Notice the current loop response — first-order, no overshoot, BW matches the design value I computed from R and L."*
4. *"Switch to CSV. Command a speed step. Notice the speed loop response is roughly 5× slower, by design."*
5. *"Run a Bode sweep — measured matches theoretical."*
6. *"Drop in different motor parameters — the auto-tuner regenerates gains."*
7. *"Behind the link is a DriveLink interface. The sim driver could be swapped for a real EtherCAT driver with the same API."*

Even a Tier 1 demo with the first three points lands well.

---

## 9.6 What to omit

You will be tempted to:
- Build a beautiful UI. Don't. Functional > pretty.
- Write a real EtherCAT master. Don't. The pysoem-shaped stub is the right level.
- Model thermal effects. Don't, unless Tier 3.
- Add induction motor model. Skip unless you have time after the demo is solid.

---

## 9.7 Exit criteria

- [ ] Repo runs end-to-end with `pip install -e . && python -m slimtorq.ui.dash_app`.
- [ ] A `README.md` walks a new viewer through what the project is and what to click.
- [ ] At least one captured Bode plot and one step response screenshot saved to `docs/`.
- [ ] A short rehearsed verbal demo of the project.
