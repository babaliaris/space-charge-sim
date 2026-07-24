import matplotlib
matplotlib.use('TkAgg')

import numpy as np
import matplotlib.pyplot as plt
from solver.fields import calculate_e_sp, calculate_e_rod_image
from solver.utilities import calculate_qcs_from_field, calculate_A_from_charge

def run_theta_b_sensitivity(R_m, Lcs_m, B, C_m, z_WH, z_points):
    """
    Performs sensitivity analysis by varying the boundary angle theta_B 
    while keeping E_c constant at 5.0 kV/cm.
    """
    theta_deg_values    = [30, 45, 60, 75]
    E_c_fixed           = 5.0  # kV/cm

    plt.figure(figsize=(9, 6))

    for deg in theta_deg_values:
        theta_B_rad = np.radians(deg)
        
        # 1. Compute Q_cs and A for this theta_B
        Q_cs = calculate_qcs_from_field(E_c_kv_cm=E_c_fixed, L_cs_m=Lcs_m, theta_B_rad=theta_B_rad)
        A = calculate_A_from_charge(Q_cs, B, C_m, L_cs_m=Lcs_m, theta_B_rad=theta_B_rad)

        # 2. Compute fields
        E_sp = calculate_e_sp(z_points, R=R_m, L_cs=Lcs_m, theta_B=theta_B_rad, A=A, B=B, C=C_m)
        E_I = calculate_e_rod_image(z_points, R=R_m, L_cs=Lcs_m, theta_B=theta_B_rad, A=A, B=B, C=C_m)
        E_total_kv_cm = (E_sp + E_I) * 1e-5

        # Plot curve
        plt.plot(z_WH * 100, E_total_kv_cm, linewidth=2, label=f'$\\theta_B$ = {deg}°')

    plt.axhline(0, color='gray', linestyle=':', linewidth=0.8)
    plt.xlabel('Z (cm) [Distance from tip apex]')
    plt.ylabel('E_total (kV/cm)')
    plt.title(f'Sensitivity Analysis: Varying $\\theta_B$ ($E_c$ = {E_c_fixed} kV/cm)')
    plt.grid(True, which='both', linestyle='--', alpha=0.5)
    plt.legend(fontsize=11)
    plt.xlim(0, 3.5)
    plt.tight_layout()


def run_ec_sensitivity(R_m, Lcs_m, B, C_m, z_WH, z_points):
    """
    Performs sensitivity analysis by varying the average field E_c 
    while keeping theta_B constant at 60 degrees.
    """
    ec_values       = np.arange(4.0, 5.2, 0.2)  # 4.0, 4.2, 4.4, 4.6, 4.8, 5.0
    theta_B_fixed   = np.radians(60)

    plt.figure(figsize=(9, 6))

    for ec in ec_values:
        # 1. Compute Q_cs and A for this E_c
        Q_cs = calculate_qcs_from_field(E_c_kv_cm=ec, L_cs_m=Lcs_m, theta_B_rad=theta_B_fixed)
        A = calculate_A_from_charge(Q_cs, B, C_m, L_cs_m=Lcs_m, theta_B_rad=theta_B_fixed)

        # 2. Compute fields
        E_sp = calculate_e_sp(z_points, R=R_m, L_cs=Lcs_m, theta_B=theta_B_fixed, A=A, B=B, C=C_m)
        E_I = calculate_e_rod_image(z_points, R=R_m, L_cs=Lcs_m, theta_B=theta_B_fixed, A=A, B=B, C=C_m)
        E_total_kv_cm = (E_sp + E_I) * 1e-5

        # Plot curve
        plt.plot(z_WH * 100, E_total_kv_cm, linewidth=1.5, label=f'$E_c$ = {ec:.1f} kV/cm')

    plt.axhline(0, color='gray', linestyle=':', linewidth=0.8)
    plt.xlabel('Z (cm) [Distance from tip apex]')
    plt.ylabel('E_total (kV/cm)')
    plt.title(f'Sensitivity Analysis: Varying $E_c$ ($\\theta_B$ = 60°)')
    plt.grid(True, which='both', linestyle='--', alpha=0.5)
    plt.legend(fontsize=10, loc='lower right')
    plt.xlim(0, 3.5)
    plt.tight_layout()


if __name__ == "__main__":
    R_m         = 0.001             # Rod tip radius (0.1 cm = 1 mm = 0.001m)
    Lcs_m       = 0.027             # Streamer length (2.7 cm)
    B           = 1.5               # Exponent
    C_m         = 0.00035           # 0.035 cm = 0.00035m

    # Observation grid setup
    z_WH        = np.linspace(0.0, 0.035, 100)  # Distance from tip surface in meters
    z_points    = z_WH + R_m                    # Distance from sphere center O

    print("Running Sensitivity Analysis for Theta_B...")
    run_theta_b_sensitivity(R_m, Lcs_m, B, C_m, z_WH, z_points)

    print("Running Sensitivity Analysis for E_c...")
    run_ec_sensitivity(R_m, Lcs_m, B, C_m, z_WH, z_points)

    # Show both figures simultaneously
    plt.show()
