# Space Charge Simulation in a Rod-Plane Gap

A software application simulating the effects of positive space charge accumulation and electric field distributions in long rod-plane air gaps, based on the Wang Wenduan & Wang Haiting framework.

## Getting Started

### 1. Set Up the Virtual Environment
```bash
git clone [https://github.com/babaliaris/space-charge-sim.git](https://github.com/babaliaris/space-charge-sim.git)
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

## Project Structure
* `main.py` - Core simulation runner.
* `interactive.py` - Interactive execution module.
* `sensitivity_analysis.py` - Parameter sensitivity scripts.
* `solver/` - Core numerical routines, field evaluations, and physical constants.
