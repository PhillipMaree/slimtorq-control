"""Dash UI: pick a SlimTorq variant + power-stage + sim parameters, click Simulate.

Run with `python src/app.py`. Opens at http://localhost:8080.

The Simulate button computes a stable hash over the full input dict (variant +
power-stage + encoder + trajectory + timing + PI tuning + bypass-PWM flag).
Vdc is not in the dict — it's derived from `motor.rated_voltage` per variant.
If a parquet file at the canonical output path already carries that hash in
its `slimtorq.params_hash` metadata, the FMU run is skipped (cache hit) and
the file is reloaded. Otherwise the four-component pipeline (motor / encoder
/ controller / inverter) is built inside a `with Simulator(...) as sim:`
block, `sim.run()` is invoked, the parquet is overwritten, and the eight
Plotly figures are re-rendered from the new data.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import polars as pl
import pyarrow.parquet as pq
from dash import Dash, Input, Output, State, dcc, html, no_update

import plots
from controller import FOCController
from encoder import EncoderMeasurement, FluxEncoder
from model import EncoderConfig, FocConfig, InverterConfig, PmsmModel, TLRef, load_catalog
from simulator import Simulator
from switching import Inverter, PMSMAbcModel
from tuning import modulus_optimum_tuning

ASSETS_DIR = str(Path(__file__).resolve().parent.parent / "assets")
_OUTPUT_DIR = Path(__file__).resolve().parent.parent / ".temp"
_SCHEMA_VERSION = "3"

CATALOG = load_catalog()
DEFAULT_VARIANT = "STM-75-20-L-4Y"
TWO_PI = 2.0 * math.pi


# ----------------------------------------------------------------------------
# Persistence helpers (parquet I/O + canonical paths + default trajectory).
# Live here because app.py is the only consumer.
# ----------------------------------------------------------------------------
def _output_path_for(motor: PmsmModel) -> Path:
    """Canonical output path: .temp/<family>_<name>.parquet."""
    fname = f"{motor.family.replace(' ', '_')}_{motor.name}.parquet"
    return _OUTPUT_DIR / fname


def _read_metadata(path: Path) -> dict[str, str]:
    raw = pq.read_metadata(str(path)).metadata or {}
    return {k.decode(): v.decode() for k, v in raw.items() if k.decode().startswith("slimtorq.")}


def _write_parquet(
    df: pl.DataFrame,
    *,
    motor: PmsmModel,
    controller: FOCController,
    Vdc: float,
    f_pwm: float,
    t_dead: float,
    pi_mode: str,
    params_json: str,
    params_hash: str,
    out_path: Path,
) -> None:
    """Persist a Simulator.run() DataFrame as parquet with slimtorq.* metadata.

    b_est (steady-state viscous-friction estimate) is derived inline from the
    trailing 20% of the run: B ~= mean(T_e - TL_ref) / mean(omega_m_true).
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n = df.height
    tail = df.slice(int(0.8 * n), n - int(0.8 * n))
    mean_omega = float(tail["omega_m_true"].mean())
    mean_dT = float((tail["T_e"] - tail["TL_ref"]).mean())
    b_est: float | None = mean_dT / mean_omega if abs(mean_omega) > 1e-3 else None

    table = df.to_arrow()
    meta = {
        b"slimtorq.schema_version": _SCHEMA_VERSION.encode(),
        b"slimtorq.params_hash": params_hash.encode(),
        b"slimtorq.params_json": params_json.encode(),
        b"slimtorq.foc_kp": f"{controller.Kp:.10g}".encode(),
        b"slimtorq.foc_ki": f"{controller.Ki:.10g}".encode(),
        b"slimtorq.pi_mode": pi_mode.encode(),
        b"slimtorq.vdc": f"{Vdc:.10g}".encode(),
        b"slimtorq.f_pwm": f"{f_pwm:.10g}".encode(),
        b"slimtorq.t_dead": f"{t_dead:.10g}".encode(),
        b"slimtorq.b_est": (b"null" if b_est is None else f"{b_est:.10g}".encode()),
        b"slimtorq.motor_family": motor.family.encode(),
        b"slimtorq.motor_name": motor.name.encode(),
        b"slimtorq.motor_rated_voltage": f"{motor.rated_voltage:.6g}".encode(),
    }
    table = table.replace_schema_metadata(meta)
    pq.write_table(table, str(out_path))


def _default_TL_ref(motor: PmsmModel, t_end: float, t_step: float, frac: float) -> TLRef:
    """Default TL_ref: zero until t_step, then step to frac · te_peak_1s, hold to t_end.

    `frac` is interpreted against the catalog's 1-second peak torque so the
    user-facing knob has the meaning "fraction of max torque the motor can
    briefly produce." Defaults around 0.5-0.7 are realistic; values > 1.0 push
    past the catalog peak and will hit the FOC's vector-saturation limit.
    """
    amp = frac * motor.te_peak_1s
    return TLRef(ref=np.array([0.0, amp]), t=np.array([t_step, t_end]))


# ----------------------------------------------------------------------------
# Param hashing
# ----------------------------------------------------------------------------
def _canonical_params_json(params: dict) -> str:
    norm = {k: (round(float(v), 12) if isinstance(v, float) else v) for k, v in sorted(params.items())}
    return json.dumps(norm, separators=(",", ":"), sort_keys=True)


def _params_hash(json_str: str) -> str:
    return hashlib.blake2b(json_str.encode(), digest_size=8).hexdigest()


def _gains_for_mode(variant: str, pi_mode: str, f_pwm: float) -> tuple[float, float] | None:
    """Compute auto-suggested (Kp, Ki) for the variant + mode. None for manual."""
    if variant is None:
        return None
    m = CATALOG[variant]
    if pi_mode == "modulus_optimum" and f_pwm is not None:
        return modulus_optimum_tuning(m.R_s, m.L_s, float(f_pwm))
    return None


# ----------------------------------------------------------------------------
# Layout helpers
# ----------------------------------------------------------------------------
LABEL_W = "10rem"


def _num(id_: str, value, step=None, mn=None, mx=None, disabled=False, suffix="", label=None):
    """Numeric input row.

    `label` may be a plain string OR a list of HTML children (e.g. mixing
    Unicode Greek with `html.Sub(...)` / `html.Sup(...)` for typographic
    subscripts/superscripts). When None, falls back to the component id.
    """
    if label is None:
        parts: list = [id_]
    elif isinstance(label, str):
        parts = [label]
    else:
        parts = list(label)
    if suffix:
        parts = [*parts, f" [{suffix}]"]
    return html.Div(
        className="alva-row",
        children=[
            html.Label(parts, htmlFor=id_),
            dcc.Input(id=id_, type="number", value=value, step=step, min=mn, max=mx, disabled=disabled),
        ],
    )


def _sub(stem: str, sub: str) -> list:
    """Render `stem_sub` with a real HTML subscript."""
    return [stem, html.Sub(sub)]


def _section(title: str, children: list) -> html.Div:
    return html.Div(className="alva-section", children=[html.H4(title), *children])


# Compute initial Kp/Ki for the default variant via modulus-optimum tuning at
# the default f_pwm so the manual inputs show a sensible starting value the
# first time the user picks Manual.
DEFAULT_F_PWM = 20000.0
kp0, ki0 = modulus_optimum_tuning(CATALOG[DEFAULT_VARIANT].R_s, CATALOG[DEFAULT_VARIANT].L_s, DEFAULT_F_PWM)


HEADER = html.Div(
    className="alva-header",
    children=[
        html.Img(src="/assets/logo.png", alt="Alva Industries"),
        html.Div(
            className="alva-header-text",
            children=[
                html.Span("SlimTorq Simulator", className="alva-header-title"),
                html.Span("FOC · PWM · Inverter", className="alva-header-sub"),
            ],
        ),
    ],
)


CONFIG_PANEL = html.Div(
    className="alva-panel",
    children=[
        HEADER,
        html.Div(
            className="alva-body",
            children=[
                _section(
                    "Motor",
                    [
                        html.Div(
                            className="alva-row",
                            children=[
                                html.Label("variant", htmlFor="variant"),
                                dcc.Dropdown(
                                    id="variant",
                                    value=DEFAULT_VARIANT,
                                    options=[{"label": k, "value": k} for k in sorted(CATALOG.keys())],
                                    clearable=False,
                                    style={"width": "18rem"},
                                ),
                            ],
                        ),
                    ],
                ),
                _section(
                    "Power stage",
                    [
                        # Vdc is derived from the selected variant's catalog rated_voltage
                        # at runtime (motor.rated_voltage); not a UI input.
                        _num("f_pwm", 20000.0, step=1000.0, mn=1000.0, mx=50000.0, suffix="Hz", label=_sub("f", "pwm")),
                        _num("t_dead", 1.5e-6, step=1e-7, mn=0.0, mx=5e-6, suffix="s", label=_sub("t", "dead")),
                    ],
                ),
                _section(
                    "Encoder",
                    [
                        _num("n_bits", 22, step=1, mn=10, mx=26, label=_sub("N", "bits")),
                        _num("theta_offset", 0.0, step=1e-3, mn=-math.pi, mx=math.pi, suffix="rad", label=_sub("θ", "offset")),
                        _num("A1", 2.4e-5, step=1e-6, mn=0.0, mx=1e-3, suffix="rad", label=_sub("A", "1")),
                        _num("k1", 1, step=1, mn=1, mx=100, label=_sub("k", "1")),
                        _num("phi1", 0.0, step=1e-3, mn=0.0, mx=TWO_PI, suffix="rad", label=_sub("φ", "1")),
                        _num("A2", 5.0e-6, step=1e-6, mn=0.0, mx=1e-3, suffix="rad", label=_sub("A", "2")),
                        _num("k2", 2, step=1, mn=1, mx=100, label=_sub("k", "2")),
                        _num("phi2", 0.0, step=1e-3, mn=0.0, mx=TWO_PI, suffix="rad", label=_sub("φ", "2")),
                        _num("A3", 1.0e-6, step=1e-6, mn=0.0, mx=1e-3, suffix="rad", label=_sub("A", "3")),
                        _num("k3", 4, step=1, mn=1, mx=100, label=_sub("k", "3")),
                        _num("phi3", 0.0, step=1e-3, mn=0.0, mx=TWO_PI, suffix="rad", label=_sub("φ", "3")),
                        _num("ts_enc", 1e-4, step=1e-5, mn=1e-6, mx=1e-2, suffix="s", label=_sub("T", "s,enc")),
                    ],
                ),
                _section(
                    "Trajectory (load-torque step)",
                    [
                        _num("t_end", 0.05, step=1e-3, mn=1e-3, mx=1.0, suffix="s", label=_sub("t", "end")),
                        _num("t_step", 0.005, step=1e-3, mn=0.0, mx=1.0, suffix="s", label=_sub("t", "step")),
                        # The amplitude of the load-torque step is t_step_frac · T_e^peak,
                        # i.e. this input *is* T_L^ref / T_e^peak.
                        _num("t_step_frac", 2 / 3, step=0.05, mn=0.0, mx=1.5, label=["T", html.Sub("L"), html.Sup("ref"), " / T", html.Sub("e"), html.Sup("peak")]),
                        _num("Tf", None, step=1e-3, mn=1e-3, mx=5.0, suffix="s (None=auto)", label=_sub("T", "f")),
                    ],
                ),
                _section(
                    "Timing",
                    [
                        _num("dt_sim", None, step=1e-7, mn=1e-7, mx=1e-4, suffix="s (None=T_pwm/20)", label=["Δt", html.Sub("sim")]),
                    ],
                ),
                _section(
                    "Current loop",
                    [
                        html.Div(
                            className="alva-row",
                            children=[
                                html.Label("PI tuning"),
                                dcc.RadioItems(
                                    id="pi_mode",
                                    className="alva-radio",
                                    options=[{"label": " Modulus Optimum (f_pwm)", "value": "modulus_optimum"}, {"label": " Manual (Kp, Ki)", "value": "manual"}],
                                    value="modulus_optimum",
                                    labelStyle={"display": "block"},
                                ),
                            ],
                        ),
                        _num("Kp", round(kp0, 6), step=1e-3, mn=0.0, suffix="V/A", disabled=True, label=_sub("K", "p")),
                        _num("Ki", round(ki0, 6), step=1e-3, mn=0.0, suffix="V/(A·s)", disabled=True, label=_sub("K", "i")),
                    ],
                ),
                # Collapsed Debug section — diagnostic toggles that bypass parts
                # of the normal pipeline. Native <details>/<summary> so it stays
                # closed by default and doesn't clutter the daily UI.
                html.Details(
                    className="alva-section alva-debug",
                    children=[
                        html.Summary("Debug"),
                        dcc.Checklist(
                            id="bypass_pwm",
                            options=[{"label": " Bypass PWM (feed v_abc_ref straight into FMU — diagnostic only)", "value": "on"}],
                            value=[],
                        ),
                    ],
                ),
                html.Button("Simulate", id="simulate", n_clicks=0, className="alva-btn-simulate"),
                html.Div(id="status", className="alva-status"),
            ],
        ),
    ],
)


PLOT_PANEL = dcc.Loading(
    html.Div(
        [
            dcc.Graph(id="fig_tracking", mathjax=True),
            dcc.Graph(id="fig_pi", mathjax=True),
            dcc.Graph(id="fig_vdq_rt", mathjax=True),
            dcc.Graph(id="fig_iq_zoom", mathjax=True),
            dcc.Graph(id="fig_iq_fft", mathjax=True),
            dcc.Graph(id="fig_fft", mathjax=True),
            dcc.Graph(id="fig_iabc", mathjax=True),
            dcc.Graph(id="fig_iabc_fft", mathjax=True),
            dcc.Graph(id="fig_vabc", mathjax=True),
            dcc.Graph(id="fig_duties", mathjax=True),
            dcc.Graph(id="fig_enc", mathjax=True),
            dcc.Graph(id="fig_speed", mathjax=True),
        ],
        className="alva-plot-panel",
    ),
    type="default",
    color="#F76E5C",
    # Without this, dcc.Loading's wrapper div collapses to content width and
    # the .alva-plot-panel `flex: 1` inside it has nothing to expand into.
    parent_style={"flex": "1 1 auto", "minWidth": "0", "display": "flex", "flexDirection": "column"},
)


app = Dash(
    __name__,
    title="SlimTorq Simulator — Alva Industries",
    assets_folder=ASSETS_DIR,
    # Load MathJax explicitly so $…$ in Plotly titles / axes / trace
    # names renders reliably (Plotly 6 + Dash 4 auto-loader is racy).
    external_scripts=[
        "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js",
    ],
)
app.layout = html.Div([CONFIG_PANEL, PLOT_PANEL], style={"display": "flex", "alignItems": "flex-start"})


# ----------------------------------------------------------------------------
# Enable/disable PI-tuning inputs based on radio
# ----------------------------------------------------------------------------
@app.callback(
    Output("Kp", "disabled"),
    Output("Ki", "disabled"),
    Input("pi_mode", "value"),
)
def toggle_pi_inputs(pi_mode: str):
    # Modulus Optimum -> Kp/Ki disabled (auto-populated from f_pwm).
    # Manual -> Kp/Ki enabled.
    if pi_mode == "manual":
        return False, False
    return True, True


# ----------------------------------------------------------------------------
# Auto-populate Kp/Ki when variant or f_pwm changes (modulus-optimum mode)
# ----------------------------------------------------------------------------
@app.callback(
    Output("Kp", "value"),
    Output("Ki", "value"),
    Input("variant", "value"),
    Input("f_pwm", "value"),
    Input("pi_mode", "value"),
)
def suggest_pi_gains(variant, f_pwm, pi_mode):
    if pi_mode == "manual":
        return no_update, no_update
    gains = _gains_for_mode(variant, pi_mode, f_pwm)
    if gains is None:
        return no_update, no_update
    kp, ki = gains
    return round(kp, 6), round(ki, 6)


# ----------------------------------------------------------------------------
# Simulate button
# ----------------------------------------------------------------------------
PLOT_OUTPUTS = (
    Output("fig_tracking", "figure"),
    Output("fig_pi", "figure"),
    Output("fig_vdq_rt", "figure"),
    Output("fig_iq_zoom", "figure"),
    Output("fig_iq_fft", "figure"),
    Output("fig_fft", "figure"),
    Output("fig_iabc", "figure"),
    Output("fig_iabc_fft", "figure"),
    Output("fig_vabc", "figure"),
    Output("fig_duties", "figure"),
    Output("fig_enc", "figure"),
    Output("fig_speed", "figure"),
    Output("status", "children"),
)


def _render_all(df: pl.DataFrame, meta: dict[str, str]):
    return (
        plots.figure_tracking(df, meta),
        plots.figure_pi_performance(df, meta),
        plots.figure_vdq_roundtrip(df, meta),
        plots.figure_iq_zoom(df, meta),
        plots.figure_iq_fft(df, meta),
        plots.figure_fft_omega(df, meta),
        plots.figure_phase_currents(df, meta),
        plots.figure_iabc_fft(df, meta),
        plots.figure_phase_voltages(df, meta),
        plots.figure_duties(df, meta),
        plots.figure_encoder_error(df, meta),
        plots.figure_speed_and_saturation(df, meta),
    )


@app.callback(
    *PLOT_OUTPUTS,
    Input("simulate", "n_clicks"),
    State("variant", "value"),
    State("f_pwm", "value"),
    State("t_dead", "value"),
    State("n_bits", "value"),
    State("theta_offset", "value"),
    State("A1", "value"),
    State("k1", "value"),
    State("phi1", "value"),
    State("A2", "value"),
    State("k2", "value"),
    State("phi2", "value"),
    State("A3", "value"),
    State("k3", "value"),
    State("phi3", "value"),
    State("ts_enc", "value"),
    State("dt_sim", "value"),
    State("t_end", "value"),
    State("t_step", "value"),
    State("t_step_frac", "value"),
    State("Tf", "value"),
    State("pi_mode", "value"),
    State("Kp", "value"),
    State("Ki", "value"),
    State("bypass_pwm", "value"),
    prevent_initial_call=True,
)
def simulate(
    n_clicks,
    variant,
    f_pwm,
    t_dead,
    n_bits,
    theta_offset,
    A1,
    k1,
    phi1,
    A2,
    k2,
    phi2,
    A3,
    k3,
    phi3,
    ts_enc,
    dt_sim,
    t_end,
    t_step,
    t_step_frac,
    Tf,
    pi_mode,
    Kp,
    Ki,
    bypass_pwm_value,
):
    if variant is None:
        return *([no_update] * 8), "no variant selected"
    # Dash returns None for any numeric input whose value is outside [min, max].
    # Report which fields are out of range instead of crashing on float(None).
    required = {
        "f_pwm": f_pwm,
        "t_dead": t_dead,
        "n_bits": n_bits,
        "theta_offset": theta_offset,
        "A1": A1,
        "k1": k1,
        "phi1": phi1,
        "A2": A2,
        "k2": k2,
        "phi2": phi2,
        "A3": A3,
        "k3": k3,
        "phi3": phi3,
        "ts_enc": ts_enc,
        "t_end": t_end,
        "t_step": t_step,
        "t_step_frac": t_step_frac,
    }
    missing = [k for k, v in required.items() if v is None]
    if missing:
        return *([no_update] * 8), f"input(s) empty or out of range: {', '.join(missing)}"
    if t_step >= t_end:
        return *([no_update] * 8), f"t_step ({t_step}) must be < t_end ({t_end})"

    motor_cfg = CATALOG[variant]
    Vdc = float(motor_cfg.rated_voltage)
    bypass_pwm = bool(bypass_pwm_value) and "on" in (bypass_pwm_value or [])

    params = {
        "variant_name": variant,
        "f_pwm": float(f_pwm),
        "t_dead": float(t_dead),
        "n_bits": int(n_bits),
        "theta_offset": float(theta_offset),
        "A1": float(A1),
        "k1": int(k1),
        "phi1": float(phi1),
        "A2": float(A2),
        "k2": int(k2),
        "phi2": float(phi2),
        "A3": float(A3),
        "k3": int(k3),
        "phi3": float(phi3),
        "ts_enc": float(ts_enc),
        "dt_sim": None if dt_sim is None else float(dt_sim),
        "t_end": float(t_end),
        "t_step": float(t_step),
        "t_step_frac": float(t_step_frac),
        "Tf": None if Tf is None else float(Tf),
        "pi_mode": pi_mode,
        "Kp": float(Kp) if Kp is not None else None,
        "Ki": float(Ki) if Ki is not None else None,
        "bypass_pwm": bypass_pwm,
    }
    params_json = _canonical_params_json(params)
    h = _params_hash(params_json)
    out_path = _output_path_for(motor_cfg)

    cache_hit = False
    if out_path.exists():
        try:
            existing = _read_metadata(out_path)
            cache_hit = existing.get("slimtorq.params_hash") == h
        except Exception:
            cache_hit = False

    if cache_hit:
        df = pl.read_parquet(out_path)
    else:
        encoder_cfg = EncoderConfig(
            n_bits=int(n_bits),
            theta_offset=float(theta_offset),
            A1=float(A1),
            k1=int(k1),
            phi1=float(phi1),
            A2=float(A2),
            k2=int(k2),
            phi2=float(phi2),
            A3=float(A3),
            k3=int(k3),
            phi3=float(phi3),
            Ts_enc=float(ts_enc),
        )
        TL = _default_TL_ref(motor_cfg, t_end=float(t_end), t_step=float(t_step), frac=float(t_step_frac))

        # Pick Kp/Ki per pi_mode: manual passes through, otherwise modulus-optimum.
        use_manual = pi_mode == "manual" and Kp is not None and Ki is not None
        if use_manual:
            Kp_used, Ki_used = float(Kp), float(Ki)
        else:
            Kp_used, Ki_used = modulus_optimum_tuning(motor_cfg.R_s, motor_cfg.L_s, float(f_pwm))

        foc_cfg = FocConfig(
            R_s=motor_cfg.R_s,
            L_s=motor_cfg.L_s,
            psi_m=motor_cfg.psi_m,
            p=motor_cfg.p,
            Vdc=Vdc,
            f_pwm=float(f_pwm),
            Kp=Kp_used,
            Ki=Ki_used,
        )
        controller = FOCController(foc_cfg)
        inverter = Inverter(InverterConfig(Vdc=Vdc, f_pwm=float(f_pwm), t_dead=float(t_dead)))
        encoder = EncoderMeasurement(FluxEncoder(encoder_cfg), p=motor_cfg.p)
        motor = PMSMAbcModel(motor_cfg)

        try:
            with Simulator(motor, encoder, controller, inverter) as sim:
                df = sim.run(
                    TL,
                    T_s=None if dt_sim is None else float(dt_sim),
                    T_f=None if Tf is None else float(Tf),
                    bypass_pwm=bypass_pwm,
                )
        except Exception as e:
            return *([no_update] * 8), f"error: {e}"

        _write_parquet(
            df,
            motor=motor_cfg,
            controller=controller,
            Vdc=Vdc,
            f_pwm=float(f_pwm),
            t_dead=float(t_dead),
            pi_mode=pi_mode,
            params_json=params_json,
            params_hash=h,
            out_path=out_path,
        )

    meta = _read_metadata(out_path)
    figs = _render_all(df, meta)
    state = "cache hit" if cache_hit else "ran sim"
    status = (
        f"{state}: {out_path.name}   "
        f"hash={h}   rows={df.height}   "
        f"Kp={meta.get('slimtorq.foc_kp', '?')}  "
        f"Ki={meta.get('slimtorq.foc_ki', '?')}  "
        f"[{meta.get('slimtorq.pi_mode', '?')}]"
    )
    return (*figs, status)


if __name__ == "__main__":
    app.run(debug=True, port=8080)
