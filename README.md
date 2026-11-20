# Space Charge Simulation in a Rod-Plane Gap

A software application simulating the effects of positive space charge accumulation and electric field distributions in long rod-plane air gaps, based on the Wang Wenduan & Wang Haiting framework.

## Getting Started

### 1. Set Up the Virtual Environment
```bash
git clone https://github.com/babaliaris/space-charge-sim.git
```
```bash
cd space-charge-sim
```

### 2. Clone the Repository

# Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

# Windows (Command Prompt):
```bash
python3 -m venv .venv
.venv\Scripts\activate.bat
```

# Windows (PowerShell):
```bash
python3 -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
Install the required project dependencies (configured via pyproject.toml):
```bash
pip install --upgrade pip
pip install .
```

## Download (no Python needed)

Ready-made packages are on the [Releases](https://github.com/babaliaris/space-charge-sim/releases) page:

- **Windows:** `SpaceChargeSimulator-<version>-windows-setup.exe` installs the program (no administrator rights
  needed) with a Start-menu shortcut. Or unzip `…-windows-portable.zip` and run `SpaceChargeSimulator.exe`.
  If Windows shows *"Windows protected your PC"* (unsigned build), click **More info → Run anyway**.
- **Linux:** download `SpaceChargeSimulator-<version>-x86_64.AppImage`, then `chmod +x` it and run it.

`SHA256SUMS.txt` lets you check a download (`sha256sum -c SHA256SUMS.txt`). Results are saved by default in
`Documents/Space-Charge Simulator`.

## Graphical Interface

Run the whole simulation from a window (from the repository root):

```bash
python -m app
```

Enter the inputs (or pick a preset), press **Run simulation** and follow the progress bar and the current stage
(applied field, cone angle, bursts and drift, field profiles). The results appear in tabs (voltage and tip field,
field profiles E(z) with a time slider, cloud positions, drift and charge, bursts, parameters, log); hover over a
curve to read its values. Tick **Save CSV files** or **Save an Excel workbook** to write the results to disk, and
tick earlier runs in the runs list to compare them. Inputs can be saved to and loaded from JSON.

## Building the Packages

The packages are built by GitHub Actions (`.github/workflows/release.yml`): pushing a tag such as `v1.0.0`
builds the Windows installer, the portable zip and the Linux AppImage, runs each one's `--selftest`, and
publishes them as a release (**Actions → Build and release → Run workflow** only builds and tests them).
To build locally on the matching system:

```bash
pip install pyinstaller pillow
pyinstaller packaging/space_charge.spec --noconfirm      # -> dist/SpaceChargeSimulator/
dist/SpaceChargeSimulator/SpaceChargeSimulator --selftest
bash packaging/build_appimage.sh 1.0.0                    # Linux -> dist/*.AppImage
iscc /DMyAppVersion=1.0.0 packaging\installer.iss         # Windows (Inno Setup 6) -> dist\*-windows-setup.exe
```

**Code signing (Windows).** The workflow signs the executable and the installer when the repository has the
secrets `WINDOWS_CERT_PFX` (the code-signing certificate `.pfx`, base64: `base64 -w0 cert.pfx`) and
`WINDOWS_CERT_PASSWORD` (*Settings → Secrets and variables → Actions*); otherwise it builds unsigned packages.

## License

Free software under the [GNU General Public License v3.0](LICENSE) (required by PyQt5, which is GPL).

## Project Structure
* `main.py` - Core simulation runner.
* `interactive.py` - Interactive execution module.
* `sensitivity_analysis.py` - Parameter sensitivity scripts.
* `solver/` - Core numerical routines, field evaluations, and physical constants.
