# Space-Charge Simulator: Impulse Corona in a Rod-Plane Gap

Software that estimates the development of the impulse corona discharge in a long rod-plane air gap: the
successive corona bursts under a switching impulse, the positive space charge each burst leaves, its drift, and the
total electric field at every point and instant. It follows the model of Wang Wenduan and Wang Haiting (1988).

Diploma thesis, School of Electrical and Computer Engineering, Aristotle University of Thessaloniki:
*Estimation of the Development of the Impulse Corona Discharge in a Non-Uniform Gap*
(*Εκτίμηση της ανάπτυξης της κρουστικής εκκένωσης κορώνα σε ανομοιογενές διάκενο*).

## Download (no Python needed)

Ready-made packages are on the [Releases](https://github.com/babaliaris/space-charge-sim/releases) page:

- **Windows:** `SpaceChargeSimulator-<version>-windows-setup.exe` installs the program (no administrator rights
  needed) with a Start-menu shortcut. Or unzip `…-windows-portable.zip` and run `SpaceChargeSimulator.exe`.
  If Windows shows *"Windows protected your PC"* (unsigned build), click **More info → Run anyway**.
- **Linux:** download `SpaceChargeSimulator-<version>-x86_64.AppImage`, make it executable
  (`chmod +x SpaceChargeSimulator-*.AppImage`) and run it.

`SHA256SUMS.txt` lets you check a download (`sha256sum -c SHA256SUMS.txt`).

## Using the Program

Enter the inputs (or pick a preset), press **Run simulation** and follow the progress bar and the current stage
(applied field, cone angle, bursts and drift, field profiles). By default the run covers the whole front of the
impulse; it stops earlier if the burst limit is reached, or if the successive-burst model reaches its limit (the
tip field no longer falls below the threshold between bursts).

The results appear in tabs: voltage and tip field, field profiles E(z) with a time slider, cloud positions, drift
and charge, bursts, parameters and log. Hover over a curve to read its values. Tick **Save CSV files** or
**Save an Excel workbook** to write the results to disk (by default in `Documents/Space-Charge Simulator`), and
tick earlier runs in the runs list to compare them. Inputs can be saved to and loaded from JSON.

## Running from Source

Requires Python 3.10 or newer.

### 1. Clone the repository

```bash
git clone https://github.com/babaliaris/space-charge-sim.git
cd space-charge-sim
```

### 2. Create a virtual environment

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (Command Prompt):

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install

```bash
pip install --upgrade pip
pip install .
```

This installs the dependencies (numpy, scipy, matplotlib, PyQt5, mplcursors, openpyxl) and the command
`space-charge-simulator`, which opens the program. From the repository root it also runs with:

```bash
python -m app
```

## Reproducing the Thesis Results

The scripts in `thesis/` reproduce the figures of the paper and produce the data behind the thesis figures. Run
them from the repository root as modules. Each writes an Excel workbook to `thesis/output/`:

```bash
python -m thesis.wh_time_lag_fit           # time-lag law (V0, k, n) from the paper's Fig. 6; run this first
python -m thesis.wh_fig3_reproduction      # Fig. 3: space charge of the first streamer, cone angle
python -m thesis.wh_fig3_fit_cases         # Fig. 3: the six fitting cases (~10 min)
python -m thesis.wh_fig4_reproduction      # Fig. 4: drift of the space charge
python -m thesis.wh_fig5_reproduction      # Fig. 5: applied field under the impulse, with drifting charge
python -m thesis.wh_fig678_reproduction    # Figs. 6-8: first and second streamer vs front time (~2 min)
python -m thesis.wh_calibration            # optional study (thesis Appendix G, ~10 min)
```

The charts are made in Excel, in the workbooks of `thesis/excel/`. `python -m thesis.export_excel_charts`
redraws them as vector PDFs for the thesis (`--lang el` for the Greek version; it needs LaTeX, for example through
the LyX Flatpak).

## Project Structure

- `solver/`: the physics. It covers the space-charge field integrals, the applied field (Charge Simulation
  Method), the cone angle, the drift and the successive-burst simulation. All in SI units, with z measured from
  the tip apex.
- `app/`: the graphical interface. It depends only on `solver/`.
- `thesis/`: everything specific to the thesis.
  - the scripts: reproductions of the paper's figures, the fits, and the chart tools;
  - `input/`: curves digitized from the paper;
  - `excel/`: workbooks with the charts of the thesis;
  - `output/`: what the scripts write (not in git);
  - `Theory/`: the thesis itself (LyX and PDF, English and Greek), its figures, the paper, and the defence
    presentation.
- `packaging/`, `.github/workflows/`: building the Windows and Linux packages.

## Building the Packages

GitHub Actions builds the packages (`.github/workflows/release.yml`). Pushing a tag such as `v1.0.0` builds the
Windows installer, the portable zip and the Linux AppImage. It then runs each package's `--selftest` and publishes
them as a release. **Actions → Build and release → Run workflow** only builds and tests them. To build locally on
the matching system:

```bash
pip install pyinstaller pillow
pyinstaller packaging/space_charge.spec --noconfirm      # -> dist/SpaceChargeSimulator/
dist/SpaceChargeSimulator/SpaceChargeSimulator --selftest
bash packaging/build_appimage.sh 1.0.0                    # Linux -> dist/*.AppImage
iscc /DMyAppVersion=1.0.0 packaging\installer.iss         # Windows (Inno Setup 6) -> dist\*-windows-setup.exe
```

The workflow signs the Windows executable and installer when the repository has the secrets `WINDOWS_CERT_PFX`
(the code-signing certificate `.pfx`, base64-encoded) and `WINDOWS_CERT_PASSWORD`. Without them it builds
unsigned packages.

## License

Free software under the [GNU General Public License v3.0](LICENSE), which PyQt5 (GPL) requires.
