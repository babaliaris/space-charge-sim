"""
Complete space-charge simulation of a rod-plane gap: successive corona bursts
that drift (the whole framework of the write-up in one place).

Model
-----
The space charge is a sum of clouds, one per corona burst k = 1, 2, ...

    rho(x, t) = sum_k rho_k(x - z_d,k(t) * e_z)

Every cloud is a cone with its apex at the rod tip apex when it is created, the
common cone angle theta_B, its own length L_k and the density
rho_k(r) = A_k / (r + C)^B. Its charge Q_k follows from Gauss's law at its head
(E_c over the head disc) and A_k from Q_k, exactly as for the first streamer.

1. Burst condition. A new burst k happens at the first instant t_k at which the
   total field at the tip apex reaches the inception field:

       E_total(0, t_k) = V(t_k) e_ex(0) + sum_{j<k} E_j(0; z_d,j(t_k)) = E_inc

   where e_ex is the applied field per volt and E_j = E_sp + E_I,rod + E_I,plane
   of cloud j. E_inc is the tip field at the first-streamer inception of the
   calibration case (Fig. 3: V = 27.5 kV, D = 80 cm).

2. Length of the new cloud. The streamer grows while the field at its head stays
   above E_c, so L_k is the length beyond which the head field stays below E_c
   (the last crossing; short dips close to the tip are crossed):

       V(t_k) e_ex(L_k) + E_k(L_k; L_k) + sum_{j<k} E_j(L_k; z_d,j(t_k)) = E_c

   The older clouds are frozen during the burst (a streamer takes much less
   than a microsecond; the ions move micrometres in that time).

3. Drift. Between bursts every cloud moves as a rigid body:

       d z_d,k / dt = mu+ [ V(t) e_ex(z_c,k) + E_I,rod,k(z_c,k) + E_I,plane,k(z_c,k)
                            + sum_{j != k} E_j(z_c,k) ],      z_c,k = z_c0,k + z_d,k

   A cloud's own direct field E_sp,k is left out (it cannot push itself).

4. Absorption. The charge of a cloud that crosses the plane z = D is removed
   (the field integrals stop at the plane). When its apex reaches the plane the
   cloud has been absorbed completely and is dropped.

5. End. The simulation runs until t_end (or until max_bursts bursts happened).

Inputs and outputs: theta_B and E_inc are INPUTS of the model (GapModel); every
streamer length L_k, also the first one, is an OUTPUT of step 2. When theta_B is
not known (the paper gives L_cs = 2.7 cm for Fig. 3 but not theta_B),
GapModel.calibrated recovers it once by inverting the head condition for a known
first streamer, and sets E_inc = V_ref e_ex(0); the first burst of that case then
gives back L_ref.

Units: everything is SI (m, s, V, V/m, C, rad), z measured from the tip apex.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from solver.applied_field import calculate_applied_field
from solver.drift import find_e_sp_zero
from solver.fields import calculate_e_plane_image, calculate_e_rod_image, calculate_e_sp
from solver.theta_b import solve_theta_b
from solver.utilities import (
    calculate_A_from_charge,
    calculate_qcs_from_field,
    terminal_event,
)


@dataclass
class GapModel:
    """The fixed physics of one gap: geometry, cone angle, thresholds, ion mobility."""
    R: float          # rod tip radius [m]
    D: float          # tip apex to plane [m]
    theta_B: float    # full cone angle [rad], common to every cloud
    E_c: float        # average streamer field [V/m]
    E_inc: float      # inception field at the tip apex [V/m]
    B: float          # density exponent
    C: float          # density offset [m]
    mobility: float   # positive ion mobility mu+ [m^2/(V s)]
    rod_length: float | None = None   # modelled rod length for the applied field [m] (None = 5 * D)

    @classmethod
    def calibrated(cls, R, D, E_c, B, C, mobility, V_ref, L_ref, D_ref, rod_length=None, rod_length_ref=None):
        """theta_B and E_inc from a known first streamer (V_ref, L_ref) in a gap D_ref.

        Use this only when theta_B is not known: it inverts the head condition once.
        Otherwise build GapModel directly with your own theta_B and E_inc.
        rod_length_ref is the rod length of the reference gap, rod_length that of D
        (None = 5 * gap).
        """
        theta_B = solve_theta_b(R, D_ref, V_ref, L_ref, E_c, B, C, rod_length=rod_length_ref)
        E_inc = V_ref * float(calculate_applied_field(R, D_ref, 1.0, 0.0, rod_length=rod_length_ref))
        return cls(R, D, theta_B, E_c, E_inc, B, C, mobility, rod_length)

    def applied_per_volt(self, z):
        """Applied field per volt e_ex(z) [1/m]. The applied field is V(t) * e_ex(z)."""
        return calculate_applied_field(self.R, self.D, 1.0, z, rod_length=self.rod_length)


@dataclass
class Cloud:
    """The space charge left by one corona burst."""
    number: int        # k = 1, 2, ...
    t_birth: float     # burst instant t_k [s]
    V_birth: float     # voltage at the burst [V]
    L: float           # length L_k [m]
    Q: float           # charge Q_k [C]
    A: float           # density amplitude A_k [C m^(B-3)]
    z_c0: float        # zero of its own E_sp before any drift [m]
    t_absorbed: float | None = None   # instant its apex reached the plane [s], None if never


def cloud_charge_and_amplitude(model, L):
    """Q_k [C] (Gauss's law at the head) and A_k for a cloud of length L [m]."""
    Q = calculate_qcs_from_field(model.E_c, L_cs_m=L, theta_B_rad=model.theta_B)
    A = calculate_A_from_charge(Q, model.B, model.C, L_cs_m=L, theta_B_rad=model.theta_B)
    return Q, A


def cloud_field(model, L, A, z, z_drift, with_direct=True):
    """E_sp + E_I,rod + E_I,plane [V/m] of one cloud drifted by z_drift, at z (array or float).

    with_direct=False leaves out E_sp (used for the cloud's own driving field).
    The charge beyond the plane (absorbed) is left out.
    """
    m = model
    total = (calculate_e_rod_image(z, m.R, L, m.theta_B, A, m.B, m.C, z_drift=z_drift, z_cut=m.D)
             + calculate_e_plane_image(z, m.D, m.R, L, m.theta_B, A, m.B, m.C, z_drift=z_drift, z_cut=m.D))
    if with_direct:
        total = total + calculate_e_sp(z, m.R, L, m.theta_B, A, m.B, m.C, z_drift=z_drift, z_cut=m.D)
    return total


def solve_streamer_length(model, V, history, L_min=5e-4, L_max=None, n_scan=60):
    """
    Length L_k [m] of a new burst: the length beyond which the head field
        V e_ex(L) + E_k(L; L) + history(L)
    stays below E_c for good (the LAST crossing of E_c).

    Close to the tip the history can make a narrow dip in the head field (the
    drifted apex of an older cloud is its densest point). The streamer is taken
    to cross such short dips, so the last crossing, not the first, is the length.

    V       : voltage at the burst [V]
    history : function z -> field [V/m] of all older clouds at their present drift
    Returns (L, Q, A).
    """
    m = model
    if L_max is None:
        L_max = 0.5 * m.D

    def head_field_minus_E_c(L):
        _, A = cloud_charge_and_amplitude(m, L)
        return (V * float(m.applied_per_volt(L)) + cloud_field(m, L, A, L, 0.0)
                + history(L) - m.E_c)

    lengths = np.geomspace(L_min, L_max, n_scan)
    g = np.array([head_field_minus_E_c(L) for L in lengths])
    above = np.nonzero(g > 0)[0]
    if len(above) == 0:
        raise RuntimeError("The head field is below E_c at every length.")
    last = above[-1]
    if last == len(lengths) - 1:
        raise RuntimeError(f"The head field stays above E_c up to L = {L_max} m.")
    L_k = cast(float, brentq(head_field_minus_E_c, lengths[last], lengths[last + 1], xtol=1e-7))
    Q, A = cloud_charge_and_amplitude(m, L_k)
    return L_k, Q, A


@dataclass
class SimulationResult:
    """Clouds created during the run plus their drift history."""
    model: GapModel
    voltage: Callable[[float], float]  # V(t) [V]
    clouds: list = field(default_factory=list)
    t_end: float = 0.0
    _segments: list = field(default_factory=list)   # (t0, t1, solution, cloud numbers)

    def z_drift(self, cloud, t):
        """Drift [m] of a cloud at time t (0 before its birth, frozen after absorption)."""
        if t <= cloud.t_birth:
            return 0.0
        if cloud.t_absorbed is not None and t >= cloud.t_absorbed:
            return self.model.D
        for t0, t1, solution, numbers in self._segments:
            if t0 <= t <= t1 and cloud.number in numbers:
                return float(solution.sol(t)[numbers.index(cloud.number)])
        raise ValueError(f"t = {t} s lies outside the simulated time.")

    def alive(self, t):
        """Clouds that exist at time t (born, not yet absorbed)."""
        return [c for c in self.clouds
                if c.t_birth <= t and (c.t_absorbed is None or t < c.t_absorbed)]

    def space_charge_field(self, z, t):
        """Field [V/m] of all clouds at time t (direct + images)."""
        total = np.zeros_like(np.atleast_1d(np.asarray(z, dtype=float)))
        for c in self.alive(t):
            total = total + cloud_field(self.model, c.L, c.A, z, self.z_drift(c, t))
        return total if np.ndim(z) else float(total[0])

    def total_field(self, z, t):
        """E_total(z, t) [V/m] = applied + every cloud."""
        return self.voltage(t) * self.model.applied_per_volt(z) + self.space_charge_field(z, t)

    def tip_field(self, t):
        """E_total at the tip apex [V/m]."""
        return float(np.atleast_1d(self.total_field(0.0, t))[0])

    def total_charge(self, t):
        """Charge of all clouds present at t [C] (absorption by the plane not subtracted
        for partly absorbed clouds; use it while every cloud is inside the gap)."""
        return sum(c.Q for c in self.alive(t))


def simulate(model, voltage, t_end, max_bursts=None, t_start=0.0, max_step=None, verbose=False):
    """
    Run the burst / drift / absorption loop from t_start to t_end.

    model      : GapModel
    voltage    : V(t) [V], function of the time since the impulse started
    t_end      : end of the simulation [s]
    max_bursts : stop right after this many bursts (None: no limit)
    max_step   : largest time step of the drift integration [s] (default (t_end - t_start)/400)

    Returns a SimulationResult.
    """
    m = model
    result = SimulationResult(model=m, voltage=voltage, t_end=t_end)
    e_tip = float(m.applied_per_volt(0.0))
    if max_step is None:
        max_step = (t_end - t_start) / 400.0
    t_now = t_start
    drifts = {}                         # cloud number -> drift at t_now

    def log(text):
        if verbose:
            print(text)

    while t_now < t_end:
        live = [c for c in result.clouds if c.t_absorbed is None]
        numbers = [c.number for c in live]

        # live is passed as a default argument so that each function keeps the list
        # of its own iteration (solve_ivp only calls them within this iteration anyway)
        def drift_velocity(t, y, live=live):
            V = voltage(t)
            speeds = []
            for i, c in enumerate(live):
                z_c = min(c.z_c0 + y[i], m.D * (1 - 1e-6))
                E = V * float(m.applied_per_volt(z_c)) + cloud_field(m, c.L, c.A, z_c, y[i], with_direct=False)
                for j, other in enumerate(live):
                    if j != i:
                        E += cloud_field(m, other.L, other.A, z_c, y[j])
                speeds.append(m.mobility * E)
            return speeds if live else [0.0]

        def tip_minus_E_inc(t, y, live=live):
            E = voltage(t) * e_tip
            for i, c in enumerate(live):
                E += cloud_field(m, c.L, c.A, 0.0, y[i])
            return E - m.E_inc

        def apex_at_plane(i):
            def event(_t, y):
                return y[i] - m.D
            return terminal_event(event)

        events = [terminal_event(tip_minus_E_inc)] + [apex_at_plane(i) for i in range(len(live))]
        y0 = [drifts[n] for n in numbers] if live else [0.0]
        solution = solve_ivp(drift_velocity, (t_now, t_end), y0, events=events, dense_output=True,
                             rtol=1e-6, atol=1e-12, max_step=max_step)
        if not solution.success:
            raise RuntimeError(f"Drift integration failed: {solution.message}")
        t_stop = float(solution.t[-1])
        if live:
            result._segments.append((t_now, t_stop, solution, numbers))
            for i, n in enumerate(numbers):
                drifts[n] = float(solution.y[i, -1])
        t_now = t_stop

        absorbed = [i for i in range(len(live)) if len(solution.t_events[1 + i]) > 0]
        for i in absorbed:
            live[i].t_absorbed = t_now
            log(f"  cloud {live[i].number} absorbed by the plane at t = {t_now * 1e6:.2f} us")

        if len(solution.t_events[0]) == 0:
            if not absorbed:
                break                    # reached t_end
            continue

        # ---- a new burst at t_now --------------------------------------------
        V_now = voltage(t_now)
        older = [c for c in result.clouds if c.t_absorbed is None]

        def history(z, older=older):
            return sum(cloud_field(m, c.L, c.A, z, drifts[c.number]) for c in older)

        L, Q, A = solve_streamer_length(m, V_now, history)
        z_c0 = find_e_sp_zero(m.R, L, m.theta_B, A, m.B, m.C)
        cloud = Cloud(number=len(result.clouds) + 1, t_birth=t_now, V_birth=V_now,
                      L=L, Q=Q, A=A, z_c0=z_c0)
        result.clouds.append(cloud)
        drifts[cloud.number] = 0.0
        log(f"  burst {cloud.number}: t = {t_now * 1e6:.3f} us, V = {V_now / 1e3:.2f} kV, "
            f"L = {L * 100:.3f} cm, Q = {Q * 1e9:.2f} nC")
        if max_bursts is not None and len(result.clouds) >= max_bursts:
            result.t_end = t_now
            break

    return result
