"""
matplotlib drawings of a RunResult for the GUI tabs. Every curve gets a hover cursor
(mplcursors) that shows its name and the x, y values under the mouse.

Each function draws the selected run (solid lines) and, dashed, the runs ticked for comparison.
"""

import mplcursors
import numpy as np

COLORS = {"E_ex": "#6B7090", "E_sp": "#2B5CB8", "E_I,rod": "#C0392B", "E_I,plane": "#1F8A70", "E_total": "#1B1F3B"}
CLOUD_COLORS = ["#4B3FA8", "#D9780F", "#1F8A70", "#C0392B", "#2B5CB8", "#8E44AD", "#7F8C8D", "#B7950B"]


def cloud_color(i):
    return CLOUD_COLORS[i % len(CLOUD_COLORS)]


def attach_cursor(fig, axes_units):
    """Hover cursor on every line of the figure. axes_units: {axes: (x name, x unit, y name, y unit)}."""
    lines = [ln for ax in axes_units for ln in ax.get_lines() if not ln.get_label().startswith("_")]
    if not lines:
        return None
    cursor = mplcursors.cursor(lines, hover=mplcursors.HoverMode.Transient)

    @cursor.connect("add")
    def _(sel):
        xn, xu, yn, yu = axes_units.get(sel.artist.axes, ("x", "", "y", ""))
        x, y = sel.target
        sel.annotation.set_text(f"{sel.artist.get_label()}\n{xn} = {x:.5g} {xu}\n{yn} = {y:.5g} {yu}")
        sel.annotation.get_bbox_patch().set(fc="#FFFFF0", alpha=0.95)
    fig._cursor = cursor          # keep a reference, or the cursor is garbage-collected
    return cursor


def _style(ax, xlabel, ylabel):
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, color="#E3E5EE", linewidth=0.7)
    ax.set_axisbelow(True)


def voltage_and_tip(fig, run, others):
    fig.clear()
    ax1, ax2 = fig.subplots(2, 1, sharex=True)
    ax1.plot(run.t_us, run.V_kV, color="#1B1F3B", label=f"V(t) · {run.name}")
    ax2.plot(run.t_us, run.E_tip_kVcm, color="#4B3FA8", label=f"E_tip(t) · {run.name}")
    for o in others:
        ax1.plot(o.t_us, o.V_kV, "--", label=f"V(t) · {o.name}")
        ax2.plot(o.t_us, o.E_tip_kVcm, "--", label=f"E_tip(t) · {o.name}")
    E0 = run.derived["E0 = V0 e_ex(0) (threshold at the tip) [kV/cm]"]
    ax2.axhline(E0, color="#D9780F", linestyle=":", linewidth=1.2, label=f"E₀ = {E0:.2f} kV/cm")
    for i, c in enumerate(run.clouds):
        ax1.plot([c["t_birth_us"]], [c["V_kV"]], "o", color=cloud_color(i), label=f"burst {c['number']}")
        ax2.axvline(c["t_birth_us"], color=cloud_color(i), linewidth=0.8, alpha=0.6)
    _style(ax1, "", "Voltage [kV]")
    _style(ax2, "t [µs]", "Total field at the tip [kV/cm]")
    ax1.legend(fontsize=8, loc="upper left")
    ax2.legend(fontsize=8, loc="best")
    ax1.set_title("Impulse voltage and total field at the rod tip", fontsize=10)
    fig.tight_layout()
    attach_cursor(fig, {ax1: ("t", "µs", "V", "kV"), ax2: ("t", "µs", "E", "kV/cm")})


def cloud_positions(fig, run, others):
    fig.clear()
    ax = fig.subplots()
    for i, c in enumerate(run.clouds):
        zd = run.zd_cm[i]
        col = cloud_color(i)
        ax.fill_between(run.t_us, zd, zd + c["L_cm"], color=col, alpha=0.15, linewidth=0)
        ax.plot(run.t_us, zd, color=col, linewidth=1.0, label=f"cloud {c['number']}: apex")
        ax.plot(run.t_us, zd + c["z_c0_cm"], color=col, linewidth=1.6, linestyle="-.", label=f"cloud {c['number']}: z_c (E_sp = 0)")
        ax.plot(run.t_us, zd + c["L_cm"], color=col, linewidth=1.0, label=f"cloud {c['number']}: head")
    for o in others:
        for i, c in enumerate(o.clouds):
            ax.plot(o.t_us, o.zd_cm[i] + c["L_cm"], "--", color=cloud_color(i), alpha=0.7, label=f"{o.name} · cloud {c['number']}: head")
    _style(ax, "t [µs]", "Position along the axis z [cm]")
    ax.set_title("Clouds: apex, zero of E_sp and head (shaded: the cloud)", fontsize=10)
    if run.clouds:
        ax.legend(fontsize=8, loc="best", ncol=2)
    else:
        ax.text(0.5, 0.5, "no burst in this run", transform=ax.transAxes, ha="center", color="#6B7090")
    fig.tight_layout()
    attach_cursor(fig, {ax: ("t", "µs", "z", "cm")})


def drift_distance(fig, run, others):
    fig.clear()
    ax1, ax2 = fig.subplots(2, 1, sharex=True)
    for i, c in enumerate(run.clouds):
        ax1.plot(run.t_us, run.zd_cm[i], color=cloud_color(i), label=f"z_drift cloud {c['number']}")
    for o in others:
        for i, c in enumerate(o.clouds):
            ax1.plot(o.t_us, o.zd_cm[i], "--", color=cloud_color(i), label=f"{o.name} · cloud {c['number']}")
    ax2.plot(run.t_us, run.Q_total_nC, color="#4B3FA8", drawstyle="steps-post", label=f"total charge · {run.name}")
    for o in others:
        ax2.plot(o.t_us, o.Q_total_nC, "--", drawstyle="steps-post", label=f"total charge · {o.name}")
    _style(ax1, "", "Drift distance [cm]")
    _style(ax2, "t [µs]", "Space charge in the gap [nC]")
    ax1.set_title("Drift of every cloud and total space charge", fontsize=10)
    if run.clouds or others:
        ax1.legend(fontsize=8, loc="upper left")
    ax2.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    attach_cursor(fig, {ax1: ("t", "µs", "z_drift", "cm"), ax2: ("t", "µs", "Q", "nC")})


def field_profile(fig, run, others, snap_index, shown, log_x=False, y_limits=None):
    """E(z) with its components at run.snap_t_us[snap_index]; others: E_total at their nearest instant."""
    fig.clear()
    ax = fig.subplots()
    t = run.snap_t_us[snap_index]
    for k in shown:
        ax.plot(run.z_cm, run.profiles[k][snap_index], color=COLORS[k], linewidth=2.0 if k == "E_total" else 1.3,
                label=k)
    for o in others:
        j = int(np.argmin(np.abs(o.snap_t_us - t)))
        ax.plot(o.z_cm, o.profiles["E_total"][j], "--", label=f"E_total · {o.name} (t = {o.snap_t_us[j]:.3g} µs)")
    ax.axhline(run.inputs["E_c_kVcm"], color="#D9780F", linestyle=":", linewidth=1.0, label="E_c")
    ax.axhline(0.0, color="#999", linewidth=0.6, label="_zero")
    for i, c in enumerate(run.clouds):           # heads of the clouds present
        if c["t_birth_us"] <= t and (c["t_absorbed_us"] is None or t < c["t_absorbed_us"]):
            j = int(np.argmin(np.abs(run.t_us - t)))
            zd = run.zd_cm[i, j] if run.zd_cm[i, j] == run.zd_cm[i, j] else 0.0
            ax.axvline(zd + c["L_cm"], color=cloud_color(i), linewidth=0.8, linestyle="--", alpha=0.7, label="_head")
    if log_x:
        ax.set_xscale("log")
    if y_limits:
        ax.set_ylim(*y_limits)
    note = run.snap_labels[snap_index]
    ax.set_title(f"Field along the axis at t = {t:.4g} µs" + (f" ({note})" if note else "")
                 + "  ·  dashed verticals: cloud heads", fontsize=10)
    _style(ax, "Distance z from the tip apex [cm]", "Electric field [kV/cm]")
    ax.legend(fontsize=8, loc="best")
    fig.tight_layout()
    attach_cursor(fig, {ax: ("z", "cm", "E", "kV/cm")})


def burst_bars(fig, run, others):
    fig.clear()
    ax1, ax2 = fig.subplots(1, 2)
    runs = [run] + list(others)
    width = 0.8 / len(runs)
    for ri, r in enumerate(runs):
        num = np.array([c["number"] for c in r.clouds], dtype=float)
        if not len(num):
            continue
        x = num - 0.4 + width * (ri + 0.5)
        lab = r.name
        ax1.bar(x, [c["L_cm"] for c in r.clouds], width, label=lab, alpha=1.0 if ri == 0 else 0.6)
        ax2.bar(x, [c["Q_nC"] for c in r.clouds], width, label=lab, alpha=1.0 if ri == 0 else 0.6)
    _style(ax1, "Burst", "Streamer length L [cm]")
    _style(ax2, "Burst", "Charge Q [nC]")
    for ax in (ax1, ax2):
        ax.xaxis.get_major_locator().set_params(integer=True)
        ax.margins(y=0.25)
        if run.clouds:
            ax.legend(fontsize=8)
    fig.tight_layout()
    bars = [b for ax in (ax1, ax2) for b in ax.containers]
    if bars:
        cursor = mplcursors.cursor(bars, hover=mplcursors.HoverMode.Transient)

        @cursor.connect("add")
        def _(sel):
            rect = sel.artist[sel.index]
            first = rect.axes is ax1
            sel.annotation.set_text(f"{sel.artist.get_label()}\nburst {sel.index + 1}\n"
                                    f"{'L' if first else 'Q'} = {rect.get_height():.4g} {'cm' if first else 'nC'}")
        fig._cursor = cursor
