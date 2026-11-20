"""
Interactive manual calibration against the paper's Fig. 3.

Our space-charge fields are drawn as solid lines and the digitized curves of the
paper (input/wh_fig3_datasets.csv) as dashed lines in the same colours. Move the
sliders and press Compute to see how each parameter changes the curves, and try
to make the solid lines fall on the dashed ones.

Top panel:    E_sp, E_I,rod and their sum (ours solid, paper dashed). The dotted
              vertical lines mark where E_sp has its maximum (ours and paper's).
Bottom panel: total field E_ex + E_sp + E_I,rod + E_I,plane along the axis, with
              the E_c line and the streamer head z = L_cs. The dashed curve is
              "our E_ex + the paper's E_sp + E_I,rod" (the paper's implied total).
              Rule to satisfy: E_total >= E_c inside the streamer, decreasing,
              with its minimum E_c at the head.

The charge amplitude is A = (A scale) * A_Gauss, where A_Gauss comes from Q_cs
(Gauss's law with E_c) as in the solver. A scale = 1 is the paper's model; any
other value tells by how much the charge would have to change.

Every z is measured from the rod tip apex. Run from the repo root:
    python interactive.py
"""

import matplotlib

matplotlib.use('TkAgg')

import matplotlib.pyplot as plt
import mplcursors
import numpy as np
from matplotlib.widgets import Button, Slider

from compare_datasets import load_curves
from solver.applied_field import calculate_applied_field
from solver.fields import calculate_e_plane_image, calculate_e_rod_image, calculate_e_sp
from solver.utilities import calculate_A_from_charge, calculate_qcs_from_field

# =============================================================================
# INPUTS (high-voltage engineering units)
# =============================================================================
R_cm          = 0.1       # rod tip radius [cm]
D_cm          = 80.0      # tip-to-plane gap [cm]
V_kV          = 27.5      # rod voltage of Fig. 3 [kV]
ROD_LENGTH_cm = 400.0     # modelled rod length for the CSM applied field [cm] (assumed 5 * D)

PAPER_FILE = 'input/wh_fig3_datasets.csv'   # digitized curves of the paper's Fig. 3
PAPER_ESP, PAPER_EI, PAPER_SUM = 'Esp', 'Ei,rod', 'Esp+Ei,rod'   # curve names in that file

Z_MIN_cm, Z_MAX_cm = 0.005, 3.5   # observation range along the axis [cm]
N_NEAR, N_FAR = 40, 80           # points in [Z_MIN, 0.5 cm] (log-spaced, steep apex region) and [0.5 cm, Z_MAX]
Z_ERROR_FROM_cm = 0.1     # RMS errors against the paper use only z >= this [cm] (steep, hard-to-digitize apex)

# Initial slider values (paper's Fig. 3 parameters, theta_B from E_total(2.7) = 5)
INIT = {
    'L_cs':    2.7,       # streamer length [cm]
    'theta_B': 93.39,     # full cone angle [deg]
    'B':       1.5,       # density exponent [-]
    'C':       0.035,     # density offset [cm]
    'E_c':     5.0,       # stability field [kV/cm]
    'A_scale': 1.0,       # multiplier on A from Gauss's law [-]
}

CM_TO_M, KV_TO_V, VM_TO_KVCM = 1e-2, 1e3, 1e-5

# =============================================================================
# 1. Fixed data: observation points, applied field, paper curves
# =============================================================================
z_cm = np.concatenate((np.geomspace(Z_MIN_cm, 0.5, N_NEAR, endpoint=False), np.linspace(0.5, Z_MAX_cm, N_FAR)))
z_m = z_cm * CM_TO_M
R_m, D_m = R_cm * CM_TO_M, D_cm * CM_TO_M

print('Computing the applied field (CSM)...')
E_ex = calculate_applied_field(R_m, D_m, V_kV * KV_TO_V, z_m,
                               rod_length=ROD_LENGTH_cm * CM_TO_M) * VM_TO_KVCM

paper_curves, _ = load_curves(PAPER_FILE)
paper = {curve.name: curve for curve in paper_curves}
paper_esp, paper_ei, paper_sum = paper[PAPER_ESP], paper[PAPER_EI], paper[PAPER_SUM]

# Paper's implied total: our E_ex + the paper's E_sp + E_I,rod (on our z grid, inside the digitized range)
inside_paper = (z_cm >= paper_sum.x.min()) & (z_cm <= paper_sum.x.max())
paper_total = np.where(inside_paper, E_ex + np.interp(z_cm, paper_sum.x, paper_sum.y), np.nan)


def peak_position(x, y):
    """z of the maximum of a curve."""
    return x[int(np.nanargmax(y))]


def rms_against_paper(curve, ours):
    """RMS of (ours - paper) at the paper's x values, z >= Z_ERROR_FROM_cm, inside our z range."""
    use = (curve.x >= Z_ERROR_FROM_cm) & (curve.x <= z_cm[-1])
    return float(np.sqrt(np.mean((np.interp(curve.x[use], z_cm, ours) - curve.y[use]) ** 2)))


# =============================================================================
# 2. Our fields for a set of parameters
# =============================================================================
def compute_fields(L_cs, theta_B, B, C, E_c, A_scale):
    """All axial fields [kV/cm] on z_cm, plus Q_cs [C] and A [SI], for HV-unit inputs."""
    L_m, C_m, theta_rad = L_cs * CM_TO_M, C * CM_TO_M, np.radians(theta_B)

    Q_gauss = calculate_qcs_from_field(E_c / VM_TO_KVCM, L_cs_m=L_m, theta_B_rad=theta_rad)
    A = A_scale * calculate_A_from_charge(Q_gauss, B, C_m, L_cs_m=L_m, theta_B_rad=theta_rad)
    Q = A_scale * Q_gauss   # charge is linear in A

    geometry = {'R': R_m, 'L_cs': L_m, 'theta_B': theta_rad, 'A': A, 'B': B, 'C': C_m}
    E_sp = calculate_e_sp(z_m, **geometry) * VM_TO_KVCM
    E_rod = calculate_e_rod_image(z_m, **geometry) * VM_TO_KVCM
    E_plane = calculate_e_plane_image(z_m, d=D_m, **geometry) * VM_TO_KVCM
    return E_sp, E_rod, E_plane, Q, A


# =============================================================================
# 3. Figure
# =============================================================================
fig, (ax_top, ax_bot) = plt.subplots(2, 1, figsize=(11, 10), sharex=True,
                                     gridspec_kw={'height_ratios': [3, 2]})
plt.subplots_adjust(left=0.08, right=0.97, top=0.97, bottom=0.30, hspace=0.08)

# Top: space-charge fields, ours (solid) and paper (dashed)
blank = np.full_like(z_cm, np.nan)
line_esp, = ax_top.plot(z_cm, blank, 'b-', lw=2, label=r'$E_{sp}$ (ours)')
line_ei, = ax_top.plot(z_cm, blank, 'r-', lw=2, label=r'$E_{I,rod}$ (ours)')
line_sum, = ax_top.plot(z_cm, blank, 'k-', lw=2, label=r'$E_{sp}+E_{I,rod}$ (ours)')
ax_top.plot(paper_esp.x, paper_esp.y, 'b--', lw=1.3, alpha=0.7, label=r'$E_{sp}$ (paper)')
ax_top.plot(paper_ei.x, paper_ei.y, 'r--', lw=1.3, alpha=0.7, label=r'$E_{I,rod}$ (paper)')
ax_top.plot(paper_sum.x, paper_sum.y, 'k--', lw=1.3, alpha=0.7, label=r'$E_{sp}+E_{I,rod}$ (paper)')
paper_peak = peak_position(paper_esp.x, paper_esp.y)
ax_top.axvline(paper_peak, color='b', ls=':', alpha=0.7)
peak_ours = ax_top.axvline(np.nan, color='b', ls=':', lw=1.5)
ax_top.axhline(0, color='gray', lw=0.8)
ax_top.set_ylabel('E [kV/cm]')
ax_top.set_ylim(-60, 15)
ax_top.grid(True, ls='--', alpha=0.5)
ax_top.legend(fontsize=9, loc='lower right', ncol=2)

status = ax_top.text(0.22, 0.03, '', transform=ax_top.transAxes, fontsize=9, va='bottom',
                     family='monospace', bbox={'boxstyle': 'round', 'facecolor': 'lightyellow', 'alpha': 0.85})

# Bottom: total field and the rule
ax_bot.plot(z_cm, E_ex, color='gray', lw=1.2, label=r'$E_{ex}$ (CSM)')
line_total, = ax_bot.plot(z_cm, blank, 'k-', lw=2, label=r'$E_{total}$ (ours)')
ax_bot.plot(z_cm, paper_total, 'k--', lw=1.3, alpha=0.7, label=r'$E_{ex}$ + paper $E_{sp}+E_{I,rod}$')
line_ec = ax_bot.axhline(INIT['E_c'], color='g', ls='--', lw=1.2, label=r'$E_c$')
line_head = ax_bot.axvline(INIT['L_cs'], color='m', ls=':', lw=1.5, label=r'head $z = L_{cs}$')
ax_bot.set_xlabel('z from the tip apex [cm]')
ax_bot.set_ylabel('E [kV/cm]')
ax_bot.set_ylim(0, 15)
ax_bot.set_xlim(0, Z_MAX_cm)
ax_bot.grid(True, ls='--', alpha=0.5)
ax_bot.legend(fontsize=9, loc='upper right')

# Sliders
slider_specs = [  # key, label, min, max, step
    ('L_cs',    r'$L_{cs}$ [cm]',     1.0,   4.0,  0.05),
    ('theta_B', r'$\theta_B$ [deg]',  10.0, 175.0, 0.5),
    ('B',       'B [-]',              0.5,   3.0,  0.05),
    ('C',       'C [cm]',             0.005, 0.3,  0.005),
    ('E_c',     r'$E_c$ [kV/cm]',     3.0,   7.0,  0.1),
    ('A_scale', r'A / $A_{Gauss}$',   0.1,   4.0,  0.01),
]
sliders = {}
for i, (key, label, low, high, step) in enumerate(slider_specs):
    slider_ax = fig.add_axes((0.14, 0.24 - i * 0.037, 0.58, 0.022))
    sliders[key] = Slider(slider_ax, label, low, high, valinit=INIT[key], valstep=step)

btn_compute = Button(fig.add_axes((0.78, 0.115, 0.18, 0.13)), 'Compute', color='lightgreen', hovercolor='orange')
btn_reset = Button(fig.add_axes((0.78, 0.04, 0.18, 0.06)), 'Reset', color='lightgray', hovercolor='orange')


# =============================================================================
# 4. Update
# =============================================================================
def rule_check(E_total, L_cs, E_c):
    """Report the rule inside the streamer (z_error_from <= z <= L_cs): >= E_c, decreasing, E_c at the head."""
    inside = (z_cm >= Z_ERROR_FROM_cm) & (z_cm <= L_cs)
    E_in = E_total[inside]
    head = float(np.interp(L_cs, z_cm, E_total))
    below = bool(np.any(E_in < E_c - 1e-9))
    decreasing = bool(np.all(np.diff(E_in) <= 1e-9))
    return (f'E_total(head) = {head:6.2f} kV/cm   min inside = {E_in.min():6.2f}\n'
            f'>= E_c inside: {"yes" if not below else "NO"}    decreasing: {"yes" if decreasing else "NO"}')


def compute(_event=None):
    values = {key: slider.val for key, slider in sliders.items()}
    status.set_text('Computing integrals, please wait...')
    fig.canvas.draw()
    fig.canvas.flush_events()

    E_sp, E_rod, E_plane, Q, A = compute_fields(**values)
    E_sum = E_sp + E_rod
    E_total = E_ex + E_sum + E_plane

    line_esp.set_ydata(E_sp)
    line_ei.set_ydata(E_rod)
    line_sum.set_ydata(E_sum)
    line_total.set_ydata(E_total)
    our_peak = peak_position(z_cm, E_sp)
    peak_ours.set_xdata([our_peak, our_peak])
    line_ec.set_ydata([values['E_c'], values['E_c']])
    line_head.set_xdata([values['L_cs'], values['L_cs']])

    status.set_text(
        f'Q_cs = {Q * 1e9:7.3f} nC   A = {A:.4g} SI\n'
        f'E_sp max at z = {our_peak:5.2f} cm (paper {paper_peak:5.2f} cm)\n'
        f'RMS vs paper [kV/cm] (z >= {Z_ERROR_FROM_cm} cm):\n'
        f'  E_sp {rms_against_paper(paper_esp, E_sp):6.2f}   E_I,rod {rms_against_paper(paper_ei, E_rod):6.2f}'
        f'   sum {rms_against_paper(paper_sum, E_sum):6.2f}\n'
        + rule_check(E_total, values['L_cs'], values['E_c']))
    fig.canvas.draw_idle()


def reset(_event=None):
    for slider in sliders.values():
        slider.reset()
    compute()


btn_compute.on_clicked(compute)
btn_reset.on_clicked(reset)

print('Computing the initial curves...')
compute()
mplcursors.cursor([line_esp, line_ei, line_sum, line_total], hover=True)
plt.show()
