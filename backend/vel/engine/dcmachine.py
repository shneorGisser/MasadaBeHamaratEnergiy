"""Magnetic and mechanical steady state of a DC machine (model: experiments/dc_machine/spec.py).

The DC network is linear in the armature source voltage E_eff (internal EMF minus brush drop),
so every branch current is affine in it: I = β + α·E_eff. Two network solves give α and β for
the armature, shunt-field and series-field currents. The machine is then one scalar equation

    g(E) = E − r·OCC(F(E)) + U_b·tanh(I_a(E)/I_b) = 0,   F = I_f + ρ_s·I_s − k_ar·|I_a| + F_res

with r = n/n_ref. A self-excited generator can have several solutions (the residual-voltage
point, the built-up point, an unstable one in between); the physical one is the one the field
transient reaches when the machine starts from its remanence, so the root is searched by
marching from E₀ = r·OCC(F_res) in the direction the transient moves (sign of −g).

Speed: "speed" mode = the machine is driven (dynamometer / servo) at n_set; "torque" mode =
motor loaded by a brake of M_load. In torque mode n follows from the torque balance
M_em(n) = M_fric(n) + M_load (brake opposes the rotation); a field-less shunt motor or an
unloaded series motor has no balance below the speed limit and is reported as overspeed.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any, Literal

from vel.engine.circuit import CircuitModel
from vel.engine.netlist import CATALOG, CircuitValidationError, _f
from vel.engine.simulate import MechanicalError, OperatingPoint
from vel.experiments.dc_machine.spec import DCSpec

Electrical = Callable[..., OperatingPoint]
I_BRUSH = 0.05  # A: current over which the brush drop reaches its constant value
E_SCAN = 600
N_SCAN = 160
OVERSPEED_FACTOR = 1.5  # search range for the speed, in units of n_max


def _currents(op: OperatingPoint, mid: str) -> tuple[float, float, float]:
    d = op.internals[f"{mid}.dc"]
    return d["Ia"], d["If"], d["Is"]


def dc_operating_point(
    circuit: CircuitModel,
    equipment: Any,
    electrical: Electrical,
    on_stall: Literal["raise", "stall"] = "raise",
) -> OperatingPoint:
    machines = [c for c in circuit.components if c.type == "dcmachine"]
    if len(machines) != 1:
        raise MechanicalError("unsupported", "exactly one DC machine per circuit")
    if not isinstance(equipment, DCSpec):
        raise CircuitValidationError(
            [{"code": "no_spec", "message": "this project has no DC-machine spec"}]
        )
    spec = equipment
    m = machines[0]
    ct = CATALOG[m.type]
    mode = str(m.params.get("speed_mode", "speed"))
    occ, ecm, npl = spec.occ, spec.ecm, spec.nameplate
    w_ref = 2 * math.pi * occ.n_ref / 60

    op0 = electrical(circuit, equipment, True, {}, None, {m.id: 0.0})
    op1 = electrical(circuit, equipment, True, {}, None, {m.id: 1.0})
    b = _currents(op0, m.id)
    a = tuple(x1 - x0 for x0, x1 in zip(b, _currents(op1, m.id), strict=True))

    def currents(e: float) -> tuple[float, float, float]:
        return b[0] + a[0] * e, b[1] + a[1] * e, b[2] + a[2] * e

    def mmf(e: float) -> float:
        ia, i_f, i_s = currents(e)
        return i_f + ecm.rho_s * i_s - ecm.k_ar * abs(ia) + occ.F_res

    def g(e: float, r: float) -> float:
        ia = currents(e)[0]
        return e - r * occ.emf(mmf(e)) + ecm.U_brush * math.tanh(ia / I_BRUSH)

    def solve_e(n: float) -> float:
        r = n / occ.n_ref
        e0 = r * occ.emf(occ.F_res)
        g0 = g(e0, r)
        if g0 == 0:
            return e0
        direction = -1.0 if g0 > 0 else 1.0
        bound = abs(r) * occ.a * occ.I_s * 1.05 + ecm.U_brush + 1.0
        # with a supply the network can force E beyond the open-circuit bound
        bound = max(bound, abs(b[0] / a[0]) * 1.05 + 1.0) if a[0] != 0 else bound
        span = bound + abs(e0)
        step = span / E_SCAN
        lo, glo = e0, g0
        for k in range(1, E_SCAN + 1):
            hi = e0 + direction * step * k
            ghi = g(hi, r)
            if (ghi > 0) != (glo > 0) or ghi == 0:
                break
            lo, glo = hi, ghi
        else:
            raise MechanicalError(
                "convergence_failure", "לא נמצאה נקודת שיווי משקל למתח המושרה", {"n": n}
            )
        # Illinois between lo and hi
        flo, fhi = glo, ghi
        e = hi
        for _ in range(200):
            e = hi - fhi * (hi - lo) / (fhi - flo) if fhi != flo else 0.5 * (lo + hi)
            fv = g(e, r)
            if abs(fv) <= 1e-12 * max(1.0, abs(e)) or abs(hi - lo) < 1e-14:
                return e
            if (fv > 0) == (fhi > 0):
                hi, fhi = e, fv
                flo /= 2
            else:
                lo, flo = e, fv
                fhi /= 2
        return e

    def m_fric(n: float) -> float:
        # P_rot ∝ |n|^k  ⇒  friction torque ∝ |n|^(k−1), opposing the rotation
        if n == 0:
            return 0.0
        m0 = ecm.P_rot_n / (2 * math.pi * npl.n_n / 60)
        return math.copysign(m0 * abs(n / npl.n_n) ** (ecm.k_rot - 1), n)

    def m_em_motor(n: float) -> tuple[float, float]:
        e = solve_e(n)
        ia = currents(e)[0]
        return -occ.emf(mmf(e)) / w_ref * ia, e

    warnings: list[dict[str, Any]] = []
    stalled = False
    if mode == "speed":
        n = _f(m.params, "n_set", ct, m.id)
        e_eff = solve_e(n)
    else:
        m_load = _f(m.params, "M_load", ct, m.id)
        m0, _ = m_em_motor(0.0)
        if abs(m0) <= m_load:
            if on_stall == "raise":
                raise MechanicalError(
                    "constraint_violation",
                    f"המנוע אינו מתניע: מומנט ההתנעה {abs(m0):.4g} N·m אינו עולה על מומנט "
                    f"הבלם {m_load:.4g} N·m",
                    {"M_start": abs(m0), "M_load": m_load},
                )
            stalled = True
            n = 0.0
            e_eff = solve_e(0.0)
        else:
            d = 1.0 if m0 > 0 else -1.0
            n_cap = OVERSPEED_FACTOR * npl.n_max

            def bal(n_abs: float) -> float:
                nn = d * n_abs
                return d * m_em_motor(nn)[0] - abs(m_fric(nn)) - m_load

            grid = [n_cap * k / N_SCAN for k in range(N_SCAN + 1)]
            vals = [bal(x) for x in grid]
            root = None
            for k in range(N_SCAN):
                if vals[k] > 0 >= vals[k + 1]:
                    root = (grid[k], grid[k + 1], vals[k], vals[k + 1])
                    break
            if root is None:
                raise MechanicalError(
                    "constraint_violation",
                    f"המנוע מתבדר: אין שיווי משקל מומנטים מתחת ל-{n_cap:.0f} סל״ד "
                    "(עירור מקבילי קטוע או חלש מדי, או מנוע טורי ללא עומס)",
                    {"n_cap": n_cap, "M_load": m_load},
                )
            lo, hi, flo, fhi = root
            x = hi
            for _ in range(200):
                x = lo - flo * (hi - lo) / (fhi - flo) if fhi != flo else 0.5 * (lo + hi)
                fv = bal(x)
                if abs(fv) <= 1e-12 * max(1.0, m_load) or hi - lo < 1e-12:
                    break
                if fv > 0:
                    lo, flo = x, fv
                    fhi /= 2
                else:
                    hi, fhi = x, fv
                    flo /= 2
            n = d * x
            e_eff = solve_e(n)

    if abs(n) > npl.n_max * (1 + 1e-9):
        raise MechanicalError(
            "constraint_violation",
            f"המהירות {abs(n):.0f} סל״ד חורגת מהמהירות המרבית המותרת {npl.n_max:.0f} סל״ד — "
            "במעבדה יש להפסיק מיד (סכנת התפרקות העוגן)",
            {"n": n, "n_max": npl.n_max},
        )

    op = electrical(circuit, equipment, True, {}, None, {m.id: e_eff})
    ia, i_f, i_s = _currents(op, m.id)
    f_res = mmf(e_eff)
    r = n / occ.n_ref
    e_int = r * occ.emf(f_res)
    w = 2 * math.pi * n / 60
    m_em = occ.emf(f_res) / w_ref * ia  # generator convention: torque opposing the drive
    p_em = e_int * ia  # electromagnetic power, generator convention
    p_fric = m_fric(n) * w if n != 0 else 0.0
    p_cu_a = ia**2 * ecm.R_a
    p_brush = abs(ecm.U_brush * math.tanh(ia / I_BRUSH) * ia)
    op.readings[m.id] = {"n": n, "M": (m_em + m_fric(n)) if mode == "speed" else _brake(m)}
    op.internals[f"{m.id}.mech"] = {
        "n": n,
        "E_int": e_int,
        "F_res": f_res,
        "Ia": ia,
        "If": i_f,
        "Is": i_s,
        "M_em": m_em,
        "M_fric": m_fric(n),
        "P_em": p_em,
        "P_rot": abs(p_fric),
        "P_cu_a": p_cu_a,
        "P_brush": p_brush,
        "P_cu_f": i_f**2 * ecm.R_f,
        "P_cu_s": i_s**2 * ecm.R_s,
        # mechanical power at the shaft: into the machine (generator) is positive
        "P_shaft_in": p_em + abs(p_fric),
        "stalled": 1.0 if stalled else 0.0,
        "saturation": (occ.a * abs(f_res) / abs(occ.emf(f_res))) if f_res != 0 else 1.0,
    }
    weak = abs(occ.emf(f_res)) < 2 * abs(occ.emf(occ.F_res)) + 1e-9
    if mode == "speed" and n != 0 and weak and (abs(i_f) > 1e-3 or abs(i_s) > 1e-3):
        warnings.append(
            {
                "code": "no_buildup",
                "message": "הגנרטור לא נבנה: העירור מחליש את השטף השיורי או שהתנגדות "
                "מעגל העירור גבוהה מההתנגדות הקריטית",
            }
        )
    if stalled:
        warnings.append({"code": "stalled", "message": "המנוע עומד: מומנט הבלם גדול ממומנט ההתנעה"})
    op.warnings = warnings + op.warnings
    return op


def _brake(m: Any) -> float:
    return float(m.params.get("M_load", 0.0))
