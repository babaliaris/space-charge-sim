"""
Trial runs of the Gauss-charge model (B, C calibrated once) compared with the paper
==================================================================================

Writes into trials/<name>/:
    fig4.xlsx                     Figure 4: drift of the calibrated first-streamer cloud by 0.07 cm
                                  (your Fig. 4 charts, with the paper's digitized curves)
    fig678_no_time_lag.xlsx       Figures 6-8, one inception voltage for every front (option A)
    fig678_measured_v1.xlsx       Figures 6-8, first-streamer inception voltage of every front taken
                                  from the paper's measured curve (Fig. 6, 40 cm)
    plots/*.pdf, png/*.png        the charts as they would appear in the thesis

Error measure: normalized RMS error, NRMSE = RMS(this work - paper) / RMS(paper) * 100 %, over the
points where both curves exist. It is written into every legend entry of this work and into the
"Comparison" sheets; the "Values" sheets list the point-by-point values and differences in %.

Run from the repo root (each case in its own folder trials/<name>/):
    python trials/make_trials.py --name paper_BC_theta90 --B 1.5 --C 0.035 --theta 90
    python trials/make_trials.py --name calibrated              (B, C, theta_B from output/wh_calibration.xlsx)
"""

import subprocess
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import cast

import numpy as np
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from scipy.integrate import IntegrationWarning

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from excel_export import save_to_excel
from solver.applied_field import calculate_applied_field
from solver.calibration import (
    CalibrationProblem,
    first_streamer_length,
    gauss_amplitude,
    gauss_charge,
)
from solver.drift import simulate_drift
from solver.fields import calculate_e_plane_image, calculate_e_rod_image, calculate_e_sp
from solver.simulation import GapModel, simulate
from solver.utilities import (
    double_exponential_parameters,
    impulse_voltage,
)
from wh_fig678_reproduction import add_charts, gallet_crest_kV

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "trials"
FRONTS = [15, 20, 30, 50, 75, 100, 150, 200, 300, 400, 500, 600]
ROD_LENGTH = {40.0: 2.0, 80.0: 4.0}          # m (5 * D)
V1_MEASURED_40 = dict(zip(FRONTS, [38.5, 36.0, 32.4, 27.9, 25.1, 23.6, 21.1, 19.2, 18.9, 17.8, 16.8, 15.2]))  # kV, Fig. 6
FIGURES = {  # sheet: (quantity key, gap, unit, title, y label)
    "Fig6": ("V", 40.0, "kV", "Inception voltage of the first and second corona streamer (D = 40 cm)", "Inception voltage (kV)"),
    "Fig7": ("L", 40.0, "cm", "Length of the first and second corona streamer (D = 40 cm)", "Streamer length (cm)"),
    "Fig8a": ("Q", 40.0, "nC", "Charge of the first and second corona streamer (D = 40 cm)", "Streamer charge (nC)"),
    "Fig8b": ("Q", 80.0, "nC", "Charge of the first and second corona streamer (D = 80 cm)", "Streamer charge (nC)"),
}


def read_calibration(path):
    """B, C [cm], theta_B [deg] and E_c [kV/cm] from the Parameters sheet of wh_calibration.py."""
    sheet = load_workbook(path, data_only=True)["Parameters"]
    values = {row[0]: row[1] for row in sheet.iter_rows(min_row=2, values_only=True)}
    return tuple(float(str(values[key])) for key in ("B", "C", "Cone angle theta_B", "Stability field E_c"))


def nrmse(ours, paper):
    pairs = [(o, p) for o, p in zip(ours, paper) if o is not None and p is not None]
    if not pairs:
        return None
    o, p = np.array(pairs).T
    return float(np.sqrt(np.mean((o - p) ** 2)) / np.sqrt(np.mean(p**2)) * 100)


# =============================================================================
# Figures 6-8
# =============================================================================
def tip_field_per_volt(gap_cm):
    return float(calculate_applied_field(1e-3, gap_cm * 1e-2, 1.0, 0.0, rod_length=ROD_LENGTH[gap_cm]))


def run_front(job):
    """One gap and front: (gap, front, [(V, L, Q) of bursts 1 and 2]).

    inception: ("fixed", None)          one inception field (27.5 kV in the 80 cm gap), no time lag
               ("measured", V1_kV)      the measured first-streamer voltage of the 40 cm gap as threshold
               ("lag", (V0_kV, tau))    threshold V0 (40 cm gap) and time lag tau [s]
               ("rate", (V0_kV, k_SI, n)) threshold V0 (40 cm gap); burst when the tip field reaches
                                        E0 + k_SI (dE_tip/dt)^n
    """
    gap_cm, front, inception, B, C_m, theta_B, E_c, subtract = job
    warnings.simplefilter("ignore", IntegrationWarning)
    R, D = 1e-3, gap_cm * 1e-2
    kind, value = inception
    lag, k_ov, n_ov = 0.0, 0.0, 1.0
    if kind == "fixed":
        E_inc = 27.5e3 * tip_field_per_volt(80.0)
    elif kind == "measured":
        E_inc = value * 1e3 * tip_field_per_volt(40.0)
    elif kind == "lag":
        E_inc, lag = value[0] * 1e3 * tip_field_per_volt(40.0), value[1]
    else:
        E_inc, k_ov, n_ov = value[0] * 1e3 * tip_field_per_volt(40.0), value[1], value[2]
    model = GapModel(R, D, theta_B, E_c, E_inc, B, C_m, 1.36e-4, rod_length=ROD_LENGTH[gap_cm],
                     subtract_enclosed=subtract, time_lag=lag, overvoltage_k=k_ov, overvoltage_n=n_ov)
    a, b, k = double_exponential_parameters(front * 1e-6, 2500e-6)
    crest = gallet_crest_kV(gap_cm) * 1e3
    result = simulate(model, lambda t: impulse_voltage(t, crest, a, b, k), t_end=front * 1e-6, max_bursts=2)
    return gap_cm, front, [(c.V_birth / 1e3, c.L * 100, c.Q * 1e9) for c in result.clouds]


def fit_time_lag():
    """Fit the threshold V0 (40 cm gap) and the time lag tau to the paper's measured first-streamer voltages.

    Without space charge the first burst happens tau after V(t) reaches V0, so V1 = V(t(V0) + tau).
    Returns V0 [kV], tau [s], the table of fitted values and the prediction for the Fig. 3 impulse.
    """
    from scipy.optimize import brentq, least_squares

    def first_inception(V0_kV, tau, crest_kV, front_us):
        a, b, k = double_exponential_parameters(front_us * 1e-6, 2500e-6)
        def V(t):
            return impulse_voltage(t, crest_kV, a, b, k)
        t0 = brentq(lambda t: V(t) - V0_kV, 0.0, front_us * 1e-6)
        return V(t0 + tau)

    crest = gallet_crest_kV(40.0)
    measured = np.array([V1_MEASURED_40[f] for f in FRONTS])

    def residuals(x):
        return np.array([first_inception(x[0], x[1] * 1e-6, crest, f) for f in FRONTS]) / measured - 1.0

    sol = least_squares(residuals, [14.0, 2.0], bounds=([1.0, 0.0], [measured.min() - 1e-3, 100.0]))
    V0, tau = float(sol.x[0]), float(sol.x[1]) * 1e-6
    fitted = [first_inception(V0, tau, crest, f) for f in FRONTS]
    # independent check: Fig. 3 impulse (320 kV, 130 us, 80 cm gap); same threshold tip field
    V0_80 = V0 * tip_field_per_volt(40.0) / tip_field_per_volt(80.0)
    check = first_inception(V0_80, tau, 320.0, 130.0)
    return V0, tau, fitted, check, V0_80


def fit_rate_lag():
    """Fit V1 = V0 + k (dV/dt at V = V0)^n to the paper's measured first-streamer voltages (40 cm gap).

    V0 [kV], k [kV per (kV/us)^n], n. Returns them, the fitted values, the SI coefficient of the field law
    E_req = E0 + k_SI (dE_tip/dt)^n (gap independent), and the prediction for the Fig. 3 impulse.
    """
    from scipy.optimize import brentq, least_squares

    def rise(V0_kV, crest_kV, front_us):
        a, b, k = double_exponential_parameters(front_us * 1e-6, 2500e-6)
        def V(t):
            return impulse_voltage(t, crest_kV, a, b, k)
        t0 = cast(float, brentq(lambda t: V(t) - V0_kV, 0.0, front_us * 1e-6))
        h = 1e-3 * t0
        return (V(t0 + h) - V(t0 - h)) / (2 * h) * 1e-6     # kV/us

    crest = gallet_crest_kV(40.0)
    measured = np.array([V1_MEASURED_40[f] for f in FRONTS])

    def model(x):
        return np.array([x[0] + x[1] * rise(x[0], crest, f) ** x[2] for f in FRONTS])

    sol = least_squares(lambda x: model(x) / measured - 1.0, [12.0, 3.0, 0.6],
                        bounds=([1.0, 0.0, 0.05], [measured.min() - 1e-3, 1e3, 3.0]))
    V0, k, n = (float(v) for v in sol.x)
    fitted = list(model(sol.x))
    e40, e80 = tip_field_per_volt(40.0), tip_field_per_volt(80.0)
    # field form: dE = e0 dV, rate_E = e0 dV/dt  ->  dE [V/m] = e40 * 1e3 k (rate_E / (e40 * 1e9))^n
    k_SI = e40 * 1e3 * k / (e40 * 1e9) ** n
    V0_80 = V0 * e40 / e80
    rate_E = e80 * rise(V0_80, 320.0, 130.0) * 1e9           # V/(m s)
    check = V0_80 + k_SI * rate_E**n / e80 / 1e3
    return V0, k, n, fitted, k_SI, check, V0_80


def figure_workbook(path, runs, note, extra=None):
    paper = load_workbook(ROOT / "input/wh_fig678_paper.xlsx", data_only=True)
    sheets, comparison, values_rows = {}, [], []
    index = {"V": 0, "L": 1, "Q": 2}
    for name, (key, gap, unit, _t, _y) in FIGURES.items():
        rows = list(paper[name].iter_rows(values_only=True))
        cols = {h: [r[i] for r in rows[1:]] for i, h in enumerate(rows[0])}
        lookup = {h: dict(zip(cols["time to crest [us]"], v)) for h, v in cols.items()}
        ours = {n: [runs[(gap, f)][n - 1][index[key]] if len(runs[(gap, f)]) >= n else None for f in FRONTS] for n in (1, 2)}
        sheet: dict[str, list] = {"time to crest [us]": list(FRONTS)}
        for n in (1, 2):
            measured = [lookup[f"streamer {n} experimental [{unit}]"].get(f) for f in FRONTS]
            e = nrmse(ours[n], measured)
            label = f"streamer {n} (this work, RMS {e:.0f} %) [{unit}]" if e is not None else f"streamer {n} (this work) [{unit}]"
            sheet[label] = ours[n]
        for n in (1, 2):
            for kind in ("calculated", "experimental"):
                sheet[f"streamer {n}, paper {kind} [{unit}]"] = [lookup[f"streamer {n} {kind} [{unit}]"].get(f) for f in FRONTS]
        sheets[name] = sheet
        for n in (1, 2):
            for kind in ("experimental", "calculated"):
                theirs = sheet[f"streamer {n}, paper {kind} [{unit}]"]
                comparison.append((name, gap, n, kind, unit, nrmse(ours[n], theirs)))
            for f, o, p in zip(FRONTS, ours[n], sheet[f"streamer {n}, paper experimental [{unit}]"]):
                values_rows.append((name, n, f, unit, o, p, None if (o is None or p is None) else (o - p) / p * 100))
    sheets["Comparison"] = {
        "figure": [c[0] for c in comparison], "gap [cm]": [c[1] for c in comparison], "streamer": [c[2] for c in comparison],
        "paper curve": [c[3] for c in comparison], "unit": [c[4] for c in comparison],
        "NRMSE = RMS(this work - paper)/RMS(paper) [%]": [c[5] for c in comparison]}
    sheets["Values"] = {
        "figure": [v[0] for v in values_rows], "streamer": [v[1] for v in values_rows], "time to crest [us]": [v[2] for v in values_rows],
        "unit": [v[3] for v in values_rows], "this work": [v[4] for v in values_rows], "paper (measured)": [v[5] for v in values_rows],
        "difference [%]": [v[6] for v in values_rows]}
    sheets["Notes"] = {"note": note}
    if extra:
        sheets.update(extra)
    save_to_excel(path, sheets)
    add_charts(path, {name: (f[3], f[4]) for name, f in FIGURES.items()})
    return comparison


# =============================================================================
# Figure 4
# =============================================================================
def figure4_workbook(path, B, C_m, theta_B, E_c):
    """Drift of the first-streamer cloud (27.5 kV, 80 cm gap; length from the head condition, charge from
    Gauss's law) by 0.07 cm; written into a copy of your Fig. 4 workbook (charts + digitized paper curves)."""
    warnings.simplefilter("ignore", IntegrationWarning)
    R, D, V, L_rod = 1e-3, 0.80, 27.5e3, 4.0
    problem = CalibrationProblem(R=R, D=D, V_inc=V, theta_B=theta_B, E_c=E_c, rod_length=L_rod)
    L1 = first_streamer_length(problem, B, C_m)
    if L1 is None:
        raise SystemExit("No first-streamer length found for these B, C, theta_B.")
    A = gauss_amplitude(E_c, L1, theta_B, B, C_m)
    drift = simulate_drift(R, D, V, L1, theta_B, A, B, C_m, 1.36e-4, drift_distance=7e-4, rod_length=L_rod)
    z_d = drift["distance"]
    wb = load_workbook(ROOT / "excel/wh_fig4_reproduction.xlsx")          # your charts + the paper's curves
    ws = cast(Worksheet, wb["Fields"])
    rows = range(2, ws.max_row + 1)
    z_cm = np.array([ws.cell(row=r, column=1).value for r in rows], dtype=float)
    z = z_cm * 1e-2
    args = (R, L1, theta_B, A, B, C_m)
    E_ex = calculate_applied_field(R, D, V, z, rod_length=L_rod)
    cols = {2: calculate_e_sp(z, *args), 3: calculate_e_sp(z, *args, z_drift=z_d),
            4: calculate_e_rod_image(z, *args), 5: calculate_e_rod_image(z, *args, z_drift=z_d),
            6: calculate_e_plane_image(z, D, *args), 7: calculate_e_plane_image(z, D, *args, z_drift=z_d), 8: E_ex}
    cols[9] = E_ex + cols[2] + cols[4] + cols[6]
    cols[10] = E_ex + cols[3] + cols[5] + cols[7]
    for c, values in cols.items():
        for r, v in zip(rows, values / 1e5):
            ws.cell(row=r, column=c, value=float(v))
    wd = cast(Worksheet, wb["Drift"])
    wd.delete_rows(1, wd.max_row)
    wd.append(["time [us]", "drift distance z_drift [cm]"])
    for t, d in zip(drift["t"], drift["z_drift"]):
        wd.append([float(t) * 1e6, float(d) * 100])
    wp = cast(Worksheet, wb["Parameters"])
    wp.delete_rows(1, wp.max_row)
    for row in [("Parameter", "Value", "Unit"), ("B", B, "-"), ("C", C_m * 100, "cm"), ("theta_B", np.degrees(theta_B), "deg"),
                ("V", 27.5, "kV"), ("First-streamer length L_1 (head condition)", L1 * 100, "cm"),
                ("Charge Q_1 (Gauss)", gauss_charge(E_c, L1, theta_B) * 1e9, "nC"), ("Drift distance", z_d * 100, "cm"),
                ("Drift time", drift["time"] * 1e6, "us")]:
        wp.append(list(row))
    errors = {}
    for our_col, paper_x, label in ((2, 14, "before"), (3, 12, "after")):        # B/C vs paper N-O / L-M
        ours = cols[our_col] / 1e5
        px = [ws.cell(row=r, column=paper_x).value for r in range(4, ws.max_row + 1)]
        py = [ws.cell(row=r, column=paper_x + 1).value for r in range(4, ws.max_row + 1)]
        pts = [(x, y) for x, y in zip(px, py) if isinstance(x, (int, float)) and isinstance(y, (int, float)) and x <= z_cm.max()]
        x, y = np.array(pts).T
        errors[label] = nrmse(list(np.interp(x, z_cm, ours)), list(y))
        ws.cell(row=1, column=our_col, value=f"E_sp {label} drift (RMS {errors[label]:.0f} %) [kV/cm]")
    wb.save(path)
    restore_charts(path, ROOT / "excel/wh_fig4_reproduction.xlsx", {"9.15 μs": f"{drift['time'] * 1e6:.2f} μs"})
    return errors, L1, drift["time"]


def restore_charts(path, original, replacements):
    """openpyxl does not keep every detail of a chart when it re-saves a workbook (axis titles are lost),
    so the chart parts of the original workbook are copied back unchanged (title text updated)."""
    import shutil
    import zipfile
    with zipfile.ZipFile(original) as zo:
        charts = {n: zo.read(n) for n in zo.namelist() if n.startswith("xl/charts/chart")}
    tmp = Path(str(path) + ".tmp")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = charts.get(item.filename, zin.read(item.filename))
            if item.filename in charts:
                text = data.decode("utf-8")
                for old, new_text in replacements.items():
                    text = text.replace(old, new_text)
                data = text.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, path)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Trial runs against the paper's Figs 4, 6-8.")
    parser.add_argument("--name", required=True, help="sub-folder of trials/ for this case")
    parser.add_argument("--B", type=float, help="density exponent (default: from output/wh_calibration.xlsx)")
    parser.add_argument("--C", type=float, help="density offset [cm] (default: from the calibration)")
    parser.add_argument("--theta", type=float, help="cone angle [deg] (default: from the calibration)")
    parser.add_argument("--time-lag", action="store_true",
                        help="fit V0 and tau to the paper's first-streamer voltages and run only that case")
    parser.add_argument("--rate-lag", action="store_true",
                        help="fit V0, k, n of the rate-dependent lag and run only that case")
    parser.add_argument("--subtract", action="store_true",
                        help="Gauss charge of a new cloud minus the older charge inside its cone")
    args = parser.parse_args()
    B, C_cm, theta_B_deg, E_c_kV = read_calibration(str(ROOT / "output/wh_calibration.xlsx"))
    B = args.B if args.B is not None else B
    C_cm = args.C if args.C is not None else C_cm
    theta_B_deg = args.theta if args.theta is not None else theta_B_deg
    out = OUT / args.name
    out.mkdir(parents=True, exist_ok=True)
    common = (B, C_cm * 1e-2, np.radians(theta_B_deg), E_c_kV * 1e5)
    print(f"Case {args.name}: B = {B:g}, C = {C_cm:g} cm, theta_B = {theta_B_deg:g} deg", flush=True)

    e4, L1, t4 = figure4_workbook(out / "fig4.xlsx", *common)
    print(f"   Fig 4: L_1 = {L1 * 100:.2f} cm, drift 0.07 cm in {t4 * 1e6:.2f} us, "
          f"NRMSE before {e4['before']:.0f} %, after {e4['after']:.0f} %", flush=True)
    model_note = (f"B = {B:g}, C = {C_cm:g} cm, theta_B = {theta_B_deg:g} deg, charge from Gauss's law"
                  + (" minus the older charge inside the new cone" if args.subtract else "") + ", largest root.")
    head = [(f"Case {args.name}: B = {B:g}, C = {C_cm:g} cm, theta_B = {theta_B_deg:g} deg, L_1 (80 cm, 27.5 kV) = {L1 * 100:.2f} cm, "
             f"enclosed-charge subtraction {'on' if args.subtract else 'off'}"),
            f"Fig 4: E_sp NRMSE before {e4['before']:.0f} %, after {e4['after']:.0f} % (drift 0.07 cm in {t4 * 1e6:.2f} us)"]
    if args.rate_lag:
        V0, k, n, fitted, k_SI, check, V0_80 = fit_rate_lag()
        law = f"V1 = V0 + k (dV/dt)^n, V0 = {V0:.2f} kV, k = {k:.3f} kV/(kV/us)^n, n = {n:.3f}"
        print(f"   rate-dependent lag fit: {law}; Fig. 3 impulse (320 kV, 130 us, 80 cm) -> V1 = {check:.2f} kV (paper 27.5 kV)",
              flush=True)
        jobs = [(g, f, ("rate", (V0, k_SI, n)), *common, args.subtract) for g in (40.0, 80.0) for f in FRONTS]
        with ProcessPoolExecutor(16) as pool:
            runs = {(g, f): c for g, f, c in pool.map(run_front, jobs)}
        blank = [None] * (len(FRONTS) - 1)
        fit_sheet = {"Rate-lag fit": {
            "time to crest [us]": FRONTS, "V1 measured (paper, 40 cm) [kV]": [V1_MEASURED_40[f] for f in FRONTS],
            "V1 of the fit [kV]": fitted, "difference [%]": [(v - V1_MEASURED_40[f]) / V1_MEASURED_40[f] * 100 for v, f in zip(fitted, FRONTS)],
            "V0 [kV] (40 cm gap)": [V0] + blank, "k [kV/(kV/us)^n]": [k] + blank, "n [-]": [n] + blank,
            "check: V1 for the Fig. 3 impulse (320 kV, 130 us, 80 cm) [kV]": [check] + blank}}
        comp = figure_workbook(out / "fig678_rate_lag.xlsx", runs,
                               [(f"Rate-dependent lag: a burst happens when the tip field reaches E0 + k (dE_tip/dt)^n, with E0 = V0 e_ex(0); "
                                 f"in voltage terms for the first burst {law} (40 cm gap; the same field law in the 80 cm gap)."),
                                ("V0, k and n are fitted to the paper's measured first-streamer voltages (Fig. 6, 40 cm); "
                                 "everything else is a prediction."), model_note], extra=fit_sheet)
        books = ("fig4", "fig678_rate_lag")
        lines = head + [f"Rate-dependent lag: {law}; Fig. 3 impulse -> V1 = {check:.2f} kV (paper 27.5)",
                        "NRMSE against the paper's measured curves [%]:", f"{'figure':8s} {'streamer':>8s} {'rate lag':>10s}"]
        for c in [c for c in comp if c[3] == "experimental"]:
            lines.append(f"{c[0]:8s} {c[2]:>8d} {'-' if c[5] is None else f'{c[5]:.0f}':>10s}")
    elif args.time_lag:
        V0, tau, fitted, check, V0_80 = fit_time_lag()
        print(f"   time lag fit: V0 = {V0:.2f} kV (40 cm; {V0_80:.2f} kV in the 80 cm gap), tau = {tau * 1e6:.3f} us; "
              f"Fig. 3 impulse (320 kV, 130 us, 80 cm) -> V1 = {check:.2f} kV (paper 27.5 kV)", flush=True)
        jobs = [(g, f, ("lag", (V0, tau)), *common, args.subtract) for g in (40.0, 80.0) for f in FRONTS]
        with ProcessPoolExecutor(16) as pool:
            runs = {(g, f): c for g, f, c in pool.map(run_front, jobs)}
        fit_sheet = {"Time-lag fit": {
            "time to crest [us]": FRONTS, "V1 measured (paper, 40 cm) [kV]": [V1_MEASURED_40[f] for f in FRONTS],
            "V1 of the fit [kV]": fitted, "difference [%]": [(v - V1_MEASURED_40[f]) / V1_MEASURED_40[f] * 100 for v, f in zip(fitted, FRONTS)],
            "V0 [kV] (40 cm gap)": [V0] + [None] * (len(FRONTS) - 1), "tau [us]": [tau * 1e6] + [None] * (len(FRONTS) - 1),
            "check: V1 for the Fig. 3 impulse (320 kV, 130 us, 80 cm) [kV]": [check] + [None] * (len(FRONTS) - 1)}}
        comp = figure_workbook(out / "fig678_time_lag.xlsx", runs,
                               [(f"Time lag: a burst happens tau = {tau * 1e6:.3f} us after the tip field reaches the threshold "
                                 f"V0 e_ex(0), V0 = {V0:.2f} kV in the 40 cm gap (same tip field in the 80 cm gap)."),
                                ("V0 and tau are fitted to the paper's measured first-streamer voltages (Fig. 6, 40 cm); "
                                 "everything else is a prediction."), model_note], extra=fit_sheet)
        books = ("fig4", "fig678_time_lag")
        lines = head + [f"Time lag: V0 = {V0:.2f} kV (40 cm), tau = {tau * 1e6:.3f} us; Fig. 3 impulse -> V1 = {check:.2f} kV (paper 27.5)",
                        "NRMSE against the paper's measured curves [%]:", f"{'figure':8s} {'streamer':>8s} {'time lag':>10s}"]
        for c in [c for c in comp if c[3] == "experimental"]:
            lines.append(f"{c[0]:8s} {c[2]:>8d} {'-' if c[5] is None else f'{c[5]:.0f}':>10s}")
    else:
        jobs_a = [(g, f, ("fixed", None), *common, args.subtract) for g in (40.0, 80.0) for f in FRONTS]
        jobs_b = [(g, f, ("measured", V1_MEASURED_40[f]), *common, args.subtract) for g in (40.0, 80.0) for f in FRONTS]
        with ProcessPoolExecutor(16) as pool:
            runs_a = {(g, f): c for g, f, c in pool.map(run_front, jobs_a)}
            runs_b = {(g, f): c for g, f, c in pool.map(run_front, jobs_b)}
        comp_a = figure_workbook(out / "fig678_no_time_lag.xlsx", runs_a,
                                 ["One inception field for every front: 27.5 kV in the 80 cm gap (26.2 kV in the 40 cm gap). No time lag.",
                                  model_note])
        comp_b = figure_workbook(out / "fig678_measured_v1.xlsx", runs_b,
                                 ["First-streamer inception voltage of every front from the paper's measured curve (Fig. 6, 40 cm);",
                                  "the same tip field is used in the 80 cm gap. Streamer 1 of Fig. 6 therefore agrees by construction.",
                                  model_note])
        books = ("fig4", "fig678_no_time_lag", "fig678_measured_v1")
        lines = head + ["NRMSE against the paper's measured curves [%]:",
                        f"{'figure':8s} {'streamer':>8s} {'no time lag':>12s} {'measured V1':>12s}"]
        for a, b in zip([c for c in comp_a if c[3] == "experimental"], [c for c in comp_b if c[3] == "experimental"]):
            fa = "-" if a[5] is None else f"{a[5]:.0f}"
            fb = "-" if b[5] is None else f"{b[5]:.0f}"
            lines.append(f"{a[0]:8s} {a[2]:>8d} {fa:>12s} {fb:>12s}")
    (out / "plots").mkdir(exist_ok=True)
    (out / "png").mkdir(exist_ok=True)
    for book in books:
        subprocess.run([sys.executable, str(ROOT / "export_excel_charts.py"), str(out / f"{book}.xlsx"), "--output-dir", str(out / "plots")],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    for pdf in sorted((out / "plots").glob("*.pdf")):
        subprocess.run(["pdftoppm", "-r", "110", "-png", "-singlefile", str(pdf), str(out / "png" / pdf.stem)], check=True)
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
