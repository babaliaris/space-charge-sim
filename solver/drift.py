"""
Drift of the space-charge cloud during the dark period (Wang & Haiting, Eq. 6).

Model
-----
After the first corona streamer stops there is no new ionization, so the cloud
keeps its charge Q_cs and its shape (A, B, C, L_cs, theta_B do not change). It is
moved as a RIGID BODY towards the plane by the distance z_drift(t):

    d z_drift / dt = b * [ E_ex(z_c) + E_I,rod(z_c) + E_I,plane(z_c) ]
    z_c(t)         = z_c0 + z_drift(t)

where b is the positive ion mobility and z_c0 is the point where the cloud's
own field E_sp is zero before the drift. The cloud's own field is left out of
the driving field on purpose: a charge distribution cannot push itself as a
whole, and z_c is exactly the point where E_sp vanishes. Because E_sp moves
with the cloud, its zero stays at z_c0 + z_drift.

The image fields are evaluated for the DRIFTED cloud (the rod and plane stay
fixed), see solver/fields.py. The applied voltage may rise during the drift (an
impulse): pass V as a function of the time since the drift started.

Units: everything is SI (metres, seconds, V/m, m^2/(V*s)).
"""

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from solver.applied_field import calculate_applied_field
from solver.fields import calculate_e_sp, calculate_e_rod_image, calculate_e_plane_image


def find_e_sp_zero(R, L_cs, theta_B, A, B, C):
    """z [m] (from the tip apex) where the undrifted E_sp changes sign from - to +."""
    def e_sp(z):
        return calculate_e_sp(z, R, L_cs, theta_B, A, B, C)
    return brentq(e_sp, 1e-6, L_cs, xtol=1e-9)


def driving_field(z_drift, z_c0, R, D, V, L_cs, theta_B, A, B, C):
    """Field [V/m] that moves the cloud: E_ex + E_I,rod + E_I,plane at z_c = z_c0 + z_drift.

    V is the applied voltage [V] at that instant.
    """
    z_c = z_c0 + z_drift
    return (float(calculate_applied_field(R, D, V, z_c))
            + calculate_e_rod_image(z_c, R, L_cs, theta_B, A, B, C, z_drift=z_drift)
            + calculate_e_plane_image(z_c, D, R, L_cs, theta_B, A, B, C, z_drift=z_drift))


def simulate_drift(R, D, V, L_cs, theta_B, A, B, C, mobility,
                   drift_time=None, drift_distance=None, n_samples=41, max_time=1e-3,
                   sample_times=None):
    """
    Integrate the rigid-body drift. Give exactly one of:

        drift_time     [s] : drift for this long, report the distance reached
        drift_distance [m] : drift until this distance is reached, report the time needed

    V            : applied voltage [V], either a number (constant voltage) or a
                   function V(t) of the time t [s] since the drift started (impulse)
    mobility     : positive ion mobility [m^2/(V*s)]
    n_samples    : number of evenly spaced time samples in the returned history
    sample_times : optional explicit sample times [s] (since the drift started),
                   used instead of n_samples; they must lie within the drift
    max_time     : give up if drift_distance is not reached within this time [s]

    Returns a dict with z_c0, final time / distance, the sampled history
    (t, z_drift, z_c, E_drive, velocity) and "z_drift_at", a function giving
    z_drift at any time within the drift. All in SI units.
    """
    if (drift_time is None) == (drift_distance is None):
        raise ValueError("Give exactly one of drift_time or drift_distance.")

    z_c0 = find_e_sp_zero(R, L_cs, theta_B, A, B, C)
    voltage = V if callable(V) else (lambda _t: V)

    def velocity(t, state):
        return [mobility * driving_field(state[0], z_c0, R, D, voltage(t), L_cs, theta_B, A, B, C)]

    events = None
    if drift_distance is not None:
        def reached(_t, state):
            return state[0] - drift_distance
        reached.terminal = True
        reached.direction = 1
        events = reached

    t_end = drift_time if drift_time is not None else max_time
    # max_step stops the solver from trying huge steps that would carry the cloud out of the gap
    solution = solve_ivp(velocity, (0.0, t_end), [0.0], events=events, dense_output=True,
                         rtol=1e-6, atol=1e-12, max_step=t_end / 200.0)
    if not solution.success:
        raise RuntimeError(f"Drift integration failed: {solution.message}")

    if drift_distance is not None:
        if len(solution.t_events[0]) == 0:
            raise RuntimeError(f"The cloud did not drift {drift_distance} m within {max_time} s.")
        t_final = float(solution.t_events[0][0])
    else:
        t_final = float(solution.t[-1])

    def z_drift_at(time):
        return np.where(np.asarray(time) <= 0.0, 0.0, solution.sol(np.asarray(time, dtype=float))[0])

    t = np.linspace(0.0, t_final, n_samples) if sample_times is None else np.asarray(sample_times, dtype=float)
    if np.any(t < 0.0) or np.any(t > t_final * (1 + 1e-9)):
        raise ValueError("sample_times must lie between 0 and the end of the drift.")
    z_drift = z_drift_at(t)
    E_drive = np.array([driving_field(zd, z_c0, R, D, voltage(ti), L_cs, theta_B, A, B, C)
                        for ti, zd in zip(t, z_drift)])

    return {
        "z_c0": z_c0,
        "time": t_final,
        "distance": float(z_drift[-1]),
        "t": t,
        "z_drift": z_drift,
        "z_c": z_c0 + z_drift,
        "E_drive": E_drive,
        "velocity": mobility * E_drive,
        "z_drift_at": z_drift_at,
    }
