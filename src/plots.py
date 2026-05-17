"""Plotly figures for the Dash app. Pure data -> figure; no I/O.

Each function takes a polars DataFrame (loaded from .temp/*.parquet) and
the decoded slimtorq.* metadata dict, and returns a plotly.graph_objects.Figure.

Titles, axis labels, and trace names use MathJax LaTeX delimiters $…$ so
Greek and subscripted symbols render properly (θ, ω, ψ, τ, K_p, V_{dc}, …).

Palette: every data trace is coloured from `assets/style.css` (Alva brand
palette). The CSS file is the single source of truth — variables
`--alva-text`, `--alva-coral-dark`, `--alva-text-muted` resolve to
(#1A1A1A, #E0543F, #5B5B5B) in that order. Reference traces (`T_L^ref`,
`i_q^*`, `ω_m^meas` paired with `ω_m^true`, …) share the colour of the
measurement they pair with but render dashed. Limit guides (V_max, ±Vdc/2,
0.5) stay red-dotted / thin black — they are limits, not data.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import polars as pl
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Palette — parsed once at import from assets/style.css.
# ---------------------------------------------------------------------------
_PALETTE_VARS = ("--alva-text", "--alva-coral-dark", "--alva-text-muted")


def _load_palette() -> tuple[str, str, str]:
    css_path = Path(__file__).resolve().parent.parent / "assets" / "style.css"
    css = css_path.read_text()
    out: list[str] = []
    for var in _PALETTE_VARS:
        m = re.search(rf"{var}\s*:\s*(#[0-9A-Fa-f]{{6}})", css)
        if m is None:
            msg = f"plots.py: palette variable {var!r} not found in {css_path}"
            raise RuntimeError(msg)
        out.append(m.group(1))
    return out[0], out[1], out[2]


_PALETTE: tuple[str, str, str] = _load_palette()


def _line(idx: int, *, ref: bool = False, **extra) -> dict:
    """Plotly `line=` dict for trace #idx. ref=True ⇒ dashed; ref=False ⇒ solid.

    `idx` is per *logical signal*: a measurement and its reference share the
    same slot so they read as a pair.
    """
    return {"color": _PALETTE[idx % len(_PALETTE)], "dash": "dash" if ref else "solid", **extra}


def _t_ms(df: pl.DataFrame) -> np.ndarray:
    return df["t"].to_numpy() * 1e3


def _title(meta: dict[str, str], suffix: str = "") -> str:
    base = f"{meta.get('slimtorq.motor_family', '?')} / {meta.get('slimtorq.motor_name', '?')}"
    return f"{base} — {suffix}" if suffix else base


# Shared layout to give every figure a horizontal legend above the plot and
# minimal side margins, so the x-axis runs almost to the panel edge.
_FIG_MARGIN = dict(l=55, r=20, t=80, b=50)
_FIG_LEGEND = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1.0)


def figure_tracking(df: pl.DataFrame, meta: dict[str, str]) -> go.Figure:
    r"""T_L_ref vs T_e, i_q^* vs i_q, i_d^* vs i_d on a 3-row shared-x subplot."""
    t = _t_ms(df)
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, subplot_titles=(r"$\text{Torque } [\mathrm{N \cdot m}]$", r"$i_q \;[\mathrm{A}]$", r"$i_d \;[\mathrm{A}]$")
    )
    fig.add_trace(go.Scatter(x=t, y=df["TL_ref"], name=r"$T_L^{\,ref}$", line=_line(0, ref=True)), row=1, col=1)
    fig.add_trace(go.Scatter(x=t, y=df["T_e"], name=r"$T_e$", line=_line(0)), row=1, col=1)
    fig.add_trace(go.Scatter(x=t, y=df["i_q_ref"], name=r"$i_q^{\,*}$", line=_line(1, ref=True)), row=2, col=1)
    fig.add_trace(go.Scatter(x=t, y=df["i_q_meas"], name=r"$i_q$", line=_line(1)), row=2, col=1)
    fig.add_trace(go.Scatter(x=t, y=df["i_d_ref"], name=r"$i_d^{\,*}$", line=_line(2, ref=True)), row=3, col=1)
    fig.add_trace(go.Scatter(x=t, y=df["i_d_meas"], name=r"$i_d$", line=_line(2)), row=3, col=1)
    fig.update_xaxes(title_text=r"$t \;[\mathrm{ms}]$", row=3, col=1)
    fig.update_layout(title=_title(meta, "Tracking"), height=700, hovermode="x unified", margin=_FIG_MARGIN, legend=_FIG_LEGEND)
    return fig


def figure_pi_performance(df: pl.DataFrame, meta: dict[str, str]) -> go.Figure:
    r"""PI errors and dq voltage refs with the V_{max} = V_{dc}/2 vector limit."""
    t = _t_ms(df)
    e_d = (df["i_d_ref"] - df["i_d_meas"]).to_numpy()
    e_q = (df["i_q_ref"] - df["i_q_meas"]).to_numpy()
    Vdc = float(meta.get("slimtorq.vdc", "72"))
    V_max = Vdc / 2.0
    kp = meta.get("slimtorq.foc_kp", "?")
    ki = meta.get("slimtorq.foc_ki", "?")
    pi_mode = meta.get("slimtorq.pi_mode", "?")

    v_d = df["v_d_ref"].to_numpy()
    v_q = df["v_q_ref"].to_numpy()
    v_mag = np.sqrt(v_d * v_d + v_q * v_q)

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=(r"$\text{PI error } [\mathrm{A}]$", r"$v_d^{\,ref}, \; v_q^{\,ref} \;[\mathrm{V}]$", r"$|v_{dq}| \;\text{vs}\; V_{max}=V_{dc}/2 \;[\mathrm{V}]$"),
    )
    fig.add_trace(go.Scatter(x=t, y=e_d, name=r"$e_d$", line=_line(0)), row=1, col=1)
    fig.add_trace(go.Scatter(x=t, y=e_q, name=r"$e_q$", line=_line(1)), row=1, col=1)
    fig.add_hline(y=0.0, line=dict(width=0.5, color="black"), row=1, col=1)

    fig.add_trace(go.Scatter(x=t, y=v_d, name=r"$v_d^{\,ref}$", line=_line(0)), row=2, col=1)
    fig.add_trace(go.Scatter(x=t, y=v_q, name=r"$v_q^{\,ref}$", line=_line(1)), row=2, col=1)
    fig.add_hline(y=V_max, line=dict(width=0.5, color="red", dash="dot"), annotation_text=rf"$+V_{{max}}={V_max:g}$", row=2, col=1)
    fig.add_hline(y=-V_max, line=dict(width=0.5, color="red", dash="dot"), row=2, col=1)

    fig.add_trace(go.Scatter(x=t, y=v_mag, name=r"$|v_{dq}|$", line=_line(2)), row=3, col=1)
    fig.add_hline(y=V_max, line=dict(width=0.5, color="red", dash="dot"), annotation_text=rf"$V_{{max}}={V_max:g}$", row=3, col=1)

    fig.update_xaxes(title_text=r"$t \;[\mathrm{ms}]$", row=3, col=1)
    fig.update_layout(
        title=rf"{_title(meta, 'PI performance')}  —  "
        rf"$K_p={kp}\,\mathrm{{V/A}},\; K_i={ki}\,\mathrm{{V/(A\cdot s)}}$  "
        f"[{pi_mode}]",
        height=720,
        hovermode="x unified",
        margin=_FIG_MARGIN,
        legend=_FIG_LEGEND,
    )
    return fig


def figure_fft_omega(df: pl.DataFrame, meta: dict[str, str]) -> go.Figure:
    r"""Log-magnitude spectrum of \omega_m^{meas} on the trailing 80 % (DC removed)."""
    t = df["t"].to_numpy()
    sig = df["omega_m_meas"].to_numpy()
    n = len(t)
    start = int(0.2 * n)
    sig = sig[start:]
    if len(sig) < 8:
        fig = go.Figure()
        fig.update_layout(title="FFT skipped: signal too short")
        return fig
    Ts = float(t[1] - t[0])
    sig = sig - np.mean(sig)
    freqs = np.fft.rfftfreq(len(sig), d=Ts)
    mag = np.abs(np.fft.rfft(sig)) / len(sig)
    mag = np.maximum(mag, 1e-12)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=freqs, y=mag, name=r"$|\mathrm{FFT}(\omega_m^{\,meas})|$", line=_line(0)))
    fig.update_yaxes(type="log", title_text=r"$|\mathrm{FFT}(\omega_m^{\,meas})| \;[\mathrm{rad/s,\,normalised}]$")
    fig.update_xaxes(title_text=r"$f \;[\mathrm{Hz}]$")
    fig.update_layout(
        title=rf"{_title(meta, r'$\omega_m^{meas}$ spectrum')}  "
        f"(steady-state window: last {100 * (n - start) // n}% of samples)",
        height=450,
        hovermode="x",
        margin=_FIG_MARGIN,
        legend=_FIG_LEGEND,
    )
    return fig


def figure_phase_currents(df: pl.DataFrame, meta: dict[str, str]) -> go.Figure:
    r"""i_a, i_b, i_c overlaid vs time."""
    t = _t_ms(df)
    fig = go.Figure()
    for idx, name in enumerate(("i_a", "i_b", "i_c")):
        latex_name = rf"$i_{name[2]}$"
        fig.add_trace(go.Scatter(x=t, y=df[name], name=latex_name, line=_line(idx)))
    fig.update_xaxes(title_text=r"$t \;[\mathrm{ms}]$")
    fig.update_yaxes(title_text=r"$\text{phase current } [\mathrm{A}]$")
    fig.update_layout(title=_title(meta, "Phase currents (abc)"), height=450, hovermode="x unified", margin=_FIG_MARGIN, legend=_FIG_LEGEND)
    return fig


def figure_phase_voltages(df: pl.DataFrame, meta: dict[str, str]) -> go.Figure:
    r"""FOC v_k^{ref} overlaid with post-inverter switched v_k (the PWM ripple).

    Per phase the ref and the post-inverter signal share a palette slot — same
    color, ref dashed, post-inverter solid faint. Reads as one pair per phase.
    """
    t = _t_ms(df)
    Vdc = float(meta.get("slimtorq.vdc", "72"))
    half = Vdc / 2.0
    fig = go.Figure()
    for idx, ph in enumerate(("a", "b", "c")):
        fig.add_trace(
            go.Scatter(
                x=t,
                y=df[f"v_{ph}"],
                name=rf"$v_{ph} \,(\text{{post-inv}})$",
                line=_line(idx, width=1.0),
                opacity=0.45,
                legendgroup=ph,
                hovertemplate=None,
            )
        )
        fig.add_trace(go.Scatter(x=t, y=df[f"v_{ph}_ref"], name=rf"$v_{ph}^{{\,ref}}$", line=_line(idx, ref=True, width=2.0), legendgroup=ph))
    fig.add_hline(y=half, line=dict(width=0.5, color="red", dash="dot"), annotation_text=rf"$+V_{{dc}}/2={half:g}$")
    fig.add_hline(y=-half, line=dict(width=0.5, color="red", dash="dot"))
    fig.update_xaxes(title_text=r"$t \;[\mathrm{ms}]$")
    fig.update_yaxes(title_text=r"$\text{phase voltage } [\mathrm{V}]$")
    fig.update_layout(title=_title(meta, "Phase voltages: FOC refs vs post-inverter"), height=500, hovermode="x unified", margin=_FIG_MARGIN, legend=_FIG_LEGEND)
    return fig


def figure_duties(df: pl.DataFrame, meta: dict[str, str]) -> go.Figure:
    r"""PWM duty cycles d_a, d_b, d_c (continuous in [0,1]) with 0.5 midpoint guide."""
    t = _t_ms(df)
    fig = go.Figure()
    for idx, ph in enumerate(("a", "b", "c")):
        fig.add_trace(go.Scatter(x=t, y=df[f"d_{ph}"], name=rf"$d_{ph}$", line=_line(idx)))
    fig.add_hline(y=0.5, line=dict(width=0.5, color="black", dash="dot"), annotation_text=r"$0.5$")
    fig.update_xaxes(title_text=r"$t \;[\mathrm{ms}]$")
    fig.update_yaxes(title_text=r"$\text{duty}$", range=[-0.05, 1.05])
    fig.update_layout(title=_title(meta, "PWM duty cycles"), height=400, hovermode="x unified", margin=_FIG_MARGIN, legend=_FIG_LEGEND)
    return fig


def figure_encoder_error(df: pl.DataFrame, meta: dict[str, str]) -> go.Figure:
    r"""Shortest-distance angular error \theta_m^{true} - \theta_m^{meas}, in mrad.

    \theta_m^{true} is unwrapped (the FMU integrates it without bound) while
    \theta_m^{meas} is wrapped to [0, 2\pi) by the encoder's quantization.
    Naïve subtraction leaks 2\pi jumps into the plot whenever the rotor crosses
    zero. We wrap the difference into [-\pi, \pi) so the result reflects pure
    encoder error: ZOH sample-and-hold latency (dominant at speed:
    \omega \cdot T_s^{enc}), cyclic harmonics, and N-bit quantization.
    """
    t = _t_ms(df)
    diff = (df["theta_m_true"] - df["theta_m_meas"]).to_numpy()
    err_wrapped = ((diff + np.pi) % (2.0 * np.pi)) - np.pi
    err_mrad = err_wrapped * 1e3
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=t, y=err_mrad, name=r"$\theta_m^{\,true} - \theta_m^{\,meas}$", line=_line(0)))
    fig.add_hline(y=0.0, line=dict(width=0.5, color="black"))
    fig.update_xaxes(title_text=r"$t \;[\mathrm{ms}]$")
    fig.update_yaxes(title_text=r"$\mathrm{wrap}(\theta_m^{\,true} - \theta_m^{\,meas}) \;[\mathrm{mrad}]$")
    fig.update_layout(title=_title(meta, "Encoder error (shortest-distance)"), height=450, hovermode="x unified", margin=_FIG_MARGIN, legend=_FIG_LEGEND)
    return fig


def figure_speed_and_saturation(df: pl.DataFrame, meta: dict[str, str]) -> go.Figure:
    r"""\omega_m^{true} vs \omega_m^{meas} with a saturation rug strip beneath."""
    t = _t_ms(df)
    omega_true = df["omega_m_true"].to_numpy()
    omega_meas = df["omega_m_meas"].to_numpy()
    sat_d = df["sat_d"].to_numpy()
    sat_q = df["sat_q"].to_numpy()

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.82, 0.18], vertical_spacing=0.04, subplot_titles=(r"$\text{Speed } [\mathrm{rad/s}]$", r"$\text{PI saturation flags}$")
    )
    # true/meas pair share slot 0 (same physical quantity).
    fig.add_trace(go.Scatter(x=t, y=omega_true, name=r"$\omega_m^{\,true}$", line=_line(0)), row=1, col=1)
    fig.add_trace(go.Scatter(x=t, y=omega_meas, name=r"$\omega_m^{\,meas}$", line=_line(0, ref=True)), row=1, col=1)

    t_d = t[sat_d]
    t_q = t[sat_q]
    # Saturation rug markers are event indicators, not signal traces — keep
    # them off-palette so they read as flags rather than data.
    if len(t_d):
        fig.add_trace(go.Scatter(x=t_d, y=np.zeros_like(t_d), mode="markers", marker=dict(symbol="line-ns", size=10, color="orange"), name=r"$\mathrm{sat}_d$"), row=2, col=1)
    if len(t_q):
        fig.add_trace(go.Scatter(x=t_q, y=np.ones_like(t_q), mode="markers", marker=dict(symbol="line-ns", size=10, color="red"), name=r"$\mathrm{sat}_q$"), row=2, col=1)
    fig.update_yaxes(range=[-0.5, 1.5], tickvals=[0, 1], ticktext=[r"$\mathrm{sat}_d$", r"$\mathrm{sat}_q$"], row=2, col=1)
    fig.update_xaxes(title_text=r"$t \;[\mathrm{ms}]$", row=2, col=1)
    fig.update_layout(title=_title(meta, "Speed tracking + PI saturation"), height=550, hovermode="x unified", margin=_FIG_MARGIN, legend=_FIG_LEGEND)
    return fig
