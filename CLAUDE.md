# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Numerical simulation of positive space-charge effects in a long rod-plane air gap, reproducing the Wang Wenduan & Wang Haiting model (paper in `Theory/Resources/`; the project's own write-up is `Theory/A Software Application For Simulating The Effects Of Space Charge In A Rod-Plane Gap.lyx`/`.pdf`). The physics derivations (integrand geometry, image-charge distances r1–r5) live in that write-up and the figures in `Theory/assets/`; consult them before changing any integrand. The rest of `Theory/` is course material, not code.

## Workflow: Python produces data, Excel plots it

New analysis scripts compute data and save it to an `.xlsx` workbook in `output/` (git-ignored) using `excel_export.save_to_excel`; the user does all plotting in Excel. Don't use matplotlib in new scripts. `wh_fig3_reproduction.py` is the template for new scripts:

- An **INPUTS** block at the top with named constants in high-voltage engineering units (cm, kV, kV/cm, degrees), each with a short comment.
- The work runs as numbered steps. Inputs are converted to SI **once** on the way into `solver/`, and results are converted back to engineering units **once** on the way out.
- A `Fields` sheet (one row per z, one column per quantity, with units in the header) and a `Parameters` sheet (every input plus solved values, so each file records the settings that produced it).
- Short progress prints and a module docstring explaining what the script does and how to run it. Keep scripts readable for the user; favour clarity over cleverness.

The user copies the output workbooks to `excel/` and adds charts there. `export_excel_charts.py` turns those charts into vector PDFs (`Theory/assets/plots/<workbook>_chart<N>.pdf`, numbered by sheet and position) for the LyX write-up. It redraws each chart with pgfplots from the chart XML and the cell data, and leaves the title out because the LyX caption replaces it.

There is a Greek version of the write-up for publication: `Theory/A Software Application … v2 Greek.lyx` (file name kept in English on purpose). It uses LuaLaTeX with CMU Serif (non-TeX fonts, `\language greek`), Greek names for refstyle references in its preamble, and the Greek figures in `Theory/assets/v2/greek/` (Ipe, LuaLaTeX) and `Theory/assets/plots/greek/`. Only words are translated; symbols, subscripts, units, code and file names stay in English. Approved terms: διάκενο ακίδας-πλάκας, εσωτερική κρουστική τάση (SI), τάση έναυσης, παλμός (corona burst; not ριπή), νημάτιο (streamer; οχετός only for the leader, which the thesis does not model), ευκινησία ιόντων, Μέθοδος Προσομοίωσης Φορτίων (ΜΠΦ), σημείο ελέγχου (contour point), ημισφαιρική απόληξη, συντελεστής κανονικοποίησης A / "normalisation constant A" (never amplitude/πλάτος: A is not a density; the apex density is ρ(0) = A/C^B). E_sp, E_I,rod, E_I,plane (and a cloud's E_k) are «συνιστώσες» of the total field; only the geometric/applied field E_ex is called «πεδίο». Thesis title: «Εκτίμηση της ανάπτυξης της κρουστικής εκκένωσης κορώνα σε ανομοιογενές διάκενο» / "Estimation of the Development of the Impulse Corona Discharge in a Non-Uniform Gap". The paper's two authors share the surname Wang: name them «Wang και Wang [1]» / "Wang and Wang [1]" only once (Introduction); elsewhere refer to «η δημοσίευση [1]» / "the paper [1]" (headings: "Published Formulation/Results"); never "Wang & Wang" or "et al." for them; full names only in the bibliography. An equation is numbered once, where it is first defined; when it is repeated later it reuses that number with `\tag{\ref{eq:...}}` (a new variant gets its own number). When the English v2 changes, the Greek version needs the same change.

Conclusions from analyses are written up as editable LyX notes in `Theory/Notes/` (`NN_topic.lyx`, LyX 2.5 / `\lyxformat 643`, header copied from the main write-up) for reuse in the thesis. LyX is installed as a Flatpak: check a note compiles with `flatpak run --filesystem=<dir> org.lyx.LyX -batch -e pdf2 <file>` on a copy.

The older matplotlib scripts (`main.py`, `interactive.py`, `interactive2.py`, `calculate_thetab.py`, `sensitivity_analysis.py`) are kept for now; keep them working when the solver API changes.

## Setup and running

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install .            # deps from pyproject.toml: numpy, scipy, matplotlib, pyqt5, mplcursors, openpyxl
```

There is no test suite, linter, or build step. Scripts are run directly from the repo root (they import `solver.*` as a package):

```bash
python wh_fig3_reproduction.py    # solves theta_B, writes all field components to output/wh_fig3_reproduction.xlsx
python wh_fig3_fit.py             # fits theta_B, B, C (charge closed-form) to the digitized Fig. 3 curves; error maps -> output/wh_fig3_fit.xlsx (~4 min, all cores)
python wh_fig3_fit_cases.py       # the six Fig. 3 fitting cases of thesis Ch. 6 (r1 typo, coarse quadrature, ...) with charts -> output/wh_fig3_fit_cases.xlsx (~10 min)
python wh_time_lag_fit.py         # fits V0, k, n of the rate-dependent time lag V1 = V0 + k (dV/dt)^n to the paper's measured first-streamer V (Fig. 6, 40 cm) -> output/wh_time_lag_fit.xlsx (seconds); run before wh_fig4/wh_fig678
python wh_calibration.py          # (optional study, thesis Appendix G) B, C grid calibration on the first streamer -> output/wh_calibration.xlsx (~10 min)
python wh_fig4_reproduction.py    # first streamer of the Fig. 3/4 case with the final model (V1 predicted by the time-lag law, L from the head condition, Gauss charge), drifted 0.07 cm, fields before/after -> output/wh_fig4_reproduction.xlsx (needs wh_time_lag_fit)
python wh_fig5_reproduction.py    # 320 kV 100/2500 us impulse: applied field (5a) and with drifting space charge (5b) per time step
python wh_fig678_reproduction.py  # successive bursts with the final model: V, L, Q of streamers 1 and 2 vs time to crest (15-600 us, D = 40/80 cm, Gallet crest), next to the paper's curves (input/wh_fig678_paper.xlsx) with charts (RMS % in the legends), Comparison/Values sheets (needs wh_time_lag_fit, ~2 min)
python export_excel_charts.py     # redraw the user's Excel charts (excel/*.xlsx) as vector PDFs in Theory/assets/plots/ (pgfplots, needs pdflatex)
python export_excel_charts.py --lang el   # same with Greek labels -> Theory/assets/plots/greek/ (LuaLaTeX + CMU Serif via the LyX Flatpak)
python compare_datasets.py        # interactive: compare two curve files (e.g. digitized paper data vs our output)
python compare_datasets.py --reference input/wh_fig3_datasets.csv --compare output/wh_fig3_reproduction.xlsx \
    --pair "Esp=E_sp space" --pair "Ei,rod=E_I,rod"   # same, scripted; --list FILE shows a file's curves
python -m app                     # GUI (PyQt5): inputs, progress bar per stage, plots with hover cursor, CSV/xlsx export (app/)
python main.py                    # (old) plots paper Fig. 3 (E_sp, E_I_rod), writes figure_3_fields.csv
python interactive.py             # (old) slider GUI for the space-charge fields
python interactive2.py            # (old) GUI: solves theta_B, plots all field components
python sensitivity_analysis.py    # (old) theta_B / E_c sweeps
python -m solver.applied_field    # CSM applied-field demo
```

The `dblquad` integrals are slow (one 2-D adaptive quadrature per observation point, ~30 ms each for the three space-charge fields), so a 300-point run takes ~15 s. Within ~0.01 cm of the apex scipy emits `IntegrationWarning`s (the field point touches the start of the charge cone); the values are smooth and fine. The old scripts force `matplotlib.use('TkAgg')` and open GUI windows. Type checking is configured via `pyrightconfig.json` (uses `.venv`, covers `solver/` and `main.py`).

## Architecture

`solver/` holds the physics; the top-level scripts pick parameters, call the solver, and save or plot.

- `solver/utilities.py`: `impulse_voltage` (double exponential) and `double_exponential_parameters(t_crest, t_half)`, which gives α, β and k from the HV description of the waveform. It also builds the charge model: `calculate_qcs_from_field` gets the total streamer charge Q_cs from the average streamer field E_c via Gauss's law over the cone head; `calculate_A_from_charge` inverts the volume integral of ρ(r) = A/(r+C)^B over the cone to get A.
- `solver/fields.py`: axial space-charge fields as `dblquad` integrals over the cone (r ∈ [0, L_cs] from the apex, θ ∈ [0, θ_B/2]): direct field `calculate_e_sp`, rod Kelvin image `calculate_e_rod_image`, grounded plane image `calculate_e_plane_image`, and `calculate_total_field` (adds the CSM applied field).
- `solver/applied_field.py`: the applied (Laplacian) field E_ex computed with the Charge Simulation Method: fictitious axial point charges in the hemispherical tip plus line segments in the shank, mirrored in the plane, solved by least squares so the rod surface sits at V. The modelled rod length `rod_length` (L_rod, not given in the paper) defaults to 5·D; `solve_theta_b`, `simulate_drift`, `calculate_total_field` and `GapModel` pass it through, and the scripts set it as the `ROD_LENGTH_cm` input (per gap in `wh_fig678_reproduction.py`, `ROD_LENGTHS_cm`).
- `solver/theta_b.py`: `solve_theta_b` finds the cone angle θ_B for which E_ex + E_sp + E_I,rod + E_I,plane = E_c at the streamer tip (z = L_cs), recomputing Q_cs and A for each trial angle; `density_amplitude` wraps the Q_cs → A chain.
- `solver/drift.py`: dark-period drift (paper Eq. 6). The cloud moves as a rigid body at speed b·[E_ex + E_I,rod + E_I,plane] evaluated at z_c, the zero of E_sp, which moves with the cloud. `simulate_drift` takes either a drift time or a drift distance. V may be a constant or a function V(t) of the time since the drift began (impulse), and the result includes `z_drift_at(t)`. The mobility `POSITIVE_ION_MOBILITY` is in `solver/constants.py`.
- **Drift in the field functions:** `calculate_e_sp`, `calculate_e_rod_image`, `calculate_e_plane_image` and `calculate_total_field` take `z_drift` (default 0). It shifts the **charge** (r·cosθ → r·cosθ + z_drift) while the rod and plane stay fixed. Only E_sp becomes an exact shift (`E_sp(z; z_d) = E_sp(z − z_d)`). The image fields change shape, so never implement drift as z → z − z_drift for them. E_ex does not depend on the drift.
- **The applied field is linear in V.** Compute `calculate_applied_field(R, D, 1.0, z)` once and scale it by V(t) rather than re-solving the CSM at each time step.
- `solver/calibration.py`: helpers for the first streamer: `gauss_charge` / `gauss_amplitude` (Q = pi eps0 E_c (L tan(theta_B/2))^2, A from Q), `amplitude_to_charge`, `first_streamer_length` (root of the head condition) and the optional B, C grid calibration (`calibrate`, score = RMS of (E_total - E_c)/E_c over the body). The calibration is NOT part of the model any more: it pushes C to the grid edge and fits the paper worse, so B and C are user inputs (thesis Appendix G).
- `solver/simulation.py`: the whole framework (write-up Chapter 5 "The Successive-Burst Model", summarised in Section 5.10; Section 4.4 summarises the single-cloud drift model, Section 2.6 the electrostatics). Final model: `GapModel(..., B, C, subtract_enclosed=True, overvoltage_k=k_SI, overvoltage_n=n)` with E_inc = E_0 = V_0 e_ex(0) the static threshold. `simulate(model, V, t_end, max_bursts)`: when the tip field first reaches E_0 the rate dE_tip/dt is taken and the burst happens when the tip field reaches E_0 + k_SI rate^n (rate-dependent time lag, Kind 1957 / Darveniza 1988); the length is the LARGEST root of "field at the head = E_c" on top of the older clouds (narrow dips crossed, width recorded in `dip_width`); the charge is Gauss's law over the head minus the older charge inside the new cone (`enclosed_charge`), A_k follows from Q_k; all clouds drift together, each pushed by the fields of the others. Charge past the plane is cut (`z_cut`) and a cloud is dropped when its apex reaches the plane. Final inputs: B = 1.5, C = 0.035 cm (paper), theta_B = 93.39 deg (head condition on the Fig. 3 streamer), V0 = 8.52 kV (40 cm), k = 7.69 kV/(kV/us)^n, n = 0.316 (k_SI = 856). Fig. 3 impulse (320 kV, 130 us, 80 cm) -> V1 = 26.42 kV (paper 27.5).
- `simulate(..., on_progress, on_message, cancel)`: optional callbacks for front ends: `on_progress(t, text)` is called from inside the drift integration, `on_message(text)` receives the log lines (bursts, absorptions, dip warnings), and `cancel()` returning True raises `SimulationCancelled`. Without them `simulate` behaves as before.
- `app/`: the GUI (`python -m app`), which depends only on `solver/`. `inputs.py` holds every input field (engineering units, defaults = final model), the presets and JSON save/load; `engine.py` (no Qt) runs the four stages (CSM, θ_B given or solved, `simulate`, then the tip field and E(z) profiles in spawned worker processes) and returns a `RunResult` in engineering units; `export.py` writes CSV/xlsx; `plots.py` draws the tabs with mplcursors; `window.py` is the PyQt5 window (the run happens in a QThread). The time-lag law is entered as V0, k, n of the gap where it was fitted and converted to E_0, k_SI with e_ex(0) of that gap (rod 5·D). The GUI writes CSV on request: the user asked for it, unlike the analysis scripts, which keep the .xlsx rule.
- Packaging (`packaging/`, `.github/workflows/release.yml`): PyInstaller one-folder build (`space_charge.spec`, entry `launcher.py` with `multiprocessing.freeze_support()`: the worker processes are spawned and must start through it), Inno Setup installer (`installer.iss`, per-user) and AppImage (`build_appimage.sh`) for Windows and Linux; a tag `v*` builds, runs `--selftest` (headless run checking burst charges 9.47/5.98 nC) and publishes a GitHub release. Optional signing via the `WINDOWS_CERT_PFX`/`WINDOWS_CERT_PASSWORD` secrets (`sign.ps1`). The license is GPL-3.0 (PyQt5). `app/__init__.py` holds `__version__`, stamped from the tag in CI; `packaging/make_icon.py` draws `app/icon.png` and `packaging/icon.ico`.
- `excel_export.py`: `save_to_excel(path, {sheet: {header: column}})`.
- `compare_datasets.py`: compares curves sampled at different x. It keeps the REFERENCE file's x values and linearly interpolates the COMPARE file's curves onto them, with no extrapolation, then writes the differences and error statistics (bias, MAE, RMS, max) to `output/comparison_*.xlsx`. It reads `.csv`/`.xlsx` in two auto-detected layouts: the WebPlotDigitizer wide export (name row, X/Y row, X/Y column pairs; unquoted commas in curve names are re-joined) and our own "x column + curve columns" tables. `input/` holds external data such as digitized paper curves; `output/` holds what our scripts generate.

### Units and coordinate origin

- **Every `solver/` function takes and returns SI units** (m, V, V/m, rad, C).
- **Every z is measured from the rod tip apex** (z = 0 at the apex, sphere centre at z = −R, plane at z = D, where D is the tip-to-plane gap), matching the paper's Z_WH. `calculate_applied_field` requires 0 ≤ z < D.
- `theta_B` is always the **full** cone angle; the functions halve it internally.
- Scripts convert at their boundaries: cm → m `* 1e-2`, kV → V `* 1e3`, kV/cm ↔ V/m `* 1e5`.

The LyX write-up derives the integrands in a frame centred on the tip sphere and puts the plane at `d` from the sphere centre. The code works in the apex frame instead: the rod-image integrand shifts z by R internally, and the plane image uses `2D − r·cosθ − z`.

Reference benchmark parameters (paper Fig. 3): R = 0.1 cm, L_cs = 2.7 cm, B = 1.5, C = 0.035 cm, E_c = 5 kV/cm, D = 80 cm, V = 27.5 kV. These give θ_B ≈ 93.39°.
