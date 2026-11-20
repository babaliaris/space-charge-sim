"""
Calibration of the density shape B, C of rho(r) = A / (r + C)^B on the first corona streamer.

The paper chooses A so that the field in the streamer region is about E_c, and B and C
so that this field is nearly uniform. Here A always follows from Gauss's law over the
head of the cone (the charge of a streamer of length L, see `gauss_amplitude`), and B
and C are found numerically, once, on the first streamer at the inception voltage
V_inc (no older space charge), with the cone angle theta_B given.

For every trial (B, C):
    1. the length L_1 of the first streamer is the root of the head condition
           V_inc e_ex(L) + E_sp(L) + E_I,rod(L) + E_I,plane(L) = E_c
       with the charge (and A) of a cloud of length L from Gauss's law;
    2. the total field E_total(z) along the body of that streamer, from `near_tip_fraction`
       of its length to the head, is computed at test points. Closer to the tip the applied
       field of the rod dominates (it is several times E_c whatever the charge), so that zone
       is left out;
    3. the combination is scored by the RMS of (E_total - E_c) / E_c over the body. The score is
       small only when the field along the body is, on average, close to E_c AND nearly uniform:
       the stability field E_c is measured as an average (voltage over streamer length), so the
       field is not required to stay above E_c at every point. The mean field over the body,
       E_mean = (1 / length of the body) * integral of E_total dz (the potential drop over the body
       divided by its length), and the lowest field are reported.
The combination with the smallest score gives B and C (and L_1 as a prediction).
A coarse grid over (B, C) is followed by a local refinement of the best point.

Units: SI (m, V, V/m, rad, C), z from the tip apex.
"""

import warnings
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import cast

import numpy as np
from scipy.integrate import IntegrationWarning, quad
from scipy.optimize import brentq, minimize

from solver.applied_field import calculate_applied_field
from solver.fields import calculate_e_plane_image, calculate_e_rod_image, calculate_e_sp
from solver.utilities import calculate_A_from_charge, calculate_qcs_from_field

# Test points along the streamer as fractions of its length: dense near the tip,
# where the field changes fast, evenly spaced along the rest of the streamer.
DEFAULT_FRACTIONS = np.concatenate((np.geomspace(0.005, 0.1, 8, endpoint=False), np.linspace(0.1, 1.0, 22)))


@dataclass
class CalibrationProblem:
    """Everything the calibration needs (SI units)."""
    R: float                       # rod tip radius [m]
    D: float                       # tip apex to plane [m]
    V_inc: float                   # inception voltage of the first streamer [V]
    theta_B: float                 # full cone angle [rad]
    E_c: float                     # stability field [V/m]
    rod_length: float | None = None
    near_tip_fraction: float = 0.1     # the body of the streamer starts at this fraction of L
    tolerance: float = 1e3             # numerical slack of the reported checks [V/m] (0.01 kV/cm)
    L_min: float = 5e-4                # range in which the length of the first streamer is searched [m]
    L_max: float = 0.10
    fractions: np.ndarray = field(default_factory=lambda: DEFAULT_FRACTIONS.copy())


def gauss_charge(E_c, L, theta_B):
    """Q [C] of a cloud of length L from Gauss's law over its head: pi eps0 E_c (L tan(theta_B/2))^2."""
    return calculate_qcs_from_field(E_c, L_cs_m=L, theta_B_rad=theta_B)


def gauss_amplitude(E_c, L, theta_B, B, C, Q=None):
    """Amplitude A of a cloud of length L whose charge is Q (default: Gauss's law with E_c)."""
    if Q is None:
        Q = gauss_charge(E_c, L, theta_B)
    return calculate_A_from_charge(Q, B, C, L_cs_m=L, theta_B_rad=theta_B)


def amplitude_to_charge(A, B, C, L, theta_B):
    """Q = integral of rho over the cone = A * 2 pi (1 - cos(theta_B/2)) * int_0^L r^2/(r+C)^B dr [C]."""
    radial, _ = quad(lambda r: r**2 / (r + C) ** B, 0.0, L)
    return A * 2.0 * np.pi * (1.0 - np.cos(theta_B / 2.0)) * radial


def cloud_fields(problem, B, C, L, A, z):
    """E_sp + E_I,rod + E_I,plane [V/m] of an undrifted cloud of length L and amplitude A at z."""
    p = problem
    return (calculate_e_sp(z, p.R, L, p.theta_B, A, B, C)
            + calculate_e_rod_image(z, p.R, L, p.theta_B, A, B, C)
            + calculate_e_plane_image(z, p.D, p.R, L, p.theta_B, A, B, C))


def first_streamer_length(problem, B, C, n_scan=40):
    """Length L_1 [m] of the first streamer (Gauss charge): root of the head condition, None if none in range."""
    warnings.simplefilter("ignore", IntegrationWarning)
    p = problem

    def head_minus_E_c(L):
        A = gauss_amplitude(p.E_c, L, p.theta_B, B, C)
        applied = float(calculate_applied_field(p.R, p.D, p.V_inc, L, rod_length=p.rod_length))
        return applied + float(cloud_fields(p, B, C, L, A, L)) - p.E_c

    lengths = np.geomspace(p.L_min, p.L_max, n_scan)
    values = [head_minus_E_c(lengths[0])]
    for i in range(1, len(lengths)):
        values.append(head_minus_E_c(lengths[i]))
        if values[-2] > 0 >= values[-1]:
            return cast(float, brentq(head_minus_E_c, lengths[i - 1], lengths[i], xtol=1e-7))
    return None


def evaluate(problem, B, C):
    """Length, amplitude, field profile, checks and score of one combination (B, C)."""
    warnings.simplefilter("ignore", IntegrationWarning)
    p = problem
    L = first_streamer_length(p, B, C)
    if L is None:
        return {"B": B, "C": C, "L": None, "A": None, "feasible": False, "checks": {"length found": False},
                "score": np.inf, "z_body": None, "E_mean": None, "E_min": None, "max_deviation": None,
                "z": None, "E": None}
    A = gauss_amplitude(p.E_c, L, p.theta_B, B, C)
    z = p.fractions * L
    E = calculate_applied_field(p.R, p.D, p.V_inc, z, rod_length=p.rod_length) + cloud_fields(p, B, C, L, A, z)

    body = p.fractions >= p.near_tip_fraction - 1e-12          # streamer body: from near_tip_fraction * L to the head
    inside, z_in = E[body], z[body]
    E_mean = float(np.trapezoid(inside, z_in) / (z_in[-1] - z_in[0]))
    checks = {  # reported, not required (see the module docstring)
        "length found": True,
        "E >= E_c inside": bool(np.all(inside >= p.E_c - p.tolerance)),
        "decreasing inside": bool(np.all(np.diff(inside) <= p.tolerance)),
    }
    score = float(np.sqrt(np.mean(((inside - p.E_c) / p.E_c) ** 2)))
    return {"B": B, "C": C, "L": L, "A": float(A), "feasible": True, "checks": checks,
            "score": score, "z_body": float(z_in[0]), "E_mean": E_mean, "E_min": float(inside.min()),
            "max_deviation": float(np.max(np.abs(inside - p.E_c)) / p.E_c), "z": z, "E": E}


def _evaluate_job(job):
    problem, B, C = job
    result = evaluate(problem, B, C)
    return {k: v for k, v in result.items() if k not in ("z", "E")}


@dataclass
class CalibrationResult:
    A: float           # amplitude of the first streamer (from Gauss's law)
    B: float
    C: float
    L1: float          # length of the first streamer predicted by the calibration [m]
    Q1: float          # its charge [C]
    score: float
    best: dict         # evaluate() of the best combination (profile included)
    grid: list         # every grid combination (without profiles)


def calibrate(problem, B_values, C_values, workers=None, refine=True, verbose=False):
    """Grid search over (B, C) followed by a local refinement of the best feasible point."""
    jobs = [(problem, B, C) for B in B_values for C in C_values]
    if verbose:
        print(f"  calibration grid: {len(jobs)} combinations")
    with ProcessPoolExecutor(max_workers=workers) as pool:
        grid = list(pool.map(_evaluate_job, jobs))
    feasible = [r for r in grid if r["feasible"]]
    if not feasible:
        raise RuntimeError("No combination of B and C gives a first-streamer length; widen the ranges.")
    start = min(feasible, key=lambda r: r["score"])
    best = evaluate(problem, start["B"], start["C"])

    if refine:
        low = np.array([min(B_values), np.log10(min(C_values))])
        high = np.array([max(B_values), np.log10(max(C_values))])

        def objective(x):
            x = np.clip(x, low, high)
            r = evaluate(problem, x[0], 10 ** x[1])
            return r["score"] if r["feasible"] else 10.0 + (r["score"] if np.isfinite(r["score"]) else 10.0)

        x0 = np.array([best["B"], np.log10(best["C"])])
        steps = np.array([np.ptp(B_values), np.ptp(np.log10(C_values))]) / 20
        solution = minimize(objective, x0, method="Nelder-Mead",
                            options={"initial_simplex": np.vstack([x0, x0 + np.diag(steps)]),
                                     "xatol": 1e-3, "fatol": 1e-4, "maxfev": 60})
        x = np.clip(solution.x, low, high)
        refined = evaluate(problem, x[0], 10 ** x[1])
        if refined["feasible"] and refined["score"] < best["score"]:
            best = refined

    Q1 = gauss_charge(problem.E_c, best["L"], problem.theta_B)
    return CalibrationResult(A=best["A"], B=best["B"], C=best["C"], L1=best["L"], Q1=Q1,
                             score=best["score"], best=best, grid=grid)
