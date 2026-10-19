"""One steady-state operating point: build → solve → instrument readings + loss bookkeeping."""

from __future__ import annotations

from dataclasses import dataclass, field

from vel.engine.circuit import CircuitModel
from vel.engine.mna import Network, Solution, solve
from vel.engine.netlist import Built, build
from vel.experiments.transformer3ph.spec import TransformerSpec


@dataclass
class OperatingPoint:
    readings: dict[str, dict[str, float | None]]
    undefined: dict[str, str]  # "instrument.quantity" -> reason
    internals: dict[str, dict[str, float]]
    iterations: int
    cond: float
    floating_groups: list[list[str]] = field(default_factory=list)


def _series_current(net: Network, sol: Solution, name: str) -> complex:
    """Current a→b through a named series element (admittance or zero-volt branch)."""
    for adm in net.admittances:
        if adm.name == name:
            return adm.y * sol.vdiff(adm.a, adm.b)
    if name in sol.branch_i:
        return sol.branch_i[name]
    raise KeyError(name)


def operating_point(
    circuit: CircuitModel, transformer: TransformerSpec | None, *, dc: bool = False
) -> OperatingPoint:
    built: Built = build(circuit, transformer=transformer, dc=dc)
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
            readings[iid] = {"U": v.real if dc else abs(v)}
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
    )
