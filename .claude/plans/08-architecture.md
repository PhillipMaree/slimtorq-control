# Module 8 — System Architecture (UI + Backend Engine)

**Goal:** Have a defensible architecture for a tuning tool that an engineer would use on a bench. Two halves: a hard-real-time control engine and a soft-real-time interactive UI. The seams between them — protocol abstraction, telemetry, parameter management — are where the engineering judgment shows.

**Time:** 4–6 hours
**Prereq:** Some software architecture intuition.

---

## 8.1 The three-tier picture

```
┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND (browser or native)                                   │
│  - Gain editors, target setpoints, mode switches                │
│  - Live plots: i_d/i_q, speed, position, following error        │
│  - Test runners: step, bode sweep, trajectory                   │
│  - Persistence: save/load profile, capture export               │
└──────────────────▲──────────────────────────────────────────────┘
                   │ WebSocket (telemetry, commands)
                   │ HTTP/REST (config, profiles, captures)
┌──────────────────▼──────────────────────────────────────────────┐
│  BACKEND ENGINE (Python service)                                │
│  - Connection state machine                                     │
│  - Parameter store (object dictionary mirror)                   │
│  - Telemetry ring buffer + downsampler                          │
│  - Test orchestrator (scripts, sweeps)                          │
│  - Protocol abstraction (DriveLink)                             │
└──────────────────▲──────────────────────────────────────────────┘
                   │ DriveLink interface
       ┌───────────┴───────────┐
       ▼                       ▼
┌──────────────┐       ┌──────────────────┐
│ Sim driver   │       │ EtherCAT driver  │
│ (PMSM model) │       │ (pysoem)         │
└──────────────┘       └──────────────────┘
```

The protocol abstraction is the most important seam: it lets the same backend talk to a simulated motor today and a real EtherCAT slave later.

---

## 8.2 Protocol abstraction (`DriveLink`)

Define the interface in terms of DS402 objects, not transport details:

```python
class DriveLink(Protocol):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def read(self, index: int, subindex: int = 0) -> bytes: ...
    async def write(self, index: int, subindex: int, value: bytes) -> None: ...
    async def set_mode(self, mode: Mode402) -> None: ...
    async def enable(self) -> None: ...
    async def disable(self) -> None: ...
    def subscribe(self, indices: list[int]) -> AsyncIterator[Snapshot]: ...
```

Two implementations:
- **`SimDriveLink`** — talks to the in-process PMSM simulator from Module 7.
- **`EtherCATDriveLink`** — wraps pysoem, configures PDO mapping from an ESI file, runs the cyclic loop.

The frontend never knows which one is connected.

---

## 8.3 Real-time considerations (and where Python falls down)

Python is not hard-real-time. For prep purposes that's OK because:
- The control loop runs **inside the drive** (or inside the sim, which is timed by `dt` not wall clock).
- Python's job is the master cycle (1 kHz comfortable, 4 kHz achievable with care) — orchestration, not inner-loop computation.

**If real-time is needed**, options:
- Linux with PREEMPT_RT kernel, `mlockall`, SCHED_FIFO threads, isolated CPU.
- C/C++ master with SOEM, called from Python via FFI for the time-critical loop.
- Xenomai or RTAI for hard RT on Linux.

For the slimtorq prototype, an asyncio loop at 1 ms cycle is fine. State that as a design choice in the interview, not as a limitation you didn't see.

---

## 8.4 Telemetry pipeline

Requirements:
- Sample at drive's cycle rate (say 1 kHz).
- Buffer recent N seconds for live plotting.
- Downsample for the UI (no UI needs 1 kHz refresh).
- Allow full-rate capture-on-trigger for scope-like screenshots.

Design:
```
DriveLink (1 kHz)  ──►  RingBuffer (10 s × 1 kHz × M signals)
                            │
                ┌───────────┼───────────┐
                ▼           ▼           ▼
         downsampler    trigger     export
         (60 Hz UI)   (capture on)   (CSV/parquet)
                ▼
         WebSocket out
```

Capture-on-trigger is gold for tuning: arm a trigger condition (`step on i_q*` or `fault`), grab the previous 100 ms and next 100 ms at full rate, ship to UI as a scope-like plot.

---

## 8.5 Parameter management

Treat the DS402 object dictionary as the source of truth on the drive side. Your backend mirrors it.

- **Read on connect:** dump dictionary, cache locally.
- **Edit:** user changes a parameter in UI → backend writes via SDO → on success, update local cache; on failure, revert UI.
- **Profiles:** dictionary subset saved as JSON/YAML. Diff and apply.
- **Versioning:** the ESI file declares the object structure; tie profiles to a (vendor, product, revision) tuple so a profile from drive A doesn't get applied to drive B.

---

## 8.6 Test orchestrator

Tests are pure-Python functions over the `DriveLink` and a telemetry stream:

```python
async def current_step_test(drive, mag=2.0, dur=0.05):
    await drive.set_mode(Mode402.CST)
    await drive.enable()
    capture = telemetry.arm(["i_q_meas", "i_q_ref"], pre=0.01, post=dur)
    await drive.set_target_torque(mag)
    await asyncio.sleep(dur)
    await drive.set_target_torque(0.0)
    return await capture.result()
```

Build a small library: step, ramp, sine sweep (Bode), trajectory follow, friction ID, inertia ID. Each returns a capture artifact the UI can plot.

---

## 8.7 Frontend choice

Three reasonable paths:

| Stack | Pros | Cons |
|---|---|---|
| **Plotly Dash / Streamlit** | All-Python, fastest to demo | Limited UX, harder for real-time |
| **FastAPI + React/Vue + Plotly.js** | Production-grade, real-time WS friendly | More code, two languages |
| **PyQt6/PySide6 (native)** | Best real-time plots (pyqtgraph) | Desktop only, dated UX |

For interview demo, **FastAPI + React + Plotly.js** or **PyQt6 with pyqtgraph** are both strong. Pyqtgraph is genuinely fast for live scope-like displays.

---

## 8.8 Where C# fits

The job description mentions C# (TwinCAT's host-side tooling is .NET; many test-automation rigs are C# on Windows talking to TwinCAT or to drives via vendor SDKs). If you have a few extra hours, build a tiny C# console app that connects to your backend's REST/WS API. Demonstrating that you can work in both Python and .NET is a credible signal.

---

## 8.9 Versioning, logging, observability

- **Structured logs** (`structlog` or Python's `logging` with JSON formatter): every command, every fault, with timestamp + drive ID.
- **Captures saved as Parquet:** efficient binary format with schema, replayable.
- **Build info baked in:** firmware version, ESI revision, tool version on every capture.
- **Reproducibility:** every test takes a seed (random initial conditions), stored in capture metadata.

---

## 8.10 Exit criteria

- [ ] Draw the three-tier architecture from memory.
- [ ] Explain why the protocol layer is abstracted and how that lets sim → real-hardware transition.
- [ ] Justify Python for the host side and identify where it would fail in a hard-RT context.
- [ ] Describe the capture-on-trigger telemetry flow.
- [ ] Pick a frontend stack and defend the choice.
