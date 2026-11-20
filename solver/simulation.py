"""
Complete space-charge simulation of a rod-plane gap: successive corona bursts
that drift (the whole framework of the write-up in one place).

Model
-----
The space charge is a sum of clouds, one per corona burst k = 1, 2, ...

    rho(x, t) = sum_k rho_k(x - z_d,k(t) * e_z)

Every cloud is a cone with its apex at the rod tip apex when it is created, the
common cone angle theta_B, its own length L_k and the density rho_k(r) = A_k / (r + C)^B.
B and C are constants of the gap, found once by the calibration on the first streamer
(solver/calibration.py). The charge of a cloud follows from Gauss's law over its head,
Q_k = pi eps0 E_c (L_k tan(theta_B/2))^2 (optionally minus the charge of the older
clouds that lies inside the new cone), and A_k from Q_k through the volume integral
Q_k = A_k 2 pi (1 - cos(theta_B/2)) int_0^L_k r^2 / (r + C)^B dr.

1. Burst condition. The total field at the tip apex must first reach the inception
   (threshold) field E_inc, at an instant t*:

       E_total(0, t*) = V(t*) e_ex(0) + sum_{j<k} E_j(0; z_d,j(t*)) = E_inc

   and the burst follows after a time lag (the time a free electron needs to appear and the
   avalanche needs to grow), in one of two forms:
     - a constant delay: t_k = t* + tau (GapModel.time_lag);
     - an overvoltage that grows with the rate of rise of the tip field at t*: the burst
       happens when the tip field reaches E_inc + k (dE_tip/dt)^n (GapModel.overvoltage_k,
       overvoltage_n; SI units, field rate in V/(m s)).
   Without either the burst happens at t*. During the lag the clouds keep drifting.
   If a burst leaves the tip field above E_inc (it does not pull it back below the threshold),
   the threshold counts as reached at once, at the burst instant, and the next lag starts there.

   where e_ex is the applied field per volt and E_j = E_sp + E_I,rod + E_I,plane
   of cloud j. E_inc is the tip field at the first-streamer inception of the
   calibration case (Fig. 3: V = 27.5 kV, D = 80 cm).

2. Length of the new cloud: the LARGEST root of the head condition

       V(t_k) e_ex(L) + E_k(L; L) + sum_{j<k} E_j(L; z_d,j(t_k)) = E_c

   with the charge of the new cloud from Gauss's law for each trial L. On slow fronts
   the drifted apex of an older cloud lowers the field just in front of it; the new
   streamer is taken to cross that narrow dip and to stop where the head field falls
   below E_c for good. The width of every crossed dip is recorded (Cloud.dip_width).

   The older clouds are frozen during the burst (a streamer takes much less
   than a microsecond; the ions move micrometres in that time).

3. Drift. Between bursts every cloud moves as a rigid body:

       d z_d,k / dt = mu+ [ V(t) e_ex(z_c,k) + E_I,rod,k(z_c,k) + E_I,plane,k(z_c,k)
                            + sum_{j != k} E_j(z_c,k) ],      z_c,k = z_c0,k + z_d,k

   A cloud's own direct field E_sp,k is left out (it cannot push itself).

4. Absorption. The charge of a cloud that crosses the plane z = D is removed
   (the field integrals stop at the plane). When its apex reaches the plane the
   cloud has been absorbed completely and is dropped.

5. End. The simulation runs until t_end (or until max_bursts bursts happened). It also stops when the
   older clouds already hold all the Gauss charge of a new cone (with subtract_enclosed): the new
   cloud would get no charge, the tip field would stay above the threshold and bursts would repeat
   at the same instant without end; the successive-burst model no longer applies there
   (SimulationResult.stop_reason says why the run ended).

Inputs and outputs: theta_B, E_inc and the calibrated B, C are INPUTS of the model
(GapModel); every length L_k, charge Q_k and amplitude A_k, also of the first
streamer, are OUTPUTS.

Units: everything is SI (m, s, V, V/m, C, rad), z measured from the tip apex.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import cast

import numpy as np
from scipy.integrate import dblquad, solve_ivp
from scipy.optimize import brentq

from solver.applied_field import calculate_applied_field
from solver.calibration import gauss_amplitude, gauss_charge
from solver.drift import find_e_sp_zero
from solver.fields import calculate_e_plane_image, calculate_e_rod_image, calculate_e_sp
from solver.utilities import terminal_event


@dataclass
class GapModel:
    """The fixed physics of one gap: geometry, cone angle, thresholds, charge model, ion mobility."""
    R: float          # rod tip radius [m]
    D: float          # tip apex to plane [m]
    theta_B: float    # full cone angle [rad], common to every cloud
    E_c: float        # stability field [V/m]
    E_inc: float      # inception (threshold) field at the tip apex [V/m]; with a time lag: V_0 e_ex(0)
    B: float          # density exponent  } calibrated once on the first streamer
    C: float          # density offset [m]} (solver/calibration.py)
    mobility: float   # positive ion mobility mu+ [m^2/(V s)]
    rod_length: float | None = None   # modelled rod length for the applied field [m] (None = 5 * D)
    subtract_enclosed: bool = False   # Gauss charge of a new cloud minus the older charge inside its cone
    L_min: float = 5e-4               # range of the length search [m]
    L_max: float | None = None        # (None = D / 2)
    n_scan: int = 80                  # lengths sampled (log spaced) to find the roots of the head condition
    dip_warning: float = 3e-3         # warn when a crossed dip is wider than this [m]
    time_lag: float = 0.0             # tau: delay between reaching E_inc at the tip and the burst [s]
    overvoltage_k: float = 0.0        # rate-dependent lag: burst when the tip field reaches E_inc + k (dE/dt)^n
    overvoltage_n: float = 1.0

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
    A: float           # density amplitude A_k of this burst [C m^(B-3)]
    z_c0: float        # zero of its own E_sp before any drift [m]
    t_absorbed: float | None = None   # instant its apex reached the plane [s], None if never
    dip_width: float = 0.0             # total width of the low-field dips the streamer crossed [m]


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


def enclosed_charge(model, L_old, A_old, z_drift, L_new):
    """Charge [C] of an older cloud (length L_old, amplitude A_old, drifted by z_drift) that lies
    inside a new cone of length L_new with its apex at the tip (distance from the apex < L_new)."""
    m = model
    if L_new <= z_drift:
        return 0.0

    def r_max(theta):
        reach = -z_drift * np.cos(theta) + np.sqrt(max(L_new**2 - (z_drift * np.sin(theta)) ** 2, 0.0))
        return float(min(L_old, max(reach, 0.0)))

    value = dblquad(lambda r, theta: r**2 * np.sin(theta) / (r + m.C) ** m.B,
                    0.0, m.theta_B / 2, lambda _t: 0.0, r_max, epsrel=1e-6)[0]
    return 2.0 * np.pi * A_old * value


def new_cloud_charge(model, L, older):
    """Charge [C] and amplitude of a new cloud of length L: Gauss's law, optionally minus the older
    charge inside its cone. older: list of (L, A, z_drift)."""
    m = model
    Q = gauss_charge(m.E_c, L, m.theta_B)
    if m.subtract_enclosed:
        Q -= sum(enclosed_charge(m, L_j, A_j, d_j, L) for L_j, A_j, d_j in older)
        Q = max(Q, 1e-3 * gauss_charge(m.E_c, L, m.theta_B))
    return Q, gauss_amplitude(m.E_c, L, m.theta_B, m.B, m.C, Q=Q)


class SimulationCancelled(Exception):
    """Raised inside simulate() when its cancel() callback returns True."""


def solve_streamer_length(model, V, older, check=None):
    """
    Length L_k [m] of a new burst at voltage V [V]: the LARGEST root of the head condition
        V e_ex(L) + E_k(L; L) + sum_older E_j(L) = E_c,
    the charge of the new cloud (Gauss's law) recomputed for every trial L.

    older : list of (L, A, z_drift) of the clouds present at the burst
    check : optional function called before every trial length (simulate() uses it to cancel)
    Returns (L, Q, A, dip_width): dip_width is the total width of the regions below E_c that
    the streamer crosses on its way to L (0 when the first and the largest root coincide).
    """
    m = model
    L_max = 0.5 * m.D if m.L_max is None else m.L_max

    def head_minus_E_c(L):
        if check is not None:
            check()
        _, A = new_cloud_charge(m, L, older)
        field = V * float(m.applied_per_volt(L)) + cloud_field(m, L, A, L, 0.0)
        field += sum(cloud_field(m, L_j, A_j, L, d_j) for L_j, A_j, d_j in older)
        return float(field) - m.E_c

    lengths = np.geomspace(m.L_min, L_max, m.n_scan)
    values = np.array([head_minus_E_c(L) for L in lengths])
    above = np.nonzero(values > 0)[0]
    if len(above) == 0:
        raise RuntimeError(f"The head field is below E_c at every length (V = {V / 1e3:.1f} kV).")
    last = above[-1]
    if last == len(lengths) - 1:
        raise RuntimeError(f"The head field stays above E_c up to L = {L_max} m.")
    L_k = cast(float, brentq(head_minus_E_c, lengths[last], lengths[last + 1], xtol=1e-7))
    below = values[: last + 1] <= 0           # sampled lengths below E_c before the final crossing
    widths = np.diff(lengths[: last + 2])
    dip_width = float(np.sum(widths[below]))
    Q, A = new_cloud_charge(m, L_k, older)
    return L_k, Q, A, dip_width


@dataclass
class SimulationResult:
    """Clouds created during the run plus their drift history."""
    model: GapModel
    voltage: Callable[[float], float]  # V(t) [V]
    clouds: list = field(default_factory=list)
    t_end: float = 0.0
    stop_reason: str = "end time reached"   # or "burst limit reached", or the model limit (see simulate)
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


def simulate(model, voltage, t_end, max_bursts=None, t_start=0.0, max_step=None, verbose=False,
             on_progress=None, on_message=None, cancel=None):
    """
    Run the burst / drift / absorption loop from t_start to t_end.

    model      : GapModel
    voltage    : V(t) [V], function of the time since the impulse started
    t_end      : end of the simulation [s]
    max_bursts : stop right after this many bursts (None: no limit)
    max_step   : largest time step of the drift integration [s] (default (t_end - t_start)/400)
    on_progress: optional on_progress(t, text): the simulated time t [s] reached and what the
                 solver is doing (called often, from inside the drift integration)
    on_message : optional on_message(text) for the log lines (bursts, absorptions, warnings);
                 without it they are printed when verbose (warnings always)
    cancel     : optional cancel() -> bool, polled during the run; True raises SimulationCancelled

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
        if on_message is not None:
            on_message(text.strip())
        elif verbose:
            print(text)

    def check():
        if cancel is not None and cancel():
            raise SimulationCancelled("simulation cancelled")

    def report(t, text):
        if on_progress is not None:
            on_progress(t, text)

    pending = None                      # instant of a burst that is waiting for its time lag
    target = None                       # tip field a burst is waiting for (rate-dependent lag)
    while t_now < t_end:
        live = [c for c in result.clouds if c.t_absorbed is None]
        numbers = [c.number for c in live]

        # live is passed as a default argument so that each function keeps the list
        # of its own iteration (solve_ivp only calls them within this iteration anyway)
        def drift_velocity(t, y, live=live):
            check()
            report(t, f"drift of {len(live)} cloud(s)" if live else "rise of the tip field to inception")
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

        def tip_field(t, y, live=live):
            E = voltage(t) * e_tip
            for i, c in enumerate(live):
                E += cloud_field(m, c.L, c.A, 0.0, y[i])
            return E

        def tip_minus_E_inc(t, y, threshold=(m.E_inc if target is None else target)):
            return tip_field(t, y) - threshold

        def apex_at_plane(i):
            def event(_t, y):
                return y[i] - m.D
            return terminal_event(event)

        # The event below needs an UPWARD crossing of the threshold. When the tip field is already
        # above it (a burst that did not pull the tip field back below E_inc), it has been reached now.
        burst_now = False
        y_now = [drifts[n] for n in numbers] if live else [0.0]
        if pending is None and tip_field(t_now, y_now) >= (m.E_inc if target is None else target):
            if m.overvoltage_k > 0 and target is None:   # wait for the overvoltage, from the rate now
                # fixed 10 ns: much shorter than the field changes, long enough that the quadrature
                # noise (about 1e-5 of the field) does not enter the difference
                dt = 1e-8
                speeds = drift_velocity(t_now, y_now)
                y_next = [y + v * dt for y, v in zip(y_now, speeds)] if live else y_now
                rate = (tip_field(t_now + dt, y_next) - tip_field(t_now, y_now)) / dt
                target = m.E_inc + m.overvoltage_k * max(rate, 0.0) ** m.overvoltage_n
                log(f"  tip field already above E_inc at t = {t_now * 1e6:.3f} us; burst at {target / 1e5:.2f} kV/cm")
                continue
            if target is None and m.time_lag > 0:
                pending = t_now + m.time_lag
                log(f"  tip field already above E_inc at t = {t_now * 1e6:.3f} us; burst after {m.time_lag * 1e6:.3f} us")
                continue
            target = None
            burst_now = True
        if not burst_now:
            # while a burst waits for its time lag, only absorption can interrupt the drift
            events = ([terminal_event(tip_minus_E_inc)] if pending is None else []) + [apex_at_plane(i) for i in range(len(live))]
            n_tip = 1 if pending is None else 0
            t_target = t_end if pending is None else min(pending, t_end)
            y0 = [drifts[n] for n in numbers] if live else [0.0]
            if t_target <= t_now:
                t_target = t_now + 1e-15
            t_seg0 = t_now
            solution = solve_ivp(drift_velocity, (t_now, t_target), y0, events=events or None, dense_output=True,
                                 rtol=1e-6, atol=1e-12, max_step=max_step)
            if not solution.success:
                raise RuntimeError(f"Drift integration failed: {solution.message}")
            t_stop = float(solution.t[-1])
            if live:
                result._segments.append((t_now, t_stop, solution, numbers))
                for i, n in enumerate(numbers):
                    drifts[n] = float(solution.y[i, -1])
            t_now = t_stop

            t_events = solution.t_events if solution.t_events is not None else []
            absorbed = [i for i in range(len(live)) if len(t_events[n_tip + i]) > 0]
            for i in absorbed:
                live[i].t_absorbed = t_now
                log(f"  cloud {live[i].number} absorbed by the plane at t = {t_now * 1e6:.2f} us")

            if pending is None:
                if len(t_events[0]) == 0:
                    if not absorbed:
                        break                # reached t_end
                    continue
                if m.overvoltage_k > 0 and target is None:   # threshold reached: wait for the overvoltage
                    dt = max(1e-10, 1e-3 * (t_now - t_seg0))
                    if live and t_now - dt >= t_seg0:
                        rate = (tip_field(t_now, solution.sol(t_now)) - tip_field(t_now - dt, solution.sol(t_now - dt))) / dt
                    else:
                        rate = (voltage(t_now) - voltage(t_now - dt)) / dt * e_tip
                    target = m.E_inc + m.overvoltage_k * max(rate, 0.0) ** m.overvoltage_n
                    log(f"  tip field reached E_inc at t = {t_now * 1e6:.3f} us; burst at {target / 1e5:.2f} kV/cm")
                    continue
                target = None
                if m.time_lag > 0:           # threshold reached: the burst follows after the time lag
                    pending = t_now + m.time_lag
                    log(f"  tip field reached E_inc at t = {t_now * 1e6:.3f} us; burst after {m.time_lag * 1e6:.3f} us")
                    continue
            else:
                if absorbed and t_now < pending:
                    continue                 # an absorption interrupted the waiting time
                if t_now < pending:
                    break                    # t_end reached while waiting
                pending = None

        # ---- a new burst at t_now --------------------------------------------
        V_now = voltage(t_now)
        older = [(c.L, c.A, drifts[c.number]) for c in result.clouds if c.t_absorbed is None]
        report(t_now, f"burst {len(result.clouds) + 1}: solving the streamer length")
        L, Q, A, dip_width = solve_streamer_length(m, V_now, older, check=check)
        if m.subtract_enclosed and older and Q <= 1.001e-3 * gauss_charge(m.E_c, L, m.theta_B):
            # The older clouds already hold all the Gauss charge of the new cone, so the new cloud would get
            # no charge, would not lower the tip field, and bursts would repeat at the same instant without
            # end: beyond this point the tip field no longer falls below the threshold between bursts and
            # the successive-burst model does not apply.
            result.t_end = t_now
            result.stop_reason = (f"model limit at t = {t_now * 1e6:.3f} us: the older clouds already fill "
                                  f"the cone of burst {len(result.clouds) + 1} (no charge left for it)")
            log("  stopped: " + result.stop_reason)
            break
        z_c0 = find_e_sp_zero(m.R, L, m.theta_B, A, m.B, m.C)
        cloud = Cloud(number=len(result.clouds) + 1, t_birth=t_now, V_birth=V_now,
                      L=L, Q=Q, A=A, z_c0=z_c0, dip_width=dip_width)
        if dip_width > m.dip_warning:
            warning = f"  warning: burst {cloud.number} crossed {dip_width * 100:.2f} cm of field below E_c"
            if on_message is not None:
                on_message(warning.strip())
            else:
                print(warning)
        result.clouds.append(cloud)
        drifts[cloud.number] = 0.0
        log(f"  burst {cloud.number}: t = {t_now * 1e6:.3f} us, V = {V_now / 1e3:.2f} kV, "
            f"L = {L * 100:.3f} cm, Q = {Q * 1e9:.2f} nC, dip crossed {dip_width * 100:.2f} cm")
        if max_bursts is not None and len(result.clouds) >= max_bursts:
            result.t_end = t_now
            result.stop_reason = "burst limit reached"
            break

    return result
