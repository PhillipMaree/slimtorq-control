# slimtorq-control

Python-side **Field-Oriented Control (FOC)** for an OpenModelica slotless-PMSM
motor model, with a real **PWM + inverter** in the loop, dead-time emulation,
selectable PWM modulation (sine / SVPWM / DPWMMAX / DPWMMIN / DPWM1 / auto
hybrid), optional **LCL output filter** between inverter and motor (component
values derived from a cutoff target), modulus-optimum / pole-zero-cancellation
current-loop tuning, and a single-container web UI: a **FastAPI** Python
service exposing the simulator over HTTP at `/api/*` and serving a prebuilt
**Next.js + Apache ECharts** static bundle at `/` for the 12 diagnostic plots.

The motor is parameterised from [config/catalog.yaml](config/catalog.yaml) against the Alva
**SlimTorq** lineup (9 families × ~12 winding configurations ≈ 86 entries).

## Architecture

One container, one port. FastAPI hosts `/api/*` (the simulator) and `/`
(the static Next.js bundle). The React app POSTs a 28-field `SimParams`
JSON, gets metadata back, fetches the trace as Apache Arrow IPC, and
renders 12 ECharts figures client-side. Parquet artifacts (with
`slimtorq.*` metadata) remain the canonical persistence — external
consumers (polars, duckdb, …) read them unchanged.

```mermaid
flowchart LR
    subgraph Frontend["Browser — Next.js static bundle"]
        direction TB
        F1["ConfigPanel<br/>(28 react-hook-form inputs)"]
        F1 -->|"POST /api/simulate"| F2
        F2["lib/api.ts<br/>Arrow IPC decode"]
        F2 --> F3["PlotPanel<br/>12 ECharts modules"]
    end

    subgraph API["src/api.py — FastAPI (single process, port 8000)"]
        direction TB
        STATIC["StaticFiles('/' → frontend/out)"]
        A1["POST /api/simulate → SimParams<br/>blake2b hash + run_simulation()"]
        A1 --> A2["simulator.run_simulation"]
        A2 --> A3["write_parquet (slimtorq.* metadata)"]
        A4["GET /api/simulate/{hash}/data → Arrow IPC"]
        A5["GET /api/catalog · /api/defaults · /api/artifacts/{hash}.parquet"]
    end

    subgraph Pipeline["Simulator — orchestrates per-tick signal flow"]
        direction LR
        TL["TL_ref(t)"] --> C
        C["controller<br/>(FOCController)<br/>Clarke → Park → 2× PI<br/>→ dq decoupling + BEMF FF<br/>→ vector sat → InvPark → InvClarke"]
        C -->|"v_a_ref, v_b_ref, v_c_ref"| I
        I["inverter<br/>(PWM + dead-time)"]
        I -->|"v_a, v_b, v_c"| M
        M["motor<br/>PMSMAbcModel (FMU)"]
        M -->|"i_abc, θ_m, ω_m, T_e"| E
        E["encoder<br/>EncoderMeasurement<br/>θ_e_meas = p · θ_m_meas mod 2π"]
        E -->|"i_abc_meas, θ_e_meas, ω_e_meas"| C
    end

    Frontend -.-|"HTTP + Arrow IPC"| API
    API -.-|"builds + drives"| Pipeline
```

**Clocks.** Two outer clocks plus one inside the encoder:

- `T_s` — inner simulation step (FMU `doStep`, PWM carrier comparison, inverter dead-time tracking). Default `T_pwm/20`; a `T_s ≤ T_pwm/10` floor in `Simulator.run` enforces ≥10× oversampling of the carrier.
- `dt_ctrl = 1 / controller.f_pwm` — FOC current-loop tick (one FOC update per PWM cycle, the standard digital-FOC convention).
- `Ts_enc` — encoder sample period, lives inside `FluxEncoder`.

The PWM modulator is owned by the `Inverter` — `Inverter.step()` does PWM compare + dead-time-aware leg voltages in one call. Between FOC ticks the FOC's last `v_abc_ref` is held by ZOH and fed into the inverter every `T_s`.

## Physical effects modelled

Why this architecture (and not the simpler "FOC outputs continuous v_abc straight to the motor"):

| Effect | Where it's modelled | What you see |
|---|---|---|
| **Switching ripple** in i_abc at f_pwm | Naturally — `Inverter` emits square ±Vdc/2 phase voltages; FMU integrates them. | Triangular ripple of amplitude `≈ Vdc·T_pwm/(8·L_s)` on top of the fundamental current. Drives iron losses, EMI, audible noise, current-sensor bandwidth. |
| **Dead time** (1–3 µs gate-driver blanking) | `Inverter` tracks per-leg t_since_edge; during the t_dead window, freewheel diode clamps v_k = −sign(i_k)·Vdc/2. | 5th + 7th harmonic distortion in i_abc; small low-frequency torque ripple FOC's integrator absorbs. Set `t_dead = 0` to disable. |
| **Vdc utilisation limit** (sinusoidal-PWM linear range `\|v_phase\| ≤ Vdc/2`) | `FOCController` clips `(v_d, v_q)` to magnitude `V_max = Vdc/2` *before* inverse Park. Anti-windup freezes both integrators when the vector saturates. | Beyond the envelope, achievable torque plateaus; the PI-performance plot's `\|v_dq\|` trace clamps at the red line. |
| **dq cross-coupling + BEMF** (`−ω_e·L_s·i_q` on d-axis; `+ω_e·L_s·i_d + ω_e·ψ_m` on q-axis) | `FOCController` adds them as feedforward to the raw PI output (so the per-axis plant the PI sees collapses to a pure R/L circuit; vector saturation acts on the combined PI + FF command). | At high speed the BEMF term `ω_e·ψ_m` dominates v_q; without feedforward the PI integrator absorbs it with tracking lag. With feedforward, i_q tracks immediately and the integrator only handles modelling error. |

## One tick of the inner loop

```mermaid
sequenceDiagram
    autonumber
    participant SIM as Simulator
    participant M as motor (PMSMAbcModel)
    participant E as encoder
    participant C as controller (FOC)
    participant I as inverter (PWM + dead-time)

    SIM->>M: measure()
    M-->>SIM: i_abc, θ_m, ω_m, T_e
    SIM->>E: step(θ_m, ω_m, i_abc, t)
    E-->>SIM: θ_m_meas, ω_m_meas, θ_e_meas, i_abc_meas
    alt control-tick boundary (every dt_ctrl)
        SIM->>C: step(i_abc_meas, θ_e_meas, ω_e_meas, i_d_ref, i_q_ref, dt_ctrl)
        C-->>SIM: v_a_ref, v_b_ref, v_c_ref
    end
    SIM->>I: step(v_*_ref, i_abc, t, T_s)
    I-->>SIM: d_abc, s_abc, v_a, v_b, v_c (post-inverter)
    SIM->>M: step(v_abc, T_L, T_s)
```

Between FOC ticks the v_*_ref values are held by ZOH and fed into the inverter every `T_s`, so the power stage runs at the carrier-resolution timescale while the FOC integrates only once per PWM period.

## Modules

```mermaid
graph TD
    catalog["config/catalog.yaml"]
    model["model.py
    Pydantic schema +
    load_catalog()"]
    tuning["tuning.py
    auto_pi_gains_from_bw
    modulus_optimum_tuning
    skogestad_tuning"]
    transform["transform.py
    Clarke / Park /
    inverses"]
    controller["controller.py
    PIController
    FOCController"]
    encoder["encoder.py
    FluxEncoder
    EncoderMeasurement"]
    switching["switching.py
    PWMModulator (private)
    Inverter (PWM + dead time)
    PMSMAbcModel"]
    fmu["modelica/
    SlotlessPMSM_abc.fmu"]
    simulator["simulator.py
    Simulator orchestrator +
    SimParams pipeline +
    parquet I/O (run_simulation)"]
    server["server.py
    FastAPI service"]
    parquet[".temp/
    *.parquet
    (gitignored)"]
    frontend["frontend/
    Next.js + ECharts UI
    (12 figure modules)"]

    catalog --> model
    model --> controller
    model --> switching
    model --> encoder
    model --> simulator
    tuning --> controller
    tuning --> simulator
    transform --> controller
    encoder --> simulator
    controller --> simulator
    switching --> simulator
    fmu --> switching
    simulator --> parquet
    simulator --> server
    server --> frontend
    parquet --> server
```

| File | Role |
|---|---|
| [modelica/Alva.mo](modelica/Alva.mo) | `SlotlessPMSM_abc`: surface-PM motor, abc external interface, dq internal dynamics on the **true** rotor angle, optional 6th-electrical-harmonic torque ripple. |
| [modelica/build_fmu.mos](modelica/build_fmu.mos) | `omc` build script producing `SlotlessPMSM_abc.fmu`. |
| [config/catalog.yaml](config/catalog.yaml) | Nested family → variant → winding data. Every cell is `{unit, value}` so units are explicit. |
| [src/model.py](src/model.py) | All Pydantic v2 models — catalog-parsing schema, the `MotorSku` + `decode_sku` serial decoder (catalog REV1.8 p.28), the `CatalogMotor` connection-aware computed-field bridge (R_s / L_s / ψ_m / J per p.35), the simulation-facing flat types (`PmsmModel`, `EncoderConfig`, `FocConfig`, `InverterConfig`, `TLRef`), and the catalog loader. `python -m src.model` exercises the decoder, prints the STM-75-20-L-4Y worked example, then cross-checks every variant against its catalog continuous-torque. |
| [src/tuning.py](src/tuning.py) | Pure functions `auto_pi_gains_from_bw(R, L, bw_hz)` (pole-zero cancellation), `modulus_optimum_tuning(R, L, f_pwm)` (Leonhard / Schroeder MO), and `skogestad_tuning(R, L, f_pwm, k1, Tc)` (Skogestad SIMC, Haugen §7.5 Table 7.1 row 2; defaults `k1=1.44` and `Tc=1.5/f_pwm` per Haugen footnote 11 and eq. 7.91). |
| [src/transform.py](src/transform.py) | Amplitude-invariant Clarke / Park + composed `abc_to_dq`, `dq_to_abc`. `python transform.py` round-trip self-test. |
| [src/controller.py](src/controller.py) | `PIController` (parallel-form PI with split unsaturated/integrate API for shared anti-windup), `FOCController` (Clarke → Park → 2× PI → **dq decoupling + BEMF feedforward** → **vector saturation** → InvPark → InvClarke). Exposes `f_pwm` so the Simulator can derive `dt_ctrl`. |
| [src/encoder.py](src/encoder.py) | `FluxEncoder` (sample-and-hold + 3-harmonic cyclic error + N-bit quantization), `EncoderMeasurement` (composite wrapper adding `θ_e_meas` + i_abc pass-through). |
| [src/switching.py](src/switching.py) | `PWMModulator` (centered triangular-carrier compare with selectable zero-sequence injection: sine / svpwm / dpwmmax / dpwmmin / dpwm1 / auto-hybrid), `Inverter` (PWM compare + gate-driver dead-time via freewheel-diode model — one `step()` does both), `LCLFilter` (optional per-phase Python-side LCL low-pass between inverter terminals and motor, integrated by forward Euler at the simulator's inner step), `PMSMAbcModel` (thin FMU wrapper). |
| [src/simulator.py](src/simulator.py) | Two layers. (1) `Simulator(motor, encoder, controller, inverter)` — the multi-rate orchestrator. Context-managed (`with … as sim`) so the FMU is released on exit. `sim.run(TL_ref, T_s, T_f)` drives the multi-rate loop (`T_s` inner, `dt_ctrl = 1/f_pwm` for FOC, `Ts_enc` inside the encoder) and returns a `polars.DataFrame`. (2) `run_simulation(SimParams) -> (df, SimMeta)` — the headless pipeline: canonical-params blake2b hashing, `write_parquet` with `slimtorq.*` metadata, tracking-error summary, and the motor catalog loaded at import (`CATALOG: dict[str, PmsmModel]`). |
| [src/server.py](src/server.py) | FastAPI app + uvicorn server. `get_app()`/`get_server()` are cached lazily; `run()` awaits `serve()`. Routes: `GET /health · /catalog · /defaults`, `POST /simulate` (returns `SimMeta` JSON), `GET /simulate/{hash}/data` (Apache Arrow IPC stream of the trace), `GET /artifacts/{hash}.parquet` (raw parquet download). CORS allow-list comes from [config/app.yaml](config/app.yaml). |
| [src/main.py](src/main.py) | Async entrypoint: `asyncio.run(server.run())`. |
| [frontend/](frontend/) | Next.js (App Router) + Apache ECharts UI. `app/page.tsx` composes `<ConfigPanel>` (28 react-hook-form inputs in sections: motor / inverter / LCL / encoder / trajectory / timing / PI / debug) and `<PlotPanel>` (12 figure modules under `components/PlotPanel/figures/`: tracking, piPerformance, vdqRoundtrip, iqZoom, iqFft, omegaFft, phaseCurrents, iabcFft, phaseVoltages, duties, encoderError, speedAndSaturation). `lib/api.ts` POSTs `/simulate` and fetches the Arrow trace; `lib/arrow.ts` exposes typed-array column accessors; `lib/fft.ts` runs the rFFT for the three spectrum figures; `lib/palette.ts` mirrors the three Alva CSS variables (`#1A1A1A`, `#E0543F`, `#5B5B5B`). Figure titles use KaTeX. |

## Equations

**Clarke / Park** (amplitude-invariant 3 → 2)

```
v_α = (2/3)·(v_a − 0.5·v_b − 0.5·v_c)
v_β = (1/√3)·(v_b − v_c)
v_d =  cos(θ_e)·v_α + sin(θ_e)·v_β
v_q = −sin(θ_e)·v_α + cos(θ_e)·v_β
```

**dq stator dynamics** (L_d = L_q = L_s for slotless surface-PM)

```
v_d = R_s·i_d + L_s·di_d/dt − ω_e·L_s·i_q
v_q = R_s·i_q + L_s·di_q/dt + ω_e·L_s·i_d + ω_e·ψ_m
```

**dq decoupling + BEMF feedforward** (added to the raw PI output, before vector saturation, so each PI sees a pure R/L plant)

```
ff_d = −ω_e_meas · L_s · i_q_meas
ff_q =  ω_e_meas · L_s · i_d_meas + ω_e_meas · ψ_m
v_d_raw = PI_d + ff_d
v_q_raw = PI_q + ff_q
```

**Vector saturation** before inverse Park

```
|v_dq|² > V_max² = (Vdc/2)²  ⇒  scale (v_d, v_q) by V_max/|v_dq|
                                  freeze both PI integrators
```

**PI tuning rules** (all three ship in [src/tuning.py](src/tuning.py))

```
auto / pole-zero cancellation:   K_p = L_s·2π·bw_hz,   K_i = R_s·2π·bw_hz
modulus optimum (T_σ = 1.5/f_pwm):  K_p = L_s·f_pwm/3,   K_i = R_s·f_pwm/3
Skogestad SIMC (τ = 1.5/f_pwm, default T_c = τ):
    K_p = L_s / (T_c + τ),  T_i = min(L_s/R_s, k1·(T_c + τ)),  K_i = K_p / T_i
    (k1 = 1.44 default; k1 = 4 for textbook critically-damped disturbance step)
```

**Centered sinusoidal PWM**

```
d_k = clip(0.5 + v_k_ref / Vdc, 0, 1)               k ∈ {a, b, c}
s_k = 1 if d_k > carrier(t) else 0                  triangle, period T_pwm
```

**Inverter output** (sign(i_k) is the post-FMU measured current direction)

```
outside dead time:   v_k = (s_k − 0.5) · Vdc
inside  dead time:   v_k = −sign(i_k) · Vdc/2       (freewheel diode)
```

**Electromagnetic torque** (with optional 6th-electrical-harmonic ripple)

```
T_e_dq = 1.5 · p · ψ_m · i_q
T_e    = T_e_dq · (1 + ripple_pct · sin(6·θ_e + φ_ripple))
```

**Mechanical**

```
J · dω_m/dt = T_e − T_L − B·ω_m
dθ_m/dt = ω_m
```

**Torque → current ref** (surface-PM ⇒ i_d_ref = 0)

```
i_q_ref = T_e_ref / (1.5 · p · ψ_m)
```

## Motor serial decoding (catalog REV1.8 p.28)

Every SlimTorq motor is identified by a nine-segment serial number
(`MotorSku` + `decode_sku` in [src/model.py](src/model.py)):

```
STM-130-27-L-4Y-A-18A-A0-001
 │   │   │  │  │  │  │   │  │
 │   │   │  │  │  │  │   │  └── unique_id     3 digits
 │   │   │  │  │  │  │   └───── sensor        Temp + Position (A–Z, "0" = none)
 │   │   │  │  │  │  └───────── cable         AWG(1-99) + Type(A–Z)
 │   │   │  │  │  └──────────── terminal      A = Axial / R = Radial
 │   │   │  │  └─────────────── winding       series_turns + Y(star) / D(delta)
 │   │   │  └────────────────── variant       L = Lite / M = Max
 │   │   └───────────────────── axial_length  Stator length (mm)
 │   └───────────────────────── stator_od     Stator OD (mm)
 └───────────────────────────── series        STM = SlimTorq Motor
```

The short five-segment form (`STM-75-20-L-4Y`) is the catalog key and the
filename stem for cached parquets in `.temp/` (gitignored). The
winding code's connection letter (`Y` vs `D`) drives the phase-impedance
decomposition below.

## Datasheet → dq conversions (catalog REV1.8 p.35)

Catalog values are line-to-line and Arms-referenced. `CatalogMotor` in
[src/model.py](src/model.py) derives each phase-domain parameter as a
`@computed_field` whose docstring carries the page-35 formula:

```
                                  ┌─ Star  (Y):  R_phase = 0.5 · R_LL
R_s  [Ohm]   ── from R_LL   ──────┤
                                  └─ Delta (D):  R_phase = 1.5 · R_LL

                                  ┌─ Star  (Y):  L_phase = 0.5 · L_LL · 1e-6
L_s  [H]     ── from L_LL_uH ─────┤
                                  └─ Delta (D):  L_phase = 1.5 · L_LL · 1e-6

ψ_m  [Wb]    = K_T / (1.5 · p · √2)        amp-inv Clarke ⇒ i_q_peak = √2·I_q_rms
J    [kg·m²] = J_gcm² · 1e-7
p            = common.pole_pairs
Vdc  [V]     = motor.rated_voltage (default; UI-overridable)
```

Worked example — **STM-75-20-L-4Y** (Star, 4 series turns, Lite):
`R_LL=0.457 Ω, L_LL=15.4 µH, K_T=0.109 Nm/Arms, p=18, J_gcm²=620` →
`R_s=0.2285 Ω, L_s=7.7 µH, ψ_m=2.85 mWb, J=6.2e-5 kg·m²`.

**Note — Delta windings.** Phase impedance is the physical winding value
(`1.5·R_LL`, `1.5·L_LL`), not a Y-equivalent transform. This is the literal
page-35 definition; if a future revision of the dq sim wants star-equivalent
quantities for delta motors, that conversion belongs downstream of
`CatalogMotor`, not inside its derivations.

## Getting started

The fastest path is the **prebuilt Docker image** — no Python, no `uv`, no
OpenModelica toolchain on the host. Use the source-build path only if you
plan to edit the code or rebuild the Modelica plant.

### Option A — Docker (recommended, one call)

The whole app (FastAPI + the static Next.js bundle + the FMU) ships as one
image on Docker Hub:
[`phillipmaree/slimtorq-control`](https://hub.docker.com/r/phillipmaree/slimtorq-control).

```bash
docker compose up
# → open http://localhost:8000
```

That single command pulls (or builds) the image, mounts a named volume for
parquet artifacts, and starts the service. No frontend toolchain or Python
on the host.

### Configuration

All runtime configuration lives in [config/app.yaml](config/app.yaml):

```yaml
app:        { name, host, port, version, log_config_file, log_level }
cors:       { allow_origins, allow_methods, allow_headers }
frontend:   { dist_dir }     # static Next.js export
artifacts:  { dir }          # parquet output directory
catalog:    { path }         # motor catalog YAML
```

Logging is a standard `dictConfig` in
[config/logging.yaml](config/logging.yaml). The container image bakes both
files in and overrides only the container-specific paths
(`ARTIFACTS__DIR=/data/artifacts`, `FRONTEND__DIST_DIR=/app/frontend/out`)
through env. Any field can be overridden by env with the double-underscore
delimiter — `APP__PORT=9000`, `CATALOG__PATH=/custom/catalog.yaml`, etc.
Image publishing is automated by
[`.github/workflows/docker-publish.yml`](.github/workflows/docker-publish.yml).

### Option B — From source (for development)

Requires `uv` (Python toolchain), Node.js 20+, and `omc` (OpenModelica
compiler) on the host.

```bash
# 0. Sync deps.
uv sync
(cd frontend && npm install)

# 1. Build the FMU (requires OpenModelica `omc`).
(cd modelica && omc build_fmu.mos)

# 2a. Single-process dev (rebuild the static bundle, let FastAPI serve it).
(cd frontend && npm run build)
uv run python -m src.main
# → http://localhost:8000
#   (or for hot-reload, drive uvicorn directly:
#    uv run uvicorn --factory src.server:get_app --reload --port 8000)

# 2b. Or run with HMR: two terminals, NEXT_PUBLIC_API_BASE points the dev
#     server at uvicorn. Copy frontend/.env.example to frontend/.env.local.
uv run uvicorn --factory src.server:get_app --reload --port 8000
cd frontend && npm run dev
# → http://localhost:3000 (HMR), API on http://localhost:8000

# 3. Catalog cross-check (optional).
uv run python -m src.model
```

Each `/api/simulate` POST runs a fresh sim from scratch and writes the
trace to `<artifacts.dir>/<family>_<variant>.parquet` (defaults to
`.temp/` from [config/app.yaml](config/app.yaml); the container image
points it at `/data/artifacts`). The parquet's key-value metadata holds
the 16-character blake2b hash of the canonical input dict for
traceability; there is no cache-hit path.

## Output schema (parquet v2)

| Column group | Names | Type |
|---|---|---|
| Time | `t` | float |
| References | `TL_ref`, `i_d_ref`, `i_q_ref`, `v_d_ref`, `v_q_ref`, `v_a_ref`, `v_b_ref`, `v_c_ref` | float |
| Measurements | `T_e`, `i_d_meas`, `i_q_meas`, `i_a`, `i_b`, `i_c`, `θ_m_true`, `θ_m_meas`, `ω_m_true`, `ω_m_meas` | float |
| PWM | `d_a`, `d_b`, `d_c` | float |
| Switching | `s_a`, `s_b`, `s_c` | int8 |
| Post-inverter | `v_a`, `v_b`, `v_c` | float |
| Saturation flags | `sat_d`, `sat_q` | bool |

Metadata (`slimtorq.*` keys): `schema_version`, `params_hash`, `params_json`, `foc_kp`, `foc_ki`, `pi_mode`, `pi_tc`, `pi_k1`, `vdc`, `f_pwm`, `t_dead`, `ts_enc`, `inverter_mode`, `pwm_mode`, `filter_enabled`, `filter_fc`, `filter_lf`, `filter_cf`, `filter_rd`, `b_est`, `motor_family`, `motor_name`, `motor_rated_voltage`.

## Repo layout

```
slimtorq-control/
├── README.md
├── docker-compose.yaml                single service: FastAPI on :8000 serving /api/* + the Next.js static bundle at /
├── compose/control/
│   ├── Dockerfile                     multi-stage: node builder (Next.js export) → python:3.13-slim runtime
│   └── start                          python -m src.main
├── .github/workflows/
│   └── docker-publish.yml             build + push phillipmaree/slimtorq-control
├── config/
│   ├── app.yaml                       server / cors / frontend / artifacts / catalog
│   ├── logging.yaml                   logging.dictConfig schema
│   └── catalog.yaml                   Alva SlimTorq motor data
├── pyproject.toml                     deps: fmpy, polars, fastapi, uvicorn, pyarrow, pydantic-settings, …
├── modelica/
│   ├── Alva.mo
│   ├── build_fmu.mos
│   └── SlotlessPMSM_abc.fmu           built artifact (regenerable)
├── .temp/<fam>_<var>.parquet         most recent run, overwritten each Simulate (gitignored)
├── src/                              python -m src.<module>   (package)
│   ├── __init__.py                    Pydantic-Settings loader over config/app.yaml (singleton get_config())
│   ├── main.py                        async entrypoint (await server.run())
│   ├── server.py                      FastAPI app + uvicorn.Server (get_app / get_server / run)
│   ├── model.py                       Pydantic schema + catalog loader
│   ├── tuning.py                      auto_pi_gains_from_bw, modulus_optimum_tuning, skogestad_tuning
│   ├── transform.py                   Clarke / Park / inverses
│   ├── controller.py                  PIController, FOCController
│   ├── encoder.py                     FluxEncoder, EncoderMeasurement
│   ├── switching.py                   PWMModulator (6 modes), Inverter (PWM + dead time), LCLFilter, PMSMAbcModel
│   └── simulator.py                   Simulator orchestrator + run_simulation(SimParams) → df + SimMeta + parquet
└── frontend/
    ├── package.json                   next, react, react-hook-form, echarts, apache-arrow, katex
    ├── app/                           layout + single-page UI
    ├── components/
    │   ├── ConfigPanel/               28 react-hook-form inputs (motor / inverter / filter / encoder / trajectory / timing / PI / debug)
    │   ├── PlotPanel/                 12 ECharts figure modules under figures/*.ts
    │   └── Header.tsx                 logo + status pill (artifact name, hash, err %, Kp/Ki)
    ├── lib/                           api.ts (Arrow IPC fetch) · arrow.ts (column accessors) · fft.ts · tuning.ts · palette.ts
    └── types/sim.ts                   SimParams / SimMeta / Variant (mirror of Pydantic models)
```
