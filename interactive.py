import matplotlib
matplotlib.use('TkAgg')

import mplcursors
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button
from solver.fields import calculate_e_sp, calculate_e_rod_image
from solver.utilities import calculate_qcs_from_field, calculate_A_from_charge

# Setup figure with extra space at the bottom for multiple sliders and buttons
fig, ax = plt.subplots(figsize=(10, 8.5))
plt.subplots_adjust(bottom=0.38)

# Initial baseline values matching your configuration
init_R_cm       = 0.1       # 0.1 cm = 0.001 m
init_Lcs_cm     = 2.7       # 2.7 cm = 0.027 m
init_theta_deg  = 60        # 60 degrees
init_B          = 1.5       # Exponent
init_C_cm       = 0.035     # 0.035 cm = 0.00035 m
init_ec         = 5.0       # 5 kV/cm

z_WH = np.linspace(0.0001, 0.035, 100)

# Coordinate system state tracking flag
is_wh_mode = True

def get_x_data(R_cm):
    """Return x values in cm based on active coordinate system."""
    R_m = R_cm / 100.0
    if is_wh_mode:
        return z_WH * 100  # Z_WH = 0 at tip apex
    else:
        return (z_WH + R_m) * 100  # z = 0 at rod center

def compute_all_fields(R_cm, Lcs_cm, theta_deg, B_val, C_cm, ec_val):
    R_m = R_cm / 100.0
    Lcs_m = Lcs_cm / 100.0
    C_m = C_cm / 100.0
    theta_B_rad = np.radians(theta_deg)
    
    # Solver always operates on z_points (origin at rod center)
    z_points = z_WH + R_m

    Q_cs = calculate_qcs_from_field(ec_val, L_cs_m=Lcs_m, theta_B_rad=theta_B_rad)
    A = calculate_A_from_charge(Q_cs, B_val, C_m, L_cs_m=Lcs_m, theta_B_rad=theta_B_rad)
    
    E_sp = calculate_e_sp(z_points, R=R_m, L_cs=Lcs_m, theta_B=theta_B_rad, A=A, B=B_val, C=C_m)
    E_I = calculate_e_rod_image(z_points, R=R_m, L_cs=Lcs_m, theta_B=theta_B_rad, A=A, B=B_val, C=C_m)
    E_total_space = E_sp + E_I

    # Convert to kV/cm
    E_sp_kv_cm = E_sp * 1e-5
    E_I_kv_cm = E_I * 1e-5
    E_total_kv_cm = E_total_space * 1e-5

    return E_sp_kv_cm, E_I_kv_cm, E_total_kv_cm

# Initial data evaluation
esp_init, ei_init, etot_init = compute_all_fields(
    init_R_cm, init_Lcs_cm, init_theta_deg, init_B, init_C_cm, init_ec
)

x_init = get_x_data(init_R_cm)

# Plot curves
line_esp, = ax.plot(x_init, esp_init, 'b-', label=r'1: $E_{SP} \sim Z$', linewidth=2)
line_ei, = ax.plot(x_init, ei_init, 'r--', label=r'2: $E_{I} \sim Z$', linewidth=2)
line_etot, = ax.plot(x_init, etot_init, 'k-.', label=r'3: $E_{SP} + E_{I} \sim Z$', linewidth=2)

ax.axhline(0, color='gray', linestyle=':', linewidth=0.8)
ax.set_xlabel('Z_WH (cm) [Distance from tip apex]')
ax.set_ylabel('E (kV/cm)')
ax.set_title('Interactive Replication of Wang-Haiting Fig 3')
ax.grid(True, which='both', linestyle='--', alpha=0.5)
ax.legend(fontsize=11)
ax.set_ylim(-55, 10)

# Status indicator text box on the plot
status_text = ax.text(0.02, 0.92, 'Ready. Adjust parameters and click Compute.', 
                      transform=ax.transAxes, fontsize=11,
                      verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.6))

# Add Sliders (stacked vertically)
ax_R     = plt.axes((0.15, 0.31, 0.55, 0.025))
ax_Lcs   = plt.axes((0.15, 0.27, 0.55, 0.025))
ax_theta = plt.axes((0.15, 0.23, 0.55, 0.025))
ax_B     = plt.axes((0.15, 0.19, 0.55, 0.025))
ax_C     = plt.axes((0.15, 0.15, 0.55, 0.025))
ax_ec    = plt.axes((0.15, 0.11, 0.55, 0.025))

slider_R     = Slider(ax_R, 'R (cm)', 0.05, 0.5, valinit=init_R_cm, valstep=0.01)
slider_Lcs   = Slider(ax_Lcs, 'L_cs (cm)', 1.0, 5.0, valinit=init_Lcs_cm, valstep=0.1)
slider_theta = Slider(ax_theta, 'Theta_B (°)', 15, 80, valinit=init_theta_deg, valstep=5)
slider_B     = Slider(ax_B, 'B (exp)', 1.0, 2.5, valinit=init_B, valstep=0.05)
slider_C     = Slider(ax_C, 'C (cm)', 0.01, 0.1, valinit=init_C_cm, valstep=0.005)
slider_ec    = Slider(ax_ec, 'Ec (kV/cm)', 3.0, 7.0, valinit=init_ec, valstep=0.2)

# Split the right control space into two buttons: Toggle Button (Top) & Compute Button (Bottom)
ax_toggle = plt.axes((0.75, 0.23, 0.18, 0.105))
btn_toggle = Button(ax_toggle, 'Coord: WH Apex', color='lightskyblue', hovercolor='deepskyblue')

ax_button = plt.axes((0.75, 0.11, 0.18, 0.105))
btn_compute = Button(ax_button, 'Compute', color='lightgreen', hovercolor='orange')

def update_x_axis():
    """Helper to refresh X data and axis labels."""
    x_new = get_x_data(slider_R.val)
    line_esp.set_xdata(x_new)
    line_ei.set_xdata(x_new)
    line_etot.set_xdata(x_new)

    if is_wh_mode:
        ax.set_xlabel('Z_WH (cm) [Distance from tip apex]')
    else:
        ax.set_xlabel('z (cm) [Distance from rod center]')

    ax.relim()
    ax.autoscale_view(scalex=True, scaley=False)

def on_toggle_clicked(event):
    global is_wh_mode
    is_wh_mode = not is_wh_mode
    
    # Update button label
    btn_toggle.label.set_text('Coord: WH Apex' if is_wh_mode else 'Coord: Rod Center')
    
    # Update plot coordinates
    update_x_axis()
    status_text.set_text(f"Switched coordinate system: {'WH Apex' if is_wh_mode else 'Rod Center'}")
    fig.canvas.draw_idle()

def on_compute_clicked(event):
    status_text.set_text("Computing integrals, please wait...")
    fig.canvas.draw()
    fig.canvas.flush_events()
    
    # Run calculation using all current slider states
    esp_new, ei_new, etot_new = compute_all_fields(
        slider_R.val, slider_Lcs.val, slider_theta.val, 
        slider_B.val, slider_C.val, slider_ec.val
    )
    
    # Update y-data
    line_esp.set_ydata(esp_new)
    line_ei.set_ydata(ei_new)
    line_etot.set_ydata(etot_new)
    
    # Ensure x-data is synchronized in case R changed
    update_x_axis()
    
    status_text.set_text("Done! All fields updated.")
    fig.canvas.draw_idle()

btn_toggle.on_clicked(on_toggle_clicked)
btn_compute.on_clicked(on_compute_clicked)

mplcursors.cursor(hover=True)
plt.show()
