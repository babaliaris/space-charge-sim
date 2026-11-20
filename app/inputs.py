"""
Inputs of the GUI: every field with its label, unit, default, limits and tooltip,
the built-in presets and saving/loading as JSON.

All values are in high-voltage engineering units (cm, kV, kV/cm, us, deg); engine.py
converts them to SI once, on the way into solver/.
"""

import json
import os
from dataclasses import dataclass, field


@dataclass
class Field:
    key: str
    label: str
    unit: str
    default: object
    kind: str = "float"            # float | int | bool | choice
    minimum: float = 0.0
    maximum: float = 1e9
    decimals: int = 3
    tooltip: str = ""
    special: str = ""               # text shown when the value equals the minimum (e.g. "auto")
    choices: list = field(default_factory=list)


def gallet_crest_kV(gap_cm):
    """Gallet formula: 50 % breakdown voltage of a rod-plane gap, U50 = 3400 / (1 + 8/d) kV, d in m."""
    return 3400.0 / (1.0 + 8.0 / (gap_cm / 100.0))


THETA_GIVEN, THETA_SOLVE = "given", "solve from a reference streamer"

GROUPS = [
    ("Gap", [
        Field("R_cm", "Rod tip radius R", "cm", 0.1, minimum=0.001, maximum=10, decimals=4,
              tooltip="Radius of the hemispherical rod tip."),
        Field("D_cm", "Gap D (tip to plane)", "cm", 40.0, minimum=1, maximum=1000, decimals=2,
              tooltip="Distance from the rod tip apex to the grounded plane."),
        Field("rod_length_cm", "Rod length", "cm", 0.0, minimum=0, maximum=10000, decimals=1, special="auto (5·D)",
              tooltip="Modelled rod length for the applied field (Charge Simulation Method). Not given in the paper; 5·D by default."),
    ]),
    ("Impulse voltage", [
        Field("crest_kV", "Crest voltage", "kV", round(gallet_crest_kV(40.0), 2), minimum=1, maximum=10000, decimals=2,
              tooltip="Peak of the double-exponential impulse. The button below sets the Gallet U50 of the gap."),
        Field("front_us", "Time to crest", "µs", 100.0, minimum=0.1, maximum=100000, decimals=2,
              tooltip="Front time of the impulse (time to crest)."),
        Field("half_us", "Time to half value", "µs", 2500.0, minimum=1, maximum=1e6, decimals=1,
              tooltip="Time to half value on the tail."),
        Field("t_end_us", "Simulate until", "µs", 100.0, minimum=0.1, maximum=1e6, decimals=2,
              tooltip="End of the simulated time, measured from the start of the impulse."),
        Field("max_bursts", "Stop after bursts", "", 3, kind="int", minimum=0, maximum=1000, special="no limit",
              tooltip="The simulation stops right after this many bursts (the drift after the last burst is then not simulated)."),
    ]),
    ("Space-charge cloud", [
        Field("E_c_kVcm", "Stability field E_c", "kV/cm", 5.0, minimum=0.1, maximum=100, decimals=3,
              tooltip="Average field along a positive streamer (head condition)."),
        Field("B", "Density exponent B", "", 1.5, minimum=0.0, maximum=10, decimals=3,
              tooltip="ρ(r) = A / (r + C)^B"),
        Field("C_cm", "Density offset C", "cm", 0.035, minimum=1e-5, maximum=10, decimals=5,
              tooltip="ρ(r) = A / (r + C)^B"),
        Field("mobility_cm2_Vs", "Ion mobility µ+", "cm²/(V·s)", 1.36, minimum=0.01, maximum=100, decimals=3,
              tooltip="Positive ion mobility (paper: 1.36e-3 cm²/(kV·µs) = 1.36 cm²/(V·s))."),
        Field("subtract_enclosed", "Subtract older charge inside a new cone", "", True, kind="bool",
              tooltip="Gauss charge of a new cloud minus the charge of the older clouds that lies inside its cone (final model)."),
        Field("theta_mode", "Cone angle θ_B", "", THETA_GIVEN, kind="choice", choices=[THETA_GIVEN, THETA_SOLVE],
              tooltip="Give θ_B, or solve it from the head condition on a reference streamer of known length."),
        Field("theta_deg", "θ_B (full angle)", "deg", 93.39, minimum=1, maximum=179, decimals=2,
              tooltip="Full cone angle (93.39° from the head condition on the paper's Fig. 3 streamer)."),
        Field("ref_D_cm", "Reference streamer: gap", "cm", 80.0, minimum=1, maximum=1000, decimals=2,
              tooltip="Gap of the reference streamer used to solve θ_B (paper Fig. 3: 80 cm)."),
        Field("ref_V_kV", "Reference streamer: voltage", "kV", 27.5, minimum=0.1, maximum=10000, decimals=2,
              tooltip="Voltage at the reference streamer's inception (paper Fig. 3: 27.5 kV)."),
        Field("ref_L_cm", "Reference streamer: length", "cm", 2.7, minimum=0.01, maximum=100, decimals=3,
              tooltip="Length of the reference streamer (paper Fig. 3: 2.7 cm)."),
    ]),
    ("Burst inception (time lag)", [
        Field("V0_kV", "Static inception voltage V₀", "kV", 8.5178, minimum=0.1, maximum=10000, decimals=4,
              tooltip="Threshold of the law V₁ = V₀ + k (dV/dt)^n, in the gap where it was fitted (below)."),
        Field("lag_k", "Coefficient k", "kV/(kV/µs)^n", 7.6912, minimum=0, maximum=1e4, decimals=4,
              tooltip="k = 0 removes the time lag: the burst happens when the tip field reaches E₀."),
        Field("lag_n", "Exponent n", "", 0.31554, minimum=0.01, maximum=5, decimals=5,
              tooltip="Exponent of the rate-dependent time lag."),
        Field("lag_ref_D_cm", "Gap where V₀, k were fitted", "cm", 40.0, minimum=1, maximum=1000, decimals=2,
              tooltip="The law is turned into tip fields with e_ex(0) of this gap (rod length 5·D), so it holds for any gap."),
    ]),
    ("Output resolution", [
        Field("n_time", "Time samples", "", 150, kind="int", minimum=10, maximum=5000,
              tooltip="Instants for V(t), the tip field, the cloud positions and the charge."),
        Field("n_snap", "Field-profile instants", "", 10, kind="int", minimum=1, maximum=200,
              tooltip="Instants (evenly spaced, plus just after every burst) for the E(z) profiles."),
        Field("n_z", "Points along z", "", 120, kind="int", minimum=10, maximum=2000,
              tooltip="Observation points of each E(z) profile (geometric spacing, dense near the tip)."),
        Field("z_min_cm", "z from", "cm", 0.005, minimum=0.0001, maximum=100, decimals=4,
              tooltip="First observation point (measured from the tip apex)."),
        Field("z_max_cm", "z to", "cm", 10.0, minimum=0.01, maximum=1000, decimals=2,
              tooltip="Last observation point (kept just inside the plane)."),
        Field("workers", "Parallel processes", "", max(1, min(8, (os.cpu_count() or 2) - 1)), kind="int",
              minimum=1, maximum=max(1, os.cpu_count() or 1),
              tooltip="Processes for the field profiles and the tip field (the burst/drift loop itself runs in one process)."),
    ]),
    ("Advanced", [
        Field("n_scan", "Length scan points", "", 80, kind="int", minimum=10, maximum=1000,
              tooltip="Trial lengths (log spaced) used to find the roots of the head condition."),
        Field("L_max_cm", "Longest streamer", "cm", 0.0, minimum=0, maximum=1000, decimals=2, special="auto (D/2)",
              tooltip="Upper end of the length search."),
        Field("max_step_us", "Largest drift time step", "µs", 0.0, minimum=0, maximum=1e5, decimals=3, special="auto",
              tooltip="Largest step of the drift integration (auto: simulated time / 400)."),
    ]),
]

FIELDS = {f.key: f for _, group in GROUPS for f in group}


def defaults():
    return {k: f.default for k, f in FIELDS.items()}


def _preset(**changes):
    values = defaults()
    values.update(changes)
    return values


PRESETS = {
    "Final model · D = 40 cm · 100 µs front": _preset(),
    "Final model · D = 80 cm · 100 µs front": _preset(D_cm=80.0, crest_kV=round(gallet_crest_kV(80.0), 2)),
    "Paper Fig. 3 impulse · 320 kV, 130 µs · D = 80 cm": _preset(D_cm=80.0, crest_kV=320.0, front_us=130.0, t_end_us=130.0),
    "Fast front · D = 40 cm · 15 µs": _preset(front_us=15.0, t_end_us=15.0),
    "Slow front · D = 40 cm · 600 µs": _preset(front_us=600.0, t_end_us=600.0),
    "Single burst, θ_B solved from the paper's Fig. 3 streamer": _preset(theta_mode=THETA_SOLVE, max_bursts=1),
}


def validate(v):
    """List of problems (empty if the inputs are consistent)."""
    problems = []
    if v["R_cm"] >= v["D_cm"]:
        problems.append("The tip radius must be smaller than the gap.")
    if v["z_min_cm"] >= min(v["z_max_cm"], v["D_cm"]):
        problems.append("'z from' must be smaller than 'z to' and than the gap.")
    if v["theta_mode"] == THETA_SOLVE and v["ref_L_cm"] >= v["ref_D_cm"]:
        problems.append("The reference streamer must be shorter than its gap.")
    if v["L_max_cm"] and v["L_max_cm"] >= v["D_cm"]:
        problems.append("The longest streamer must be shorter than the gap.")
    return problems


def save_json(path, values):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(values, f, indent=2, ensure_ascii=False)


def load_json(path):
    """Values from a JSON file; missing keys keep their defaults, unknown keys are ignored."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    values = defaults()
    values.update({k: data[k] for k in FIELDS if k in data})
    return values
