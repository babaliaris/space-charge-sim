"""
Wang & Haiting - Figure 3 reproduction (data only, for Excel)
=============================================================

What this script does
---------------------
1. Takes the benchmark rod-plane gap of the Wang & Haiting paper (inputs below).
2. Finds the cone boundary angle theta_B of the streamer space charge such that
   the total field at the streamer tip (z = L_cs) equals the streamer field E_c.
3. With that theta_B, computes every axial field component from the rod tip
   apex (z = 0) up to Z_MAX:
       E_ex        applied (Laplacian) field of the rod-plane gap
       E_sp        field of the space charge itself
       E_I,rod     field of the space charge's image in the rod
       E_I,plane   field of the space charge's image in the grounded plane
       E_total     sum of all four
4. Saves everything to an Excel workbook:
       sheet "Fields"      one row per z point, one column per field  -> plot these
       sheet "Parameters"  every input plus the solved values, so you always
                           know which settings produced the data

Units
-----
Inputs and outputs use high-voltage engineering units (cm, kV, kV/cm, degrees).
The solver works in SI units (m, V, V/m, rad); the conversion happens only in
step 2 (in) and step 5 (out) below.

z is always measured from the rod tip apex, as in the paper.

How to run
----------
    python wh_fig3_reproduction.py

It takes roughly 15-30 seconds (each point is a 2-D numerical integral).
"""

import warnings
from datetime import datetime

import numpy as np
from scipy.integrate import IntegrationWarning

from excel_export import save_to_excel
from solver.applied_field import calculate_applied_field
from solver.fields import calculate_e_sp, calculate_e_rod_image, calculate_e_plane_image
from solver.theta_b import solve_theta_b, density_amplitude, total_field_at_streamer_tip
from solver.utilities import calculate_qcs_from_field


# =============================================================================
# 1. INPUTS  (engineering units - edit these)
# =============================================================================

# --- Gap geometry and voltage (Wang & Haiting benchmark) ---------------------
ROD_TIP_RADIUS_cm        = 0.1     # R     : radius of the hemispherical rod tip
GAP_LENGTH_cm            = 80.0    # D     : distance rod tip apex -> grounded plane
APPLIED_VOLTAGE_kV       = 27.5    # V     : rod voltage

# --- Streamer space charge -------------------------------------------------
STREAMER_LENGTH_cm       = 2.7     # L_cs  : length of the space-charge cone
STREAMER_FIELD_kV_per_cm = 5.0     # E_c   : average field in the streamer region
DENSITY_EXPONENT_B       = 1.5     # B     : charge density rho(r) = A / (r + C)^B
DENSITY_OFFSET_C_cm      = 0.035   # C     : (r is the distance from the apex)

# --- Where to compute the fields (z from the tip apex) ---------------------
Z_MAX_cm                 = 3.5     # last z point
NUMBER_OF_POINTS         = 300     # points after z = 0 (z = 0 is always added)
FIRST_POINT_cm           = 0.001   # first point after z = 0; points are spaced
                                   # geometrically from here, so they are dense
                                   # near the tip where the fields change fast

# --- Search range for theta_B (the answer must lie inside it) --------------
THETA_B_MIN_deg          = 5.0
THETA_B_MAX_deg          = 175.0

# --- Output file ------------------------------------------------------------
OUTPUT_FILE              = "output/wh_fig3_reproduction.xlsx"


# Unit conversion factors
CM_TO_M        = 1e-2      # 1 cm      = 0.01 m
KV_TO_V        = 1e3       # 1 kV      = 1000 V
KV_PER_CM_TO_V_PER_M = 1e5 # 1 kV/cm   = 100 000 V/m


def main():
    # Very close to the apex the observation point touches the start of the charge
    # cone, so scipy cannot always reach its (very strict) 1e-8 tolerance and warns.
    # The values there are still smooth and correct, so these warnings are hidden.
    warnings.simplefilter("ignore", IntegrationWarning)

    # =========================================================================
    # 2. Convert the inputs to SI units for the solver
    # =========================================================================
    R   = ROD_TIP_RADIUS_cm   * CM_TO_M
    D   = GAP_LENGTH_cm       * CM_TO_M
    V   = APPLIED_VOLTAGE_kV  * KV_TO_V
    L_cs = STREAMER_LENGTH_cm * CM_TO_M
    E_c = STREAMER_FIELD_kV_per_cm * KV_PER_CM_TO_V_PER_M
    B   = DENSITY_EXPONENT_B
    C   = DENSITY_OFFSET_C_cm * CM_TO_M

    z_cm = np.concatenate(([0.0], np.geomspace(FIRST_POINT_cm, Z_MAX_cm, NUMBER_OF_POINTS)))
    z = z_cm * CM_TO_M

    # =========================================================================
    # 3. Solve for the cone boundary angle theta_B
    #    (total field at the streamer tip z = L_cs must equal E_c)
    # =========================================================================
    print("Step 1/3: solving for theta_B ...")
    theta_B = solve_theta_b(R, D, V, L_cs, E_c, B, C,
                            theta_min=np.radians(THETA_B_MIN_deg),
                            theta_max=np.radians(THETA_B_MAX_deg))
    print(f"          theta_B = {np.degrees(theta_B):.3f} deg")

    # Space-charge model that belongs to this theta_B
    Q_cs = calculate_qcs_from_field(E_c, L_cs_m=L_cs, theta_B_rad=theta_B)
    A = density_amplitude(E_c, L_cs, theta_B, B, C)
    E_tip_check = total_field_at_streamer_tip(theta_B, R, D, V, L_cs, E_c, B, C)

    # =========================================================================
    # 4. Compute every field component on the z points  (results in V/m)
    # =========================================================================
    print(f"Step 2/3: computing the fields at {len(z)} points ...")
    E_ex       = calculate_applied_field(R, D, V, z)
    E_sp       = calculate_e_sp(z, R, L_cs, theta_B, A, B, C)
    E_I_rod    = calculate_e_rod_image(z, R, L_cs, theta_B, A, B, C)
    E_I_plane  = calculate_e_plane_image(z, D, R, L_cs, theta_B, A, B, C)
    E_space_charge = E_sp + E_I_rod + E_I_plane
    E_total    = E_ex + E_space_charge

    # =========================================================================
    # 5. Convert back to engineering units and save to Excel
    # =========================================================================
    print("Step 3/3: saving to Excel ...")

    def to_kV_per_cm(field_V_per_m):
        return field_V_per_m / KV_PER_CM_TO_V_PER_M

    fields_sheet = {
        "z from tip apex [cm]":                  z_cm,
        "E_ex applied [kV/cm]":                  to_kV_per_cm(E_ex),
        "E_sp space charge [kV/cm]":             to_kV_per_cm(E_sp),
        "E_I,rod rod image [kV/cm]":             to_kV_per_cm(E_I_rod),
        "E_I,plane plane image [kV/cm]":         to_kV_per_cm(E_I_plane),
        "E_sp + E_I,rod + E_I,plane [kV/cm]":    to_kV_per_cm(E_space_charge),
        "E_total [kV/cm]":                       to_kV_per_cm(E_total),
    }

    parameters = [
        # (name, value, unit)
        ("INPUTS",                                  "",                               ""),
        ("Rod tip radius R",                        ROD_TIP_RADIUS_cm,                "cm"),
        ("Gap length D (tip apex to plane)",        GAP_LENGTH_cm,                    "cm"),
        ("Applied voltage V",                       APPLIED_VOLTAGE_kV,               "kV"),
        ("Streamer length L_cs",                    STREAMER_LENGTH_cm,               "cm"),
        ("Streamer field E_c",                      STREAMER_FIELD_kV_per_cm,         "kV/cm"),
        ("Density exponent B",                      DENSITY_EXPONENT_B,               "-"),
        ("Density offset C",                        DENSITY_OFFSET_C_cm,              "cm"),
        ("z range (from tip apex)",                 f"0 to {Z_MAX_cm:g}",             "cm"),
        ("Number of z points",                      len(z_cm),                        "-"),
        ("RESULTS",                                 "",                               ""),
        ("Solved theta_B",                          np.degrees(theta_B),              "deg"),
        ("Total streamer charge Q_cs",              Q_cs * 1e9,                       "nC"),
        ("Density amplitude A (SI)",                A,                                "C*m^(B-3)"),
        ("Check: E_total at z = L_cs (should = E_c)", to_kV_per_cm(E_tip_check),      "kV/cm"),
        ("Generated on",                            datetime.now().strftime("%Y-%m-%d %H:%M"), ""),
    ]
    parameters_sheet = {
        "Parameter": [name for name, _, _ in parameters],
        "Value":     [value for _, value, _ in parameters],
        "Unit":      [unit for _, _, unit in parameters],
    }

    save_to_excel(OUTPUT_FILE, {"Fields": fields_sheet, "Parameters": parameters_sheet})
    print(f"Done. Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
