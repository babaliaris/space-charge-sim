# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Numerical simulation of positive space-charge effects in a long rod-plane air gap, reproducing the Wang Wenduan & Wang Haiting model (paper in `Theory/Resources/`; the project's own write-up is `Theory/A Software Application For Simulating The Effects Of Space Charge In A Rod-Plane Gap.lyx`/`.pdf`). The physics derivations (integrand geometry, image-charge distances r1–r5) live in that write-up and the figures in `Theory/assets/`; consult them before changing any integrand. The rest of `Theory/` is course material, not code.

## Setup and running

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install .            # deps from pyproject.toml: numpy, scipy, matplotlib, pyqt5, mplcursors
```

There is no test suite, linter, or build step. Scripts are run directly from the repo root (they import `solver.*` as a package):

```bash
python main.py                    # reproduce paper Fig. 3 (E_sp, E_I_rod), writes figure_3_fields.csv
python interactive.py             # slider GUI for the space-charge fields
python sensitivity_analysis.py    # theta_B / E_c sweeps
python interactive2.py            # solves theta_B by root-finding, plots all field components
python -m solver.applied_field    # CSM applied-field demo
```

All plotting scripts force `matplotlib.use('TkAgg')` and open GUI windows, and the `dblquad` integrals are slow (one 2-D adaptive quadrature per observation point), so expect each run to take a while. Type checking is configured via `pyrightconfig.json` (uses `.venv`, covers `solver/` and `main.py`).

## Architecture

`solver/` holds the physics; the top-level scripts are thin drivers that pick parameters, call the solver, and plot.

- `solver/utilities.py`: builds the charge model. `calculate_qcs_from_field` gets the total streamer charge Q_cs from the average streamer field E_c via Gauss's law over the cone head; `calculate_A_from_charge` inverts the volume integral of ρ(r) = A/(r+C)^B over the cone to get A. Every driver runs these two first, in that order.
- `solver/fields.py`: axial space-charge fields as `dblquad` integrals over the cone (r ∈ [0, L_cs], θ ∈ [0, θ_B/2]): direct field `calculate_e_sp`, rod Kelvin image `calculate_e_rod_image`, grounded plane image `calculate_e_plane_image`. `calculate_total_field` still uses a `V/d` placeholder for the applied field (see TODO).
- `solver/applied_field.py`: the applied (Laplacian) field E_ex computed with the Charge Simulation Method: fictitious axial point charges in the hemispherical tip plus line segments in the shank, mirrored in the plane, solved by least squares so the rod surface sits at V. It is self-contained and defines its own `EPSILON_0`.

Total field on the axis = E_ex + E_sp + E_I_rod + E_I_plane (combined in `interactive2.py`/`calculate_thetab.py`).

### Units and coordinate origins: the main source of bugs

The two field modules use **different units and different z origins**:

| Module | Units in/out | z origin |
|---|---|---|
| `solver/fields.py` | SI in, V/m out | **centre of the tip hemisphere** (tip apex at z = R) |
| `solver/applied_field.py` (`calculate_applied_field`) | cm and kV in, kV/cm out | **tip apex** (z = 0); requires 0 ≤ z < D |

Drivers keep a grid `z_WH` measured from the apex (the paper's coordinate) and pass `z_WH + R` to `fields.py`, and `z_WH * 100` (cm) to `calculate_applied_field`. Convert `fields.py` results with `* 1e-5` to get kV/cm. `theta_B` is always the **full** cone angle in radians (functions halve it internally), and the `utilities.py` helpers take E_c in kV/cm but lengths in metres.

Reference benchmark parameters (paper Fig. 3): R = 0.1 cm, L_cs = 2.7 cm, B = 1.5, C = 0.035 cm, E_c = 5 kV/cm, D = 80 cm, V = 27.5 kV.
