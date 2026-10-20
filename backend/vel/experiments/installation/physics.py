"""Closed-form models of experiment 8. Pure functions of the spec; no network solver is needed
because every quantity the tester reads is a series loop, a threshold or a first-order
transient. Each function documents its assumptions; docs/model-installation.md collects them."""

from __future__ import annotations

import cmath
import math
from typing import Literal

from vel.experiments.installation.spec import K_INST, InstallSpec, Mcb, Rcd

SQ3 = math.sqrt(3.0)
PHASES = ("L1", "L2", "L3")
LN_PAIRS = ("L1-N", "L2-N", "L3-N")
LL_PAIRS = ("L1-L2", "L2-L3", "L3-L1")
LOOPS = ("L1-N", "L2-N", "L3-N", "L1-PE", "L2-PE", "L3-PE", "L1-L2")

TripMode = Literal["magnetic", "thermal", "none"]


# --------------------------------------------------------------------------- supply


def phase_phasors(spec: InstallSpec) -> dict[str, complex]:
    """Phase voltages with ideal 120° displacement (the lab's tester reads magnitudes only, so
    an angle error cannot be identified from the data and is not modelled)."""
    n = spec.network
    return {
        "L1": cmath.rect(n.U1, 0.0),
        "L2": cmath.rect(n.U2, -2 * math.pi / 3),
        "L3": cmath.rect(n.U3, 2 * math.pi / 3),
    }


def voltages(spec: InstallSpec) -> dict[str, float]:
    v = phase_phasors(spec)
    out = {f"{p}-N": abs(v[p]) for p in PHASES}
    for pair in LL_PAIRS:
        a, b = pair.split("-")
        out[pair] = abs(v[a] - v[b])
    return out


def loop_impedance(spec: InstallSpec, loop: str) -> float:
    """Series sum of the conductors in the loop (resistive model; the tester shows |Z|)."""
    n = spec.network
    a, b = loop.split("-")
    if b == "N":
        return n.Z_L + n.Z_N
    if b == "PE":
        return n.Z_L + n.Z_PE
    return 2 * n.Z_L


def loop_voltage(spec: InstallSpec, loop: str) -> float:
    """Nominal voltage the tester uses for the prospective current (230 V or 400 V)."""
    return spec.network.U0 * (SQ3 if loop.split("-")[1].startswith("L") else 1.0)


def z_max(spec: InstallSpec, loop: str) -> float:
    """Regulation 22: the loop must drive enough current for disconnection within t_disc. The
    manual uses the instantaneous-release current (Z = 230/(5·In) for type B), i.e. the IEC
    60898-1 upper limit of the magnetic band."""
    n = spec.network
    return loop_voltage(spec, loop) / (K_INST[n.curve_prot] * n.In_prot)


# --------------------------------------------------------------------------- MCB


def mcb_trip(
    mcb: Mcb, In: float, current: float, theta0: float = 0.0
) -> tuple[float | None, TripMode]:
    """Trip time of a breaker of rating In at a constant current.

    θ (in units of In²) obeys θ' = (k² − θ)/τ from θ0 (0 = cold); the bimetal trips when θ
    reaches k_t². The magnetic release acts after t_mag when k ≥ k_m."""
    k = current / In
    if k >= mcb.k_m:
        return mcb.t_mag, "magnetic"
    k2, kt2 = k * k, mcb.k_t * mcb.k_t
    if k2 <= kt2:
        return None, "none"
    if theta0 >= kt2:
        return 0.0, "thermal"
    return mcb.tau * math.log((k2 - theta0) / (k2 - kt2)), "thermal"


def mcb_current_for_time(mcb: Mcb, t: float) -> float:
    """Multiple of In at which the thermal release (from cold) takes exactly t."""
    return mcb.k_t / math.sqrt(1.0 - math.exp(-t / mcb.tau))


# --------------------------------------------------------------------------- RCD


def rcd_trip(rcd: Rcd, residual: float) -> float | None:
    """Trip time at a residual current |I_L + I_N| [A]; None below the trip threshold."""
    i_trip = rcd.k_trip * rcd.I_dn
    if residual < i_trip:
        return None
    return rcd.t_delay + rcd.t0 + rcd.t1 * (i_trip / residual) ** 2


# --------------------------------------------------------------------------- insulation


def megger_reading(
    R_is: float, R_su: float, C: float, R_s: float, U: float, t: float, guard: bool
) -> tuple[float, float]:
    """Apparent resistance U_t/i_meter [Ω] and terminal voltage [V] at time t after the test
    voltage U is applied through the megger's internal resistance R_s.

    Equivalent circuit (manual fig. 5.2): R_is ‖ R_su ‖ C. The capacitor charges with
    τ = C·(R_s ‖ R_p), R_p = R_is ‖ R_su. Without guard the meter carries all three currents;
    with guard the surface current returns through G and bypasses the meter."""
    r_p = R_is * R_su / (R_is + R_su)
    u_inf = U * r_p / (R_s + r_p)
    tau = C * R_s * r_p / (R_s + r_p)
    if tau > 0:
        e = math.exp(-t / tau)
        u_t = u_inf * (1 - e)
        i_c = U / R_s * e  # (U − u_t)/R_s − u_t/R_p, using u_inf·(1/R_s + 1/R_p) = U/R_s
    else:
        u_t, i_c = u_inf, 0.0
    i_meter = u_t / R_is + i_c + (0.0 if guard else u_t / R_su)
    return (u_t / i_meter if i_meter > 0 else math.inf), u_t


# --------------------------------------------------------------------------- earth


def fall_of_potential(spec: InstallSpec, r13: float, x: float) -> float:
    """Apparent resistance U(x)/I with the current electrode at r13 and the potential probe at x,
    in line, in uniform soil.

    The rod (length L, current I spread evenly along it) raises the surface at distance x to
    ρI/(2πL)·asinh(L/x); its own potential is R_g·I (Dwight). The current electrode is a point
    sink. Hence R(x) = R_g − ρ/(2π·r13) − ρ/(2πL)·asinh(L/x) + ρ/(2π·(r13 − x)).

    Far from the rod asinh(L/x) → L/x and the curve becomes the hemisphere's, for which
    x = 0.618·r13 gives R_g exactly (−1/x + 1/(r13 − x) = 1/r13) — the 62 % rule. Close to the
    rod the line-source term does not cancel, which is why the rule needs r13 ≫ L."""
    e = spec.earth
    k = e.rho / (2 * math.pi)
    lo, hi = e.rod_d / 2, r13 - e.rod_d / 2
    x = min(max(x, lo), hi)
    return spec.R_g - k / r13 - k / e.rod_L * math.asinh(e.rod_L / x) + k / (r13 - x)
