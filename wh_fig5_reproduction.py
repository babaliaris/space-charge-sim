"""
Wang & Haiting - Figure 5 reproduction: field near the rod tip during an impulse
================================================================================

What this script does
---------------------
Figure 5 of the paper shows the axial field near the rod tip at several instants
of a switching impulse:
    (a) the applied (Laplacian) field only,
    (b) the field with the space charge of the first corona streamer present.

1. Builds the impulse V(t) as a double exponential from its high-voltage
   description (crest, time to crest, tail half-value time).
2. Finds the inception instant t_inc, where V(t) reaches the first-streamer
   inception voltage. At that instant the space-charge cloud of Figure 3 is
   created (theta_B solved so the field at the streamer tip equals E_c).
3. From t_inc on, there is no new ionization (dark period): the cloud keeps its
   charge and shape and drifts towards the plane (paper's Eq. 6), driven by the
   RISING applied field.
4. At every requested time step computes, from the rod tip apex (z = 0) up to Z_MAX:
       Fig. 5(a):  E_ex(z, t) = applied field for the voltage V(t)
       Fig. 5(b):  E_ex + E_sp + E_I,rod + E_I,plane   (only E_ex before t_inc)
5. Finds when a SECOND streamer would start: the instant the total field at the
   tip is back to the value it had when the first streamer incepted. This is only
   reported; the second streamer itself is not modelled.
6. Saves everything to an Excel workbook:
       sheet "Fig5a applied"            one z column + one column per time step
       sheet "Fig5b with space charge"  same layout                  -> plot these
       sheet "Time steps"               t, V, drift, field at the tip for every step
       sheet "Parameters"               every input plus the solved values

Units
-----
Inputs and outputs use high-voltage engineering units (cm, kV, kV/cm, us).
The solver works in SI units; the conversion happens only in step 2 (in) and
step 8 (out) below. z is always measured from the rod tip apex. Time t is
measured from the start of the impulse.

How to run
----------
    python wh_fig5_reproduction.py

It takes roughly 1-2 minutes (each point is a 2-D numerical integral).
"""

import warnings
from datetime import datetime

import numpy as np
from scipy.integrate import IntegrationWarning
from scipy.optimize import brentq

from excel_export import save_to_excel
from solver.applied_field import calculate_applied_field
from solver.drift import simulate_drift
from solver.fields import calculate_e_sp, calculate_e_rod_image, calculate_e_plane_image
from solver.theta_b import solve_theta_b, density_amplitude
from solver.utilities import calculate_qcs_from_field, double_exponential_parameters, impulse_voltage


# =============================================================================
# 1. INPUTS  (engineering units - edit these)
# =============================================================================

# --- Gap geometry (Wang & Haiting, same conditions as Figures 3 and 4) -------
ROD_TIP_RADIUS_cm        = 0.1     # R     : radius of the hemispherical rod tip
GAP_LENGTH_cm            = 80.0    # D     : distance rod tip apex -> grounded plane

# --- Switching impulse --------------------------------------------------------
IMPULSE_CREST_kV         = 320.0   # crest value (given in the paper)
TIME_TO_CREST_us         = 100.0   # "time of wavefront" (given in the paper)
TIME_TO_HALF_VALUE_us    = 2500.0  # tail half-value time: NOT given in the paper;
                                   # typical switching-impulse tail (IEC 250/2500 us)

# --- First corona streamer (given in the paper) -------------------------------
INCEPTION_VOLTAGE_kV     = 27.5    # voltage at which the first streamer incepts
STREAMER_LENGTH_cm       = 2.7     # L_cs  : length of the space-charge cone
STREAMER_FIELD_kV_per_cm = 5.0     # E_c   : average field in the streamer region
DENSITY_EXPONENT_B       = 1.5     # B     : charge density rho(r) = A / (r + C)^B
DENSITY_OFFSET_C_cm      = 0.035   # C
ION_MOBILITY_cm2_per_kV_us = 1.36e-3   # b : positive ion mobility (given in the paper)

# --- Time steps (from the start of the impulse) -------------------------------
TIME_STEPS_us            = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]   # Figure 5 shows 1-4 us
                                   # (the inception instant is always added)

# --- Where to compute the fields (z from the tip apex) ------------------------
Z_MAX_cm                 = 4.0     # Figure 5 shows 0 to 4 cm
NUMBER_OF_POINTS         = 300     # points after z = 0 (z = 0 is always added)
FIRST_POINT_cm           = 0.001   # geometric spacing from here: dense near the tip

# --- Second-streamer search ---------------------------------------------------
SEARCH_SECOND_STREAMER_UNTIL_us = 100.0   # look for the second inception up to this time

# --- Search range for theta_B (the answer must lie inside it) -----------------
THETA_B_MIN_deg          = 5.0
THETA_B_MAX_deg          = 175.0

# --- Output file --------------------------------------------------------------
OUTPUT_FILE              = "output/wh_fig5_reproduction.xlsx"


# Unit conversion factors
CM_TO_M              = 1e-2       # 1 cm      = 0.01 m
KV_TO_V              = 1e3        # 1 kV      = 1000 V
KV_PER_CM_TO_V_PER_M = 1e5        # 1 kV/cm   = 100 000 V/m
US_TO_S              = 1e-6       # 1 us      = 1e-6 s
MOBILITY_TO_SI       = 1e-1       # 1 cm^2/(kV*us) = 0.1 m^2/(V*s)
M_PER_S_TO_CM_PER_US = 1e-4       # 1 m/s     = 1e-4 cm/us


def main():
    # Very close to the cone apex the observation point touches the start of the
    # charge, so scipy cannot always reach its (very strict) 1e-8 tolerance and
    # warns. The values there are still smooth and correct, so these warnings are hidden.
    warnings.simplefilter("ignore", IntegrationWarning)

    # =========================================================================
    # 2. Convert the inputs to SI units for the solver
    # =========================================================================
    R      = ROD_TIP_RADIUS_cm   * CM_TO_M
    D      = GAP_LENGTH_cm       * CM_TO_M
    V_peak = IMPULSE_CREST_kV    * KV_TO_V
    V_inc  = INCEPTION_VOLTAGE_kV * KV_TO_V
    L_cs   = STREAMER_LENGTH_cm  * CM_TO_M
    E_c    = STREAMER_FIELD_kV_per_cm * KV_PER_CM_TO_V_PER_M
    B      = DENSITY_EXPONENT_B
    C      = DENSITY_OFFSET_C_cm * CM_TO_M
    mobility = ION_MOBILITY_cm2_per_kV_us * MOBILITY_TO_SI
    t_search_end = SEARCH_SECOND_STREAMER_UNTIL_us * US_TO_S

    z_cm = np.concatenate(([0.0], np.geomspace(FIRST_POINT_cm, Z_MAX_cm, NUMBER_OF_POINTS)))
    z = z_cm * CM_TO_M

    # =========================================================================
    # 3. The impulse voltage V(t) and the inception instant
    # =========================================================================
    print("Step 1/6: building the impulse and finding the inception instant ...")
    alpha, beta, k = double_exponential_parameters(TIME_TO_CREST_us * US_TO_S,
                                                   TIME_TO_HALF_VALUE_us * US_TO_S)

    def V(t):
        return impulse_voltage(t, V_peak, alpha, beta, k)

    t_inc = brentq(lambda t: V(t) - V_inc, 0.0, TIME_TO_CREST_us * US_TO_S)
    print(f"          V(t) reaches {INCEPTION_VOLTAGE_kV} kV at t_inc = {t_inc / US_TO_S:.3f} us")

    # All time steps: the requested ones plus the inception instant
    times = np.unique(np.append(np.asarray(TIME_STEPS_us) * US_TO_S, t_inc))

    # =========================================================================
    # 4. Create the first-streamer space charge at t_inc (cloud of Figure 3)
    # =========================================================================
    print("Step 2/6: creating the space charge at inception (solving theta_B) ...")
    theta_B = solve_theta_b(R, D, V_inc, L_cs, E_c, B, C,
                            theta_min=np.radians(THETA_B_MIN_deg),
                            theta_max=np.radians(THETA_B_MAX_deg))
    Q_cs = calculate_qcs_from_field(E_c, L_cs_m=L_cs, theta_B_rad=theta_B)
    A = density_amplitude(E_c, L_cs, theta_B, B, C)
    print(f"          theta_B = {np.degrees(theta_B):.3f} deg, Q_cs = {Q_cs * 1e9:.2f} nC")

    # =========================================================================
    # 5. Drift of the cloud from t_inc on, under the rising voltage
    # =========================================================================
    print("Step 3/6: drifting the space charge under the rising voltage ...")
    drift = simulate_drift(R, D, lambda t_since: V(t_inc + t_since), L_cs, theta_B, A, B, C, mobility,
                           drift_time=t_search_end - t_inc)
    z_drift_at = drift["z_drift_at"]      # function of the time since inception

    # =========================================================================
    # 6. Fields at every time step
    # =========================================================================
    # The applied field is proportional to the voltage, so its shape is computed once.
    E_ex_per_volt = calculate_applied_field(R, D, 1.0, z)
    E_ex_tip_per_volt = float(E_ex_per_volt[0])
    E_tip_at_inception = V_inc * E_ex_tip_per_volt   # applied field at the tip when the first streamer starts

    def space_charge_fields(points, z_drift):
        """E_sp + E_I,rod + E_I,plane [V/m] for the cloud drifted by z_drift."""
        return (calculate_e_sp(points, R, L_cs, theta_B, A, B, C, z_drift=z_drift)
                + calculate_e_rod_image(points, R, L_cs, theta_B, A, B, C, z_drift=z_drift)
                + calculate_e_plane_image(points, D, R, L_cs, theta_B, A, B, C, z_drift=z_drift))

    print(f"Step 4/6: computing the fields at {len(z)} points for {len(times)} time steps ...")
    applied, total, step_rows = [], [], []
    for t in times:
        E_ex = V(t) * E_ex_per_volt
        has_charge = t >= t_inc
        z_drift = float(z_drift_at(t - t_inc)) if has_charge else 0.0
        E_total = E_ex + space_charge_fields(z, z_drift) if has_charge else E_ex
        applied.append(E_ex)
        total.append(E_total)
        step_rows.append((t, V(t), has_charge, z_drift, E_ex[0], E_total[0]))
        print(f"          t = {t / US_TO_S:5.3f} us   V = {V(t) / KV_TO_V:6.2f} kV   "
              f"{'space charge, drift ' + format(z_drift / CM_TO_M, '.4f') + ' cm' if has_charge else 'no space charge yet'}")

    # =========================================================================
    # 7. When would a second streamer start?
    #    Criterion: the total field at the tip is back to its value at the first inception.
    # =========================================================================
    print("Step 5/6: looking for the second-streamer inception ...")

    def tip_field_mismatch(t):
        tip = np.array([0.0])
        E_tip = V(t) * E_ex_tip_per_volt + float(space_charge_fields(tip, float(z_drift_at(t - t_inc)))[0])
        return E_tip - E_tip_at_inception

    t_second = None
    if tip_field_mismatch(t_search_end) > 0:
        t_second = brentq(tip_field_mismatch, t_inc * (1 + 1e-9), t_search_end, xtol=1e-9)
        print(f"          second streamer would incept at t = {t_second / US_TO_S:.3f} us "
              f"(V = {V(t_second) / KV_TO_V:.2f} kV)")
    else:
        print(f"          not reached before {SEARCH_SECOND_STREAMER_UNTIL_us} us")

    # =========================================================================
    # 8. Convert back to engineering units and save to Excel
    # =========================================================================
    print("Step 6/6: saving to Excel ...")

    def to_kV_per_cm(field_V_per_m):
        return field_V_per_m / KV_PER_CM_TO_V_PER_M

    def column_name(t):
        label = f"t = {t / US_TO_S:.3f} us (V = {V(t) / KV_TO_V:.1f} kV)"
        if abs(t - t_inc) < 1e-12:
            label += " inception"
        elif t_second is not None and t > t_second:
            label += " after 2nd-streamer criterion"
        return label + " [kV/cm]"

    fig5a_sheet = {"z from tip apex [cm]": z_cm}
    fig5b_sheet = {"z from tip apex [cm]": z_cm}
    for t, E_a, E_b in zip(times, applied, total):
        fig5a_sheet[column_name(t)] = to_kV_per_cm(E_a)
        fig5b_sheet[column_name(t)] = to_kV_per_cm(E_b)

    steps_sheet = {
        "time [us]":                              [row[0] / US_TO_S for row in step_rows],
        "voltage V(t) [kV]":                      [row[1] / KV_TO_V for row in step_rows],
        "space charge present":                   ["yes" if row[2] else "no" for row in step_rows],
        "drift distance z_drift [cm]":            [row[3] / CM_TO_M for row in step_rows],
        "E_ex at the tip [kV/cm]":                [to_kV_per_cm(row[4]) for row in step_rows],
        "E_total at the tip [kV/cm]":             [to_kV_per_cm(row[5]) for row in step_rows],
    }

    parameters = [
        # (name, value, unit)
        ("INPUTS",                                    "",                                   ""),
        ("Rod tip radius R",                          ROD_TIP_RADIUS_cm,                    "cm"),
        ("Gap length D (tip apex to plane)",          GAP_LENGTH_cm,                        "cm"),
        ("Impulse crest",                             IMPULSE_CREST_kV,                     "kV"),
        ("Time to crest",                             TIME_TO_CREST_us,                     "us"),
        ("Time to half value (assumed)",              TIME_TO_HALF_VALUE_us,                "us"),
        ("First-streamer inception voltage",          INCEPTION_VOLTAGE_kV,                 "kV"),
        ("Streamer length L_cs",                      STREAMER_LENGTH_cm,                   "cm"),
        ("Streamer field E_c",                        STREAMER_FIELD_kV_per_cm,             "kV/cm"),
        ("Density exponent B",                        DENSITY_EXPONENT_B,                   "-"),
        ("Density offset C",                          DENSITY_OFFSET_C_cm,                  "cm"),
        ("Ion mobility b",                            ION_MOBILITY_cm2_per_kV_us,           "cm^2/(kV*us)"),
        ("z range (from tip apex)",                   f"0 to {Z_MAX_cm:g}",                 "cm"),
        ("Number of z points",                        len(z_cm),                            "-"),
        ("RESULTS",                                   "",                                   ""),
        ("Double exponential alpha",                  alpha,                                "1/s"),
        ("Double exponential beta",                   beta,                                 "1/s"),
        ("Double exponential k",                      k,                                    "-"),
        ("Inception instant t_inc",                   t_inc / US_TO_S,                      "us"),
        ("Solved theta_B",                            np.degrees(theta_B),                  "deg"),
        ("Total streamer charge Q_cs",                Q_cs * 1e9,                           "nC"),
        ("Density amplitude A (SI)",                  A,                                    "C*m^(B-3)"),
        ("Applied field at the tip at inception",     to_kV_per_cm(E_tip_at_inception),     "kV/cm"),
        ("Second-streamer criterion met at",          t_second / US_TO_S if t_second is not None else "not reached", "us"),
        ("Voltage at second-streamer criterion",      V(t_second) / KV_TO_V if t_second is not None else "-", "kV"),
        ("Drift distance at second-streamer criterion",
         float(z_drift_at(t_second - t_inc)) / CM_TO_M if t_second is not None else "-", "cm"),
        ("Generated on",                              datetime.now().strftime("%Y-%m-%d %H:%M"), ""),
    ]
    parameters_sheet = {
        "Parameter": [name for name, _, _ in parameters],
        "Value":     [value for _, value, _ in parameters],
        "Unit":      [unit for _, _, unit in parameters],
    }

    save_to_excel(OUTPUT_FILE, {"Fig5a applied": fig5a_sheet,
                                "Fig5b with space charge": fig5b_sheet,
                                "Time steps": steps_sheet,
                                "Parameters": parameters_sheet})
    print(f"Done. Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
