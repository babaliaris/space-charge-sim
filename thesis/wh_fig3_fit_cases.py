"""
Wang & Haiting - Figure 3: every fitting case we tried (data + charts, for Excel)
================================================================================

What this script does
---------------------
Fits our E_sp and E_I,rod to the paper's digitized curves (thesis/input/wh_fig3_datasets.csv)
under six different assumptions ("cases"), from the worst to the best fit, and saves
for each case the fitted parameters and the curves, together with a chart in which
our curves are solid and the paper's curves are dashed in the same colour.

    1. r1 typo        : E_sp with the r1 printed in the paper, r3*sin(theta) instead of r*sin(theta);
                        paper's B = 1.5, C = 0.035 cm; theta_B and the charge fitted
    2. coarse rule    : both fields with a coarse 4 x 4 Gauss-Legendre rule (in case the paper's
                        own quadrature was coarse); theta_B, B, C and the charge fitted
    3. paper's B, C   : B = 1.5 and C = 0.035 cm kept; theta_B and the charge fitted
    4. C in metres    : C = 0.035 m = 3.5 cm (the paper gives no unit), B = 1.5; theta_B and charge fitted
    5. full fit       : theta_B, B, C and the charge fitted, L_cs = 2.7 cm kept (as wh_fig3_fit.py)
    6. free L_cs      : as 5, with the streamer length L_cs fitted as well

For every combination of the searched parameters the best charge is found exactly
(the fields are proportional to it), so the charge is never searched. Each case is a
coarse grid over its free parameters followed by a local least-squares refinement.
The error measure is the one of wh_fig3_fit.py (per-curve weighted RMS, z >= 0.1 cm).

Output: thesis/output/wh_fig3_fit_cases.xlsx
    "Summary"   one row per case: fitted values, errors, position of the E_sp maximum
    "Case 1".."Case 6"  z, our E_sp and E_I,rod, the paper's curves, and the chart

How to run
----------
    python -m thesis.wh_fig3_fit_cases          (about 10 minutes on 16 cores; case 1 is the slow one)
"""

import os
import warnings
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from typing import cast

import numpy as np
from openpyxl import load_workbook
from openpyxl.chart import Reference, ScatterChart
from openpyxl.chart.legend import Legend
from openpyxl.chart.series_factory import SeriesFactory
from openpyxl.worksheet.worksheet import Worksheet
from scipy.integrate import IntegrationWarning, dblquad
from scipy.optimize import least_squares

from thesis.excel_export import save_to_excel
from solver.constants import EPSILON_0
from solver.fields import calculate_e_rod_image, calculate_e_sp
from solver.utilities import calculate_A_from_charge
from thesis.wh_fig3_fit import PaperData

# =============================================================================
# 1. INPUTS  (engineering units)
# =============================================================================
ROD_TIP_RADIUS_cm  = 0.1      # R
STREAMER_LENGTH_cm = 2.7      # L_cs given in the paper (fixed in cases 1-5)
PAPER_B            = 1.5      # "usually B is 1.5"
PAPER_C_cm         = 0.035    # "C is about 0.035" (no unit in the paper)
COARSE_NODES       = 4        # Gauss-Legendre nodes per direction in case 2

# Search ranges (grid, then local refinement inside the same bounds)
THETA_RANGE_deg    = (20.0, 170.0)
B_RANGE            = (1.0, 3.0)
C_RANGE_cm         = (0.005, 0.5)
L_RANGE_cm         = (1.5, 3.5)

# Points for the output curves
Z_FIRST_cm, Z_MAX_cm = 0.01, 3.5
OUTPUT_FILE        = "thesis/output/wh_fig3_fit_cases.xlsx"

CM_TO_M, KV_PER_CM_TO_V_PER_M = 1e-2, 1e5
UNIT_CHARGE_C      = 1e-9     # fields are evaluated for 1 nC and scaled (see wh_fig3_fit.py)
R_m                = ROD_TIP_RADIUS_cm * CM_TO_M


# =============================================================================
# 2. Field variants, per coulomb of charge, in kV/cm
# =============================================================================
def _r1_typo_integrand(r, theta, z, B, C):
    """E_sp integrand with the paper's printed r1 = sqrt((r cos - z)^2 + (r3 sin)^2), r3 = R^2 / r2."""
    dz = z - r * np.cos(theta)
    r2 = np.hypot(R_m + r * np.cos(theta), r * np.sin(theta))
    r1 = np.hypot(dz, (R_m**2 / r2) * np.sin(theta))
    return 0.0 if r1 == 0 else (r**2 * np.sin(theta) * dz / (r + C) ** B) / r1**3


def _gauss_legendre(z_m, theta_B, B, C, L, nodes):
    """E_sp and E_I,rod (A = 1, V/m up to the 1/(2 eps0) factor) with an n x n Gauss-Legendre rule."""
    x, w = np.polynomial.legendre.leggauss(nodes)
    r, wr = 0.5 * L * (x + 1), 0.5 * L * w
    t, wt = 0.25 * theta_B * (x + 1), 0.25 * theta_B * w
    r, t = np.meshgrid(r, t, indexing="ij")
    weight = np.outer(wr, wt) * r**2 * np.sin(t) / (r + C) ** B
    e_sp, e_rod = [], []
    for z in z_m:
        dz = z - r * np.cos(t)
        e_sp.append(np.sum(weight * dz / np.hypot(dz, r * np.sin(t)) ** 3))
        h = R_m + r * np.cos(t)
        r2 = np.hypot(h, r * np.sin(t))
        s = R_m**2 / r2**2
        dzi = z + R_m - s * h
        r4 = np.hypot(dzi, s * r * np.sin(t))
        e_rod.append(-np.sum(weight * R_m * dzi / (r4**3 * r2)))
    return np.array(e_sp), np.array(e_rod)


def unit_fields_chunk(job):
    """Worker: one chunk of z points. job = (variant, field, z_cm list, theta_deg, B, C_cm, L_cm)."""
    warnings.simplefilter("ignore", IntegrationWarning)
    variant, field, z_cm, theta_deg, B, C_cm, L_cm = job
    theta, C, L = np.radians(theta_deg), C_cm * CM_TO_M, L_cm * CM_TO_M
    z_m = np.asarray(z_cm) * CM_TO_M
    A = calculate_A_from_charge(UNIT_CHARGE_C, B, C, L_cs_m=L, theta_B_rad=theta)
    scale = 1.0 / (KV_PER_CM_TO_V_PER_M * UNIT_CHARGE_C)
    if variant == "coarse":
        e_sp, e_rod = _gauss_legendre(z_m, theta, B, C, L, COARSE_NODES)
        return (e_sp if field == "sp" else e_rod) * A / (2 * EPSILON_0) * scale
    if field == "rod":
        return calculate_e_rod_image(z_m, R_m, L, theta, A, B, C) * scale
    if variant == "typo":
        values = [dblquad(_r1_typo_integrand, 0.0, theta / 2, 0.0, L, args=(z, B, C), epsabs=0, epsrel=1e-6)[0]
                  for z in z_m]
        return np.array(values) * A / (2 * EPSILON_0) * scale
    return calculate_e_sp(z_m, R_m, L, theta, A, B, C) * scale


class FieldEvaluator:
    """Evaluates the unit fields of one case at many z, spreading the points over the CPU cores."""

    def __init__(self, pool, workers):
        self.pool, self.workers = pool, workers

    def fields(self, variant, z_sp, z_rod, theta_deg, B, C_cm, L_cm):
        jobs, slices = [], []
        for field, z in (("sp", z_sp), ("rod", z_rod)):
            for chunk in np.array_split(np.asarray(z), self.workers):
                if len(chunk):
                    slices.append(field)
                    jobs.append((variant, field, list(chunk), theta_deg, B, C_cm, L_cm))
        results = list(self.pool.map(unit_fields_chunk, jobs))
        e_sp = np.concatenate([r for r, f in zip(results, slices) if f == "sp"])
        e_rod = np.concatenate([r for r, f in zip(results, slices) if f == "rod"])
        return e_sp, e_rod


# =============================================================================
# 3. Cases
# =============================================================================
CASES = [
    # name, short label, variant, free parameters, fixed values, grid (per free parameter), start points
    ("Case 1", "r1 typo", "typo", ["theta"], {"B": PAPER_B, "C": PAPER_C_cm, "L": STREAMER_LENGTH_cm},
     {"theta": np.arange(20.0, 161.0, 20.0)}),
    ("Case 2", f"coarse {COARSE_NODES}x{COARSE_NODES} quadrature", "coarse", ["theta", "B", "C"],
     {"L": STREAMER_LENGTH_cm},
     {"theta": np.arange(20.0, 171.0, 10.0), "B": np.arange(1.0, 3.01, 0.25), "C": np.geomspace(0.005, 0.5, 7)}),
    ("Case 3", "paper's B and C", "adaptive", ["theta"], {"B": PAPER_B, "C": PAPER_C_cm, "L": STREAMER_LENGTH_cm},
     {"theta": np.arange(20.0, 171.0, 10.0)}),
    ("Case 4", "C in metres (3.5 cm)", "adaptive", ["theta"], {"B": PAPER_B, "C": 100 * PAPER_C_cm, "L": STREAMER_LENGTH_cm},
     {"theta": np.arange(20.0, 171.0, 10.0)}),
    ("Case 5", "full fit, L_cs = 2.7 cm", "adaptive", ["theta", "B", "C"], {"L": STREAMER_LENGTH_cm},
     {"theta": [130.0, 140.0], "B": [1.4, 1.6], "C": [0.2, 0.3]}),
    ("Case 6", "full fit, free L_cs", "adaptive", ["theta", "B", "C", "L"], {},
     {"theta": [125.0, 135.0], "B": [1.5], "C": [0.2, 0.3], "L": [3.0, 3.5]}),
]
BOUNDS = {"theta": THETA_RANGE_deg, "B": B_RANGE, "C": C_RANGE_cm, "L": L_RANGE_cm}
# Case 5 keeps the bounds of wh_fig3_fit.py (C up to 0.3 cm) so that it is the same fit
CASE_BOUNDS = {"Case 5": {"C": (0.005, 0.3)}, "Case 6": {"C": (0.003, 1.0)}}


def fit_case(case, paper, evaluator):
    name, _label, variant, free, fixed, grid = case
    bounds = {**BOUNDS, **CASE_BOUNDS.get(name, {})}

    def evaluate(values):
        p = {**fixed, **dict(zip(free, values))}
        g_sp, g_rod = evaluator.fields(variant, paper.z_sp, paper.z_rod, p["theta"], p["B"], p["C"], p["L"])
        return paper.fit_charge(g_sp, g_rod), p

    # coarse grid
    axes = [np.asarray(grid[k], dtype=float) for k in free]
    points = np.array(np.meshgrid(*axes, indexing="ij")).reshape(len(free), -1).T
    best_error, best_point = np.inf, points[0]
    for point in points:
        result, _ = evaluate(point)
        if result["error"] < best_error:
            best_error, best_point = result["error"], point

    # local refinement (C searched on a log scale)
    def to_x(point):
        return [np.log10(v) if k == "C" else v for k, v in zip(free, point)]

    def from_x(x):
        return [10**v if k == "C" else v for k, v in zip(free, x)]

    low = to_x([bounds[k][0] for k in free])
    high = to_x([bounds[k][1] for k in free])
    x0 = np.clip(to_x(best_point), low, high)
    solution = least_squares(lambda x: evaluate(from_x(x))[0]["residuals"], x0, bounds=(low, high),
                             x_scale=[{"theta": 10.0, "B": 0.2, "C": 0.2, "L": 0.2}[k] for k in free],
                             diff_step=1e-3, max_nfev=40)
    result, p = evaluate(from_x(solution.x))
    return result, p


def main():
    warnings.simplefilter("ignore", IntegrationWarning)
    paper = PaperData()
    workers = os.cpu_count() or 1
    z_cm = np.concatenate((np.geomspace(Z_FIRST_cm, 0.5, 30, endpoint=False), np.linspace(0.5, Z_MAX_cm, 90)))

    sheets, summary = {}, []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        evaluator = FieldEvaluator(pool, workers)
        for number, case in enumerate(CASES, start=1):
            name, label, variant = case[0], case[1], case[2]
            print(f"Case {number}/{len(CASES)}: {label} ...", flush=True)
            result, p = fit_case(case, paper, evaluator)
            g_sp, g_rod = evaluator.fields(variant, z_cm, z_cm, p["theta"], p["B"], p["C"], p["L"])
            E_sp, E_rod = result["Q"] * g_sp, result["Q"] * g_rod
            peak = float(z_cm[z_cm >= 1.0][np.argmax(E_sp[z_cm >= 1.0])])
            print(f"          theta_B = {p['theta']:.1f} deg, B = {p['B']:.3f}, C = {p['C']:.4f} cm, "
                  f"L = {p['L']:.2f} cm, Q = {result['Q'] * 1e9:.2f} nC, error = {result['error']:.3f}", flush=True)
            summary.append((number, label, p, result, peak))

            longest = max(len(paper.esp.x), len(paper.rod.x), len(z_cm))

            def pad(values, longest=longest):
                values = list(values)
                return values + [None] * (longest - len(values))

            sheets[name] = {
                "z [cm]": pad(z_cm),
                "E_sp [kV/cm]": pad(E_sp),
                "E_I,rod [kV/cm]": pad(E_rod),
                "paper z (E_sp) [cm]": pad(paper.esp.x),
                "E_sp (paper) [kV/cm]": pad(paper.esp.y),
                "paper z (E_I,rod) [cm]": pad(paper.rod.x),
                "E_I,rod (paper) [kV/cm]": pad(paper.rod.y),
            }

    summary_sheet = {
        "case": [s[0] for s in summary],
        "assumption": [s[1] for s in summary],
        "theta_B [deg]": [s[2]["theta"] for s in summary],
        "B [-]": [s[2]["B"] for s in summary],
        "C [cm]": [s[2]["C"] for s in summary],
        "L_cs [cm]": [s[2]["L"] for s in summary],
        "Q_cs [nC]": [s[3]["Q"] * 1e9 for s in summary],
        "weighted error [-]": [s[3]["error"] for s in summary],
        "RMS E_sp [kV/cm]": [s[3]["rms_sp"] for s in summary],
        "RMS E_I,rod [kV/cm]": [s[3]["rms_rod"] for s in summary],
        "E_sp maximum at z [cm]": [s[4] for s in summary],
        "paper E_sp maximum at z [cm]": [float(paper.esp.x[np.argmax(paper.esp.y)])] * len(summary),
        "generated on": [datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")] * len(summary),
    }
    save_to_excel(OUTPUT_FILE, {"Summary": summary_sheet, **sheets})
    add_charts(OUTPUT_FILE, summary)
    print(f"Done. Saved to {OUTPUT_FILE}")


# =============================================================================
# 4. Charts: ours solid, paper dashed, same colour per field
# =============================================================================
COLOURS = {"sp": "1F4E9E", "rod": "C0392B"}


def add_charts(path, summary):
    workbook = load_workbook(path)
    for number, label, _p, result, _peak in summary:
        ws = cast(Worksheet, workbook[f"Case {number}"])
        rows = ws.max_row
        chart = ScatterChart()
        chart.title = f"Case {number}: {label} (error {result['error']:.2f})"
        chart.style = 13
        chart.x_axis.title = "Distance z from the rod tip [cm]"
        chart.y_axis.title = "Electric field [kV/cm]"
        chart.x_axis.scaling.min, chart.x_axis.scaling.max = 0, Z_MAX_cm
        chart.y_axis.scaling.min, chart.y_axis.scaling.max = -60, 15
        chart.x_axis.axPos = "b"
        chart.x_axis.delete = False
        chart.y_axis.delete = False
        chart.legend = Legend(legendPos="b")
        chart.width, chart.height = 22, 13
        for x_col, y_col, colour, dashed in ((1, 2, COLOURS["sp"], False), (4, 5, COLOURS["sp"], True),
                                             (1, 3, COLOURS["rod"], False), (6, 7, COLOURS["rod"], True)):
            x = Reference(ws, min_col=x_col, min_row=2, max_row=rows)
            y = Reference(ws, min_col=y_col, min_row=1, max_row=rows)
            series = SeriesFactory(values=y, xvalues=x, title_from_data=True)
            series.marker.symbol = "none"
            series.smooth = False
            series.graphicalProperties.line.solidFill = colour
            series.graphicalProperties.line.width = 22225 if not dashed else 15875
            if dashed:
                series.graphicalProperties.line.dashStyle = "dash"
            chart.series.append(series)
        ws.add_chart(chart, "I2")
    workbook.save(path)


if __name__ == "__main__":
    main()
