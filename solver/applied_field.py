"""
Applied (Laplacian) field of a rod-plane gap, computed with the Charge
Simulation Method (CSM).

Geometry (axisymmetric, everything lives on / around the z axis)
----------------------------------------------------------------
    z = 0        rod tip apex            (observation points are measured from here)
    z = -R       centre of the hemispherical tip
    z = D        grounded plane
    z < -R       the cylindrical rod "shank" (radius R), extending away from the plane

Idea of the method
------------------
We do not solve the field in the gap directly. Instead we hide fictitious
charges INSIDE the rod and choose their values so that the rod surface becomes
an equipotential at V. The grounded plane is handled with the method of images:
every charge q at height z_j gets a mirror charge -q at height 2D - z_j.

  * Tip      : a few point charges on the axis, inside the hemisphere.
  * Shank    : uniformly charged line segments on the axis (they give a smooth
               surface potential; plain point charges oscillate in sign and
               fail to hold the potential between them).

Unknowns = charges. Equations = "potential at a contour point on the rod
surface equals V". This is a linear system  P q = V  which we solve in the
least-squares sense (more contour points than unknowns -> more stable).

Units: everything is SI (metres, volts, V/m), including the public function.
"""

from dataclasses import dataclass
import numpy as np
from solver.constants import EPSILON_0

COULOMB_K = 1.0 / (4.0 * np.pi * EPSILON_0)  # 1 / (4 pi eps0)


# -----------------------------------------------------------------------------
# 1. Building blocks: potential / field of the two kinds of charges
# -----------------------------------------------------------------------------
def _point_charge_potential(r, z, z_q):
    """Potential [V per Coulomb] of a unit point charge at (0, z_q), seen at (r, z)."""
    return COULOMB_K / np.hypot(r, z - z_q)


def _log_term(x, r):
    """
    Numerically safe  x + sqrt(x^2 + r^2).
    For large negative x the plain formula subtracts two nearly equal numbers,
    so we use the algebraically identical  r^2 / (sqrt(x^2 + r^2) - x).
    """
    root = np.sqrt(x * x + r * r)
    return np.where(x < 0.0, r * r / np.maximum(root - x, 1e-300), x + root)


def _segment_potential(r, z, z_low, z_high):
    """
    Potential [V per (C/m)] of a uniform line charge on the axis between
    z_low < z_high, seen at the point (r, z).
    """
    upper = _log_term(z_high - z, r)
    lower = _log_term(z_low - z, r)
    return COULOMB_K * np.log(upper / lower)


def _segment_axis_field(z, z_low, z_high, observer_is_above):
    """
    Axial field E_z [V/m per (C/m)] of a uniform line charge on the axis, seen
    at a point (0, z) that lies OUTSIDE the segment.
    """
    if observer_is_above:      # observer above the segment: field points +z
        return COULOMB_K * (1.0 / (z - z_high) - 1.0 / (z - z_low))
    # observer below the segment: field points -z
    return COULOMB_K * (1.0 / (z_high - z) - 1.0 / (z_low - z))


# -----------------------------------------------------------------------------
# 2. The charge layout (where we put the fictitious charges)
# -----------------------------------------------------------------------------
@dataclass
class ChargeLayout:
    # tip: point charges on the axis
    tip_charge_z: np.ndarray            # z position of each tip point charge
    # shank: line segments on the axis
    seg_low: np.ndarray                 # lower end of each segment
    seg_high: np.ndarray                # upper end of each segment
    # where we demand V on the rod surface (columns: r, z)
    contour_points: np.ndarray

    @property
    def n_tip(self):
        return len(self.tip_charge_z)

    @property
    def n_segments(self):
        return len(self.seg_low)


def build_layout(R, rod_length, n_tip=30, segment_growth=1.2):
    """
    Place the charges and contour points. All lengths in metres.

    n_tip           : number of point charges (and contour points) on the hemisphere.
    segment_growth  : each shank segment is this many times longer than the one
                      before it (short segments near the tip where the field
                      changes fast, long ones far away).
    """
    # --- Tip: contour points on the hemisphere, charges on the axis inside it.
    # theta = 0 is the apex, theta = pi/2 is where the sphere meets the shank.
    theta = (np.arange(n_tip) + 0.5) / n_tip * (np.pi / 2.0)
    tip_contour = np.column_stack([R * np.sin(theta), -R + R * np.cos(theta)])
    tip_charge_z = -R + 0.5 * R * np.cos(theta)      # half-way to the sphere centre

    # --- Shank: segment edges measured downwards from the sphere centre (z = -R)
    first_length = np.pi * R / n_tip                 # comparable to the tip spacing
    edges = [0.0]
    length = first_length
    while edges[-1] < rod_length:
        edges.append(edges[-1] + length)
        length *= segment_growth
    edges = np.array(edges)

    seg_high = -R - edges[:-1]                       # upper end (closer to the tip)
    seg_low = -R - edges[1:]                         # lower end
    seg_len = seg_high - seg_low

    # contour points on the shank surface: 3 per segment (quarter, middle, 3/4)
    shank_z = np.concatenate([seg_low + f * seg_len for f in (0.25, 0.5, 0.75)])
    shank_contour = np.column_stack([np.full_like(shank_z, R), shank_z])

    return ChargeLayout(
        tip_charge_z=tip_charge_z,
        seg_low=seg_low,
        seg_high=seg_high,
        contour_points=np.vstack([tip_contour, shank_contour]),
    )


# -----------------------------------------------------------------------------
# 3. Potential of the whole charge system (real charges + plane images)
# -----------------------------------------------------------------------------
def _potential_per_unit_charge(r, z, layout, D):
    """
    Potential at points (r, z) produced by each unknown (unit value),
    INCLUDING the mirror images in the grounded plane at z = D.
    Returns an array of shape (n_points, n_unknowns).
    """
    r = np.asarray(r, dtype=float)[:, None]
    z = np.asarray(z, dtype=float)[:, None]

    # Tip point charges: real (+) and image (-) at 2D - z_q
    zq = layout.tip_charge_z[None, :]
    tip = (_point_charge_potential(r, z, zq)
           - _point_charge_potential(r, z, 2.0 * D - zq))

    # Shank segments: real (+) and image (-) reflected about z = D
    low, high = layout.seg_low[None, :], layout.seg_high[None, :]
    shank = (_segment_potential(r, z, low, high)
             - _segment_potential(r, z, 2.0 * D - high, 2.0 * D - low))

    return np.hstack([tip, shank])


def _solve_charges(layout, D, V):
    """Solve  P q = V  (least squares) for all unknown charges."""
    r = layout.contour_points[:, 0]
    z = layout.contour_points[:, 1]
    P = _potential_per_unit_charge(r, z, layout, D)
    q, *_ = np.linalg.lstsq(P, np.full(len(r), V), rcond=None)
    return q


# -----------------------------------------------------------------------------
# 4. Axial field from the solved charges
# -----------------------------------------------------------------------------
def _axial_field(z, charges, layout, D):
    """E_z [V/m] on the axis at heights z (z >= 0 and z < D)."""
    z = np.asarray(z, dtype=float)
    q_tip = charges[:layout.n_tip]
    lam = charges[layout.n_tip:]                      # line densities [C/m]

    field = np.zeros_like(z)

    # Tip point charges (real one below the observer, image above it)
    for q, zq in zip(q_tip, layout.tip_charge_z):
        field += COULOMB_K * q * (1.0 / (z - zq) ** 2 + 1.0 / (2.0 * D - zq - z) ** 2)

    # Shank segments: real segment is below the observer,
    # image segment (opposite sign) is above the plane, i.e. above the observer
    for lj, lo, hi in zip(lam, layout.seg_low, layout.seg_high):
        field += lj * _segment_axis_field(z, lo, hi, observer_is_above=True)
        field += -lj * _segment_axis_field(z, 2.0 * D - hi, 2.0 * D - lo,
                                           observer_is_above=False)
    return field


# -----------------------------------------------------------------------------
# 5. PUBLIC FUNCTION
# -----------------------------------------------------------------------------
def calculate_applied_field(R, D, V, z,
                            rod_length=None, n_tip=30, segment_growth=1.2,
                            return_boundary_error=False):
    """
    Applied (Laplacian) field E_ex(z) on the axis of a rod-plane gap.

    Parameters
    ----------
    R : float             tip (and rod) radius [m]
    D : float             gap length, tip-to-plane [m]
    V : float             applied voltage [V]
    z : float or array    observation points, measured FROM THE TIP APEX [m]
                          (0 <= z < D). z = 0 is the apex itself.
    rod_length : float, optional
                          modelled rod length above the tip [m]. Default: 5 * D.
    n_tip, segment_growth : discretisation controls (defaults are converged).
    return_boundary_error : bool
                          if True also return the worst relative deviation of the
                          rod-surface potential from V, checked at points that
                          were NOT used to fit the charges (a real accuracy test).

    Returns
    -------
    E : np.ndarray, same shape as z, field along +z [V/m].
        Positive = pointing from the rod towards the plane.
    (boundary_error, if requested)
    """
    z = np.asarray(z, dtype=float)
    if np.any(z < 0) or np.any(z >= D):
        raise ValueError("z must satisfy 0 <= z < D (measured from the tip apex).")

    if rod_length is None:
        rod_length = 5.0 * D

    layout = build_layout(R, rod_length, n_tip, segment_growth)
    charges = _solve_charges(layout, D, V)

    E = _axial_field(z.ravel(), charges, layout, D).reshape(z.shape)

    if not return_boundary_error:
        return E

    # accuracy check: potential on the surface at fresh points (first 80% of rod)
    theta = np.linspace(0.001, np.pi / 2, 300)
    s = np.linspace(1e-5, 0.8 * rod_length, 3000)
    r_chk = np.concatenate([R * np.sin(theta), np.full_like(s, R)])
    z_chk = np.concatenate([-R + R * np.cos(theta), -R - s])
    potential = _potential_per_unit_charge(r_chk, z_chk, layout, D) @ charges
    return E, float(np.max(np.abs(potential - V)) / V)


# -----------------------------------------------------------------------------
# 6. Demo
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import matplotlib.pyplot as plt
    from scipy.optimize import brentq                    # NEW: root finder

    # --- Parameters of the paper (Wang & Haiting, Fig. 3) ---------------------
    R_cm, D_cm, V_kV = 0.1, 80.0, 27.5
    E_TARGET = 5.0                                       # NEW: kV/cm

    # --- Applied field along the axis ----------------------------------------
    z = np.linspace(0.0, 6.0, 400)                       # cm from the tip apex
    E, err = calculate_applied_field(R_cm / 100.0, D_cm / 100.0, V_kV * 1e3, z / 100.0,
                                     return_boundary_error=True)
    E = E / 1e5                                          # V/m -> kV/cm
    print(f"Apex field: {E[0]:.1f} kV/cm   |   surface-potential error: {100 * err:.2f} %")

    # --- NEW: find the z where E(z) = 5 kV/cm --------------------------------
    def field_minus_target(z_value):
        E_value = calculate_applied_field(R_cm / 100.0, D_cm / 100.0, V_kV * 1e3, z_value / 100.0)
        return float(E_value) / 1e5 - E_TARGET

    z_target = brentq(field_minus_target, 0.0, 6.0, xtol=1e-6)    # cm
    print(f"E(z) = {E_TARGET} kV/cm at z = {z_target:.3f} cm from the tip apex")

    # --- Plot ------------------------------------------------------------------
    plt.figure(figsize=(8, 5))
    plt.semilogy(z, E, "b-", linewidth=2, label="Applied field $E_{ex}(z)$")
    plt.axhline(E_TARGET, color="gray", linestyle="--", linewidth=1,
                label=f"{E_TARGET:g} kV/cm")                                     # NEW
    plt.axvline(z_target, color="red", linestyle=":", linewidth=1.5)             # NEW
    plt.plot(z_target, E_TARGET, "ro", markersize=8,
             label=f"$E_{{ex}}$ = {E_TARGET:g} kV/cm at z = {z_target:.2f} cm")  # NEW
    plt.title(f"Applied field (CSM): V = {V_kV} kV, R = {R_cm} cm, D = {D_cm:g} cm")
    plt.xlabel("z from tip apex (cm)")
    plt.ylabel("E_applied (kV/cm)")
    plt.grid(True, which="both", alpha=0.4)
    plt.legend()
    plt.tight_layout()
    plt.show()
