"""Save a RunResult as CSV files (one per table) or as one Excel workbook."""

import csv
import os

from app.engine import COMPONENTS, input_rows


def _tables(r):
    """name -> (header, rows) of every table of a run."""
    cloud_cols = [("number", "burst"), ("t_birth_us", "t [µs]"), ("V_kV", "V [kV]"), ("L_cm", "L [cm]"),
                  ("Q_nC", "Q [nC]"), ("A_SI", "A [C m^(B-3)]"), ("z_c0_cm", "z_c0 [cm]"),
                  ("t_absorbed_us", "absorbed at [µs]"), ("dip_cm", "dip crossed [cm]")]
    clouds = ([h for _, h in cloud_cols], [[c[k] if c[k] is not None else "" for k, _ in cloud_cols] for c in r.clouds])

    head = ["t [µs]", "V [kV]", "E_tip [kV/cm]", "Q total [nC]"] + [f"z_drift cloud {c['number']} [cm]" for c in r.clouds]
    rows = []
    for i in range(len(r.t_us)):
        row = [r.t_us[i], r.V_kV[i], r.E_tip_kVcm[i], r.Q_total_nC[i]]
        row += ["" if v != v else v for v in r.zd_cm[:, i]] if len(r.clouds) else []
        rows.append(row)
    series = (head, rows)

    phead = ["t [µs]", "note", "z [cm]"] + [f"{k} [kV/cm]" for k in COMPONENTS]
    prow = []
    for si, ts in enumerate(r.snap_t_us):
        for j, zz in enumerate(r.z_cm):
            prow.append([ts, r.snap_labels[si], zz] + [r.profiles[k][si, j] for k in COMPONENTS])
    profiles = (phead, prow)

    params = (["parameter", "value", "unit"], [list(x) for x in input_rows(r)])
    return {"clouds": clouds, "time_series": series, "field_profiles": profiles, "parameters": params}


def save_csv(r, folder):
    """Write clouds.csv, time_series.csv, field_profiles.csv, parameters.csv and log.txt; returns the folder."""
    os.makedirs(folder, exist_ok=True)
    for name, (head, rows) in _tables(r).items():
        with open(os.path.join(folder, name + ".csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(head)
            w.writerows(rows)
    with open(os.path.join(folder, "log.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(r.log) + "\n")
    return folder


def save_xlsx(r, path):
    """One workbook with a sheet per table; returns the path."""
    from openpyxl import Workbook
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)
    for name, (head, rows) in _tables(r).items():
        ws = wb.create_sheet(name[:31])
        ws.append(head)
        for row in rows:
            ws.append([float(x) if hasattr(x, "dtype") else x for x in row])
    ws = wb.create_sheet("log")
    for line in r.log:
        ws.append([line])
    wb.save(path)
    return path
