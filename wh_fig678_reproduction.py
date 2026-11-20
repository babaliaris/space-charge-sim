"""
Wang & Haiting - Figures 6, 7 and 8 reproduction: first and second corona streamer
against the impulse front time
==================================================================================

What this script does
---------------------
Figures 6, 7 and 8 of the paper show, for the first and the second corona streamer,
how the inception voltage (Fig. 6), the streamer length (Fig. 7) and the streamer
charge (Fig. 8) change with the time to crest of a switching impulse (15 to 600 us,
gaps of 40 cm and 80 cm). The whole framework runs in solver/simulation.py:

1. Model inputs: the paper's B and C, the cone angle theta_B (recovered from the paper's
   Fig. 3 streamer, see wh_fig3_reproduction.py) and the rate-dependent time lag
   (threshold field E_0 and k, n, fitted by wh_time_lag_fit.py - run that first).
2. For every gap and front time builds the impulse V(t) (crest from the Gallet formula,
   U50 = 3400 / (1 + 8/d) kV, tail half-value 2500 us; neither is given in the paper).
3. Simulates the impulse front: a burst happens when the tip field reaches
   E_0 + k (dE_tip/dt)^n (dE_tip/dt taken when it first reaches E_0); its length is the
   largest root of the head condition, its charge comes from Gauss's law over its head
   minus the older charge inside its cone; all clouds drift between bursts.
4. Compares with the paper's curves, read from the scanned figures (input/wh_fig678_paper.xlsx):
   NRMSE = RMS(this work - paper) / RMS(paper) against the measured values.
5. Saves everything to an Excel workbook:
       sheets "Fig6", "Fig7", "Fig8a", "Fig8b"   our streamers 1 and 2 (NRMSE in the header)
                                         next to the paper's calculated and measured curves (+ chart)
       sheet "Comparison"               NRMSE, largest difference and change over the fronts
       sheet "Values"                   every point: this work, paper (measured), difference [%]
       sheet "Bursts"                   one row per burst with every detail
       sheet "Parameters"               every input

Units
-----
Inputs and outputs use high-voltage engineering units (cm, kV, kV/cm, us, nC).
The solver works in SI units. z is measured from the rod tip apex, t from the start of the impulse.

How to run
----------
    python wh_time_lag_fit.py         (once)
    python wh_fig678_reproduction.py  (about 2 minutes, all CPU cores)
"""

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
from scipy.integrate import IntegrationWarning

from excel_export import save_to_excel
from solver.simulation import GapModel, simulate
from solver.utilities import double_exponential_parameters, impulse_voltage

# =============================================================================
# 1. INPUTS  (engineering units - edit these)
# =============================================================================
ROD_TIP_RADIUS_cm          = 0.1      # R
ION_MOBILITY_cm2_per_kV_us = 1.36e-3  # mu+ (given in the paper)
STABILITY_FIELD_kV_per_cm  = 5.0      # E_c
DENSITY_EXPONENT_B         = 1.5      # B  } the paper's "usual" values
DENSITY_OFFSET_C_cm        = 0.035    # C  }
CONE_ANGLE_deg             = 93.39    # theta_B: from the paper's Fig. 3 streamer (wh_fig3_reproduction.py)
SUBTRACT_ENCLOSED          = True     # Gauss charge of a new cloud minus the older charge inside its cone
TIME_LAG_FILE              = "output/wh_time_lag_fit.xlsx"   # E_0, k, n (wh_time_lag_fit.py)

GAPS_cm                    = [40.0, 80.0]
ROD_LENGTHS_cm             = {40.0: 200.0, 80.0: 400.0}       # L_rod per gap (CSM); not given, 5 * D
FRONT_TIMES_us             = [15, 20, 30, 50, 75, 100, 150, 200, 300, 400, 500, 600]
TIME_TO_HALF_VALUE_us      = 2500.0   # tail: not given in the paper
BURSTS_PER_IMPULSE         = 2

PAPER_FILE                 = "input/wh_fig678_paper.xlsx"
OUTPUT_FILE                = "output/wh_fig678_reproduction.xlsx"

CM_TO_M, KV_TO_V, KV_PER_CM_TO_V_PER_M, US_TO_S, MOBILITY_TO_SI, C_TO_NC = 1e-2, 1e3, 1e5, 1e-6, 1e-1, 1e9

FIGURES = {  # sheet: (quantity, gap, unit, title, y label)
    "Fig6": ("V", 40.0, "kV", "Inception voltage of the first and second corona streamer (D = 40 cm)", "Inception voltage [kV]"),
    "Fig7": ("L", 40.0, "cm", "Length of the first and second corona streamer (D = 40 cm)", "Streamer length [cm]"),
    "Fig8a": ("Q", 40.0, "nC", "Charge of the first and second corona streamer (D = 40 cm)", "Streamer charge [nC]"),
    "Fig8b": ("Q", 80.0, "nC", "Charge of the first and second corona streamer (D = 80 cm)", "Streamer charge [nC]"),
}


def gallet_crest_kV(gap_cm):
    """Gallet formula: 50 % breakdown voltage of a rod-plane gap, U50 = 3400 / (1 + 8/d) kV, d in m."""
    return 3400.0 / (1.0 + 8.0 / (gap_cm / 100.0))


def read_time_lag(path):
    """E_0 [kV/cm], k_SI and n of the rate-dependent time lag (Parameters sheet of wh_time_lag_fit.py)."""
    try:
        sheet = load_workbook(path, data_only=True)["Parameters"]
    except FileNotFoundError:
        raise SystemExit(f"{path} not found: run wh_time_lag_fit.py first.") from None
    values = {row[0]: row[1] for row in sheet.iter_rows(min_row=2, values_only=True)}
    keys = ("Threshold field at the tip E0 = V0 e_ex(0)",
            "Field-form coefficient k_SI (E_req = E0 + k_SI (dE/dt)^n, SI)", "n")
    return tuple(float(str(values[key])) for key in keys)


def run_front(job):
    """Simulate one gap and front time; returns (gap, front, list of burst dicts)."""
    gap_cm, front_us, E0, k_SI, n = job
    warnings.simplefilter("ignore", IntegrationWarning)
    model = GapModel(ROD_TIP_RADIUS_cm * CM_TO_M, gap_cm * CM_TO_M, np.radians(CONE_ANGLE_deg),
                     STABILITY_FIELD_kV_per_cm * KV_PER_CM_TO_V_PER_M, E0, DENSITY_EXPONENT_B,
                     DENSITY_OFFSET_C_cm * CM_TO_M, ION_MOBILITY_cm2_per_kV_us * MOBILITY_TO_SI,
                     rod_length=ROD_LENGTHS_cm[gap_cm] * CM_TO_M, subtract_enclosed=SUBTRACT_ENCLOSED,
                     overvoltage_k=k_SI, overvoltage_n=n)
    alpha, beta, k = double_exponential_parameters(front_us * US_TO_S, TIME_TO_HALF_VALUE_us * US_TO_S)
    crest = gallet_crest_kV(gap_cm) * KV_TO_V
    result = simulate(model, lambda t: impulse_voltage(t, crest, alpha, beta, k), t_end=front_us * US_TO_S,
                      max_bursts=BURSTS_PER_IMPULSE)
    first = result.clouds[0] if result.clouds else None
    bursts = [{"number": c.number, "t_us": c.t_birth / US_TO_S, "V_kV": c.V_birth / KV_TO_V, "L_cm": c.L / CM_TO_M,
               "Q_nC": c.Q * C_TO_NC, "dip_cm": c.dip_width / CM_TO_M,
               "drift1_cm": result.z_drift(first, c.t_birth) / CM_TO_M if first else 0.0} for c in result.clouds]
    return gap_cm, front_us, bursts


def nrmse(ours, paper):
    pairs = [(o, p) for o, p in zip(ours, paper) if o is not None and p is not None]
    if not pairs:
        return None
    o, p = np.array(pairs).T
    return float(np.sqrt(np.mean((o - p) ** 2)) / np.sqrt(np.mean(p**2)) * 100)


def main():
    warnings.simplefilter("ignore", IntegrationWarning)
    E0_kV_cm, k_SI, n = read_time_lag(TIME_LAG_FILE)
    E0 = E0_kV_cm * KV_PER_CM_TO_V_PER_M
    print(f"Step 1/3: model: B = {DENSITY_EXPONENT_B}, C = {DENSITY_OFFSET_C_cm} cm, theta_B = {CONE_ANGLE_deg} deg, "
          f"E_0 = {E0_kV_cm:.2f} kV/cm, k_SI = {k_SI:.4g}, n = {n:.4f}")

    print("Step 2/3: simulating the impulse fronts ...")
    jobs = [(g, f, E0, k_SI, n) for g in GAPS_cm for f in FRONT_TIMES_us]
    with ProcessPoolExecutor() as pool:
        runs = {(g, f): b for g, f, b in pool.map(run_front, jobs)}
    for (g, f), b in runs.items():
        print(f"          D = {g:4.0f} cm, front {f:3d} us: "
              + ", ".join(f"V{x['number']} = {x['V_kV']:.1f} kV, L{x['number']} = {x['L_cm']:.2f} cm" for x in b))

    print("Step 3/3: saving to Excel ...")
    paper = load_workbook(PAPER_FILE, data_only=True)
    key_map = {"V": "V_kV", "L": "L_cm", "Q": "Q_nC"}
    sheets, comparison, values = {}, [], []
    for name, (quantity, gap, unit, _title, _ylabel) in FIGURES.items():
        rows = list(paper[name].iter_rows(values_only=True))
        cols = {h: dict(zip([r[0] for r in rows[1:]], [r[i] for r in rows[1:]])) for i, h in enumerate(rows[0])}
        ours = {s: [next((b[key_map[quantity]] for b in runs[(gap, f)] if b["number"] == s), None) for f in FRONT_TIMES_us]
                for s in (1, 2)}
        sheet: dict[str, list] = {"time to crest [us]": list(FRONT_TIMES_us)}
        for s in (1, 2):
            measured = [cols[f"streamer {s} experimental [{unit}]"].get(f) for f in FRONT_TIMES_us]
            e = nrmse(ours[s], measured)
            sheet[f"streamer {s} (this work, RMS {e:.0f} %) [{unit}]"] = ours[s]
        for s in (1, 2):
            for kind, label in (("calculated", "calculated"), ("experimental", "measured")):
                sheet[f"streamer {s}, paper {label} [{unit}]"] = [cols[f"streamer {s} {kind} [{unit}]"].get(f) for f in FRONT_TIMES_us]
        sheets[name] = sheet
        for s in (1, 2):
            theirs = sheet[f"streamer {s}, paper measured [{unit}]"]
            pairs = [(f, o, p) for f, o, p in zip(FRONT_TIMES_us, ours[s], theirs) if o is not None and p is not None]
            diffs = [(o - p) / p * 100 for _, o, p in pairs]
            change_ours = (pairs[-1][1] - pairs[0][1]) / pairs[0][1] * 100
            change_paper = (pairs[-1][2] - pairs[0][2]) / pairs[0][2] * 100
            comparison.append((name, gap, s, unit, nrmse(ours[s], theirs), diffs[int(np.argmax(np.abs(diffs)))],
                               change_ours, change_paper, f"{pairs[0][0]}-{pairs[-1][0]}"))
            values += [(name, s, f, unit, o, p, (o - p) / p * 100) for f, o, p in pairs]
    sheets["Comparison"] = {
        "figure": [c[0] for c in comparison], "gap [cm]": [c[1] for c in comparison], "streamer": [c[2] for c in comparison],
        "unit": [c[3] for c in comparison], "NRMSE vs measured [%]": [c[4] for c in comparison],
        "largest difference [%]": [c[5] for c in comparison], "change over the fronts, this work [%]": [c[6] for c in comparison],
        "change over the fronts, paper [%]": [c[7] for c in comparison], "fronts compared [us]": [c[8] for c in comparison]}
    sheets["Values"] = {
        "figure": [v[0] for v in values], "streamer": [v[1] for v in values], "time to crest [us]": [v[2] for v in values],
        "unit": [v[3] for v in values], "this work": [v[4] for v in values], "paper (measured)": [v[5] for v in values],
        "difference [%]": [v[6] for v in values]}
    all_bursts = [(g, f, b) for (g, f), bs in runs.items() for b in bs]
    sheets["Bursts"] = {
        "gap D [cm]": [x[0] for x in all_bursts], "time to crest [us]": [x[1] for x in all_bursts],
        "impulse crest (Gallet) [kV]": [gallet_crest_kV(x[0]) for x in all_bursts],
        "burst number k": [x[2]["number"] for x in all_bursts], "burst instant t_k [us]": [x[2]["t_us"] for x in all_bursts],
        "inception voltage V(t_k) [kV]": [x[2]["V_kV"] for x in all_bursts],
        "streamer length L_k [cm]": [x[2]["L_cm"] for x in all_bursts], "streamer charge Q_k [nC]": [x[2]["Q_nC"] for x in all_bursts],
        "drift of cloud 1 at t_k [cm]": [x[2]["drift1_cm"] for x in all_bursts],
        "low-field dip crossed [cm]": [x[2]["dip_cm"] for x in all_bursts]}
    parameters = [
        ("Rod tip radius R", ROD_TIP_RADIUS_cm, "cm"), ("Stability field E_c", STABILITY_FIELD_kV_per_cm, "kV/cm"),
        ("Density exponent B (paper)", DENSITY_EXPONENT_B, "-"), ("Density offset C (paper)", DENSITY_OFFSET_C_cm, "cm"),
        ("Cone angle theta_B", CONE_ANGLE_deg, "deg"), ("Ion mobility mu+", ION_MOBILITY_cm2_per_kV_us, "cm^2/(kV*us)"),
        ("Charge of later bursts", "Gauss minus the older charge inside the cone" if SUBTRACT_ENCLOSED else "Gauss", ""),
        ("Streamer length", "largest root of the head condition", ""),
        ("Time lag: threshold field E_0", E0_kV_cm, "kV/cm"), ("Time lag: k_SI", k_SI, "SI"), ("Time lag: n", n, "-"),
        ("Gaps", ", ".join(f"{g:g}" for g in GAPS_cm), "cm"), ("Times to crest", ", ".join(map(str, FRONT_TIMES_us)), "us"),
        ("Time to half value (assumed)", TIME_TO_HALF_VALUE_us, "us"), ("Crest voltage rule", "Gallet U50 = 3400/(1+8/d), d in m", ""),
        ("Generated on", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"), "")]
    sheets["Parameters"] = {"Parameter": [p[0] for p in parameters], "Value": [p[1] for p in parameters],
                            "Unit": [p[2] for p in parameters]}
    save_to_excel(OUTPUT_FILE, sheets)
    add_charts(OUTPUT_FILE, {name: (f[3], f[4]) for name, f in FIGURES.items()})
    print(f"Done. Saved to {OUTPUT_FILE}")


def add_charts(path, titles):
    """One chart per figure sheet: this work solid with circles, the paper's calculated curve dashed,
    its experimental points as triangles; blue = first streamer, red = second; log time axis."""
    workbook = load_workbook(path)
    colours = {1: "1F4E79", 2: "C00000"}
    for name, (title, y_label) in titles.items():
        ws = cast(Worksheet, workbook[name])
        n = ws.max_row
        chart = ScatterChart()
        chart.title = title
        chart.x_axis.title = "Time to crest [us]"
        chart.y_axis.title = y_label
        chart.x_axis.axPos = "b"
        chart.x_axis.scaling.logBase = 10
        chart.x_axis.scaling.min, chart.x_axis.scaling.max = 10, 700
        chart.y_axis.scaling.min = 0
        chart.x_axis.delete = False
        chart.y_axis.delete = False
        chart.legend = Legend(legendPos="b")
        chart.width, chart.height = 22, 13
        headers = [cell.value for cell in ws[1]]
        for column, header in enumerate(headers[1:], start=2):
            number = 1 if "streamer 1" in str(header) else 2
            series = SeriesFactory(values=Reference(ws, min_col=column, min_row=1, max_row=n),
                                   xvalues=Reference(ws, min_col=1, min_row=2, max_row=n), title_from_data=True)
            series.smooth = False
            line = series.graphicalProperties.line
            if "this work" in str(header):
                series.marker.symbol = "circle"
                series.marker.size = 5
                line.solidFill = colours[number]
                line.width = 19050
            elif "calculated" in str(header):
                series.marker.symbol = "none"
                line.solidFill = colours[number]
                line.width = 12700
                line.dashStyle = "dash"
            else:
                series.marker.symbol = "triangle"
                series.marker.size = 6
                series.marker.graphicalProperties.solidFill = colours[number]
                series.marker.graphicalProperties.line.solidFill = colours[number]
                line.noFill = True
            chart.series.append(series)
        ws.add_chart(chart, "J2")
    workbook.save(path)


if __name__ == "__main__":
    main()
