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

import math
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


def _steady_state_window(df: pl.DataFrame) -> tuple[np.ndarray, int, int]:
    r"""Indices into the trailing 80 % of the trace, matched with figure_fft_omega.

    Returns (t_seconds, start_idx, end_idx) so callers can both slice the data
    and report the window in titles.
    """
    t = df["t"].to_numpy()
    n = len(t)
    start = int(0.2 * n)
    return t, start, n


def figure_vdq_roundtrip(df: pl.DataFrame, meta: dict[str, str]) -> go.Figure:
    r"""Inverter voltage-preservation sanity check, in the dq frame.

    Reconstructs the *actually applied* dq voltage from the logged post-inverter
    phase voltages (v_a, v_b, v_c) via Clarke + Park using the measured
    electrical angle, then plots (v_d^actual - v_d^ref) and
    (v_q^actual - v_q^ref). The cycle-average of each must be ≈ 0 — non-zero
    mean implies a scaling or sign-convention bug in the inverter / transforms.
    The cycle-resolved trace is the PWM ripple seen in the dq frame: the
    disturbance the current-loop PI is fighting.
    """
    t = _t_ms(df)
    v_a = df["v_a"].to_numpy()
    v_b = df["v_b"].to_numpy()
    v_c = df["v_c"].to_numpy()
    theta_e = df["theta_e_meas"].to_numpy()
    v_d_ref = df["v_d_ref"].to_numpy()
    v_q_ref = df["v_q_ref"].to_numpy()

    v_alpha = (2.0 / 3.0) * (v_a - 0.5 * v_b - 0.5 * v_c)
    v_beta = (v_b - v_c) / np.sqrt(3.0)
    cos_t = np.cos(theta_e)
    sin_t = np.sin(theta_e)
    v_d_act = v_alpha * cos_t + v_beta * sin_t
    v_q_act = -v_alpha * sin_t + v_beta * cos_t

    err_d = v_d_act - v_d_ref
    err_q = v_q_act - v_q_ref

    _, start, end = _steady_state_window(df)
    mean_d = float(np.mean(err_d[start:end]))
    mean_q = float(np.mean(err_q[start:end]))

    title_d = rf"$v_d^{{\,actual}} - v_d^{{\,ref}} \;[\mathrm{{V}}]\quad (\overline{{\Delta v_d}}={mean_d:+.3g})$"
    title_q = rf"$v_q^{{\,actual}} - v_q^{{\,ref}} \;[\mathrm{{V}}]\quad (\overline{{\Delta v_q}}={mean_q:+.3g})$"
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06, subplot_titles=(title_d, title_q))
    fig.add_trace(go.Scatter(x=t, y=err_d, name=r"$\Delta v_d$", line=_line(0)), row=1, col=1)
    fig.add_hline(y=0.0, line=dict(width=0.5, color="black"), row=1, col=1)
    fig.add_trace(go.Scatter(x=t, y=err_q, name=r"$\Delta v_q$", line=_line(1)), row=2, col=1)
    fig.add_hline(y=0.0, line=dict(width=0.5, color="black"), row=2, col=1)
    fig.update_xaxes(title_text=r"$t \;[\mathrm{ms}]$", row=2, col=1)
    fig.update_layout(title=_title(meta, "dq voltage round-trip (inverter preservation check)"), height=520, hovermode="x unified", margin=_FIG_MARGIN, legend=_FIG_LEGEND)
    return fig


def figure_iq_zoom(df: pl.DataFrame, meta: dict[str, str]) -> go.Figure:
    r"""i_q^{meas} zoomed to a few PWM cycles in steady state, with carrier guides.

    The full-horizon i_q trace averages the ripple away. This view shows the
    triangular ripple at the controller's eyes and overlays vertical guides at
    each carrier valley (start of each PWM cycle), so the relationship between
    ripple, carrier phase, and the once-per-cycle FOC tick is visible.
    """
    f_pwm = float(meta.get("slimtorq.f_pwm", "20000"))
    T_pwm = 1.0 / f_pwm

    t = df["t"].to_numpy()
    iq = df["i_q_meas"].to_numpy()
    iqr = df["i_q_ref"].to_numpy()
    n = len(t)
    if n < 8:
        fig = go.Figure()
        fig.update_layout(title="i_q zoom skipped: signal too short")
        return fig

    end = n
    start = max(0, end - round(5.0 * T_pwm / (t[1] - t[0])))
    t_ms = t[start:end] * 1e3
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=t_ms, y=iqr[start:end], name=r"$i_q^{\,*}$", line=_line(1, ref=True)))
    fig.add_trace(go.Scatter(x=t_ms, y=iq[start:end], name=r"$i_q$", line=_line(1)))

    # Carrier valleys at integer multiples of T_pwm within the window.
    first_valley = math.ceil(t[start] / T_pwm) * T_pwm
    last_valley = math.floor(t[end - 1] / T_pwm) * T_pwm
    k = 0
    while first_valley + k * T_pwm <= last_valley + 1e-15:
        v_ms = (first_valley + k * T_pwm) * 1e3
        fig.add_vline(x=v_ms, line=dict(width=0.5, color="black", dash="dot"))
        k += 1

    fig.update_xaxes(title_text=r"$t \;[\mathrm{ms}]$")
    fig.update_yaxes(title_text=r"$i_q \;[\mathrm{A}]$")
    fig.update_layout(title=_title(meta, f"i_q zoom (~5 x T_pwm @ f_pwm={f_pwm:g} Hz)"), height=400, hovermode="x unified", margin=_FIG_MARGIN, legend=_FIG_LEGEND)
    return fig


def _fft_log(t: np.ndarray, sig: np.ndarray, start: int) -> tuple[np.ndarray, np.ndarray]:
    """Trailing-window DC-removed rFFT, magnitude clamped to a log floor."""
    sig = sig[start:] - np.mean(sig[start:])
    Ts = float(t[1] - t[0])
    freqs = np.fft.rfftfreq(len(sig), d=Ts)
    mag = np.abs(np.fft.rfft(sig)) / max(len(sig), 1)
    mag = np.maximum(mag, 1e-12)
    return freqs, mag


def figure_iq_fft(df: pl.DataFrame, meta: dict[str, str]) -> go.Figure:
    r"""Log-magnitude spectrum of i_q^{meas} (trailing 80 %, DC removed).

    The signal closest to the PWM source. Switching ripple shows up as discrete
    lines at 2·f_pwm, 4·f_pwm, 6·f_pwm; dead-time shows up at low electrical
    harmonics (6·f_1, 12·f_1, with f_1 = p·ω_m/2π).
    """
    t, start, n = _steady_state_window(df)
    if n - start < 8:
        fig = go.Figure()
        fig.update_layout(title="FFT skipped: signal too short")
        return fig
    freqs, mag = _fft_log(t, df["i_q_meas"].to_numpy(), start)
    f_pwm = float(meta.get("slimtorq.f_pwm", "20000"))

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=freqs, y=mag, name=r"$|\mathrm{FFT}(i_q^{\,meas})|$", line=_line(1)))
    for kx in (1, 2, 3):
        fig.add_vline(x=kx * f_pwm, line=dict(width=0.5, color="red", dash="dot"), annotation_text=f"{kx}·f_pwm")
    fig.update_yaxes(type="log", title_text=r"$|\mathrm{FFT}(i_q^{\,meas})| \;[\mathrm{A,\,normalised}]$")
    fig.update_xaxes(title_text=r"$f \;[\mathrm{Hz}]$")
    fig.update_layout(
        title=rf"{_title(meta, r'$i_q^{meas}$ spectrum')}  (last {100 * (n - start) // n}% of samples)",
        height=450,
        hovermode="x",
        margin=_FIG_MARGIN,
        legend=_FIG_LEGEND,
    )
    return fig


def figure_iabc_fft(df: pl.DataFrame, meta: dict[str, str]) -> go.Figure:
    r"""Log-magnitude spectrum of i_a (trailing 80 %, DC removed).

    Single phase is enough — the dead-time signature is 5·f_1 / 7·f_1 around
    the fundamental, and switching ripple appears at f_pwm ± n·f_1.
    """
    t, start, n = _steady_state_window(df)
    if n - start < 8:
        fig = go.Figure()
        fig.update_layout(title="FFT skipped: signal too short")
        return fig
    freqs, mag = _fft_log(t, df["i_a"].to_numpy(), start)
    f_pwm = float(meta.get("slimtorq.f_pwm", "20000"))

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=freqs, y=mag, name=r"$|\mathrm{FFT}(i_a)|$", line=_line(0)))
    fig.add_vline(x=f_pwm, line=dict(width=0.5, color="red", dash="dot"), annotation_text="f_pwm")
    fig.update_yaxes(type="log", title_text=r"$|\mathrm{FFT}(i_a)| \;[\mathrm{A,\,normalised}]$")
    fig.update_xaxes(title_text=r"$f \;[\mathrm{Hz}]$")
    fig.update_layout(
        title=rf"{_title(meta, r'$i_a$ spectrum')}  (last {100 * (n - start) // n}% of samples)",
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
