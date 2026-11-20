"""
Calibration of the charge model on the first corona streamer (data + charts, for Excel)
======================================================================================

What this script does
---------------------
Finds the shape constants B and C of the space-charge density rho(r) = A / (r + C)^B
(A always follows from Gauss's law over the head of the streamer) for which the total
field along the first streamer (at the inception voltage, no older space charge, cone
angle theta_B given)
    (a) equals E_c at the head (this gives the length L_1),
    (b) stays, along the body of the streamer (from a tenth of its length to the head), as
        close to E_c as possible: on average E_c and nearly uniform (smallest RMS deviation),
as described in solver/calibration.py. The length of the first streamer L_1 and its
charge Q_1 come out of the calibration as predictions.

Steps
-----
1. Grid over B and C, on all CPU cores; for each, L_1 is the root of the head condition
   with the Gauss charge and the field along that streamer is checked and scored.
2. Local refinement of the best combination.
3. Check: a burst at V_inc with the calibrated B, C (solver/simulation.py, largest
   root of the head condition) must give back L_1.
4. Fields of the calibrated streamer along the axis.
5. Excel workbook:
       "Profile"            z, every field component, E_total, E_c   (+ chart)
       "Grid"               every (B, C): L_1, A, score, mean and lowest field, reported checks
       "Map B-C"            score for each (B, C)  (empty: conditions not met)
       "Parameters"         inputs and results

Units: inputs and outputs in cm, kV, kV/cm, degrees, nC; SI inside the solver.

How to run
----------
    python -m thesis.wh_calibration        (about 10 minutes on 16 cores)
"""

import warnings
from datetime import datetime
from typing import cast

import numpy as np
from openpyxl import load_workbook
from openpyxl.chart import Reference, ScatterChart
from openpyxl.chart.legend import Legend
from openpyxl.chart.series_factory import SeriesFactory
from openpyxl.worksheet.worksheet import Worksheet
from scipy.integrate import IntegrationWarning

from thesis.excel_export import save_to_excel
from solver.applied_field import calculate_applied_field
from solver.calibration import CalibrationProblem, calibrate
from solver.constants import POSITIVE_ION_MOBILITY
from solver.fields import calculate_e_plane_image, calculate_e_rod_image, calculate_e_sp
from solver.simulation import GapModel, solve_streamer_length

# =============================================================================
# 1. INPUTS  (engineering units - edit these)
# =============================================================================
ROD_TIP_RADIUS_cm        = 0.1     # R     : radius of the hemispherical rod tip
GAP_LENGTH_cm            = 80.0    # D     : rod tip apex -> grounded plane
ROD_LENGTH_cm            = 400.0   # L_rod : modelled rod length for the applied field (assumed 5 * D)
INCEPTION_VOLTAGE_kV     = 27.5    # V_inc : first-streamer inception voltage (paper, Fig. 3 case)
CONE_ANGLE_deg           = 90.0    # theta_B : full cone angle (not given in the paper; Ch. 6 fit gives ~88.5)
STABILITY_FIELD_kV_cm    = 5.0     # E_c   : stability field of positive streamers

NEAR_TIP_FRACTION        = 0.1     # the conditions apply from this fraction of L to the head (body of the streamer)
TOLERANCE_kV_cm          = 0.01    # numerical slack of the checks ">= E_c" and "decreasing"

# Search grid
B_GRID                   = np.arange(1.0, 3.001, 0.25)
C_GRID_cm                = np.geomspace(0.003, 1.0, 12)

PAPER_LENGTH_cm          = 2.7     # first-streamer length given by the paper (validation only)

OUTPUT_FILE              = "thesis/output/wh_calibration.xlsx"

CM_TO_M, KV_TO_V, KV_PER_CM_TO_V_PER_M = 1e-2, 1e3, 1e5


def to_kv_cm(field):
    return np.asarray(field) / KV_PER_CM_TO_V_PER_M


def main():
    warnings.simplefilter("ignore", IntegrationWarning)
    R, D, L_rod = ROD_TIP_RADIUS_cm * CM_TO_M, GAP_LENGTH_cm * CM_TO_M, ROD_LENGTH_cm * CM_TO_M
    problem = CalibrationProblem(R=R, D=D, V_inc=INCEPTION_VOLTAGE_kV * KV_TO_V, theta_B=np.radians(CONE_ANGLE_deg),
                                 E_c=STABILITY_FIELD_kV_cm * KV_PER_CM_TO_V_PER_M, rod_length=L_rod,
                                 near_tip_fraction=NEAR_TIP_FRACTION,
                                 tolerance=TOLERANCE_kV_cm * KV_PER_CM_TO_V_PER_M)

    # 2-3. Grid and refinement
    print("Step 1/4: calibration (grid + refinement) ...")
    result = calibrate(problem, B_GRID, C_GRID_cm * CM_TO_M, verbose=True)
    print(f"          A = {result.A:.4e} SI, B = {result.B:.3f}, C = {result.C * 100:.4f} cm, "
          f"L_1 = {result.L1 * 100:.3f} cm, Q_1 = {result.Q1 * 1e9:.2f} nC, score = {result.score:.3f}")

    # 3. Check with the simulation's own length rule
    print("Step 2/4: check with the burst-length rule of the simulation ...")
    model = GapModel(R=R, D=D, theta_B=problem.theta_B, E_c=problem.E_c,
                     E_inc=problem.V_inc * float(calculate_applied_field(R, D, 1.0, 0.0, rod_length=L_rod)),
                     B=result.B, C=result.C, mobility=POSITIVE_ION_MOBILITY, rod_length=L_rod)
    L_check, _, _, _ = solve_streamer_length(model, problem.V_inc, [])
    print(f"          first root of the head condition: L = {L_check * 100:.3f} cm (calibration {result.L1 * 100:.3f} cm)")

    # 4. Fields of the calibrated first streamer
    print("Step 3/4: fields of the calibrated first streamer ...")
    z_cm = np.concatenate(([0.0], np.geomspace(0.001, 1.6 * result.L1 * 100, 250)))
    z = z_cm * CM_TO_M
    args = (R, result.L1, problem.theta_B, result.A, result.B, result.C)
    E_ex = calculate_applied_field(R, D, problem.V_inc, z, rod_length=L_rod)
    E_sp = calculate_e_sp(z, *args)
    E_rod = calculate_e_rod_image(z, *args)
    E_plane = calculate_e_plane_image(z, D, *args)
    E_total = E_ex + E_sp + E_rod + E_plane

    # 5. Excel
    print("Step 4/4: saving to Excel ...")
    profile = {
        "z from tip apex [cm]": z_cm,
        "E_ex [kV/cm]": to_kv_cm(E_ex),
        "E_sp space charge [kV/cm]": to_kv_cm(E_sp),
        "E_I,rod rod image [kV/cm]": to_kv_cm(E_rod),
        "E_I,plane plane image [kV/cm]": to_kv_cm(E_plane),
        "E_total [kV/cm]": to_kv_cm(E_total),
        "E_c [kV/cm]": np.full_like(z_cm, STABILITY_FIELD_kV_cm),
    }
    grid = [r for r in result.grid if r["L"] is not None]
    grid_sheet = {
        "B [-]": [r["B"] for r in grid],
        "C [cm]": [r["C"] * 100 for r in grid],
        "L [cm]": [r["L"] * 100 for r in grid],
        "A [SI]": [r["A"] for r in grid],
        "score [-]": [r["score"] for r in grid],
        "max deviation [-]": [r["max_deviation"] for r in grid],
        "mean field along the body [kV/cm]": [r["E_mean"] / KV_PER_CM_TO_V_PER_M for r in grid],
        "lowest field along the body [kV/cm]": [r["E_min"] / KV_PER_CM_TO_V_PER_M for r in grid],
        "checks not met (reported only)": [", ".join(k for k, ok in r["checks"].items() if not ok) for r in grid],
    }
    map_sheet = {"C [cm] \\ B": list(C_GRID_cm)}
    for B in B_GRID:
        column = []
        for C in C_GRID_cm * CM_TO_M:
            scores = [r["score"] for r in grid if r["feasible"] and np.isclose(r["B"], B) and np.isclose(r["C"], C)]
            column.append(min(scores) if scores else None)
        map_sheet[f"{B:.2f}"] = column

    best = result.best
    parameters = [
        ("INPUTS", "", ""),
        ("Rod tip radius R", ROD_TIP_RADIUS_cm, "cm"),
        ("Gap length D", GAP_LENGTH_cm, "cm"),
        ("Rod length L_rod", ROD_LENGTH_cm, "cm"),
        ("Inception voltage V_inc", INCEPTION_VOLTAGE_kV, "kV"),
        ("Cone angle theta_B", CONE_ANGLE_deg, "deg"),
        ("Stability field E_c", STABILITY_FIELD_kV_cm, "kV/cm"),
        ("Near-tip fraction", NEAR_TIP_FRACTION, "-"),
        ("Tolerance of the checks", TOLERANCE_kV_cm, "kV/cm"),
        ("Grid B", f"{B_GRID.min():g} to {B_GRID.max():g} ({len(B_GRID)})", "-"),
        ("Grid C", f"{C_GRID_cm.min():g} to {C_GRID_cm.max():g} ({len(C_GRID_cm)}, log)", "cm"),
        ("Combinations with a first-streamer length", f"{len(grid)} of {len(result.grid)}", ""),
        ("RESULTS", "", ""),
        ("A of the first streamer (Gauss)", result.A, "C*m^(B-3)"),
        ("B", result.B, "-"),
        ("C", result.C * 100, "cm"),
        ("First-streamer length L_1 (prediction)", result.L1 * 100, "cm"),
        ("First-streamer charge Q_1", result.Q1 * 1e9, "nC"),
        ("Score: RMS of (E_total - E_c)/E_c inside", result.score, "-"),
        ("Mean field along the body", best["E_mean"] / KV_PER_CM_TO_V_PER_M, "kV/cm"),
        ("Lowest field along the body", best["E_min"] / KV_PER_CM_TO_V_PER_M, "kV/cm"),
        ("Largest deviation from E_c inside", best["max_deviation"], "-"),
        ("Body of the streamer starts at z", best["z_body"] * 100, "cm"),
        ("Check: first root of the head condition", L_check * 100, "cm"),
        ("Paper's first-streamer length (validation)", PAPER_LENGTH_cm, "cm"),
        ("Generated on", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"), ""),
    ]
    parameters_sheet = {"Parameter": [p[0] for p in parameters], "Value": [p[1] for p in parameters],
                        "Unit": [p[2] for p in parameters]}
    save_to_excel(OUTPUT_FILE, {"Profile": profile, "Grid": grid_sheet, "Map B-C": map_sheet,
                                "Parameters": parameters_sheet})
    add_profile_chart(OUTPUT_FILE, len(z_cm), result.L1 * 100)
    print(f"Done. Saved to {OUTPUT_FILE}")


def add_profile_chart(path, n_rows, L1_cm):
    workbook = load_workbook(path)
    ws = cast(Worksheet, workbook["Profile"])
    chart = ScatterChart()
    chart.title = "Total field along the calibrated first streamer"
    chart.x_axis.title = "Distance z from the rod tip [cm]"
    chart.y_axis.title = "Electric field [kV/cm]"
    chart.x_axis.axPos = "b"
    chart.x_axis.scaling.min, chart.x_axis.scaling.max = 0, round(1.5 * L1_cm, 1)
    chart.y_axis.scaling.min, chart.y_axis.scaling.max = -10, 20
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    chart.legend = Legend(legendPos="b")
    chart.width, chart.height = 22, 13
    for column, colour, width, dash in ((6, "000000", 25400, None), (2, "7F7F7F", 15875, None),
                                        (7, "2E7D32", 15875, "dash")):
        series = SeriesFactory(values=Reference(ws, min_col=column, min_row=1, max_row=n_rows + 1),
                               xvalues=Reference(ws, min_col=1, min_row=2, max_row=n_rows + 1), title_from_data=True)
        series.marker.symbol = "none"
        series.smooth = False
        series.graphicalProperties.line.solidFill = colour
        series.graphicalProperties.line.width = width
        if dash:
            series.graphicalProperties.line.dashStyle = dash
        chart.series.append(series)
    ws.add_chart(chart, "J2")
    workbook.save(path)


if __name__ == "__main__":
    main()
