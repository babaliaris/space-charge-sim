"""
Self-consistent cone boundary angle theta_B of the streamer space charge.

For given gap, voltage and charge-density shape (B, C), theta_B is the cone angle
for which the TOTAL axial field at the streamer tip (z = L_cs from the apex)
equals the average streamer field E_c:

    E_ex(L_cs) + E_sp(L_cs) + E_I_rod(L_cs) + E_I_plane(L_cs) = E_c

The total charge Q_cs (and so the density amplitude A) also depends on theta_B,
so it is recomputed for every trial angle.

Units: everything is SI (metres, volts, V/m, radians).
"""

import numpy as np
from scipy.optimize import brentq

from solver.applied_field import calculate_applied_field
from solver.fields import calculate_e_sp, calculate_e_rod_image, calculate_e_plane_image
from solver.utilities import calculate_qcs_from_field, calculate_A_from_charge


def density_amplitude(E_c, L_cs, theta_B, B, C):
    """Amplitude A of rho(r) = A / (r + C)^B for a cone of angle theta_B [rad], E_c in V/m."""
    Q_cs = calculate_qcs_from_field(E_c, L_cs_m=L_cs, theta_B_rad=theta_B)
    return calculate_A_from_charge(Q_cs, B, C, L_cs_m=L_cs, theta_B_rad=theta_B)


def total_field_at_streamer_tip(theta_B, R, D, V, L_cs, E_c, B, C):
    """Total axial field [V/m] at z = L_cs for a trial cone angle theta_B [rad]."""
    A = density_amplitude(E_c, L_cs, theta_B, B, C)
    return (float(calculate_applied_field(R, D, V, L_cs))
            + calculate_e_sp(L_cs, R, L_cs, theta_B, A, B, C)
            + calculate_e_rod_image(L_cs, R, L_cs, theta_B, A, B, C)
            + calculate_e_plane_image(L_cs, D, R, L_cs, theta_B, A, B, C))


def solve_theta_b(R, D, V, L_cs, E_c, B, C,
                  theta_min=np.radians(5.0), theta_max=np.radians(175.0)):
    """
    Find theta_B [rad] such that the total field at the streamer tip equals E_c.

    Parameters
    ----------
    R : rod tip radius [m]            D : tip-to-plane gap [m]
    V : applied voltage [V]           L_cs : streamer length [m]
    E_c : average streamer field [V/m]
    B, C : charge density shape, rho(r) = A / (r + C)^B  (C in m)
    theta_min, theta_max : search bracket [rad]; the root must lie inside it.

    Raises ValueError if the total field minus E_c has the same sign at both
    ends of the bracket (no solution inside it).
    """
    def mismatch(theta_B):
        return total_field_at_streamer_tip(theta_B, R, D, V, L_cs, E_c, B, C) - E_c

    return brentq(mismatch, theta_min, theta_max)
