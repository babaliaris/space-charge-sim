# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Numerical reproduction of the Wang Wenduan & Wang Haiting model of positive space charge in a long rod-plane air gap: axial electric field from a conical streamer charge region in front of a hemispherical rod tip, plus its images in the rod and the grounded plane, plus the applied (Laplacian) field. The accompanying write-up is `Theory/A Software Application For Simulating The Effects Of Space Charge In A Rod-Plane Gap.lyx` (and `.pdf`); the rest of `Theory/` is course reference material, not code to maintain.

## Setup and running

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install .            # deps from pyproject.toml: numpy, scipy, matplotlib, pyqt5, mplcursors
```

Each top-level script is a standalone entry point run with `python <script>.py` from the repo root (imports use `from solver.... import ...`, so the cwd must be the root). All scripts force `matplotlib.use('TkAgg')` and open GUI windows.

- `main.py` — reproduces the paper's Fig. 3 (E_sp, E_I rod image, sum) and writes `figure_3_fields.csv`.
- `interactive.py` — slider UI for R, L_cs, θ_B, B, C, E_c; recomputes on "Compute".
- `sensitivity_analysis.py` — sweeps θ_B or E_c.
- `interactive2.py` / `calculate_thetab.py` — full model (applied + space charge + rod and plane images); solves for θ_B with `brentq` so the total field at the streamer tip equals E_c.

There are no tests, linter, or CI. Type checking is via `pyrightconfig.json` (uses `.venv`, covers `solver/` and `main.py`): run `pyright` if it is installed.

## Architecture

Pipeline used by every script:

1. `solver/utilities.calculate_qcs_from_field(E_c, L_cs, θ_B)` — total streamer charge Q_cs from Gauss's law over the cone head.
2. `solver/utilities.calculate_A_from_charge(Q_cs, B, C, L_cs, θ_B)` — invert the volume integral to get the amplitude A of ρ(r) = A / (r + C)^B.
3. `solver/fields.py` — `calculate_e_sp`, `calculate_e_rod_image` (Kelvin image in the spherical tip), `calculate_e_plane_image`. Each one is a `scipy.integrate.dblquad` over r ∈ [0, L_cs], θ ∈ [0, θ_B/2], run once per observation point in a Python loop, so these calls are slow. `calculate_total_field` is a placeholder (E_ext = V/d, marked TODO).
4. `solver/applied_field.calculate_applied_field` — the Laplacian field from the Charge Simulation Method: point charges inside the hemispherical tip, line segments along the shank, mirrored about the plane, and a least-squares solve of P q = V on rod-surface contour points.

`θ_B` is always the **full** cone angle; the integrals use θ_B/2.

### Unit and origin conventions differ between modules

This is the main source of bugs when combining them:

| Module | Units in/out | Observation-point origin |
|---|---|---|
| `solver/fields.py`, `solver/utilities.py` | SI (m, C, V/m) | **centre of the tip sphere**, so the apex is z = R and callers pass `z_WH + R` |
| `solver/applied_field.py` | cm, kV in; kV/cm out | **tip apex** (z = 0); raises if z < 0 or z ≥ D |

Scripts keep `z_WH` (distance from the apex, in metres) as the master grid, add `R` before calling `fields.py`, multiply by 100 for `applied_field.py`, and convert V/m to kV/cm with `* 1e-5`. In `calculate_e_plane_image`, `d` is the tip-to-plane gap. `applied_field.py` defines its own `EPSILON_0` instead of importing `solver/constants.py`.

Benchmark parameters used throughout (from the paper): R = 0.1 cm, L_cs = 2.7 cm, B = 1.5, C = 0.035 cm, E_c = 5 kV/cm, D = 80 cm, V = 27.5 kV, θ_B ≈ 60–75°.
