"""
Wang & Haiting - Figures 6, 7 and 8 reproduction: first and second corona streamer
against the impulse front time
==================================================================================

What this script does
---------------------
Figures 6, 7 and 8 of the paper show, for the first and the second corona
streamer, how the inception voltage (Fig. 6), the streamer length (Fig. 7) and
the streamer charge (Fig. 8) change with the time to crest of a switching
impulse (15 to 600 us, gaps of 40 cm and 80 cm).

The whole framework runs in solver/simulation.py. This script:

1. Calibrates the model once on the first streamer of Figure 3 (27.5 kV,
   L_cs = 2.7 cm, D = 80 cm): the cone angle theta_B and the inception field
   E_inc at the tip apex.
2. For every gap and every front time builds the impulse V(t) (crest from the
   Gallet formula, U50 = 3400 / (1 + 8/d) kV, tail half-value 2500 us; neither
   is given in the paper).
3. Simulates the impulse front: burst 1 when the tip field reaches E_inc, its
   cloud drifts, burst 2 when the tip field reaches E_inc again. Each burst
   gets its length from the head condition (field at the head = E_c) and its
   charge from Gauss's law.
4. Saves everything to an Excel workbook:
       sheet "Fig6 inception voltage"   front time + V_inc of streamers 1 and 2 per gap
       sheet "Fig7 streamer length"     same layout with L
       sheet "Fig8 streamer charge"     same layout with Q            -> plot these
       sheet "Bursts"                   one row per burst with every detail
       sheet "Parameters"               every input plus the calibrated values

Units
-----
Inputs and outputs use high-voltage engineering units (cm, kV, kV/cm, us, nC).
The solver works in SI units; the conversion happens only in step 2 (in) and
step 5 (out). z is measured from the rod tip apex, t from the start of the impulse.

How to run
----------
    python wh_fig678_reproduction.py

It takes about 10 minutes (each burst and drift step needs 2-D numerical integrals).
"""

import time
import warnings
from datetime import datetime

import numpy as np
from scipy.integrate import IntegrationWarning

from excel_export import save_to_excel
from solver.simulation import GapModel, simulate
from solver.utilities import double_exponential_parameters, impulse_voltage


# =============================================================================
# 1. INPUTS  (engineering units - edit these)
# =============================================================================

# --- Rod and charge model (same as Figures 3 to 5) ----------------------------
ROD_TIP_RADIUS_cm          = 0.1      # R : radius of the hemispherical rod tip
STREAMER_FIELD_kV_per_cm   = 5.0      # E_c : field at the streamer head
DENSITY_EXPONENT_B         = 1.5      # B : rho(r) = A / (r + C)^B
DENSITY_OFFSET_C_cm        = 0.035    # C
ION_MOBILITY_cm2_per_kV_us = 1.36e-3  # mu+ : positive ion mobility (given in the paper)

# --- Calibration: the first streamer of Figure 3 (given in the paper) ---------
CALIBRATION_VOLTAGE_kV     = 27.5     # first-streamer inception voltage
CALIBRATION_LENGTH_cm      = 2.7      # its length L_cs
CALIBRATION_GAP_cm         = 80.0     # in this gap

# --- Gaps and impulses of Figures 6 to 8 ----------------------------------------
GAPS_cm                    = [40.0, 80.0]   # Fig. 6 and 7: 40 cm; Fig. 8: 40 and 80 cm
FRONT_TIMES_us             = [15, 20, 30, 50, 75, 100, 150, 200, 300, 400, 500, 600]
TIME_TO_HALF_VALUE_us      = 2500.0   # tail: not given in the paper (IEC 250/2500 us)
BURSTS_PER_IMPULSE         = 2        # the paper shows the first and the second streamer

# --- Output file --------------------------------------------------------------
OUTPUT_FILE                = "output/wh_fig678_reproduction.xlsx"


# Unit conversion factors
CM_TO_M              = 1e-2       # 1 cm      = 0.01 m
KV_TO_V              = 1e3        # 1 kV      = 1000 V
KV_PER_CM_TO_V_PER_M = 1e5        # 1 kV/cm   = 100 000 V/m
US_TO_S              = 1e-6       # 1 us      = 1e-6 s
MOBILITY_TO_SI       = 1e-1       # 1 cm^2/(kV*us) = 0.1 m^2/(V*s)
C_TO_NC              = 1e9        # 1 C       = 1e9 nC


def gallet_crest_kV(gap_cm):
    """Gallet formula: 50 % breakdown voltage of a rod-plane gap, U50 = 3400 / (1 + 8/d) kV, d in m."""
    return 3400.0 / (1.0 + 8.0 / (gap_cm / 100.0))


def main():
    # Very close to the cone apex scipy cannot always reach its strict tolerance and
    # warns; the values there are smooth and correct, so these warnings are hidden.
    warnings.simplefilter("ignore", IntegrationWarning)

    # =========================================================================
    # 2. Convert the inputs to SI units for the solver
    # =========================================================================
    R        = ROD_TIP_RADIUS_cm * CM_TO_M
    E_c      = STREAMER_FIELD_kV_per_cm * KV_PER_CM_TO_V_PER_M
    B        = DENSITY_EXPONENT_B
    C        = DENSITY_OFFSET_C_cm * CM_TO_M
    mobility = ION_MOBILITY_cm2_per_kV_us * MOBILITY_TO_SI
    V_ref    = CALIBRATION_VOLTAGE_kV * KV_TO_V
    L_ref    = CALIBRATION_LENGTH_cm * CM_TO_M
    D_ref    = CALIBRATION_GAP_cm * CM_TO_M
    t_half   = TIME_TO_HALF_VALUE_us * US_TO_S

    # =========================================================================
    # 3. Calibrate theta_B and E_inc on the first streamer of Figure 3
    # =========================================================================
    print("Step 1/3: calibrating on the first streamer of Figure 3 ...")
    calibration = GapModel.calibrated(R, D_ref, E_c, B, C, mobility, V_ref, L_ref, D_ref)
    theta_B, E_inc = calibration.theta_B, calibration.E_inc
    print(f"          theta_B = {np.degrees(theta_B):.3f} deg, "
          f"E_inc = {E_inc / KV_PER_CM_TO_V_PER_M:.2f} kV/cm")

    # =========================================================================
    # 4. Simulate every gap and front time
    # =========================================================================
    print("Step 2/3: simulating the impulse fronts ...")
    bursts = []        # one dict per burst
    for gap_cm in GAPS_cm:
        model = GapModel(R, gap_cm * CM_TO_M, theta_B, E_c, E_inc, B, C, mobility)
        V_crest = gallet_crest_kV(gap_cm) * KV_TO_V
        for front_us in FRONT_TIMES_us:
            t_crest = front_us * US_TO_S
            alpha, beta, k = double_exponential_parameters(t_crest, t_half)

            def V(t, V_crest=V_crest, alpha=alpha, beta=beta, k=k):
                return impulse_voltage(t, V_crest, alpha, beta, k)

            started = time.time()
            result = simulate(model, V, t_end=t_crest, max_bursts=BURSTS_PER_IMPULSE)
            for cloud in result.clouds:
                first = result.clouds[0]
                bursts.append({
                    "gap_cm": gap_cm, "front_us": front_us, "crest_kV": V_crest / KV_TO_V,
                    "number": cloud.number, "t_us": cloud.t_birth / US_TO_S,
                    "V_kV": cloud.V_birth / KV_TO_V, "L_cm": cloud.L / CM_TO_M,
                    "Q_nC": cloud.Q * C_TO_NC,
                    "drift1_cm": result.z_drift(first, cloud.t_birth) / CM_TO_M,
                })
            summary = ", ".join(f"V{c.number} = {c.V_birth / KV_TO_V:.1f} kV, L{c.number} = {c.L / CM_TO_M:.2f} cm"
                                for c in result.clouds)
            print(f"          D = {gap_cm:4.0f} cm, front {front_us:3d} us: {summary or 'no burst'}"
                  f"  ({time.time() - started:.0f} s)")

    # =========================================================================
    # 5. Convert back to engineering units and save to Excel
    # =========================================================================
    print("Step 3/3: saving to Excel ...")

    def figure_sheet(key, label, unit):
        """Front time column + one column per gap and streamer."""
        sheet = {"time to crest [us]": FRONT_TIMES_us}
        for gap_cm in GAPS_cm:
            for number in range(1, BURSTS_PER_IMPULSE + 1):
                column = []
                for front_us in FRONT_TIMES_us:
                    match = [b[key] for b in bursts
                             if b["gap_cm"] == gap_cm and b["front_us"] == front_us and b["number"] == number]
                    column.append(match[0] if match else None)
                sheet[f"{label} streamer {number}, D = {gap_cm:g} cm [{unit}]"] = column
        return sheet

    bursts_sheet = {
        "gap D [cm]":                         [b["gap_cm"] for b in bursts],
        "time to crest [us]":                 [b["front_us"] for b in bursts],
        "impulse crest (Gallet) [kV]":        [b["crest_kV"] for b in bursts],
        "burst number k":                     [b["number"] for b in bursts],
        "burst instant t_k [us]":             [b["t_us"] for b in bursts],
        "inception voltage V(t_k) [kV]":      [b["V_kV"] for b in bursts],
        "streamer length L_k [cm]":           [b["L_cm"] for b in bursts],
        "streamer charge Q_k [nC]":           [b["Q_nC"] for b in bursts],
        "drift of cloud 1 at t_k [cm]":       [b["drift1_cm"] for b in bursts],
    }

    parameters = [
        # (name, value, unit)
        ("INPUTS",                                  "",                                     ""),
        ("Rod tip radius R",                        ROD_TIP_RADIUS_cm,                      "cm"),
        ("Streamer field E_c",                      STREAMER_FIELD_kV_per_cm,               "kV/cm"),
        ("Density exponent B",                      DENSITY_EXPONENT_B,                     "-"),
        ("Density offset C",                        DENSITY_OFFSET_C_cm,                    "cm"),
        ("Ion mobility mu+",                        ION_MOBILITY_cm2_per_kV_us,             "cm^2/(kV*us)"),
        ("Calibration voltage (Fig. 3)",            CALIBRATION_VOLTAGE_kV,                 "kV"),
        ("Calibration length (Fig. 3)",             CALIBRATION_LENGTH_cm,                  "cm"),
        ("Calibration gap (Fig. 3)",                CALIBRATION_GAP_cm,                     "cm"),
        ("Gaps",                                    ", ".join(f"{g:g}" for g in GAPS_cm),   "cm"),
        ("Times to crest",                          ", ".join(str(f) for f in FRONT_TIMES_us), "us"),
        ("Time to half value (assumed)",            TIME_TO_HALF_VALUE_us,                  "us"),
        ("Crest voltage rule",                      "Gallet U50 = 3400/(1+8/d), d in m",    "kV"),
    ] + [
        (f"Crest voltage for D = {g:g} cm",         gallet_crest_kV(g),                     "kV") for g in GAPS_cm
    ] + [
        ("RESULTS",                                 "",                                     ""),
        ("Calibrated theta_B",                      np.degrees(theta_B),                    "deg"),
        ("Calibrated inception field E_inc",        E_inc / KV_PER_CM_TO_V_PER_M,           "kV/cm"),
        ("Generated on",                            datetime.now().strftime("%Y-%m-%d %H:%M"), ""),
    ]
    parameters_sheet = {
        "Parameter": [name for name, _, _ in parameters],
        "Value":     [value for _, value, _ in parameters],
        "Unit":      [unit for _, _, unit in parameters],
    }

    save_to_excel(OUTPUT_FILE, {"Fig6 inception voltage": figure_sheet("V_kV", "V_inc", "kV"),
                                "Fig7 streamer length":   figure_sheet("L_cm", "L", "cm"),
                                "Fig8 streamer charge":   figure_sheet("Q_nC", "Q", "nC"),
                                "Bursts":                 bursts_sheet,
                                "Parameters":             parameters_sheet})
    print(f"Done. Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
