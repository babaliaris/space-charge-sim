"""
Runs one complete simulation for the GUI (no Qt in here, so it can also run headless and
inside the worker processes).

Stages
------
1. Applied field (Charge Simulation Method): e_ex(z) per volt along z and at the tip;
   the time-lag law V1 = V0 + k (dV/dt)^n turned into tip fields (E_0, k_SI).
2. Cone angle theta_B: given, or solved from the head condition on a reference streamer.
3. Successive bursts and drift (solver.simulation.simulate).
4. Post-processing: V(t), tip field, cloud positions and charge against time, and the
   field profiles E(z) with their components at chosen instants (in parallel).

Inputs are in engineering units (app/inputs.py); they are converted to SI once here and the
results are converted back to engineering units once, at the end.
"""

import math
import multiprocessing
import time
import traceback
import warnings
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass, field

import numpy as np
from scipy.integrate import IntegrationWarning

from solver.applied_field import calculate_applied_field
from solver.fields import calculate_e_plane_image, calculate_e_rod_image, calculate_e_sp
from solver.simulation import GapModel, SimulationCancelled, simulate
from solver.theta_b import solve_theta_b
from solver.utilities import double_exponential_parameters, impulse_voltage

from app.inputs import FIELDS, THETA_SOLVE

CM, KV, KV_PER_CM, US, NC = 1e-2, 1e3, 1e5, 1e-6, 1e-9
COMPONENTS = ["E_ex", "E_sp", "E_I,rod", "E_I,plane", "E_total"]

# share of the progress bar given to each stage
STAGES = [("Applied field (CSM)", 0.03), ("Cone angle θ_B", 0.07), ("Bursts and drift", 0.55), ("Fields and profiles", 0.35)]


class Cancelled(Exception):
    pass


@dataclass
class RunResult:
    name: str
    inputs: dict
    derived: dict                    # solved / converted quantities, engineering units
    clouds: list                     # one dict per burst
    t_us: np.ndarray
    V_kV: np.ndarray
    E_tip_kVcm: np.ndarray
    Q_total_nC: np.ndarray
    zd_cm: np.ndarray                # (clouds, times) drift, NaN where the cloud does not exist
    snap_t_us: np.ndarray
    snap_labels: list
    z_cm: np.ndarray
    profiles: dict                   # component -> (snapshots, z) [kV/cm]
    log: list = field(default_factory=list)
    elapsed_s: float = 0.0


# ----------------------------------------------------------------------------- worker processes
def _components(model, clouds, z):
    """E_sp, E_I,rod, E_I,plane [V/m] at z of clouds given as (L, A, z_drift)."""
    m = model
    z = np.asarray(z, dtype=float)
    sp, rod, plane = np.zeros_like(z), np.zeros_like(z), np.zeros_like(z)
    for L, A, zd in clouds:
        sp = sp + calculate_e_sp(z, m.R, L, m.theta_B, A, m.B, m.C, z_drift=zd, z_cut=m.D)
        rod = rod + calculate_e_rod_image(z, m.R, L, m.theta_B, A, m.B, m.C, z_drift=zd, z_cut=m.D)
        plane = plane + calculate_e_plane_image(z, m.D, m.R, L, m.theta_B, A, m.B, m.C, z_drift=zd, z_cut=m.D)
    return sp, rod, plane


def _job(args):
    """One parallel job: a list of (clouds, z) items -> list of (E_sp, E_I,rod, E_I,plane)."""
    model, items = args
    warnings.simplefilter("ignore", IntegrationWarning)
    return [_components(model, clouds, z) for clouds, z in items]


def _run_jobs(model, items, workers, cancel, tick):
    """Evaluate items [(clouds, z), ...] in parallel; tick(done, total) after each item."""
    results = [None] * len(items)
    if not items:
        return results
    if workers <= 1:
        for i, it in enumerate(items):
            if cancel():
                raise Cancelled
            results[i] = _job((model, [it]))[0]
            tick(i + 1, len(items))
        return results
    size = max(1, len(items) // (workers * 6))
    chunks = [list(range(i, min(i + size, len(items)))) for i in range(0, len(items), size)]
    pool = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"))
    try:
        pending = {pool.submit(_job, (model, [items[i] for i in idx])): idx for idx in chunks}
        done_count = 0
        while pending:
            finished, _ = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
            if cancel():
                raise Cancelled
            for fut in finished:
                idx = pending.pop(fut)
                for i, r in zip(idx, fut.result()):
                    results[i] = r
                done_count += len(idx)
                tick(done_count, len(items))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return results


# ----------------------------------------------------------------------------- the run
def run(v, name="run", progress=None, message=None, cancel=None):
    """
    v        : inputs (engineering units, keys of app/inputs.py)
    progress : progress(fraction 0..1, stage number 1..4, stage name, detail text)
    message  : message(text) for the log
    cancel   : cancel() -> bool
    Returns a RunResult; raises Cancelled if cancelled.
    """
    progress = progress or (lambda *a: None)
    cancel = cancel or (lambda: False)
    log = []

    def say(text):
        log.append(text)
        if message:
            message(text)

    def stage(i, frac, detail):
        start = sum(w for _, w in STAGES[:i])
        progress(min(1.0, start + STAGES[i][1] * max(0.0, min(1.0, frac))), i + 1, STAGES[i][0], detail)

    t_clock = time.time()
    warnings.simplefilter("ignore", IntegrationWarning)

    # ---- inputs -> SI ------------------------------------------------------------------
    R, D = v["R_cm"] * CM, v["D_cm"] * CM
    rod_length = v["rod_length_cm"] * CM if v["rod_length_cm"] > 0 else 5.0 * D
    E_c = v["E_c_kVcm"] * KV_PER_CM
    B, C = float(v["B"]), v["C_cm"] * CM
    mobility = v["mobility_cm2_Vs"] * 1e-4
    crest, front, half = v["crest_kV"] * KV, v["front_us"] * US, v["half_us"] * US
    t_end = front if v.get("until_crest", False) else v["t_end_us"] * US

    # ---- 1. applied field --------------------------------------------------------------
    stage(0, 0.0, "solving the CSM charges of the rod")
    say(f"Stage 1/4: applied field (CSM), D = {v['D_cm']:g} cm, rod length {rod_length / CM:g} cm")
    e_tip = float(calculate_applied_field(R, D, 1.0, 0.0, rod_length=rod_length))
    D_lag = v["lag_ref_D_cm"] * CM
    e_lag = float(calculate_applied_field(R, D_lag, 1.0, 0.0, rod_length=5.0 * D_lag))
    E0 = v["V0_kV"] * KV * e_lag
    n = float(v["lag_n"])
    k_SI = e_lag * KV * v["lag_k"] / (e_lag * 1e9) ** n
    z_top = min(v["z_max_cm"] * CM, D * (1 - 1e-4))
    z = np.geomspace(v["z_min_cm"] * CM, z_top, int(v["n_z"]))
    e_z = np.asarray(calculate_applied_field(R, D, 1.0, z, rod_length=rod_length), dtype=float)
    say(f"  e_ex(0) = {e_tip / 100:.4g} 1/cm; threshold E0 = {E0 / KV_PER_CM:.2f} kV/cm "
        f"(V0 = {E0 / e_tip / KV:.3f} kV in this gap), k_SI = {k_SI:.4g}")
    stage(0, 1.0, "done")
    if cancel():
        raise Cancelled

    # ---- 2. cone angle -----------------------------------------------------------------
    if v["theta_mode"] == THETA_SOLVE:
        stage(1, 0.1, "head condition on the reference streamer (root finding)")
        say(f"Stage 2/4: solving θ_B on the reference streamer (D = {v['ref_D_cm']:g} cm, "
            f"V = {v['ref_V_kV']:g} kV, L = {v['ref_L_cm']:g} cm)")
        try:
            theta_B = solve_theta_b(R, v["ref_D_cm"] * CM, v["ref_V_kV"] * KV, v["ref_L_cm"] * CM, E_c, B, C,
                                    rod_length=5.0 * v["ref_D_cm"] * CM)
        except ValueError as exc:
            raise RuntimeError(f"θ_B has no solution for this reference streamer: {exc}") from None
        say(f"  θ_B = {math.degrees(theta_B):.3f}°")
    else:
        theta_B = math.radians(v["theta_deg"])
        say(f"Stage 2/4: θ_B = {v['theta_deg']:g}° (given)")
    stage(1, 1.0, f"θ_B = {math.degrees(theta_B):.2f}°")
    if cancel():
        raise Cancelled

    # ---- 3. bursts and drift -----------------------------------------------------------
    model = GapModel(R, D, theta_B, E_c, E0, B, C, mobility, rod_length=rod_length,
                     subtract_enclosed=bool(v["subtract_enclosed"]), overvoltage_k=k_SI, overvoltage_n=n,
                     n_scan=int(v["n_scan"]), L_max=(v["L_max_cm"] * CM if v["L_max_cm"] > 0 else None))
    alpha, beta, kv = double_exponential_parameters(front, half)

    def voltage(t):
        return impulse_voltage(t, crest, alpha, beta, kv)

    say(f"Stage 3/4: bursts and drift, {v['crest_kV']:g} kV {v['front_us']:g}/{v['half_us']:g} µs, "
        f"until {t_end / US:g} µs" + (" (the crest)" if v.get("until_crest", False) else ""))
    bursts = [0]

    def on_progress(t, text):
        stage(2, t / t_end, f"t = {t / US:.3f} of {t_end / US:g} µs · {bursts[0]} burst(s) · {text}")

    def on_message(text):
        if text.startswith("burst"):
            bursts[0] += 1
        say("  " + text)

    try:
        sim = simulate(model, voltage, t_end, max_bursts=(int(v["max_bursts"]) or None),
                       max_step=(v["max_step_us"] * US if v["max_step_us"] > 0 else None),
                       on_progress=on_progress, on_message=on_message, cancel=cancel)
    except SimulationCancelled:
        raise Cancelled from None
    t_stop = sim.t_end
    if not sim.clouds:
        say("  no burst: the tip field never reached the inception condition")
    if sim.stop_reason == "burst limit reached":
        say(f"  stopped after {len(sim.clouds)} burst(s) at t = {t_stop / US:.3f} µs (input 'Stop after bursts')")
    stage(2, 1.0, f"{len(sim.clouds)} burst(s)")

    # ---- 4. time series and profiles ---------------------------------------------------
    say("Stage 4/4: tip field, cloud positions and field profiles")
    eps = 1e-9 * max(t_stop, 1e-12)
    t = np.linspace(0.0, t_stop, int(v["n_time"]))
    for c in sim.clouds:                               # resolve the jump of the tip field at each burst
        t = np.concatenate([t, [max(0.0, c.t_birth - eps), c.t_birth]])
    t = np.unique(t)

    def state(tt):
        return [(c.L, c.A, sim.z_drift(c, tt)) for c in sim.alive(tt)]

    snaps = list(np.linspace(0.0, t_stop, int(v["n_snap"]) + 1)[1:]) if int(v["n_snap"]) > 1 else [t_stop]
    labels = {}
    for c in sim.clouds:
        tb = min(c.t_birth + eps, t_stop)
        snaps.append(tb)
        labels[tb] = f"just after burst {c.number}"
    snaps = sorted(set(snaps))
    zero = np.array([0.0])
    # one item per z chunk for the profiles, so that the work spreads over the processes
    chunk = max(5, len(z) // 12)
    prof_items = []
    for si, tt in enumerate(snaps):
        st = state(tt)
        for j in range(0, len(z), chunk):
            prof_items.append((si, j, (st, z[j:j + chunk])))
    items = [(state(tt), zero) for tt in t] + [it for _, _, it in prof_items]
    work = [(i, it) for i, it in enumerate(items) if it[0]]        # skip instants without clouds

    def tick(done, total):
        stage(3, done / total, f"{done} of {total} field evaluations ({int(v['workers'])} process(es))")

    stage(3, 0.0, "starting the worker processes")
    values = _run_jobs(model, [it for _, it in work], int(v["workers"]), cancel, tick)
    out = [None] * len(items)
    for (i, _), val in zip(work, values):
        out[i] = val

    V_t = np.array([voltage(tt) for tt in t])
    E_tip = V_t * e_tip
    for i in range(len(t)):
        if out[i] is not None:
            E_tip[i] += sum(float(c[0]) for c in out[i])
    nt = len(t)
    prof = {k: np.zeros((len(snaps), len(z))) for k in COMPONENTS}
    for (si, j, _), val in zip(prof_items, out[nt:]):
        if val is not None:
            sl = slice(j, j + len(val[0]))
            prof["E_sp"][si, sl], prof["E_I,rod"][si, sl], prof["E_I,plane"][si, sl] = val
    for si, tt in enumerate(snaps):
        prof["E_ex"][si] = voltage(tt) * e_z
    prof["E_total"] = prof["E_ex"] + prof["E_sp"] + prof["E_I,rod"] + prof["E_I,plane"]

    zd = np.full((len(sim.clouds), nt), np.nan)
    for ci, c in enumerate(sim.clouds):
        for i, tt in enumerate(t):
            if c.t_birth <= tt and (c.t_absorbed is None or tt < c.t_absorbed):
                zd[ci, i] = sim.z_drift(c, tt)
    Q_t = np.array([sim.total_charge(tt) for tt in t])

    clouds = [dict(number=c.number, t_birth_us=c.t_birth / US, V_kV=float(c.V_birth) / KV, L_cm=float(c.L) / CM, Q_nC=float(c.Q) / NC,
                   A_SI=float(c.A), z_c0_cm=float(c.z_c0) / CM, t_absorbed_us=(None if c.t_absorbed is None else c.t_absorbed / US),
                   dip_cm=c.dip_width / CM) for c in sim.clouds]
    derived = {"θ_B [deg]": math.degrees(theta_B), "E0 = V0 e_ex(0) (threshold at the tip) [kV/cm]": E0 / KV_PER_CM,
               "V0 in this gap [kV]": E0 / e_tip / KV, "k_SI (E_req = E0 + k_SI (dE/dt)^n)": k_SI,
               "e_ex(0) (applied field per volt at the tip) [1/cm]": e_tip / 100,
               "rod length used [cm]": rod_length / CM, "impulse alpha [1/µs]": float(alpha) * US,
               "impulse beta [1/µs]": float(beta) * US, "impulse k [-]": float(kv), "simulated until [µs]": t_stop / US, "stopped because": sim.stop_reason,
               "bursts": len(sim.clouds)}
    elapsed = time.time() - t_clock
    say(f"Done in {elapsed:.1f} s: {len(sim.clouds)} burst(s)")
    stage(3, 1.0, "done")
    return RunResult(name=name, inputs=dict(v), derived=derived, clouds=clouds, t_us=t / US, V_kV=V_t / KV,
                     E_tip_kVcm=E_tip / KV_PER_CM, Q_total_nC=Q_t / NC, zd_cm=zd / CM,
                     snap_t_us=np.array(snaps) / US, snap_labels=[labels.get(s, "") for s in snaps],
                     z_cm=z / CM, profiles={k: a / KV_PER_CM for k, a in prof.items()}, log=log, elapsed_s=elapsed)


def input_rows(result):
    """(label, value, unit) of every input and derived value, for the exports."""
    rows = [(FIELDS[k].label, result.inputs[k], FIELDS[k].unit) for k in FIELDS if k in result.inputs]
    rows += [(k, val, "") for k, val in result.derived.items()]
    return rows


def run_in_process(values, name, queue, cancel_event):
    """Entry point of the separate process the GUI starts for a run: the window stays responsive and
    Cancel works at once. Sends ("progress", args), ("message", text) and finally one of
    ("finished", RunResult), ("cancelled", None), ("failed", traceback text) through the queue."""
    last = [0.0, 0]

    def progress(frac, stage, stage_name, detail):
        now = time.time()
        if now - last[0] > 0.1 or stage != last[1] or frac >= 1.0:   # at most 10 updates per second
            last[0], last[1] = now, stage
            queue.put(("progress", (frac, stage, stage_name, detail)))

    try:
        result = run(values, name, progress, lambda text: queue.put(("message", text)), cancel_event.is_set)
        queue.put(("finished", result))
    except Cancelled:
        queue.put(("cancelled", None))
    except Exception:
        queue.put(("failed", traceback.format_exc()))
