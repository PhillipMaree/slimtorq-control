# Self-Assessment Scorecard

Score: 1 = never heard of it, 5 = could teach it. Re-score after each module.

**Pacing chosen:** ____________ (sprint / standard / thorough)
**Start date:** ____________
**Target interview date:** ____________

---

## Baseline (from 00-overview.md gap assessment)

| Score | Topic | Module |
|:---:|---|:---:|
| 2 | Three-phase AC fundamentals (phasors, balanced systems) | 1 |
| 1 | PMSM vs BLDC vs induction motor construction & physics | 1 |
| 1 | Park / Clarke transforms; d-q frame intuition | 2 |
| 1 | Field-Oriented Control (FOC) block diagram from memory | 2 |
| 3 | Current/speed/position cascaded loop tuning | 2, 5 |
| 3 | PID variants (anti-windup, feedforward, 2-DOF) | 2 |
| 1 | Encoder types (incremental, absolute, SinCos, resolver, Hall) | 3 |
| 2 | Current sensing topologies (shunt vs Hall, single vs three-shunt) | 3 |
| 1 | Space Vector Modulation (SVM/SVPWM) | 2 |
| 1 | EtherCAT frame structure, DC sync, CoE/DS402 | 4 |
| 2 | CANopen basics | 4 |
| 2 | Reading schematics, IGBT/MOSFET gate drives, dead-time | 6 |
| 3 | Oscilloscope use on a switched system | 6 |
| 2 | Power analyzer measurements (efficiency, η, THD) | 6 |
| 1 | Induction motor scalar (V/f) vs vector control | 1 |
| 1 | HIL concepts and platforms | 7 |
| 4 | Python data viz / real-time UI (PyQt, Plotly Dash, Streamlit) | 8, 9 |

**Distribution:** 7 × level-1, 5 × level-2, 3 × level-3, 1 × level-4, 0 × level-5.

**Profile read:** software-strong, control/EM-light. Module 1, 2, 3, 4, 7 need depth. Modules 5, 6, 8 mostly need refresh and judgment. Capstone (9) will be fast once the theory is in.

---

## Recommended study order (tailored to your scores)

Adjusted from the default order in [00-overview.md](00-overview.md) — Module 7 pulled earlier because the capstone needs it, and Modules 5/6/8 deferred to refresh after foundations land:

| Pass | Module | Why | Allocate |
|:---:|---|---|---|
| 1 | 1 — Motors & Alva | All 1s & 2s here | 5 h |
| 2 | 2 — Control / FOC | All 1s here, highest interview leverage | 10 h |
| 3 | 3 — Sensors | Encoders at 1 | 4 h |
| 4 | 4 — Communication | EtherCAT at 1 | 8 h |
| 5 | 7 — Simulation | Unlocks capstone | 6 h |
| 6 | 9 — Capstone Tier 1 → 2 | Python UI is your strength — bank that early win | 12 h |
| 7 | 5 — Tuning | Refresh + bench recipe rehearsal | 4 h |
| 8 | 6 — Lab Equipment | Light read | 2 h |
| 9 | 8 — Architecture | Skim — you already know this stack | 2 h |
| 10 | 10 — Interview cheat sheet | Day before | 2 h |

**Total: ~55 hours** + capstone polish. Standard-mode (3 weeks) realistic at ~18 h/week.

---

## Per-module progress

### Module 1 — Motors & Alva
| Topic | Pre | Post |
|---|:---:|:---:|
| PMSM construction & physics | 1 | _ |
| Slotless / FiberPrinting implications for control | 1 | _ |
| BLDC vs PMSM (trap vs sinusoidal) | 1 | _ |
| Induction motor equivalent circuit | 1 | _ |
| V/f vs vector control trade-offs | 1 | _ |
| Motor characterization on the bench | 1 | _ |
| Three-phase AC fundamentals | 2 | _ |

### Module 2 — Control / FOC
| Topic | Pre | Post |
|---|:---:|:---:|
| PI design & pole-zero cancellation | 3 | _ |
| Clarke / Park transforms | 1 | _ |
| FOC block diagram from memory | 1 | _ |
| SVPWM | 1 | _ |
| Current loop analytical tuning | 3 | _ |
| Speed/position cascaded tuning | 3 | _ |
| Sensorless (BEMF, HFI, EKF) | 1 | _ |
| MTPA / field weakening | 1 | _ |

### Module 3 — Sensors
| Topic | Pre | Post |
|---|:---:|:---:|
| Encoder taxonomy (inc/abs/SinCos/resolver) | 1 | _ |
| Hall sensors for FOC startup | 1 | _ |
| Speed estimation (M/T methods) | 2 | _ |
| Current sensing topologies | 2 | _ |
| Sampling timing relative to PWM | 2 | _ |

### Module 4 — Communication
| Topic | Pre | Post |
|---|:---:|:---:|
| EtherCAT frame & processing-on-the-fly | 1 | _ |
| Sync managers, FMMU, DC | 1 | _ |
| PDO vs SDO | 1 | _ |
| DS402 state machine | 1 | _ |
| DS402 modes (CSP/CSV/CST/PP/PV/TQ/HM) | 1 | _ |
| CANopen basics | 2 | _ |
| EtherCAT vs other protocols | 1 | _ |

### Module 5 — Tuning
| Topic | Pre | Post |
|---|:---:|:---:|
| Encoder zero-offset calibration | 1 | _ |
| Inertia identification | 2 | _ |
| Velocity / accel feedforward | 3 | _ |
| Notch filters for resonance | 2 | _ |
| Friction comp & disturbance observers | 2 | _ |
| Unknown-motor end-to-end recipe | 1 | _ |

### Module 6 — Lab Equipment
| Topic | Pre | Post |
|---|:---:|:---:|
| Scope probe selection | 3 | _ |
| Differential / current probes | 2 | _ |
| Power analyzer concepts | 2 | _ |
| Dynamometer fundamentals | 1 | _ |
| Bench safety culture | 3 | _ |

### Module 7 — Simulation / HIL
| Topic | Pre | Post |
|---|:---:|:---:|
| d-q PMSM ODE model | 1 | _ |
| PWM/inverter avg vs switched models | 1 | _ |
| Control/plant time-base separation | 2 | _ |
| HIL platforms (Typhoon, dSPACE, etc.) | 1 | _ |

### Module 8 — Architecture
| Topic | Pre | Post |
|---|:---:|:---:|
| Three-tier UI/engine/protocol layout | 3 | _ |
| Protocol abstraction for sim ↔ real | 3 | _ |
| Telemetry ring + trigger capture | 3 | _ |
| Real-time constraints in Python | 3 | _ |
| Frontend stack trade-offs | 4 | _ |

### Module 9 — Capstone
| Milestone | Done? |
|---|:---:|
| Tier 0 — PMSM sim + current loop | _ |
| Tier 1 — speed/position + UI | _ |
| Tier 2 — DriveLink + DS402 mirror + WS telemetry | _ |
| Tier 3 — EtherCAT scaffolding | _ |
| Bode plot artifact captured | _ |
| Demo rehearsed (5 min) | _ |

### Module 10 — Interview prep
| Item | Done? |
|---|:---:|
| Self-pitch refined | _ |
| Whiteboard bank rehearsed | _ |
| Questions-to-ask list prepared | _ |
| Morning-of routine pinned | _ |
