"""Magnetic and mechanical steady state of a synchronous machine (see experiments/synchronous/
spec.py for the model).

The electrical network is linear in the machine's air-gap EMF E (phase U, positive sequence):
the positive-sequence armature current is I₁(E) = β + α·E exactly. Two network solves give α
and β; the saturating MMF balance

    E = r·OCC(|F|)·(−j)·F/|F|,   F = F_field·e^{jθ} + k_a·I₁(E),   r = n / n_rated

is then a 2-real-unknown equation solved by Newton's method without further network solves.
Island operation (no grid source): the prime mover sets the speed, θ = 0 is the reference.
Grid operation: the speed is synchronous and θ (rotor angle) follows from the power balance
P_em(θ) = P_shaft + P_fw on the stable branch (dP_em/dθ < 0); beyond the maximum the machine
falls out of step, which is reported as an explicit failure.
"""

from __future__ import annotations

import cmath
import math
from collections.abc import Callable
from typing import Any

import numpy as np

from vel.engine.circuit import CircuitModel
from vel.engine.netlist import CATALOG, CircuitValidationError, _f, sequence_impedance_matrix
from vel.engine.simulate import MechanicalError, OperatingPoint
from vel.experiments.synchronous.spec import SyncSpec

A120 = complex(-0.5, math.sqrt(3) / 2)
THETA_SCAN = 180
Electrical = Callable[..., OperatingPoint]


def _i1(op: OperatingPoint, mid: str) -> complex:
    e = op.internals[f"{mid}.elec"]
    return complex(e["I1_re"], e["I1_im"])


def _currents(op: OperatingPoint, mid: str) -> list[complex]:
    e = op.internals[f"{mid}.elec"]
    return [complex(e[f"I_{X}_re"], e[f"I_{X}_im"]) for X in "UVW"]


def sync_operating_point(
    circuit: CircuitModel, equipment: Any, electrical: Electrical
) -> OperatingPoint:
    machines = [c for c in circuit.components if c.type == "syncmachine3"]
    if len(machines) != 1:
        raise MechanicalError("unsupported", "exactly one synchronous machine per circuit")
    if any(c.type == "transformer3" for c in circuit.components):
        # the affine-in-E shortcut needs a linear network (no saturating transformer)
        raise MechanicalError(
            "unsupported", "a synchronous machine together with a transformer is not supported"
        )
    if not isinstance(equipment, SyncSpec):
        raise CircuitValidationError(
            [{"code": "no_spec", "message": "this project has no synchronous-machine spec"}]
        )
    spec = equipment
    m = machines[0]
    ct = CATALOG[m.type]
    i_f = _f(m.params, "I_f", ct, m.id)
    grid_sources = [c for c in circuit.components if c.type == "source3"]
    grid = bool(grid_sources)
    if grid:
        f = _f(grid_sources[0].params, "f", CATALOG["source3"], grid_sources[0].id)
        n = 120 * f / spec.nameplate.poles
    else:
        n = _f(m.params, "n_drive", ct, m.id)
        f = spec.nameplate.poles * n / 120
    r = f / spec.nameplate.f_n  # EMF ∝ speed
    occ, k_a = spec.occ, spec.ecm.k_a
    f_field = i_f + occ.F_res  # remanence as an MMF offset on the field axis
    p_fw = spec.ecm.P_fw * r**2

    op0 = electrical(circuit, equipment, False, {}, {m.id: 0j})
    op1 = electrical(circuit, equipment, False, {}, {m.id: 1 + 0j})
    beta = _i1(op0, m.id)
    alpha = _i1(op1, m.id) - beta

    def emf_of(F: complex) -> complex:
        mag = abs(F)
        if mag < 1e-15:
            return 0j
        return r * occ.emf(mag) * (-1j) * F / mag

    def solve_e(ff: complex) -> complex:
        def res(e: complex) -> complex:
            return e - emf_of(ff + k_a * (beta + alpha * e))

        e = emf_of(ff + k_a * beta)
        scale = max(1.0, abs(e), r * occ.a * max(abs(ff), 1e-9))
        for _ in range(100):
            rv = res(e)
            if abs(rv) <= 1e-12 * scale:
                return e
            h = 1e-7 * scale
            d_re = (res(e + h) - rv) / h
            d_im = (res(e + 1j * h) - rv) / h
            jac = np.array([[d_re.real, d_im.real], [d_re.imag, d_im.imag]])
            try:
                step = np.linalg.solve(jac, [-rv.real, -rv.imag])
            except np.linalg.LinAlgError as exc:
                raise MechanicalError(
                    "convergence_failure", "Jacobian of the MMF balance is singular"
                ) from exc
            lam = 1.0
            while lam > 1e-6:
                cand = e + lam * complex(step[0], step[1])
                if abs(res(cand)) < abs(rv):
                    e = cand
                    break
                lam /= 2
            else:
                break
        rv = res(e)
        if abs(rv) <= 1e-9 * scale:
            return e
        raise MechanicalError(
            "convergence_failure",
            "איזון הכא״מ והתגובה העוגנית (רוויה) לא התכנס",
            {"residual": abs(rv)},
        )

    warnings: list[dict[str, Any]] = []
    if not grid:
        theta = 0.0
        e = solve_e(complex(f_field, 0))
    else:
        p_shaft = _f(m.params, "P_shaft", ct, m.id)
        target = p_shaft + p_fw  # electromagnetic power converted to mechanical (motor sign)

        def p_em(th: float) -> tuple[float, complex]:
            e_ = solve_e(f_field * cmath.exp(1j * th))
            return -3 * (e_ * (beta + alpha * e_).conjugate()).real, e_

        grid_th = [-math.pi + 2 * math.pi * i / THETA_SCAN for i in range(THETA_SCAN + 1)]
        vals = [p_em(th)[0] for th in grid_th]
        p_max, p_min = max(vals), min(vals)
        root = None
        for i in range(THETA_SCAN):
            a_, b_ = vals[i] - target, vals[i + 1] - target
            if a_ >= 0 > b_:  # P_em decreasing through the target: stable equilibrium
                root = (grid_th[i], grid_th[i + 1], a_, b_)
                break
        if root is None:
            raise MechanicalError(
                "constraint_violation",
                f"המכונה יוצאת מסנכרון: ההספק הנדרש ({target:.4g} W כולל חיכוך) מחוץ לתחום "
                f"[{p_min:.4g}, {p_max:.4g}] W שהעירור I_f = {i_f:g} A מאפשר",
                {"P_target": target, "P_max": p_max, "P_min": p_min, "I_f": i_f},
            )
        lo, hi, flo, fhi = root
        theta = 0.5 * (lo + hi)
        for _ in range(200):
            theta = lo - flo * (hi - lo) / (fhi - flo) if fhi != flo else 0.5 * (lo + hi)
            fv = p_em(theta)[0] - target
            if abs(fv) <= 1e-11 * max(1.0, abs(p_max)) or hi - lo < 1e-15:
                break
            if fv > 0:
                lo, flo = theta, fv
                fhi /= 2
            else:
                hi, fhi = theta, fv
                flo /= 2
        e = p_em(theta)[1]

    op = electrical(circuit, equipment, False, {}, {m.id: e})
    i_out = _currents(op, m.id)
    zabc = sequence_impedance_matrix(
        complex(spec.ecm.Ra, spec.ecm.X0 * r),
        complex(spec.ecm.Ra, spec.ecm.Xl * r),
        complex(spec.ecm.Ra, spec.ecm.X2 * r),
    )
    v_u = e - complex((zabc @ np.array(i_out))[0])  # winding U terminal voltage
    ef_vec = emf_of(f_field * cmath.exp(1j * theta))
    i1 = _i1(op, m.id)
    f_res_vec = f_field * cmath.exp(1j * theta) + k_a * i1
    elec = op.internals[f"{m.id}.elec"]
    p_gen = elec["P_gen"]
    delta = (
        math.degrees(cmath.phase(ef_vec / v_u)) if abs(v_u) > 1e-12 and abs(ef_vec) > 0 else None
    )
    op.readings[m.id] = {
        "If": i_f,
        "n": n,
        "f": f,
        "Ef_noload": spec.line_factor() * abs(ef_vec),
        "delta_deg": delta,
    }
    op.internals[f"{m.id}.mech"] = {
        "theta_deg": math.degrees(theta),
        "E_r": abs(e),
        "F_r": abs(f_res_vec),
        "F_field": abs(f_field),
        "P_gen": p_gen,
        "P_fw": p_fw,
        # mechanical power entering the shaft (generator) — negative when motoring
        "P_mech_in": p_gen + p_fw,
        "P_shaft_out": -(p_gen + p_fw),
        "P_field": i_f**2 * spec.ecm.R_f,
        "saturation": (r * occ.a * abs(f_res_vec) / abs(e)) if abs(e) > 1e-12 else 1.0,
    }
    if abs(f_field) > 0 and i_f < 0 and abs(i_f) < 2 * occ.F_res:
        warnings.append(
            {
                "code": "reversed_field",
                "message": "זרם העירור הפוך לשטף השיורי: המתח קטן לפני שהוא גדל מחדש",
            }
        )
    op.warnings = warnings + op.warnings
    return op
