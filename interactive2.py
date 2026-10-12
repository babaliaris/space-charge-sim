import matplotlib
matplotlib.use('TkAgg')

import mplcursors
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button
from scipy.optimize import brentq

from solver.applied_field import calculate_applied_field
from solver.fields import calculate_e_sp, calculate_e_rod_image, calculate_e_plane_image
from solver.utilities import calculate_qcs_from_field, calculate_A_from_charge

# Setup figure
fig, ax = plt.subplots(figsize=(10, 8.5))
plt.subplots_adjust(bottom=0.35)

# Fixed Wang & Haiting Benchmark Parameters
FIXED_R_cm   = 0.1
FIXED_D_cm   = 80.0
FIXED_V_kV   = 27.5
FIXED_Lcs_cm = 2.7
FIXED_EC     = 5.0

# Initial adjustable parameters for sliders (B and C)
init_B       = 1.5
init_C_cm    = 0.035

# Observation grid from the tip apex [m]: includes z = 0 and is geometrically
# spaced so the steep near-tip region (fields halve within ~1 mm) is well resolved.
z_WH = np.concatenate(([0.0], np.geomspace(1e-5, 0.035, 300)))
is_full_view = True

# Narrow y-range [kV/cm] around the 5 kV/cm target, used by the zoom toggle
ZOOM_YLIM = (-50, 35)

def objective_theta(theta_deg, B_val, C_cm):
    """
    Objective function: f(theta) = E_total(z = L_cs) - E_target = 0
    Evaluated precisely at the streamer tip z = L_cs (2.7 cm).
    """
    theta_rad = np.radians(theta_deg)
    R_m = FIXED_R_cm / 100.0
    D_m = FIXED_D_cm / 100.0
    Lcs_m = FIXED_Lcs_cm / 100.0
    C_m = C_cm / 100.0
    z_tip_m = Lcs_m  # Observation at streamer tip (measured from the tip apex)

    # Charge distribution calculations
    Q_cs = calculate_qcs_from_field(FIXED_EC * 1e5, L_cs_m=Lcs_m, theta_B_rad=theta_rad)
    A = calculate_A_from_charge(Q_cs, B_val, C_m, L_cs_m=Lcs_m, theta_B_rad=theta_rad)

    # Field components at z = L_cs
    e_ex = float(calculate_applied_field(R_m, D_m, FIXED_V_kV * 1e3, z_tip_m)) / 1e5
    e_sp = calculate_e_sp(z_tip_m, R_m, Lcs_m, theta_rad, A, B_val, C_m) / 1e5
    e_rod = calculate_e_rod_image(z_tip_m, R_m, Lcs_m, theta_rad, A, B_val, C_m) / 1e5
    e_plane = calculate_e_plane_image(z_tip_m, D_m, R_m, Lcs_m, theta_rad, A, B_val, C_m) / 1e5

    e_total = e_ex + e_sp + e_rod + e_plane
    return e_total - FIXED_EC

def compute_fields_for_theta(theta_deg, B_val, C_cm):
    theta_rad = np.radians(theta_deg)
    R_m = FIXED_R_cm / 100.0
    D_m = FIXED_D_cm / 100.0
    Lcs_m = FIXED_Lcs_cm / 100.0
    C_m = C_cm / 100.0

    Q_cs = calculate_qcs_from_field(FIXED_EC * 1e5, L_cs_m=Lcs_m, theta_B_rad=theta_rad)
    A = calculate_A_from_charge(Q_cs, B_val, C_m, L_cs_m=Lcs_m, theta_B_rad=theta_rad)
    
    E_sp = calculate_e_sp(z_WH, R=R_m, L_cs=Lcs_m, theta_B=theta_rad, A=A, B=B_val, C=C_m)
    E_I_rod = calculate_e_rod_image(z_WH, R=R_m, L_cs=Lcs_m, theta_B=theta_rad, A=A, B=B_val, C=C_m)
    E_I_plane = calculate_e_plane_image(z_WH, d=D_m, R=R_m, L_cs=Lcs_m, theta_B=theta_rad, A=A, B=B_val, C=C_m)
    E_ex_kv_cm = calculate_applied_field(R_m, D_m, FIXED_V_kV * 1e3, z_WH) * 1e-5

    E_sp_kv_cm = E_sp * 1e-5
    E_I_rod_kv_cm = E_I_rod * 1e-5
    E_I_plane_kv_cm = E_I_plane * 1e-5
    E_total_kv_cm = E_ex_kv_cm + E_sp_kv_cm + E_I_rod_kv_cm + E_I_plane_kv_cm

    return E_ex_kv_cm, E_sp_kv_cm, E_I_rod_kv_cm, E_I_plane_kv_cm, E_total_kv_cm

# Automatically solve for initial theta using brentq between 5° and 175°
try:
    solved_theta_init = brentq(objective_theta, 5.0, 175.0, args=(init_B, init_C_cm))
except Exception as e:
    solved_theta_init = 45.0  # fallback

eex_init, esp_init, eirod_init, eiplane_init, etot_init = compute_fields_for_theta(solved_theta_init, init_B, init_C_cm)
x_init = z_WH * 100  # cm from the tip apex

# Plot curves
line_eex,     = ax.plot(x_init, eex_init, 'g:',  label=r'E_ex', linewidth=1.5)
line_esp,     = ax.plot(x_init, esp_init, 'b-',  label=r'E_SP', linewidth=2)
line_eirod,   = ax.plot(x_init, eirod_init, 'r--', label=r'E_{I,rod}', linewidth=1.5)
line_eiplane, = ax.plot(x_init, eiplane_init, 'm:', label=r'E_{I,plane}', linewidth=1.5)
line_etot,    = ax.plot(x_init, etot_init, 'k-',  label=r'Total E', linewidth=2.5)

ax.axhline(0, color='gray', linestyle=':', linewidth=0.8)
ax.axhline(FIXED_EC, color='orange', linestyle='--', linewidth=1.0, label='Target 5 kV/cm')
ax.axvline(FIXED_Lcs_cm, color='cyan', linestyle='-.', linewidth=1.0, label=f'L_cs = {FIXED_Lcs_cm} cm')

ax.set_xlabel('Z_WH (cm)')
ax.set_ylabel('E (kV/cm)')
ax.set_title(f'Dynamic Theta Solver (Enforcing E_total({FIXED_Lcs_cm} cm) = {FIXED_EC} kV/cm)')
ax.grid(True, which='both', linestyle='--', alpha=0.5)
ax.legend(fontsize=9, loc='upper right')

def apply_y_limits():
    """Full view fits every curve (incl. the peaks at z = 0); zoom view shows the target region."""
    if not is_full_view:
        ax.set_ylim(*ZOOM_YLIM)
        return
    y_all = np.concatenate([line.get_ydata() for line in field_lines] + [[0.0, FIXED_EC]])
    y_min, y_max = np.nanmin(y_all), np.nanmax(y_all)
    margin = 0.05 * (y_max - y_min)
    ax.set_ylim(y_min - margin, y_max + margin)

field_lines = [line_eex, line_esp, line_eirod, line_eiplane, line_etot]
apply_y_limits()

status_text = ax.text(0.02, 0.92, f'Solved Theta_B: {solved_theta_init:.2f}°', 
                      transform=ax.transAxes, fontsize=11,
                      verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.6))

# Sliders only for secondary parameters like B and C (since L_cs and R are fixed by benchmark)
ax_B     = plt.axes((0.15, 0.22, 0.55, 0.03))
ax_C     = plt.axes((0.15, 0.16, 0.55, 0.03))

slider_B = Slider(ax_B, 'B (exp)', 1.0, 2.5, valinit=init_B, valstep=0.05)
slider_C = Slider(ax_C, 'C (cm)', 0.01, 0.1, valinit=init_C_cm, valstep=0.005)

ax_zoom = plt.axes((0.75, 0.22, 0.18, 0.06))
btn_zoom = Button(ax_zoom, 'View: Full', color='khaki', hovercolor='gold')

ax_compute = plt.axes((0.75, 0.145, 0.18, 0.06))
btn_compute = Button(ax_compute, 'Compute', color='lightgreen', hovercolor='orange')

def on_zoom_clicked(event):
    global is_full_view
    is_full_view = not is_full_view
    btn_zoom.label.set_text('View: Full' if is_full_view else 'View: Target Zoom')
    apply_y_limits()
    fig.canvas.draw_idle()

def on_compute_clicked(event):
    status_text.set_text('Computing integrals, please wait...')
    status_text.set_bbox(dict(boxstyle='round', facecolor='lightblue', alpha=0.6))
    fig.canvas.draw()
    fig.canvas.flush_events()
    update_plot()

def update_plot():
    b_val = slider_B.val
    c_val = slider_C.val
    
    try:
        # Automatically solve for theta where total field equals 5 kV/cm at L_cs = 2.7 cm
        solved_theta = brentq(objective_theta, 1.0, 179.0, args=(b_val, c_val))
        status_text.set_text(f'Solved Theta_B: {solved_theta:.2f}° (Valid Equilibrium)')
        status_text.set_bbox(dict(boxstyle='round', facecolor='lightgreen', alpha=0.6))
    except Exception as ex:
        status_text.set_text(f'Root finding failed: {str(ex)[:30]}')
        status_text.set_bbox(dict(boxstyle='round', facecolor='lightcoral', alpha=0.6))
        fig.canvas.draw_idle()
        return

    eex_new, esp_new, eirod_new, eiplane_new, etot_new = compute_fields_for_theta(solved_theta, b_val, c_val)
    
    line_eex.set_ydata(eex_new)
    line_esp.set_ydata(esp_new)
    line_eirod.set_ydata(eirod_new)
    line_eiplane.set_ydata(eiplane_new)
    line_etot.set_ydata(etot_new)
    apply_y_limits()

    fig.canvas.draw_idle()

btn_compute.on_clicked(on_compute_clicked)
btn_zoom.on_clicked(on_zoom_clicked)

mplcursors.cursor(hover=True)
plt.show()
