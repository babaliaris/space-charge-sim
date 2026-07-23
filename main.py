import matplotlib
# Try TkAgg or Qt5Agg depending on what's installed on your system
matplotlib.use('TkAgg')

import numpy as np
import matplotlib.pyplot as plt
from solver.fields import calculate_e_sp, calculate_e_rod_image
from solver.constants import calculate_qcs_from_field, calculate_A_from_charge

import csv

def export_fields_to_csv(filepath, z_wh_cm, e_sp_kv_cm, e_i_kv_cm):
    """
    Exports computed axial field distribution data to a clean CSV file.
    """
    total_space_field = e_sp_kv_cm + e_i_kv_cm

    with open(filepath, mode='w', newline='') as file:
        writer = csv.writer(file)

        # Write Header
        writer.writerow(["z_cm", "E_sp_kV_cm", "E_I_rod_kV_cm", "E_total_space_kV_cm"])

        # Write Rows
        for z_v, esp, ei, etot in zip(z_wh_cm, e_sp_kv_cm, e_i_kv_cm, total_space_field):
            writer.writerow([f"{z_v:.4f}", f"{esp:.6f}", f"{ei:.6f}", f"{etot:.6f}"])

    print(f"Data successfully saved to {filepath}")

def reproduce_figure_3(
        R_m: float,
        Lcs_m: float,
        theta_B_rad: float,
        A_m: float,
        B: float,
        C_m: float):

    # --- Observation Points along Z axis ---
    # z measured from Sphere Center O (so tip surface is at z = R = 0.001 m)
    # Fig 3 plots Z up to ~3.5 cm from tip
    z_WH        = np.linspace(0.0, 0.035, 100)   # Distance from tip surface in meters
    z_points    = z_WH + R_m                        # Distance from sphere center O

    print("Computing E_sp (Direct Space Charge Field)...")
    E_sp = calculate_e_sp(z_points, R=R_m, L_cs=Lcs_m, theta_B=theta_B_rad, A=A_m, B=B, C=C_m)

    print("Computing E_I (Rod Image Field)...")
    E_I = calculate_e_rod_image(z_points, R=R_m, L_cs=Lcs_m, theta_B=theta_B_rad, A=A_m, B=B, C=C_m)

    E_total_space = E_sp + E_I


    # --- Convert results to kV/cm for direct comparison with Fig 3 ---
    # 1 V/m = 1e-5 kV/cm
    E_sp_kv_cm      = E_sp * 1e-5
    E_I_kv_cm       = E_I * 1e-5
    z_wh_cm         = z_WH * 100.0 # Distance from tip apex in centimeters for export/Plotting
    E_total_kv_cm   = E_total_space * 1e-5

    # Export to CSV
    export_fields_to_csv("figure_3_fields.csv", z_wh_cm, E_sp_kv_cm, E_I_kv_cm)

    # --- Plotting to match Figure 3 ---
    plt.figure(figsize=(8, 6))

    # Plot curves matching Figure 3 legends
    plt.plot(z_WH * 100, E_sp_kv_cm, 'b-', label=r'1: $E_{SP} \sim Z$', linewidth=2)
    plt.plot(z_WH * 100, E_I_kv_cm, 'r--', label=r'2: $E_{I} \sim Z$', linewidth=2)
    plt.plot(z_WH * 100, E_total_kv_cm, 'k-.', label=r'3: $E_{SP} + E_{I} \sim Z$', linewidth=2)

    plt.axhline(0, color='gray', linestyle=':', linewidth=0.8)
    plt.xlabel('Z (cm) [Distance from tip apex]')
    plt.ylabel('E (kV/cm)')
    plt.title('Replication of Wang-Haiting Fig 3: Space Charge Electric Field')
    plt.grid(True, which='both', linestyle='--', alpha=0.5)
    plt.legend(fontsize=11)
    plt.ylim(-55, 10)
    plt.xlim(0, 3.5)

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    R_m         = 0.001             # Rod tip radius (0.1 cm = 1 mm)
    Lcs_m       = 0.027             # Streamer length (2.7 cm)
    theta_B_rad = np.radians(75)    # Boundary angle (60 degrees)
    B           = 1.5               # Exponent
    C_m         = 0.00035           # 0.035 cm = 0.00035 m
    E_c_kv_cm   = 5                 # Average field in streamer region = 5 kV/cm

    # Calculate Q_cs from E_c
    Q_cs = calculate_qcs_from_field(E_c_kv_cm, L_cs_m=Lcs_m, theta_B_rad=theta_B_rad)
    print(f"Calculated Q_cs: {Q_cs * 1e9:.3f} nC ({Q_cs:.4e} C)")

    # Calculate A from Q_cs and geometry
    A = calculate_A_from_charge(
        Q_cs,
        B,
        C_m,
        L_cs_m=Lcs_m,
        theta_B_rad=theta_B_rad
    )
    print(f"Calculated A: {A:.6e} SI units")
    reproduce_figure_3(R_m, Lcs_m, theta_B_rad, A, B, C_m)
