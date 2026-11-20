"""
Time lag of the corona inception: fit of V0, k and n (data + chart, for Excel)
==============================================================================

What this script does
---------------------
Without a time lag the first corona burst would start at the same voltage on every
impulse. The paper's measured first-streamer inception voltages (Fig. 6, 40 cm gap) fall
from 38.5 kV (15 us front) to 15.2 kV (600 us): the faster the voltage rises, the more it
overshoots before a streamer starts. This is described with a rate-dependent overvoltage:

    V_1 = V_0 + k (dV/dt)^n          dV/dt taken when V(t) first reaches V_0

V_0 is the static inception voltage (no streamer can start below it). For a voltage that
rises linearly near inception this is what the disruptive-effect / volt-time-area
criterion of Kind (1957) gives, with the exponent of the integral m = 1/n - 1
(the equal-area criterion, m = 1, gives n = 1/2); see Darveniza (1988).

1. Reads the measured first-streamer voltages from thesis/input/wh_fig678_paper.xlsx.
2. For trial (V_0, k, n): for every front builds the impulse (Gallet crest, 2500 us tail),
   finds the instant V(t) = V_0 and the rate dV/dt there, and predicts V_1.
3. Least squares on the relative errors gives V_0, k, n.
4. Writes the law in field form for the simulation (the tip field must reach
   E_0 + k_SI (dE_tip/dt)^n, E_0 = V_0 e_ex(0)), which holds for any gap, and checks it on
   the paper's Fig. 3 impulse (320 kV, 130 us front, 80 cm gap; paper: 27.5 kV).
5. Saves thesis/output/wh_time_lag_fit.xlsx: sheet "Fit" (+ chart, log time axis) and "Parameters".

Units: kV, us, kV/cm in the workbook; SI inside.

How to run
----------
    python -m thesis.wh_time_lag_fit        (a few seconds)
"""

from datetime import datetime
from typing import cast

import numpy as np
from openpyxl import load_workbook
from openpyxl.chart import Reference, ScatterChart
from openpyxl.chart.legend import Legend
from openpyxl.chart.series_factory import SeriesFactory
from openpyxl.worksheet.worksheet import Worksheet
from scipy.optimize import brentq, least_squares

from thesis.excel_export import save_to_excel
from solver.applied_field import calculate_applied_field
from solver.utilities import double_exponential_parameters, impulse_voltage

# =============================================================================
# 1. INPUTS  (engineering units)
# =============================================================================
PAPER_FILE            = "thesis/input/wh_fig678_paper.xlsx"   # Figs. 6-8 of the paper, read from the scan
PAPER_COLUMN          = "streamer 1 experimental [kV]" # measured first-streamer voltage (Fig. 6, 40 cm)
GAP_cm                = 40.0      # gap of Fig. 6
ROD_TIP_RADIUS_cm     = 0.1
ROD_LENGTHS_cm        = {40.0: 200.0, 80.0: 400.0}     # L_rod per gap (CSM), assumed 5 * D
TIME_TO_HALF_VALUE_us = 2500.0    # tail of the impulses (not given in the paper)
CHECK_IMPULSE         = (320.0, 130.0, 80.0)           # crest [kV], front [us], gap [cm] of the paper's Fig. 3 case
CHECK_PAPER_kV        = 27.5      # first-streamer inception voltage the paper gives for it
START                 = (12.0, 3.0, 0.6)               # initial guess V0 [kV], k, n
OUTPUT_FILE           = "thesis/output/wh_time_lag_fit.xlsx"


def gallet_crest_kV(gap_cm):
    """Gallet formula: U50 = 3400 / (1 + 8/d) kV, d in m (the crest used for Figs. 6-8)."""
    return 3400.0 / (1.0 + 8.0 / (gap_cm / 100.0))


def tip_field_per_volt(gap_cm):
    """Applied field per volt at the tip apex e_ex(0) [1/m]."""
    return float(calculate_applied_field(ROD_TIP_RADIUS_cm * 1e-2, gap_cm * 1e-2, 1.0, 0.0,
                                         rod_length=ROD_LENGTHS_cm[gap_cm] * 1e-2))


def rate_at(V0_kV, crest_kV, front_us):
    """dV/dt [kV/us] of the impulse at the instant it first reaches V0."""
    a, b, k = double_exponential_parameters(front_us * 1e-6, TIME_TO_HALF_VALUE_us * 1e-6)

    def V(t):
        return impulse_voltage(t, crest_kV, a, b, k)

    t0 = cast(float, brentq(lambda t: V(t) - V0_kV, 0.0, front_us * 1e-6))
    h = 1e-3 * t0
    return (V(t0 + h) - V(t0 - h)) / (2 * h) * 1e-6


def main():
    # 1-2. measured data and model
    sheet = load_workbook(PAPER_FILE, data_only=True)["Fig6"]
    rows = list(sheet.iter_rows(values_only=True))
    col = rows[0].index(PAPER_COLUMN)
    data = [(float(str(r[0])), float(str(r[col]))) for r in rows[1:] if r[col] is not None]
    fronts = np.array([d[0] for d in data])
    measured = np.array([d[1] for d in data])
    crest = gallet_crest_kV(GAP_cm)

    def model(x):
        return np.array([x[0] + x[1] * rate_at(x[0], crest, f) ** x[2] for f in fronts])

    # 3. least squares on the relative error
    print("Step 1/3: fitting V0, k, n ...")
    sol = least_squares(lambda x: model(x) / measured - 1.0, START,
                        bounds=([1.0, 0.0, 0.05], [measured.min() - 1e-3, 1e3, 3.0]))
    V0, k, n = (float(v) for v in sol.x)
    fitted = model(sol.x)
    rates = [rate_at(V0, crest, f) for f in fronts]
    print(f"          V0 = {V0:.3f} kV, k = {k:.4f} kV/(kV/us)^n, n = {n:.4f}  (m = 1/n - 1 = {1 / n - 1:.2f})")

    # 4. field form and check on the Fig. 3 impulse
    print("Step 2/3: field form and check on the paper's Fig. 3 impulse ...")
    e_fit = tip_field_per_volt(GAP_cm)
    k_SI = e_fit * 1e3 * k / (e_fit * 1e9) ** n            # E_req = E0 + k_SI (dE/dt)^n, SI
    E0 = V0 * 1e3 * e_fit                                  # V/m
    crest_c, front_c, gap_c = CHECK_IMPULSE
    e_c = tip_field_per_volt(gap_c)
    V0_c = E0 / e_c / 1e3
    rate_E = e_c * rate_at(V0_c, crest_c, front_c) * 1e9
    V1_check = V0_c + k_SI * rate_E**n / e_c / 1e3
    print(f"          E0 = {E0 / 1e5:.2f} kV/cm; Fig. 3 impulse -> V1 = {V1_check:.2f} kV (paper {CHECK_PAPER_kV} kV)")

    # 5. Excel
    print("Step 3/3: saving to Excel ...")
    fit_sheet = {
        "time to crest [us]": list(fronts),
        "dV/dt when V = V0 [kV/us]": rates,
        "V_1 measured (paper) [kV]": list(measured),
        "V_1 fit [kV]": list(fitted),
        "difference [%]": list((fitted - measured) / measured * 100),
    }
    parameters = [
        ("INPUTS", "", ""),
        ("Paper data", f"{PAPER_FILE}, Fig6, {PAPER_COLUMN}", ""),
        ("Gap of the data", GAP_cm, "cm"),
        ("Impulse crest (Gallet)", crest, "kV"),
        ("Time to half value", TIME_TO_HALF_VALUE_us, "us"),
        ("Law", "V1 = V0 + k (dV/dt)^n", ""),
        ("RESULTS", "", ""),
        ("V0 (40 cm gap)", V0, "kV"),
        ("k", k, "kV/(kV/us)^n"),
        ("n", n, "-"),
        ("Disruptive-effect exponent m = 1/n - 1", 1 / n - 1, "-"),
        ("Threshold field at the tip E0 = V0 e_ex(0)", E0 / 1e5, "kV/cm"),
        ("Field-form coefficient k_SI (E_req = E0 + k_SI (dE/dt)^n, SI)", k_SI, "SI"),
        ("V0 in the 80 cm gap (same E0)", E0 / tip_field_per_volt(80.0) / 1e3, "kV"),
        ("RMS of the relative fit error", float(np.sqrt(np.mean(((fitted - measured) / measured) ** 2)) * 100), "%"),
        ("Largest fit error", float(np.max(np.abs(fitted - measured) / measured) * 100), "%"),
        ("CHECK", "", ""),
        ("Fig. 3 impulse: crest / front / gap", f"{crest_c:g} kV / {front_c:g} us / {gap_c:g} cm", ""),
        ("Predicted first-streamer inception voltage", V1_check, "kV"),
        ("Paper", CHECK_PAPER_kV, "kV"),
        ("Difference", (V1_check - CHECK_PAPER_kV) / CHECK_PAPER_kV * 100, "%"),
        ("Generated on", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"), ""),
    ]
    save_to_excel(OUTPUT_FILE, {"Fit": fit_sheet, "Parameters": {
        "Parameter": [p[0] for p in parameters], "Value": [p[1] for p in parameters], "Unit": [p[2] for p in parameters]}})
    add_chart(OUTPUT_FILE, len(fronts))
    print(f"Done. Saved to {OUTPUT_FILE}")


def add_chart(path, n_rows):
    workbook = load_workbook(path)
    ws = cast(Worksheet, workbook["Fit"])
    chart = ScatterChart()
    chart.title = "First-streamer inception voltage: measured and rate-dependent time-lag law"
    chart.x_axis.title = "Time to crest [us]"
    chart.y_axis.title = "Inception voltage [kV]"
    chart.x_axis.axPos = "b"
    chart.x_axis.scaling.logBase = 10
    chart.x_axis.scaling.min, chart.x_axis.scaling.max = 10, 700
    chart.y_axis.scaling.min = 0
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    chart.legend = Legend(legendPos="b")
    chart.width, chart.height = 22, 13
    for column, measured in ((3, True), (4, False)):
        series = SeriesFactory(values=Reference(ws, min_col=column, min_row=1, max_row=n_rows + 1),
                               xvalues=Reference(ws, min_col=1, min_row=2, max_row=n_rows + 1), title_from_data=True)
        series.smooth = False
        if measured:
            series.marker.symbol = "triangle"
            series.marker.size = 6
            series.marker.graphicalProperties.solidFill = "1F4E79"
            series.marker.graphicalProperties.line.solidFill = "1F4E79"
            series.graphicalProperties.line.noFill = True
        else:
            series.marker.symbol = "none"
            series.graphicalProperties.line.solidFill = "1F4E79"
            series.graphicalProperties.line.width = 19050
        chart.series.append(series)
    ws.add_chart(chart, "H2")
    workbook.save(path)


if __name__ == "__main__":
    main()
