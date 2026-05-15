# Module 4 — Communication Protocols (EtherCAT-focused)

**Goal:** Speak EtherCAT fluently enough to integrate Alva's drives with customer master systems, debug a non-working slave, and have an opinion on protocol trade-offs. Secondary: working knowledge of CANopen because EtherCAT inherits its drive profile.

**Time:** 6–10 hours
**Prereq:** Basic Ethernet (MAC frame, switching).

This is the second-highest leverage module for the interview after Module 2.

---

## 4.1 Why EtherCAT for motion

- **Deterministic and fast:** sub-µs jitter, 1 kHz cycle rates for hundreds of axes are routine.
- **Topology flexible:** line, tree, ring, star, hot-connect.
- **Single frame, many slaves:** a master sends one Ethernet frame; each slave reads/writes its portion of the payload on the fly ("processing on the fly").
- **Distributed clocks (DC):** slaves synchronized to <1 µs across the bus.
- **Cost:** royalty-free protocol stack, low-cost ESC ASICs (Beckhoff ET1100, Renesas EC-1, Microchip LAN9252).

For motor control: the master sends a frame every cycle that tells each drive its target (torque/velocity/position), and the drives stuff their actuals into the return path of the same frame.

---

## 4.2 The protocol stack at a glance

```
Application      ┌─────────────────────────────────────────────┐
                 │  CoE (CANopen over EtherCAT, DS402 profile) │
                 │  FoE (firmware update), EoE (tunneled IP), …│
                 ├─────────────────────────────────────────────┤
Mailbox / PDO    │     SDO (config), PDO (cyclic process data)  │
                 ├─────────────────────────────────────────────┤
EtherCAT data    │  EtherType 0x88A4, datagrams, FMMU/SyncMgr  │
                 ├─────────────────────────────────────────────┤
Ethernet         │            standard 802.3 MAC frame          │
                 └─────────────────────────────────────────────┘
```

---

## 4.3 Frame & datagram structure

- Standard Ethernet frame, EtherType **0x88A4**.
- Payload = one or more **EtherCAT datagrams**.
- Each datagram has a **command** (read/write/read-write), an **address** (logical or physical), and a **working counter (WKC)** appended by slaves that successfully processed it.
- Master uses WKC to verify expected slaves participated.

Common commands you'll see in a Wireshark trace:
- `LRD/LWR/LRW` — logical read/write/read-write (FMMU-mapped).
- `BRD/BWR` — broadcast (used at startup).
- `APRD/APWR` — auto-increment physical addressing (used during enumeration).
- `FPRD/FPWR` — fixed physical addressing (after addresses assigned).

---

## 4.4 Sync managers, FMMUs, and the ESC

Inside each slave's **EtherCAT Slave Controller (ESC)**:

- **Sync managers (SM):** buffers for safe exchange between EtherCAT side and microcontroller side. Mailbox SMs are 3-buffer for safe handoff; process-data SMs use buffered or mailbox mode.
- **FMMUs (Fieldbus Memory Management Units):** map a logical address (used by the master) to a physical address (in the slave's RAM) with bit-granularity. This lets the master read/write contiguous chunks across many slaves.
- **DC unit:** local clock disciplined to the reference slave (the first slave with DC capability). Master writes adjustments using `ARMW/FRMW` datagrams to a special register.

You don't program the ESC directly — but you should know these terms when reading docs or chatting with a firmware engineer.

---

## 4.5 PDO vs SDO

**PDO (Process Data Object)** — cyclic data, mapped at startup into one of the SM buffers. Read/written every cycle. Examples:
- RxPDO (master→slave): `controlword`, `target torque`, `target velocity`, `mode of operation`.
- TxPDO (slave→master): `statusword`, `actual position`, `actual velocity`, `actual torque`, `error code`.

**SDO (Service Data Object)** — acyclic, mailbox-based, for configuration. Used to read/write parameters in the slave's **object dictionary** at startup or for tuning. Slower (single request/response per object), but allows arbitrary access.

---

## 4.6 CoE and the CiA 402 (DS402) drive profile

Alva's drives, like virtually every motion drive, implement **CoE** — CANopen application layer carried over EtherCAT — using the **CiA 402** drive profile. You **must** know DS402.

### Object dictionary highlights

| Index | Name | Role |
|---|---|---|
| 0x6040 | Controlword | Master commands (enable, fault reset, halt, etc.) |
| 0x6041 | Statusword | Drive state machine status |
| 0x6060 | Modes of operation | csp, csv, cst, pp, pv, tq, hm |
| 0x6061 | Modes of operation display | Echo of accepted mode |
| 0x607A | Target position | (csp / pp mode) |
| 0x60FF | Target velocity | (csv / pv mode) |
| 0x6071 | Target torque (per mille of rated) | (cst / tq mode) |
| 0x6064 | Position actual value | |
| 0x606C | Velocity actual value | |
| 0x6077 | Torque actual value | |
| 0x603F | Error code | |
| 0x60F4 | Following error actual value | |

### Modes you'll use

- **CSP — Cyclic Synchronous Position:** master streams position setpoints every cycle, drive runs position-velocity-current loops locally. Most common for industrial CNC.
- **CSV — Cyclic Synchronous Velocity:** master streams velocity, drive runs velocity-current loops.
- **CST — Cyclic Synchronous Torque:** master streams torque, drive runs only current loop. Highest control authority on the master side. Used by robots, advanced motion controllers, and your tuning scripts.
- **PP / PV / TQ:** profile modes — drive generates the trajectory itself given a target and motion profile params. Used when master is slow or non-deterministic.
- **HM — Homing:** drive runs an internal homing routine.

### State machine

You should be able to draw this from memory:

```
  Not Ready ──► Switch On Disabled ──► Ready to Switch On ──► Switched On ──► Operation Enabled
                              ▲              │                       │              │
                              │              ▼                       ▼              ▼
                           Fault ◄────────────────────────────── Quick Stop Active
```

Transitions are commanded by writing patterns to `controlword` (0x6040) and observed in `statusword` (0x6041).

---

## 4.7 EtherCAT state machine (master perspective)

Different from DS402 — this is the bus state:

`Init → Pre-Op → Safe-Op → Op`

- **Init:** no mailbox, no PDO. Master writes basic config.
- **Pre-Op:** mailbox active, SDO works. Master configures PDO mapping, sync managers, FMMUs.
- **Safe-Op:** PDOs being exchanged, but **drive outputs are inhibited**.
- **Op:** outputs active, drive responds to RxPDO.

Going **Safe-Op → Op** typically also requires the DS402 state to be in **Operation Enabled** (via controlword).

---

## 4.8 Distributed Clocks (DC) for motion

For multi-axis coordination, every drive must apply its setpoint at the **same instant**, regardless of its position in the cable order. DC accomplishes this:

1. Master measures propagation delays during init.
2. One slave designated **reference clock**; others drift-compensated to it.
3. Master writes a "sync 0" event time into each drive that lands at the same global instant.
4. Drive interrupts on sync 0 → sample feedback, latch new setpoint, kick current loop.

Cycle time for motion is usually 250 µs–1 ms. DC sync jitter below 100 ns is achievable.

---

## 4.9 Tooling

- **Beckhoff TwinCAT** — the de facto master + IDE. Free runtime, license needed for full features. You can build a Windows PC into an EtherCAT master with this.
- **SOEM (Simple Open EtherCAT Master)** — open-source C library. Great for embedded Linux masters and prototypes.
- **pysoem** — Python bindings for SOEM. Excellent for test automation. **Use this in your slimtorq-control prototype.**
- **EtherCAT Explorer / ec_tool** — diagnostic CLIs.
- **Wireshark with EtherCAT dissector** — every interview-ready engineer has cracked open a frame in Wireshark.
- **ESI files (.xml)** — slave description files. Every drive vendor (including Alva) ships one. Tells the master what objects, PDOs, sync managers, and FMMUs to configure.

---

## 4.10 CANopen (quick comparison)

You should be able to talk about CANopen because:
- DS402 lives in both. The object dictionary you learn for CoE applies directly.
- Smaller systems and older customer integrations use CAN.
- "Why EtherCAT over CANopen?" is an obvious interview question.

| Aspect | CANopen | EtherCAT |
|---|---|---|
| Physical | CAN bus, 1 Mbps typical | 100 Mbps Ethernet |
| Determinism | Priority-based, can be tight but limited | Hard real-time, sub-µs |
| Throughput | KB/s | MB/s |
| Topology | Bus | Almost any |
| Wiring cost | Low | Slightly higher (cat5e) |
| Sync | SYNC object (~10 µs jitter typical) | DC (<100 ns) |
| Best for | <16 axes, lower bandwidth | Many axes, hard sync |

---

## 4.11 Other protocols you should namedrop

- **PROFINET** — Siemens ecosystem, used in process automation; isochronous real-time mode similar to EtherCAT.
- **POWERLINK** — open-source-ish, time-slotted Ethernet.
- **EtherNet/IP w/ CIP Motion** — Rockwell ecosystem.
- **SERCOS III** — older but still found in machine tools.
- **STO / safe motion (FSoE — Safety over EtherCAT, CIP Safety, PROFIsafe)** — every modern drive needs to integrate with a functional-safety layer. Know the term **STO (Safe Torque Off)** at minimum.

---

## 4.12 Exercises

1. Install Wireshark with EtherCAT dissector. Find a sample `.pcap` online (or capture from TwinCAT in run mode) and identify: SM2 PDO, SM3 PDO, an SDO transfer, a DC sync write.
2. Read the [SOEM examples](https://github.com/OpenEtherCATsociety/SOEM) — at least `simple_test.c` and `slaveinfo.c`. Understand the init sequence (Init → Pre-Op → Safe-Op → Op).
3. With pysoem, write a script that fakes being a master: enumerate slaves (or your sim), set PDO mapping, transition to Op, send a CST torque command, read back actual torque. Use this as the protocol layer in [09-project.md](09-project.md).
4. Sketch the DS402 state machine from memory and label each transition's controlword pattern.

---

## 4.13 Exit criteria

- [ ] Explain "processing on the fly" in one paragraph.
- [ ] State the difference between PDO and SDO, and when to use each.
- [ ] Draw the DS402 state machine from memory.
- [ ] List the seven operating modes of DS402 and what each is for.
- [ ] Describe DC synchronization and why it matters for multi-axis motion.
- [ ] Pick between CANopen and EtherCAT for a hypothetical 24-axis machine and justify.
