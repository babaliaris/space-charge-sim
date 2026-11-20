"""
Wang & Haiting - Figure 3 parameter fit (data only, for Excel)
==============================================================

What this script does
---------------------
The paper gives L_cs = 2.7 cm but not theta_B, and B, C only approximately.
This script finds the combination (theta_B, B, C, A) for which OUR E_sp and
E_I,rod come closest to the paper's digitized curves (input/wh_fig3_datasets.csv).

1. Reads the digitized E_sp and E_I,rod of the paper (points with z >= Z_FIT_FROM).
2. Coarse grid over theta_B x B x C (in parallel on all CPU cores). For every
   combination the best charge is found exactly: the fields are proportional to
   the charge, so the best Q_cs is a one-line least-squares formula (A follows
   from Q_cs). So A is never searched.
3. Refines the best grid points with scipy's least_squares (local optimizer).
4. With the best fit, computes all fields along the axis (and, for comparison,
   the paper's parameters with our Gauss's-law charge) and checks:
       - Q_cs(fit) / Q_cs(Gauss with E_c)      -> is our Gauss's-law charge right?
       - where E_sp has its maximum             -> paper: about 2.29 cm
       - total field rule inside the streamer   -> >= E_c, decreasing, E_c at the head
5. Saves everything to Excel:
       "Best fit"     inputs, fitted values, errors and checks
       "Fields"       one row per z: best-fit fields, reference fields, paper curves
       "Paper"        the digitized curves as read
       "Grid"         one row per grid combination (error, fitted charge)
       "Map B-theta"  smallest error over C, for each (B, theta_B)  -> heat map
       "Map C-B"      smallest error over theta_B, for each (C, B)  -> heat map
       "Refinement"   start and end point of each local refinement

Error measure
-------------
Each curve's residuals are divided by the RMS of that paper curve (when
WEIGHT_BY_CURVE_SCALE is True) and by sqrt(number of its points), so E_sp and
E_I,rod count equally and the steep values near the apex do not swamp the
region near the head. The plain RMS errors in kV/cm are reported as well.

Units
-----
Inputs and outputs in cm, kV, kV/cm, degrees, nC; SI inside the solver.
z is measured from the rod tip apex.

How to run
----------
    python wh_fig3_fit.py

About 3-5 minutes on 16 cores.
"""

import os
import warnings
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

import numpy as np
from scipy.integrate import IntegrationWarning
from scipy.optimize import least_squares

from compare_datasets import load_curves
from excel_export import save_to_excel
from solver.applied_field import calculate_applied_field
from solver.fields import calculate_e_plane_image, calculate_e_rod_image, calculate_e_sp
from solver.utilities import calculate_A_from_charge, calculate_qcs_from_field

# =============================================================================
# 1. INPUTS  (engineering units - edit these)
# =============================================================================

# --- Known from the paper ---------------------------------------------------
ROD_TIP_RADIUS_cm        = 0.1     # R     : radius of the hemispherical rod tip
GAP_LENGTH_cm            = 80.0    # D     : rod tip apex -> grounded plane
ROD_LENGTH_cm            = 400.0   # L_rod : modelled rod length for the CSM (not in the paper, assumed 5 * D)
APPLIED_VOLTAGE_kV       = 27.5    # V     : rod voltage of Fig. 3
STREAMER_LENGTH_cm       = 2.7     # L_cs  : fixed (given in the paper)
STREAMER_FIELD_kV_per_cm = 5.0     # E_c   : only used for the Gauss's-law comparison and the rule check

# --- Paper's digitized curves -------------------------------------------------
PAPER_FILE               = "input/wh_fig3_datasets.csv"
PAPER_ESP_NAME           = "Esp"           # curve names in that file
PAPER_EI_ROD_NAME        = "Ei,rod"
PAPER_SUM_NAME           = "Esp+Ei,rod"    # not fitted, only reported as a check
Z_FIT_FROM_cm            = 0.1     # fit only z >= this (the apex region is too steep to digitize well)
WEIGHT_BY_CURVE_SCALE    = True    # divide each curve's residuals by its RMS (see docstring)

# --- Coarse grid (stage 1) ------------------------------------------------------
THETA_B_GRID_deg         = np.arange(20.0, 171.0, 10.0)   # full cone angle
B_GRID                   = np.arange(1.0, 3.01, 0.2)      # density exponent
C_GRID_cm                = np.geomspace(0.005, 0.3, 8)    # density offset

# --- Local refinement (stage 2) ------------------------------------------------
NUMBER_OF_STARTS         = 4       # refine this many of the best (well separated) grid points
MAX_EVALUATIONS          = 150     # per refinement

# --- Paper's own parameters, for the reference curves ------------------------
REFERENCE_THETA_B_deg    = 93.39   # from E_total(2.7 cm) = 5 kV/cm (wh_fig3_reproduction.py)
REFERENCE_B              = 1.5
REFERENCE_C_cm           = 0.035

# --- Output ---------------------------------------------------------------------
Z_MAX_cm                 = 3.5     # fields sheet: z range
NUMBER_OF_POINTS         = 200
FIRST_POINT_cm           = 0.001
OUTPUT_FILE              = "output/wh_fig3_fit.xlsx"

# Unit conversion factors
CM_TO_M              = 1e-2
KV_TO_V              = 1e3
KV_PER_CM_TO_V_PER_M = 1e5
C_TO_NC              = 1e9
UNIT_CHARGE_C        = 1e-9   # charge used to evaluate the per-coulomb fields


# =============================================================================
# Field of the cone per coulomb of charge (all combinations go through here)
# =============================================================================
def unit_fields(theta_B_deg, B, C_cm, z_sp_cm, z_rod_cm):
    """E_sp at z_sp and E_I,rod at z_rod [kV/cm per coulomb of Q_cs], HV-unit inputs.

    The integrals are evaluated for a realistic charge (1 nC) and then divided by it:
    the solver's absolute tolerance is set for real field magnitudes, and a 1 C charge
    would make the quadrature work about ten times longer for no gain.
    """
    warnings.simplefilter("ignore", IntegrationWarning)
    R, L_cs = ROD_TIP_RADIUS_cm * CM_TO_M, STREAMER_LENGTH_cm * CM_TO_M
    theta_B, C = np.radians(theta_B_deg), C_cm * CM_TO_M
    A = calculate_A_from_charge(UNIT_CHARGE_C, B, C, L_cs_m=L_cs, theta_B_rad=theta_B)
    E_sp = calculate_e_sp(np.asarray(z_sp_cm) * CM_TO_M, R, L_cs, theta_B, A, B, C)
    E_rod = calculate_e_rod_image(np.asarray(z_rod_cm) * CM_TO_M, R, L_cs, theta_B, A, B, C)
    scale = 1.0 / (KV_PER_CM_TO_V_PER_M * UNIT_CHARGE_C)
    return E_sp * scale, E_rod * scale


class PaperData:
    """The two fitted paper curves and their weights."""

    def __init__(self):
        curves, _ = load_curves(PAPER_FILE)
        by_name = {curve.name: curve for curve in curves}
        self.all = by_name
        self.esp = by_name[PAPER_ESP_NAME]
        self.rod = by_name[PAPER_EI_ROD_NAME]
        use_sp, use_rod = self.esp.x >= Z_FIT_FROM_cm, self.rod.x >= Z_FIT_FROM_cm
        self.z_sp, self.y_sp = self.esp.x[use_sp], self.esp.y[use_sp]
        self.z_rod, self.y_rod = self.rod.x[use_rod], self.rod.y[use_rod]

        def weight(y):
            scale = np.sqrt(np.mean(y**2)) if WEIGHT_BY_CURVE_SCALE else 1.0
            return 1.0 / (scale * np.sqrt(len(y)))

        self.w_sp, self.w_rod = weight(self.y_sp), weight(self.y_rod)

    def fit_charge(self, g_sp, g_rod):
        """Best Q_cs [C] and the error measures for unit fields g_sp, g_rod [kV/cm per C]."""
        numerator = self.w_sp**2 * (g_sp @ self.y_sp) + self.w_rod**2 * (g_rod @ self.y_rod)
        denominator = self.w_sp**2 * (g_sp @ g_sp) + self.w_rod**2 * (g_rod @ g_rod)
        Q = numerator / denominator
        residuals = np.concatenate((self.w_sp * (Q * g_sp - self.y_sp), self.w_rod * (Q * g_rod - self.y_rod)))
        return {
            "Q": Q,
            "residuals": residuals,
            "error": float(np.sqrt(np.sum(residuals**2) / 2.0)),   # weighted RMS (per curve)
            "rms_sp": float(np.sqrt(np.mean((Q * g_sp - self.y_sp) ** 2))),
            "rms_rod": float(np.sqrt(np.mean((Q * g_rod - self.y_rod) ** 2))),
        }


def evaluate(arguments):
    """Worker: (theta_B, B, C) -> fit result. Runs in a separate process."""
    theta_B_deg, B, C_cm, paper = arguments
    g_sp, g_rod = unit_fields(theta_B_deg, B, C_cm, paper.z_sp, paper.z_rod)
    result = paper.fit_charge(g_sp, g_rod)
    result.update(theta_B=theta_B_deg, B=B, C=C_cm)
    return result


def refine(arguments):
    """Worker: local least-squares refinement from one start point."""
    start, paper, bounds = arguments

    def residuals(p):
        theta_B_deg, B, log10_C = p
        g_sp, g_rod = unit_fields(theta_B_deg, B, 10.0**log10_C, paper.z_sp, paper.z_rod)
        return paper.fit_charge(g_sp, g_rod)["residuals"]

    p0 = [start["theta_B"], start["B"], np.log10(start["C"])]
    solution = least_squares(residuals, p0, bounds=bounds, x_scale=[10.0, 0.2, 0.2],
                             diff_step=1e-3, max_nfev=MAX_EVALUATIONS)
    theta_B_deg, B, log10_C = solution.x
    result = evaluate((theta_B_deg, B, 10.0**log10_C, paper))
    result["start"] = start
    result["evaluations"] = solution.nfev
    return result


def well_separated_best(results, count):
    """The `count` lowest-error grid points, skipping neighbours of points already taken."""
    steps = (np.diff(THETA_B_GRID_deg)[0], np.diff(B_GRID)[0], np.diff(np.log10(C_GRID_cm))[0])
    chosen = []
    for result in sorted(results, key=lambda r: r["error"]):
        position = (result["theta_B"], result["B"], np.log10(result["C"]))
        if all(any(abs(a - b) > 1.01 * s for a, b, s in zip(position, other, steps)) for other in
               [(c["theta_B"], c["B"], np.log10(c["C"])) for c in chosen]):
            chosen.append(result)
        if len(chosen) == count:
            break
    return chosen


def all_fields(theta_B_deg, B, C_cm, Q, z_cm):
    """Every axial field [kV/cm] on z_cm for the given cone and charge Q [C]."""
    R, D, L_rod = ROD_TIP_RADIUS_cm * CM_TO_M, GAP_LENGTH_cm * CM_TO_M, ROD_LENGTH_cm * CM_TO_M
    L_cs, theta_B, C = STREAMER_LENGTH_cm * CM_TO_M, np.radians(theta_B_deg), C_cm * CM_TO_M
    A = calculate_A_from_charge(Q, B, C, L_cs_m=L_cs, theta_B_rad=theta_B)
    z = z_cm * CM_TO_M
    E = {
        "E_ex": calculate_applied_field(R, D, APPLIED_VOLTAGE_kV * KV_TO_V, z, rod_length=L_rod),
        "E_sp": calculate_e_sp(z, R, L_cs, theta_B, A, B, C),
        "E_I,rod": calculate_e_rod_image(z, R, L_cs, theta_B, A, B, C),
        "E_I,plane": calculate_e_plane_image(z, D, R, L_cs, theta_B, A, B, C),
    }
    E = {name: value / KV_PER_CM_TO_V_PER_M for name, value in E.items()}
    E["E_total"] = E["E_ex"] + E["E_sp"] + E["E_I,rod"] + E["E_I,plane"]
    return E, A


def gauss_charge(theta_B_deg):
    """Q_cs [C] from Gauss's law with E_c (the solver's charge model)."""
    return calculate_qcs_from_field(STREAMER_FIELD_kV_per_cm * KV_PER_CM_TO_V_PER_M,
                                    L_cs_m=STREAMER_LENGTH_cm * CM_TO_M,
                                    theta_B_rad=np.radians(theta_B_deg))


def rule_check(z_cm, E_total):
    """Total-field rule inside the streamer (Z_FIT_FROM <= z <= L_cs)."""
    inside = (z_cm >= Z_FIT_FROM_cm) & (z_cm <= STREAMER_LENGTH_cm)
    E_in = E_total[inside]
    return {
        "head": float(np.interp(STREAMER_LENGTH_cm, z_cm, E_total)),
        "minimum": float(E_in.min()),
        "z_minimum": float(z_cm[inside][np.argmin(E_in)]),
        "decreasing": bool(np.all(np.diff(E_in) <= 1e-9)),
    }


def peak_position(z_cm, E):
    """z of the maximum of E for z >= 1 cm (away from the apex)."""
    use = z_cm >= 1.0
    return float(z_cm[use][np.argmax(E[use])])


def main():
    warnings.simplefilter("ignore", IntegrationWarning)
    paper = PaperData()
    workers = os.cpu_count() or 1

    # =========================================================================
    # 2. Coarse grid
    # =========================================================================
    grid = [(t, b, c, paper) for t in THETA_B_GRID_deg for b in B_GRID for c in C_GRID_cm]
    print(f"Step 1/4: coarse grid, {len(grid)} combinations on {workers} cores ...")
    with ProcessPoolExecutor(max_workers=workers) as pool:
        grid_results = []
        for result in pool.map(evaluate, grid, chunksize=4):
            grid_results.append(result)
            if len(grid_results) % max(1, len(grid) // 10) == 0:
                print(f"          {100 * len(grid_results) // len(grid)} % done", flush=True)
    best_grid = min(grid_results, key=lambda r: r["error"])
    print(f"          best grid point: theta_B = {best_grid['theta_B']:.0f} deg, B = {best_grid['B']:.1f}, "
          f"C = {best_grid['C']:.4f} cm, error = {best_grid['error']:.4f}")

    # =========================================================================
    # 3. Local refinement from the best well-separated grid points
    # =========================================================================
    starts = well_separated_best(grid_results, NUMBER_OF_STARTS)
    bounds = ([THETA_B_GRID_deg.min(), B_GRID.min(), np.log10(C_GRID_cm.min())],
              [THETA_B_GRID_deg.max(), B_GRID.max(), np.log10(C_GRID_cm.max())])
    print(f"Step 2/4: refining {len(starts)} start points ...")
    with ProcessPoolExecutor(max_workers=len(starts)) as pool:
        refined = list(pool.map(refine, [(s, paper, bounds) for s in starts]))
    best = min(refined, key=lambda r: r["error"])
    print(f"          best fit: theta_B = {best['theta_B']:.2f} deg, B = {best['B']:.3f}, "
          f"C = {best['C']:.4f} cm, Q_cs = {best['Q'] * C_TO_NC:.3f} nC, error = {best['error']:.4f}")

    # =========================================================================
    # 4. Fields of the best fit and of the paper's parameters
    # =========================================================================
    print("Step 3/4: computing the fields of the best fit and of the reference ...")
    z_cm = np.concatenate(([0.0], np.geomspace(FIRST_POINT_cm, Z_MAX_cm, NUMBER_OF_POINTS)))
    E_fit, A_fit = all_fields(best["theta_B"], best["B"], best["C"], best["Q"], z_cm)
    Q_ref = gauss_charge(REFERENCE_THETA_B_deg)
    E_ref, A_ref = all_fields(REFERENCE_THETA_B_deg, REFERENCE_B, REFERENCE_C_cm, Q_ref, z_cm)

    Q_gauss_fit = gauss_charge(best["theta_B"])
    rule_fit, rule_ref = rule_check(z_cm, E_fit["E_total"]), rule_check(z_cm, E_ref["E_total"])
    paper_peak = peak_position(paper.esp.x, paper.esp.y)
    fit_peak, ref_peak = peak_position(z_cm, E_fit["E_sp"]), peak_position(z_cm, E_ref["E_sp"])
    paper_sum = paper.all[PAPER_SUM_NAME]
    use_sum = (paper_sum.x >= Z_FIT_FROM_cm) & (paper_sum.x <= Z_MAX_cm)
    rms_sum = float(np.sqrt(np.mean(
        (np.interp(paper_sum.x[use_sum], z_cm, E_fit["E_sp"] + E_fit["E_I,rod"]) - paper_sum.y[use_sum]) ** 2)))
    print(f"          Q_cs(fit) / Q_cs(Gauss) = {best['Q'] / Q_gauss_fit:.3f}, "
          f"E_sp peak at {fit_peak:.2f} cm (paper {paper_peak:.2f} cm)")

    # =========================================================================
    # 5. Save to Excel
    # =========================================================================
    print("Step 4/4: saving to Excel ...")

    def paper_on_grid(curve):
        inside = (z_cm >= curve.x.min()) & (z_cm <= curve.x.max())
        return [float(v) if ok else None for v, ok in zip(np.interp(z_cm, curve.x, curve.y), inside)]

    fields_sheet: dict[str, object] = {"z from tip apex [cm]": z_cm}
    for name in ["E_ex", "E_sp", "E_I,rod", "E_I,plane", "E_total"]:
        fields_sheet[f"{name} fit [kV/cm]"] = E_fit[name]
    fields_sheet["E_sp + E_I,rod fit [kV/cm]"] = E_fit["E_sp"] + E_fit["E_I,rod"]
    for name in ["E_sp", "E_I,rod", "E_total"]:
        fields_sheet[f"{name} reference [kV/cm]"] = E_ref[name]
    fields_sheet["E_sp + E_I,rod reference [kV/cm]"] = E_ref["E_sp"] + E_ref["E_I,rod"]
    fields_sheet["E_sp paper [kV/cm]"] = paper_on_grid(paper.esp)
    fields_sheet["E_I,rod paper [kV/cm]"] = paper_on_grid(paper.rod)
    fields_sheet["E_sp + E_I,rod paper [kV/cm]"] = paper_on_grid(paper_sum)
    fields_sheet["E_c [kV/cm]"] = np.full_like(z_cm, STREAMER_FIELD_kV_per_cm)

    longest = max(len(c.x) for c in paper.all.values())
    paper_sheet = {}
    for curve in paper.all.values():
        pad = [None] * (longest - len(curve.x))
        paper_sheet[f"{curve.name} z [cm]"] = list(curve.x) + pad
        paper_sheet[f"{curve.name} E [kV/cm]"] = list(curve.y) + pad

    grid_sheet = {
        "theta_B [deg]": [r["theta_B"] for r in grid_results],
        "B [-]": [r["B"] for r in grid_results],
        "C [cm]": [r["C"] for r in grid_results],
        "Q_cs fit [nC]": [r["Q"] * C_TO_NC for r in grid_results],
        "Q_cs fit / Q_cs Gauss [-]": [r["Q"] / gauss_charge(r["theta_B"]) for r in grid_results],
        "weighted error [-]": [r["error"] for r in grid_results],
        "RMS E_sp [kV/cm]": [r["rms_sp"] for r in grid_results],
        "RMS E_I,rod [kV/cm]": [r["rms_rod"] for r in grid_results],
    }

    def error_map(row_values, column_values, row_key, column_key, row_label, column_format):
        sheet = {row_label: list(row_values)}
        for column in column_values:
            sheet[column_format(column)] = [
                min(r["error"] for r in grid_results
                    if np.isclose(r[row_key], row) and np.isclose(r[column_key], column))
                for row in row_values]
        return sheet

    map_b_theta = error_map(B_GRID, THETA_B_GRID_deg, "B", "theta_B", "B \\ theta_B [deg]", lambda t: f"{t:g}")
    map_c_b = error_map(C_GRID_cm, B_GRID, "C", "B", "C [cm] \\ B", lambda b: f"{b:.1f}")

    refinement_sheet = {
        "start theta_B [deg]": [r["start"]["theta_B"] for r in refined],
        "start B": [r["start"]["B"] for r in refined],
        "start C [cm]": [r["start"]["C"] for r in refined],
        "start error": [r["start"]["error"] for r in refined],
        "end theta_B [deg]": [r["theta_B"] for r in refined],
        "end B": [r["B"] for r in refined],
        "end C [cm]": [r["C"] for r in refined],
        "end Q_cs [nC]": [r["Q"] * C_TO_NC for r in refined],
        "end error": [r["error"] for r in refined],
        "evaluations": [r["evaluations"] for r in refined],
    }

    yes_no = {True: "yes", False: "NO"}
    parameters = [
        ("INPUTS", "", ""),
        ("Rod tip radius R", ROD_TIP_RADIUS_cm, "cm"),
        ("Gap length D", GAP_LENGTH_cm, "cm"),
        ("Rod length L_rod (CSM)", ROD_LENGTH_cm, "cm"),
        ("Applied voltage V", APPLIED_VOLTAGE_kV, "kV"),
        ("Streamer length L_cs (fixed)", STREAMER_LENGTH_cm, "cm"),
        ("Streamer field E_c (Gauss comparison, rule)", STREAMER_FIELD_kV_per_cm, "kV/cm"),
        ("Paper file", PAPER_FILE, ""),
        ("Fitted points: z >= ", Z_FIT_FROM_cm, "cm"),
        ("Fitted points E_sp / E_I,rod", f"{len(paper.z_sp)} / {len(paper.z_rod)}", "-"),
        ("Weight by curve scale", str(WEIGHT_BY_CURVE_SCALE), ""),
        ("Grid theta_B", f"{THETA_B_GRID_deg.min():g} to {THETA_B_GRID_deg.max():g} ({len(THETA_B_GRID_deg)})", "deg"),
        ("Grid B", f"{B_GRID.min():g} to {B_GRID.max():g} ({len(B_GRID)})", "-"),
        ("Grid C", f"{C_GRID_cm.min():g} to {C_GRID_cm.max():g} ({len(C_GRID_cm)}, log)", "cm"),
        ("BEST FIT", "", ""),
        ("theta_B", best["theta_B"], "deg"),
        ("B", best["B"], "-"),
        ("C", best["C"], "cm"),
        ("Q_cs (fitted)", best["Q"] * C_TO_NC, "nC"),
        ("A (SI)", A_fit, "C*m^(B-3)"),
        ("weighted error", best["error"], "-"),
        ("RMS E_sp", best["rms_sp"], "kV/cm"),
        ("RMS E_I,rod", best["rms_rod"], "kV/cm"),
        ("RMS E_sp + E_I,rod (not fitted, check)", rms_sum, "kV/cm"),
        ("CHECKS", "", ""),
        ("Q_cs from Gauss with E_c at the fitted theta_B", Q_gauss_fit * C_TO_NC, "nC"),
        ("Q_cs(fit) / Q_cs(Gauss)", best["Q"] / Q_gauss_fit, "-"),
        ("E_sp maximum at z (fit)", fit_peak, "cm"),
        ("E_sp maximum at z (paper)", paper_peak, "cm"),
        ("E_total at the head (fit)", rule_fit["head"], "kV/cm"),
        ("E_total minimum inside (fit)", rule_fit["minimum"], "kV/cm"),
        ("  at z", rule_fit["z_minimum"], "cm"),
        ("E_total decreasing inside (fit)", yes_no[rule_fit["decreasing"]], ""),
        ("REFERENCE (paper B, C; theta_B from E_total(2.7) = 5; Gauss charge)", "", ""),
        ("theta_B / B / C", f"{REFERENCE_THETA_B_deg:g} / {REFERENCE_B:g} / {REFERENCE_C_cm:g}", "deg / - / cm"),
        ("Q_cs (Gauss)", Q_ref * C_TO_NC, "nC"),
        ("A (SI)", A_ref, "C*m^(B-3)"),
        ("E_sp maximum at z", ref_peak, "cm"),
        ("E_total at the head", rule_ref["head"], "kV/cm"),
        ("E_total minimum inside", rule_ref["minimum"], "kV/cm"),
        ("E_total decreasing inside", yes_no[rule_ref["decreasing"]], ""),
        ("Generated on", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"), ""),
    ]
    parameters_sheet = {
        "Parameter": [name for name, _, _ in parameters],
        "Value": [value for _, value, _ in parameters],
        "Unit": [unit for _, _, unit in parameters],
    }

    save_to_excel(OUTPUT_FILE, {
        "Best fit": parameters_sheet,
        "Fields": fields_sheet,
        "Paper": paper_sheet,
        "Grid": grid_sheet,
        "Map B-theta": map_b_theta,
        "Map C-B": map_c_b,
        "Refinement": refinement_sheet,
    })
    print(f"Done. Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
