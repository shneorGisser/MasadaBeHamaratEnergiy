"""One steady-state operating point: build → solve → instrument readings + loss bookkeeping."""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass, field
from typing import Any, Literal

from vel.engine.circuit import CircuitModel
from vel.engine.mna import Network, Solution, solve
from vel.engine.netlist import Built, CircuitValidationError, build
from vel.experiments.wound_rotor.spec import WoundSpec

SLIP_SCAN = 80  # grid points used to locate the pull-out torque before root finding
SLIP_TOL = 1e-13


@dataclass
class OperatingPoint:
    readings: dict[str, dict[str, float | None]]
    undefined: dict[str, str]  # "instrument.quantity" -> reason
    internals: dict[str, dict[str, float]]
    iterations: int
    cond: float
    floating_groups: list[list[str]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)


class MechanicalError(Exception):
    """The mechanical steady state requested cannot exist (e.g. brake torque above pull-out)."""

    def __init__(
        self,
        status: Literal["constraint_violation", "convergence_failure", "unsupported"],
        message: str,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details


def _series_current(net: Network, sol: Solution, name: str) -> complex:
    """Current a→b through a named series element (admittance or zero-volt branch)."""
    for adm in net.admittances:
        if adm.name == name:
            return adm.y * sol.vdiff(adm.a, adm.b)
    if name in sol.branch_i:
        return sol.branch_i[name]
    raise KeyError(name)


def operating_point(
    circuit: CircuitModel,
    equipment: Any = None,
    *,
    dc: bool = False,
    on_stall: Literal["raise", "stall"] = "raise",
) -> OperatingPoint:
    """Steady state of the circuit. For an induction motor the slip is found from the torque
    balance M_shaft(s) = M_load on the stable branch (0 ≤ s < s_pull-out)."""
    if not dc and any(c.type == "syncmachine3" for c in circuit.components):
        from vel.engine.synchronous import sync_operating_point

        return sync_operating_point(circuit, equipment, _electrical)
    motors = [c for c in circuit.components if c.type in ("motor3", "woundmotor3")]
    if dc or not motors:
        return _electrical(circuit, equipment, dc, {})
    if len(motors) > 1:
        raise MechanicalError(
            "unsupported", "only one induction motor per circuit is supported (one brake)"
        )
    m = motors[0]
    if bool(m.params.get("locked", False)):
        return _electrical(circuit, equipment, dc, {m.id: 1.0})
    if m.type == "woundmotor3" and m.params.get("speed_mode", "torque") == "speed":
        # speed imposed (turned by hand, or driven above synchronism as a generator)
        supplies = [c for c in circuit.components if c.type == "source3"]
        if not supplies or not isinstance(equipment, WoundSpec):
            raise CircuitValidationError(
                [{"code": "no_source", "message": "imposed speed needs an AC supply"}]
            )
        f = float(supplies[0].params.get("f", 50.0))
        n_sync = 120 * f / equipment.nameplate.poles
        n_set = float(m.params.get("n_set", 0.0))
        return _electrical(circuit, equipment, dc, {m.id: 1 - n_set / n_sync})
    try:
        m_load = float(m.params.get("M_load", 0.0))
    except (TypeError, ValueError) as exc:
        raise CircuitValidationError(
            [{"code": "bad_param", "component": m.id, "message": f"{m.id}.M_load is not a number"}]
        ) from exc
    if not math.isfinite(m_load) or m_load < 0:
        raise CircuitValidationError(
            [
                {
                    "code": "param_out_of_range",
                    "component": m.id,
                    "message": f"{m.id}.M_load must be ≥ 0 N·m (the brake only absorbs power)",
                }
            ]
        )

    cache: dict[float, OperatingPoint] = {}

    def at(slip: float) -> OperatingPoint:
        if slip not in cache:
            cache[slip] = _electrical(circuit, equipment, dc, {m.id: slip})
        return cache[slip]

    def torque(slip: float) -> float:
        val = at(slip).readings[m.id]["M"]
        assert val is not None
        return val

    # Locate the pull-out torque on a grid dense near s = 0 (where the stable branch lies).
    grid = [0.0] + [10 ** (-6 + 6 * i / (SLIP_SCAN - 1)) for i in range(SLIP_SCAN)]
    values = [torque(x) for x in grid]
    i_max = max(range(len(grid)), key=lambda i: values[i])
    lo_i, hi_i = max(i_max - 1, 0), min(i_max + 1, len(grid) - 1)
    a, b = grid[lo_i], grid[hi_i]
    for _ in range(50):  # golden-section refinement of the maximum
        c1, c2 = b - 0.618034 * (b - a), a + 0.618034 * (b - a)
        if torque(c1) < torque(c2):
            a = c1
        else:
            b = c2
    s_max = 0.5 * (a + b)
    m_max = torque(s_max)
    m_start = torque(1.0)
    warnings: list[dict[str, Any]] = []
    if m_load > m_max:
        if on_stall == "raise":
            raise MechanicalError(
                "constraint_violation",
                f"מומנט הבלם {m_load:.4g} N·m גבוה ממומנט הפריצה {m_max:.4g} N·m — המנוע נעצר "
                "(נקודת עבודה יציבה אינה קיימת)",
                {"M_load": m_load, "M_max": m_max, "s_at_M_max": s_max},
            )
        op = at(1.0)
        op.warnings = [
            {
                "code": "stalled",
                "message": f"המנוע נעצר: מומנט הבלם {m_load:.4g} N·m > מומנט הפריצה "
                f"{m_max:.4g} N·m. הזרם הוא זרם רוטור נעול.",
            }
        ]
        op.readings[m.id]["M"] = min(m_load, m_start)
        return op
    if values[0] >= m_load:
        # M_load ≤ M(s = 0) can only happen with zero friction and zero brake: ideal no-load.
        op = at(0.0)
    else:
        lo, hi = 0.0, s_max
        f_lo, f_hi = values[0] - m_load, m_max - m_load
        side = 0
        for _ in range(300):  # Illinois (modified regula falsi): bracketed, superlinear
            x = hi - f_hi * (hi - lo) / (f_hi - f_lo) if f_hi != f_lo else 0.5 * (lo + hi)
            fx = torque(x) - m_load
            if abs(fx) <= 1e-12 * max(1.0, m_max) or (hi - lo) <= SLIP_TOL:
                break
            if (fx > 0) == (f_hi > 0):
                hi, f_hi = x, fx
                if side == 1:
                    f_lo *= 0.5
                side = 1
            else:
                lo, f_lo = x, fx
                if side == -1:
                    f_hi *= 0.5
                side = -1
        else:
            raise MechanicalError("convergence_failure", "איזון המומנטים (חיפוש ההחלקה) לא התכנס")
        op = at(x)
    if m_load > m_start + 1e-12:
        warnings.append(
            {
                "code": "cannot_start_under_load",
                "message": f"מומנט הבלם ({m_load:.4g} N·m) גבוה ממומנט ההתנעה ({m_start:.4g} N·m): "
                "הנקודה קיימת רק אם המנוע הואץ לפני שהבלם הופעל.",
            }
        )
    op.warnings = warnings + op.warnings
    # The brake unit displays the torque it applies; in steady state that IS the shaft torque.
    # The root finder leaves |M_shaft − M_load| ≤ 1e-12·max(1, M_max) — shown as the setting
    # instead of a meaningless 1e-12 residual (the residual stays visible in internals).
    op.internals[f"{m.id}.mech"]["balance_residual"] = (
        torque(op.readings[m.id]["s"] or 0.0) - m_load
    )
    op.readings[m.id]["M"] = m_load
    op.internals[f"{m.id}.mech"] = {
        **op.internals[f"{m.id}.mech"],
        "M_max": m_max,
        "s_at_M_max": s_max,
        "M_start": m_start,
    }
    return op


def _electrical(
    circuit: CircuitModel,
    equipment: Any,
    dc: bool,
    slips: dict[str, float],
    sync_emf: dict[str, complex] | None = None,
) -> OperatingPoint:
    built: Built = build(circuit, equipment=equipment, dc=dc, slips=slips, sync_emf=sync_emf)
    sol = solve(built.network)
    readings: dict[str, dict[str, float | None]] = {}
    undefined: dict[str, str] = {}

    def node(cid: str, t: str) -> int:
        return built.node_of_terminal[f"{cid}.{t}"]

    def same_group(a: int, b: int) -> bool:
        return built.group_of_node[a] == built.group_of_node[b]

    for iid, meta in built.instruments.items():
        typ = meta["type"]
        if typ == "ammeter":
            i = sol.branch_i[f"{iid}#I"]
            readings[iid] = {"I": i.real if dc else abs(i)}
        elif typ == "voltmeter":
            a, b = node(iid, "p"), node(iid, "n")
            if not same_group(a, b):
                readings[iid] = {"U": None}
                undefined[f"{iid}.U"] = (
                    "terminals are in galvanically isolated parts of the circuit; "
                    "the voltage between them is not defined"
                )
                continue
            v = sol.vdiff(a, b)
            # angle_deg is a simulation-only phasor quantity (a lab voltmeter shows |U| only);
            # absolute angle reference = phase L1 of the first AC source.
            readings[iid] = (
                {"U": v.real} if dc else {"U": abs(v), "angle_deg": math.degrees(cmath.phase(v))}
            )
        elif typ == "wattmeter":
            i = sol.branch_i[f"{iid}#I"]
            a, b = node(iid, "Vp"), node(iid, "Vn")
            if not same_group(a, b):
                readings[iid] = {
                    "P": None,
                    "Q": None,
                    "S": None,
                    "pf": None,
                    "U": None,
                    "I": abs(i),
                }
                undefined[f"{iid}.P"] = "voltage coil spans isolated circuit parts"
                continue
            v = sol.vdiff(a, b)
            s = v * i.conjugate()
            mag = abs(s)
            pf: float | None = s.real / mag if mag > 1e-15 else None
            if pf is None:
                undefined[f"{iid}.pf"] = "apparent power is zero; cos φ is undefined"
            readings[iid] = {
                "P": s.real,
                "Q": s.imag,
                "S": mag,
                "pf": pf,
                "U": abs(v),
                "I": abs(i),
            }

    # instruments in a rotating rotor's circuit read slip-frequency quantities: the network
    # is solved referred to stator frequency (impedances / s), so voltages and powers × s
    for iid, sc in built.rotor_instruments.items():
        r = readings.get(iid, {})
        for q in ("U", "S"):
            if r.get(q) is not None:
                r[q] = abs(sc) * float(r[q])  # type: ignore[arg-type]
        for q in ("P", "Q"):
            if r.get(q) is not None:
                r[q] = sc * float(r[q])  # type: ignore[arg-type]
        if r:
            r["f"] = abs(sc) * built.f
    for iid in built.mixed_instruments:
        for q in list(readings.get(iid, {})):
            if q != "I":
                readings[iid][q] = None
                undefined[f"{iid}.{q}"] = (
                    "המכשיר מחבר את מעגל הרוטור המסתובב (תדר החלקה) עם צד הסטטור — אין ערך אחד"
                )

    internals: dict[str, dict[str, float]] = {}
    for xid, meta in built.xfmr_internals.items():
        tot = {"P_cu1": 0.0, "P_cu2": 0.0, "P_fe": 0.0, "Q_m": 0.0}
        for P, ph in meta["phases"].items():
            if ph.get("dc"):
                continue
            i1 = _series_current(built.network, sol, f"{xid}#{P}#Z1")
            s_lower = P.lower()
            i2 = _series_current(built.network, sol, f"{xid}#{s_lower}#Z2")
            e1 = sol.vdiff(ph["e1"], ph["p2"])
            p_cu1 = abs(i1) ** 2 * meta["R1"]
            p_cu2 = abs(i2) ** 2 * meta["R2"]
            p_fe = abs(e1) ** 2 / meta["R_fe"]
            internals[f"{xid}.{P}"] = {
                "E1": abs(e1),
                "I1": abs(i1),
                "I2": abs(i2),
                "P_cu1": p_cu1,
                "P_cu2": p_cu2,
                "P_fe": p_fe,
            }
            tot["P_cu1"] += p_cu1
            tot["P_cu2"] += p_cu2
            tot["P_fe"] += p_fe
        if meta["phases"] and not any(ph.get("dc") for ph in meta["phases"].values()):
            internals[f"{xid}.total"] = tot

    op_warnings: list[dict[str, Any]] = []
    for mid, meta in built.motor_internals.items():
        if meta["dc"]:
            continue
        spec = meta["spec"]
        e, npl = spec.ecm, spec.nameplate
        slip, f = meta["slip"], meta["f"]
        tot = {"P_cu1": 0.0, "P_fe": 0.0, "P_ag": 0.0}
        e_mags = []
        wound = isinstance(spec, WoundSpec)
        p_cu2_int = 0.0
        for X, ph in meta["phases"].items():
            i1 = _series_current(built.network, sol, f"{mid}#{X}#Z1")
            if wound:
                ev = sol.vdiff(ph["e"], ph["q"])
                e_mags.append(abs(ev))
                i_xf = sol.branch_i[f"{mid}#{X}#xf"]
                i2a = _series_current(built.network, sol, f"{mid}#{X}#Z2")  # actual rotor I
                p_cu1 = abs(i1) ** 2 * e.R1
                p_fe = abs(ev) ** 2 / e.R_fe
                p_ag = (ev * i_xf.conjugate()).real  # power through the air gap
                p_cu2_int += abs(i2a) ** 2 * e.R2
                internals[f"{mid}.{X}"] = {
                    "E": abs(ev),
                    "I1": abs(i1),
                    "I2": abs(i2a),
                    "P_cu1": p_cu1,
                    "P_fe": p_fe,
                    "P_ag": p_ag,
                }
                tot["P_cu1"] += p_cu1
                tot["P_fe"] += p_fe
                tot["P_ag"] += p_ag
                continue
            i2 = _series_current(built.network, sol, f"{mid}#{X}#Z2") if slip > 0 else 0j
            ev = sol.vdiff(ph["e"], ph["q"])
            e_mags.append(abs(ev))
            p_cu1 = abs(i1) ** 2 * e.R1
            p_fe = abs(ev) ** 2 / e.R_fe
            p_ag = abs(i2) ** 2 * e.R2p / slip if slip > 0 else 0.0
            internals[f"{mid}.{X}"] = {
                "E": abs(ev),
                "I1": abs(i1),
                "I2p": abs(i2),
                "P_cu1": p_cu1,
                "P_fe": p_fe,
                "P_ag": p_ag,
            }
            tot["P_cu1"] += p_cu1
            tot["P_fe"] += p_fe
            tot["P_ag"] += p_ag
        n_sync = 120 * f / npl.poles
        w_sync = 2 * math.pi * n_sync / 60
        n = n_sync * (1 - slip)
        w_m = 2 * math.pi * n / 60
        p_fw = e.P_fw_n * (n / npl.n_n) ** 2
        m_em = tot["P_ag"] / w_sync if w_sync > 0 else 0.0
        m_fw = p_fw / w_m if w_m > 0 else 0.0  # standstill: no friction torque modelled
        p_cu2 = slip * tot["P_ag"]
        p_mech = (1 - slip) * tot["P_ag"]
        internals[f"{mid}.total"] = {**tot, "P_cu2": p_cu2}
        if wound:
            # rotor circuit losses s·P_ag split into the winding and the external resistors
            internals[f"{mid}.total"]["P_cu2_winding"] = p_cu2_int
            internals[f"{mid}.total"]["P_rotor_external"] = p_cu2 - p_cu2_int
        internals[f"{mid}.mech"] = {
            "s": slip,
            "n_sync": n_sync,
            "n": n,
            "M_em": m_em,
            "M_fw": m_fw,
            "P_mech": p_mech,
            "P_fw": p_fw,
            "P2": p_mech - p_fw,
        }
        # what the brake control unit displays: speed and the torque it holds
        readings[mid] = {"n": n, "M": m_em - m_fw, "s": slip, "f_rotor": abs(slip) * f}
        spread = (max(e_mags) - min(e_mags)) / max(max(e_mags), 1e-30)
        if spread > 0.01:
            op_warnings.append(
                {
                    "code": "unbalanced_supply",
                    "message": f"{mid}: מתחי הליפופים אינם מאוזנים ({spread:.1%}). המודל לכל "
                    "ליפוף תקף רק להזנה סימטרית; רכיב הסדר השלילי אינו ממודל.",
                }
            )

    for sid, meta in built.sync_internals.items():
        if meta["dc"]:
            continue
        cpl = meta["coupled"]
        i_out = cpl.currents(sol.v)  # out of terminals X1 (generator convention)
        a120 = complex(-0.5, math.sqrt(3) / 2)
        e_u = meta["emf"]
        e_k = [e_u, e_u * a120 * a120, e_u * a120]
        p_gen = sum((ek * complex(ik).conjugate()).real for ek, ik in zip(e_k, i_out, strict=True))
        ra = meta["spec"].ecm.Ra
        i1 = (complex(i_out[0]) + a120 * complex(i_out[1]) + a120 * a120 * complex(i_out[2])) / 3
        internals[f"{sid}.elec"] = {
            "P_gen": p_gen,  # air-gap power, generator convention
            "P_cu": ra * sum(abs(complex(x)) ** 2 for x in i_out),
            "I1_re": i1.real,
            "I1_im": i1.imag,
            **{
                f"I_{X}_{part}": (
                    complex(i_out[k]).real if part == "re" else complex(i_out[k]).imag
                )
                for k, X in enumerate("UVW")
                for part in ("re", "im")
            },
        }

    # total active power delivered by AC sources (for power-balance checks)
    p_src = 0.0
    for vs in built.network.vsources:
        if "#ph" in vs.name:
            # source current i flows from + terminal through the source to N, i.e. it is the
            # current drawn *into* the source; delivered power is -Re(V · conj(i)).
            p_src += -(vs.v * sol.branch_i[vs.name].conjugate()).real
    internals["_sources"] = {"P_delivered": p_src}

    return OperatingPoint(
        readings=readings,
        undefined=undefined,
        internals=internals,
        iterations=sol.iterations,
        cond=sol.cond,
        floating_groups=built.floating_groups,
        warnings=op_warnings,
    )


def operating_point_at_slip(circuit: CircuitModel, equipment: Any, slip: float) -> OperatingPoint:
    """Electrical steady state at an imposed slip (no torque balance) — for the simulation-only
    torque–speed characteristic, including its unstable branch that no brake setting reaches."""
    motors = [c for c in circuit.components if c.type in ("motor3", "woundmotor3")]
    if len(motors) != 1:
        raise MechanicalError("unsupported", "the circuit must contain exactly one motor")
    return _electrical(circuit, equipment, False, {motors[0].id: slip})
