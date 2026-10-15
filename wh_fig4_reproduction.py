"""
Wang & Haiting - Figure 4 reproduction: drift of the space charge (data for Excel)
==================================================================================

What this script does
---------------------
Figure 4 of the paper shows E_sp near the rod tip before and after the space
charge has drifted towards the plane during the dark period.

1. Builds the same space-charge cloud as Figure 3 (inputs below): solves the
   cone angle theta_B so that the total field at the streamer tip equals E_c.
2. Drifts the cloud as a RIGID BODY towards the plane (no new ionization, so its
   charge and shape stay the same), using the paper's Eq. (6):
       d z_drift / dt = b * [E_ex + E_I,rod + E_I,plane] at z_c
   where z_c is the point where the cloud's own field E_sp is zero.
   You choose EITHER how far it drifts (DRIFT_DISTANCE_cm) OR for how long
   (DRIFT_TIME_us); the script reports the other one.
3. Computes every field BEFORE and AFTER the drift from the rod tip apex (z = 0)
   up to Z_MAX:
       E_sp        moves with the cloud (an exact shift by z_drift)
       E_I,rod     image in the rod: the rod does NOT move, so this curve changes shape
       E_I,plane   image in the plane: it moves towards the cloud, so it also changes
       E_ex        applied field: does not depend on the space charge at all
4. Saves everything to an Excel workbook:
       sheet "Fields"      one row per z point, before/after columns  -> plot these
       sheet "Drift"       time history of the drift (position, field, speed)
       sheet "Parameters"  every input plus the solved values

Units
-----
Inputs and outputs use high-voltage engineering units (cm, kV, kV/cm, us,
degrees). The solver works in SI units; the conversion happens only in step 2
(in) and step 6 (out) below. z is always measured from the rod tip apex.

How to run
----------
    python wh_fig4_reproduction.py

It takes roughly 30-60 seconds (each point is a 2-D numerical integral).
"""

import warnings
from datetime import datetime

import numpy as np
from scipy.integrate import IntegrationWarning

from excel_export import save_to_excel
from solver.applied_field import calculate_applied_field
from solver.drift import simulate_drift
from solver.fields import calculate_e_sp, calculate_e_rod_image, calculate_e_plane_image
from solver.theta_b import solve_theta_b, density_amplitude
from solver.utilities import calculate_qcs_from_field


# =============================================================================
# 1. INPUTS  (engineering units - edit these)
# =============================================================================

# --- Gap geometry and voltage (Wang & Haiting benchmark, same as Figure 3) ---
ROD_TIP_RADIUS_cm        = 0.1     # R     : radius of the hemispherical rod tip
GAP_LENGTH_cm            = 80.0    # D     : distance rod tip apex -> grounded plane
APPLIED_VOLTAGE_kV       = 27.5    # V     : rod voltage

# --- Streamer space charge (same as Figure 3) -------------------------------
STREAMER_LENGTH_cm       = 2.7     # L_cs  : length of the space-charge cone
STREAMER_FIELD_kV_per_cm = 5.0     # E_c   : average field in the streamer region
DENSITY_EXPONENT_B       = 1.5     # B     : charge density rho(r) = A / (r + C)^B
DENSITY_OFFSET_C_cm      = 0.035   # C     : (r is the distance from the cone apex)

# --- Drift during the dark period --------------------------------------------
# Set ONE of these two and leave the other as None.
DRIFT_DISTANCE_cm        = 0.07    # how far the cloud drifts (about 0.07 cm read from Fig. 4)
DRIFT_TIME_us            = None    # or: how long the cloud drifts
ION_MOBILITY_cm2_per_kV_us = 1.36e-3   # b : positive ion mobility (value given in the paper)

# --- Where to compute the fields (z from the tip apex) ----------------------
Z_MAX_cm                 = 1.0     # Figure 4 shows 0 to 0.8 cm
NUMBER_OF_POINTS         = 300     # points after z = 0 (z = 0 and z = z_drift are always added)
FIRST_POINT_cm           = 0.001   # geometric spacing from here: dense near the tip

# --- Search range for theta_B (the answer must lie inside it) ----------------
THETA_B_MIN_deg          = 5.0
THETA_B_MAX_deg          = 175.0

# --- Output file -------------------------------------------------------------
OUTPUT_FILE              = "output/wh_fig4_reproduction.xlsx"


# Unit conversion factors
CM_TO_M              = 1e-2       # 1 cm      = 0.01 m
KV_TO_V              = 1e3        # 1 kV      = 1000 V
KV_PER_CM_TO_V_PER_M = 1e5        # 1 kV/cm   = 100 000 V/m
US_TO_S              = 1e-6       # 1 us      = 1e-6 s
MOBILITY_TO_SI       = 1e-1       # 1 cm^2/(kV*us) = 1e-4 m^2 / (1e3 V * 1e-6 s) = 0.1 m^2/(V*s)
M_PER_S_TO_CM_PER_US = 1e-4       # 1 m/s     = 1e-4 cm/us


def main():
    # Very close to the cone apex the observation point touches the start of the
    # charge, so scipy cannot always reach its (very strict) 1e-8 tolerance and
    # warns. The values there are still smooth and correct, so these warnings are hidden.
    warnings.simplefilter("ignore", IntegrationWarning)

    if (DRIFT_DISTANCE_cm is None) == (DRIFT_TIME_us is None):
        raise SystemExit("Set exactly one of DRIFT_DISTANCE_cm or DRIFT_TIME_us (the other must be None).")

    # =========================================================================
    # 2. Convert the inputs to SI units for the solver
    # =========================================================================
    R    = ROD_TIP_RADIUS_cm   * CM_TO_M
    D    = GAP_LENGTH_cm       * CM_TO_M
    V    = APPLIED_VOLTAGE_kV  * KV_TO_V
    L_cs = STREAMER_LENGTH_cm  * CM_TO_M
    E_c  = STREAMER_FIELD_kV_per_cm * KV_PER_CM_TO_V_PER_M
    B    = DENSITY_EXPONENT_B
    C    = DENSITY_OFFSET_C_cm * CM_TO_M
    mobility = ION_MOBILITY_cm2_per_kV_us * MOBILITY_TO_SI
    drift_distance = None if DRIFT_DISTANCE_cm is None else DRIFT_DISTANCE_cm * CM_TO_M
    drift_time     = None if DRIFT_TIME_us is None else DRIFT_TIME_us * US_TO_S

    # =========================================================================
    # 3. Build the space-charge cloud of Figure 3 (solve theta_B)
    # =========================================================================
    print("Step 1/4: solving for theta_B (cloud of Figure 3) ...")
    theta_B = solve_theta_b(R, D, V, L_cs, E_c, B, C,
                            theta_min=np.radians(THETA_B_MIN_deg),
                            theta_max=np.radians(THETA_B_MAX_deg))
    Q_cs = calculate_qcs_from_field(E_c, L_cs_m=L_cs, theta_B_rad=theta_B)
    A = density_amplitude(E_c, L_cs, theta_B, B, C)
    print(f"          theta_B = {np.degrees(theta_B):.3f} deg, Q_cs = {Q_cs * 1e9:.2f} nC")

    # =========================================================================
    # 4. Drift the cloud as a rigid body (paper's Eq. 6)
    # =========================================================================
    print("Step 2/4: drifting the space charge ...")
    drift = simulate_drift(R, D, V, L_cs, theta_B, A, B, C, mobility,
                           drift_time=drift_time, drift_distance=drift_distance)
    z_drift = drift["distance"]
    print(f"          drifted {z_drift / CM_TO_M:.4f} cm in {drift['time'] / US_TO_S:.2f} us "
          f"(E_sp zero point moved from {drift['z_c0'] / CM_TO_M:.4f} to "
          f"{(drift['z_c0'] + z_drift) / CM_TO_M:.4f} cm)")

    # =========================================================================
    # 5. Compute every field before and after the drift  (results in V/m)
    # =========================================================================
    z_cm = np.unique(np.concatenate((
        [0.0, z_drift / CM_TO_M],                                   # tip and new cone apex
        np.geomspace(FIRST_POINT_cm, Z_MAX_cm, NUMBER_OF_POINTS))))
    z = z_cm * CM_TO_M

    print(f"Step 3/4: computing the fields at {len(z)} points, before and after the drift ...")
    E_ex             = calculate_applied_field(R, D, V, z)
    E_sp_before      = calculate_e_sp(z, R, L_cs, theta_B, A, B, C)
    E_sp_after       = calculate_e_sp(z, R, L_cs, theta_B, A, B, C, z_drift=z_drift)
    E_I_rod_before   = calculate_e_rod_image(z, R, L_cs, theta_B, A, B, C)
    E_I_rod_after    = calculate_e_rod_image(z, R, L_cs, theta_B, A, B, C, z_drift=z_drift)
    E_I_plane_before = calculate_e_plane_image(z, D, R, L_cs, theta_B, A, B, C)
    E_I_plane_after  = calculate_e_plane_image(z, D, R, L_cs, theta_B, A, B, C, z_drift=z_drift)
    E_total_before   = E_ex + E_sp_before + E_I_rod_before + E_I_plane_before
    E_total_after    = E_ex + E_sp_after + E_I_rod_after + E_I_plane_after

    # =========================================================================
    # 6. Convert back to engineering units and save to Excel
    # =========================================================================
    print("Step 4/4: saving to Excel ...")

    def to_kV_per_cm(field_V_per_m):
        return field_V_per_m / KV_PER_CM_TO_V_PER_M

    fields_sheet = {
        "z from tip apex [cm]":              z_cm,
        "E_sp before drift [kV/cm]":         to_kV_per_cm(E_sp_before),
        "E_sp after drift [kV/cm]":          to_kV_per_cm(E_sp_after),
        "E_I,rod before drift [kV/cm]":      to_kV_per_cm(E_I_rod_before),
        "E_I,rod after drift [kV/cm]":       to_kV_per_cm(E_I_rod_after),
        "E_I,plane before drift [kV/cm]":    to_kV_per_cm(E_I_plane_before),
        "E_I,plane after drift [kV/cm]":     to_kV_per_cm(E_I_plane_after),
        "E_ex applied (unchanged) [kV/cm]":  to_kV_per_cm(E_ex),
        "E_total before drift [kV/cm]":      to_kV_per_cm(E_total_before),
        "E_total after drift [kV/cm]":       to_kV_per_cm(E_total_after),
    }

    drift_sheet = {
        "time [us]":                         drift["t"] / US_TO_S,
        "drift distance z_drift [cm]":       drift["z_drift"] / CM_TO_M,
        "E_sp zero point z_c [cm]":          drift["z_c"] / CM_TO_M,
        "driving field at z_c [kV/cm]":      to_kV_per_cm(drift["E_drive"]),
        "drift speed [cm/us]":               drift["velocity"] * M_PER_S_TO_CM_PER_US,
    }

    i_tip = 0                                        # z = 0 is the first grid point
    parameters = [
        # (name, value, unit)
        ("INPUTS",                                    "",                                   ""),
        ("Rod tip radius R",                          ROD_TIP_RADIUS_cm,                    "cm"),
        ("Gap length D (tip apex to plane)",          GAP_LENGTH_cm,                        "cm"),
        ("Applied voltage V",                         APPLIED_VOLTAGE_kV,                   "kV"),
        ("Streamer length L_cs",                      STREAMER_LENGTH_cm,                   "cm"),
        ("Streamer field E_c",                        STREAMER_FIELD_kV_per_cm,             "kV/cm"),
        ("Density exponent B",                        DENSITY_EXPONENT_B,                   "-"),
        ("Density offset C",                          DENSITY_OFFSET_C_cm,                  "cm"),
        ("Ion mobility b",                            ION_MOBILITY_cm2_per_kV_us,           "cm^2/(kV*us)"),
        ("Drift distance requested",                  DRIFT_DISTANCE_cm if DRIFT_DISTANCE_cm is not None else "-", "cm"),
        ("Drift time requested",                      DRIFT_TIME_us if DRIFT_TIME_us is not None else "-", "us"),
        ("z range (from tip apex)",                   f"0 to {Z_MAX_cm:g}",                 "cm"),
        ("Number of z points",                        len(z_cm),                            "-"),
        ("RESULTS",                                   "",                                   ""),
        ("Solved theta_B",                            np.degrees(theta_B),                  "deg"),
        ("Total streamer charge Q_cs (unchanged)",    Q_cs * 1e9,                           "nC"),
        ("Density amplitude A (SI)",                  A,                                    "C*m^(B-3)"),
        ("Drift distance z_drift",                    z_drift / CM_TO_M,                    "cm"),
        ("Drift time",                                drift["time"] / US_TO_S,              "us"),
        ("E_sp zero point before drift z_c0",         drift["z_c0"] / CM_TO_M,              "cm"),
        ("E_sp zero point after drift",               (drift["z_c0"] + z_drift) / CM_TO_M,  "cm"),
        ("E_sp at rod tip before / after",            f"{to_kV_per_cm(E_sp_before[i_tip]):.2f} / "
                                                      f"{to_kV_per_cm(E_sp_after[i_tip]):.2f}", "kV/cm"),
        ("E_total at rod tip before / after",         f"{to_kV_per_cm(E_total_before[i_tip]):.2f} / "
                                                      f"{to_kV_per_cm(E_total_after[i_tip]):.2f}", "kV/cm"),
        ("Generated on",                              datetime.now().strftime("%Y-%m-%d %H:%M"), ""),
    ]
    parameters_sheet = {
        "Parameter": [name for name, _, _ in parameters],
        "Value":     [value for _, value, _ in parameters],
        "Unit":      [unit for _, _, unit in parameters],
    }

    save_to_excel(OUTPUT_FILE, {"Fields": fields_sheet, "Drift": drift_sheet,
                                "Parameters": parameters_sheet})
    print(f"Done. Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
