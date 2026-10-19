"""Component library and CircuitModel → MNA network expansion.

Every component type declares its terminals, parameters (with SI units) and how it expands
into MNA primitives. Instruments are ideal: ammeters have zero impedance, voltmeters and
wattmeter voltage coils infinite impedance. Probe loading, meter accuracy class, bandwidth and
true-RMS vs. average-responding behaviour are NOT modelled.
"""

from __future__ import annotations

import cmath
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from vel.engine.circuit import CircuitModel, Component
from vel.engine.mna import (
    Admittance,
    CoupledAdmittance,
    IdealTransformer,
    Network,
    NonlinearShunt,
    Pin,
    VSource,
)
from vel.experiments.induction_motor.spec import MotorSpec
from vel.experiments.synchronous.spec import SyncSpec
from vel.experiments.transformer3ph.spec import TransformerSpec

ZERO_Z = 1e-12


class CircuitValidationError(Exception):
    def __init__(self, issues: list[dict[str, Any]]) -> None:
        super().__init__("; ".join(i["message"] for i in issues))
        self.issues = issues


@dataclass(frozen=True)
class ParamDef:
    key: str
    label_he: str
    unit: str
    kind: str = "float"  # float | bool | choice
    default: Any = None
    min: float | None = None
    max: float | None = None
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class ComponentType:
    type: str
    label_he: str
    category: str  # source | switch | machine | load | passive | instrument
    terminals: tuple[str, ...]
    params: tuple[ParamDef, ...] = ()
    instrument: bool = False


CATALOG: dict[str, ComponentType] = {
    t.type: t
    for t in [
        ComponentType(
            "source3",
            "רשת תלת-פאזית דרך וריאק",
            "source",
            ("L1", "L2", "L3", "N"),
            (
                ParamDef("U_line", "מתח קווי (כיוון הווריאק)", "V", default=380.0, min=0, max=1e5),
                ParamDef("f", "תדירות", "Hz", default=50.0, min=1, max=1000),
            ),
        ),
        ComponentType(
            "source_dc",
            "ספק כוח זרם ישר",
            "source",
            ("P", "N"),
            (ParamDef("U", "מתח", "V", default=10.0, min=0, max=1000),),
        ),
        ComponentType(
            "switch3",
            "מפסק תלת-קוטבי",
            "switch",
            ("i1", "i2", "i3", "o1", "o2", "o3"),
            (ParamDef("closed", "סגור", "", kind="bool", default=True),),
        ),
        ComponentType(
            "transformer3",
            "שנאי תלת-פזי",
            "machine",
            ("A1", "A2", "B1", "B2", "C1", "C2", "a1", "a2", "b1", "b2", "c1", "c2"),
        ),
        ComponentType(
            "motor3",
            "מנוע השראה תלת-פזי + בלם אבקה מגנטית",
            "machine",
            ("U1", "U2", "V1", "V2", "W1", "W2"),
            (
                ParamDef("M_load", "מומנט הבלם", "N·m", default=0.0, min=0, max=1e4),
                ParamDef("locked", "רוטור נעול", "", kind="bool", default=False),
            ),
        ),
        ComponentType(
            "syncmachine3",
            "מכונה סינכרונית תלת-פזית",
            "machine",
            ("U1", "U2", "V1", "V2", "W1", "W2", "F1", "F2"),
            (
                ParamDef("I_f", "זרם עירור", "A", default=0.0, min=-100, max=100),
                ParamDef(
                    "n_drive", "מהירות המנוע המניע (ללא רשת)", "rpm", default=1500.0, min=1, max=1e5
                ),
                ParamDef(
                    "P_shaft",
                    "הספק בציר (מחובר לרשת; + מנוע, − מחולל)",
                    "W",
                    default=0.0,
                    min=-1e7,
                    max=1e7,
                ),
            ),
        ),
        ComponentType(
            "load3",
            "עומס תלת-פאזי",
            "load",
            ("1", "2", "3"),
            (
                ParamDef("kind", "סוג", "", kind="choice", default="R", choices=("R", "L", "C")),
                ParamDef("connection", "חיבור", "", kind="choice", default="Y", choices=("Y", "D")),
                ParamDef("value", "ערך לפאזה (Ω / H / F)", "", default=50.0, min=1e-12, max=1e9),
            ),
        ),
        ComponentType(
            "resistor",
            "נגד",
            "passive",
            ("p", "n"),
            (ParamDef("R", "התנגדות", "Ω", default=100.0, min=0, max=1e12),),
        ),
        ComponentType(
            "inductor",
            "סליל",
            "passive",
            ("p", "n"),
            (ParamDef("L", "השראות", "H", default=0.1, min=0, max=1e6),),
        ),
        ComponentType(
            "capacitor",
            "קבל",
            "passive",
            ("p", "n"),
            (ParamDef("C", "קיבול", "F", default=1e-5, min=1e-15, max=10),),
        ),
        ComponentType("ammeter", "מד זרם", "instrument", ("p", "n"), instrument=True),
        ComponentType("voltmeter", "מד מתח", "instrument", ("p", "n"), instrument=True),
        ComponentType(
            "wattmeter",
            "מד הספק חד-פאזי (כולל cos φ)",
            "instrument",
            ("Ip", "In", "Vp", "Vn"),
            instrument=True,
        ),
    ]
}

VOLTAGE_FREE_INSTRUMENTS = {"voltmeter"}


def catalog_json() -> list[dict[str, Any]]:
    return [
        {
            "type": t.type,
            "label_he": t.label_he,
            "category": t.category,
            "terminals": list(t.terminals),
            "instrument": t.instrument,
            "params": [
                {
                    "key": p.key,
                    "label_he": p.label_he,
                    "unit": p.unit,
                    "kind": p.kind,
                    "default": p.default,
                    "min": p.min,
                    "max": p.max,
                    "choices": list(p.choices),
                }
                for p in t.params
            ],
        }
        for t in CATALOG.values()
    ]


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def add(self, k: str) -> None:
        self.parent.setdefault(k, k)

    def find(self, k: str) -> str:
        self.add(k)
        root = k
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[k] != root:
            self.parent[k], k = root, self.parent[k]
        return root

    def union(self, a: str, b: str) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.parent[rb] = ra
        return True


@dataclass
class Built:
    """Result of expanding a CircuitModel into an MNA network."""

    network: Network
    node_of_terminal: dict[str, int]
    f: float
    floating_groups: list[list[str]] = field(default_factory=list)
    group_of_node: dict[int, int] = field(default_factory=dict)
    # instrument id -> how to read it
    instruments: dict[str, dict[str, Any]] = field(default_factory=dict)
    # transformer internals per phase (for loss bookkeeping; NOT instrument readings)
    xfmr_internals: dict[str, dict[str, Any]] = field(default_factory=dict)
    # induction-motor internals (slip, branch names) for the mechanical bookkeeping
    motor_internals: dict[str, dict[str, Any]] = field(default_factory=dict)
    # synchronous-machine internals (EMF source names, coupled winding branches)
    sync_internals: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)


def _f(params: dict[str, Any], key: str, ctype: ComponentType, cid: str) -> float:
    pd = next(p for p in ctype.params if p.key == key)
    raw = params.get(key, pd.default)
    try:
        val = float(raw)
    except (TypeError, ValueError) as exc:
        raise CircuitValidationError(
            [{"code": "bad_param", "component": cid, "message": f"{cid}.{key} is not a number"}]
        ) from exc
    if (
        not math.isfinite(val)
        or (pd.min is not None and val < pd.min)
        or (pd.max is not None and val > pd.max)
    ):
        raise CircuitValidationError(
            [
                {
                    "code": "param_out_of_range",
                    "component": cid,
                    "message": f"{cid}.{key}={val} {pd.unit} outside [{pd.min}, {pd.max}]",
                }
            ]
        )
    return val


def validate_structure(circuit: CircuitModel) -> list[dict[str, Any]]:
    """Static checks that do not need the solver. Returns blocking issues."""
    issues: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in circuit.components:
        if c.id in seen:
            issues.append(
                {"code": "duplicate_id", "component": c.id, "message": f"duplicate id {c.id}"}
            )
        seen.add(c.id)
        if c.type not in CATALOG:
            issues.append(
                {
                    "code": "unknown_type",
                    "component": c.id,
                    "message": f"{c.id}: unknown type {c.type}",
                }
            )
    by_id = {c.id: c for c in circuit.components}
    for w in circuit.wires:
        for end in (w.a, w.b):
            comp = by_id.get(end.component)
            if comp is None:
                issues.append(
                    {
                        "code": "dangling_wire",
                        "wire": w.id,
                        "message": f"wire {w.id} ends on missing component {end.component}",
                    }
                )
            elif comp.type in CATALOG and end.terminal not in CATALOG[comp.type].terminals:
                issues.append(
                    {
                        "code": "unknown_terminal",
                        "wire": w.id,
                        "message": f"wire {w.id}: {comp.id} has no terminal {end.terminal}",
                    }
                )
        if w.a == w.b:
            issues.append(
                {
                    "code": "self_wire",
                    "wire": w.id,
                    "message": f"wire {w.id} connects a terminal to itself",
                }
            )
    return issues


def build(
    circuit: CircuitModel,
    *,
    equipment: Any = None,
    dc: bool = False,
    slips: dict[str, float] | None = None,
    sync_emf: dict[str, complex] | None = None,
) -> Built:
    """Expand a circuit into an MNA network.

    `equipment` is the project's equipment spec (TransformerSpec, MotorSpec); machine
    components take their parameters from it (single source of truth). `slips` gives the
    operating slip of each induction motor — the mechanical balance that determines it is
    solved one level up, in `simulate.operating_point`. Likewise `sync_emf` gives the air-gap
    EMF (phase U, positive sequence) of each synchronous machine; the magnetic (saturation /
    armature reaction) and mechanical balance that fixes it is solved in `simulate`.
    """
    issues = validate_structure(circuit)
    if issues:
        raise CircuitValidationError(issues)

    uf = _UnionFind()
    for c in circuit.components:
        for t in CATALOG[c.type].terminals:
            uf.add(f"{c.id}.{t}")
    for w in circuit.wires:
        uf.union(w.a.key(), w.b.key())
    for c in circuit.components:
        if c.type == "switch3" and bool(c.params.get("closed", True)):
            for k in (1, 2, 3):
                uf.union(f"{c.id}.i{k}", f"{c.id}.o{k}")

    roots: dict[str, int] = {}
    node_of_terminal: dict[str, int] = {}
    for key in list(uf.parent):
        r = uf.find(key)
        if r not in roots:
            roots[r] = len(roots)
        node_of_terminal[key] = roots[r]

    counter = [len(roots)]

    def new_node() -> int:
        counter[0] += 1
        return counter[0] - 1

    def N(cid: str, term: str) -> int:
        return node_of_terminal[f"{cid}.{term}"]

    sources = [c for c in circuit.components if c.type in ("source3", "source_dc")]
    machines = [c for c in circuit.components if c.type == "syncmachine3"]
    if not sources and not (machines and not dc):
        raise CircuitValidationError([{"code": "no_source", "message": "circuit has no source"}])
    f_values = {_f(c.params, "f", CATALOG[c.type], c.id) for c in sources if c.type == "source3"}
    if machines and not dc and not f_values:
        # island operation: the generators' speed sets the frequency
        if not isinstance(equipment, SyncSpec):
            raise CircuitValidationError(
                [{"code": "no_spec", "message": "this project has no synchronous-machine spec"}]
            )
        f_values = {
            equipment.nameplate.poles * _f(m.params, "n_drive", CATALOG[m.type], m.id) / 120
            for m in machines
        }
    if dc and any(c.type == "source3" for c in sources):
        raise CircuitValidationError(
            [{"code": "mixed_sources", "message": "DC study cannot contain an AC source"}]
        )
    if not dc and any(c.type == "source_dc" for c in sources):
        raise CircuitValidationError(
            [{"code": "mixed_sources", "message": "AC study cannot contain a DC source"}]
        )
    if len(f_values) > 1:
        raise CircuitValidationError(
            [{"code": "multi_frequency", "message": "all AC sources must share one frequency"}]
        )
    if machines and not dc and any(c.type == "source3" for c in sources) and len(machines) > 1:
        raise CircuitValidationError(
            [
                {
                    "code": "unsupported",
                    "message": "only one synchronous machine per grid is supported",
                }
            ]
        )
    f = 0.0 if dc else f_values.pop()
    omega = 2 * math.pi * f

    net_items: dict[str, list[Any]] = {
        "adm": [],
        "nl": [],
        "vs": [],
        "xf": [],
        "pin": [],
        "cpl": [],
    }
    built = Built(network=Network(n_nodes=0), node_of_terminal=node_of_terminal, f=f)

    def series_z(a: int, b: int, z: complex, name: str) -> None:
        if abs(z) < ZERO_Z:
            net_items["vs"].append(VSource(a, b, 0j, name))
        else:
            net_items["adm"].append(Admittance(a, b, 1 / z, name))

    for c in circuit.components:
        ct = CATALOG[c.type]
        p = c.params
        if c.type == "source3":
            u = _f(p, "U_line", ct, c.id)
            uph = u / math.sqrt(3)
            for k, (t, ang) in enumerate((("L1", 0.0), ("L2", -120.0), ("L3", 120.0))):
                v = cmath.rect(uph, math.radians(ang))
                net_items["vs"].append(VSource(N(c.id, t), N(c.id, "N"), v, f"{c.id}#ph{k}"))
            net_items["pin"].append(Pin(N(c.id, "N"), f"{c.id}#ground"))
        elif c.type == "source_dc":
            u = _f(p, "U", ct, c.id)
            net_items["vs"].append(VSource(N(c.id, "P"), N(c.id, "N"), complex(u), f"{c.id}#src"))
            net_items["pin"].append(Pin(N(c.id, "N"), f"{c.id}#ground"))
        elif c.type == "switch3":
            pass  # handled by node merging
        elif c.type == "transformer3":
            if not isinstance(equipment, TransformerSpec):
                raise CircuitValidationError(
                    [
                        {
                            "code": "no_spec",
                            "component": c.id,
                            "message": f"{c.id}: this project has no transformer specification",
                        }
                    ]
                )
            _expand_transformer(c, equipment, f, dc, N, new_node, series_z, net_items, built)
        elif c.type == "motor3":
            if not isinstance(equipment, MotorSpec):
                raise CircuitValidationError(
                    [
                        {
                            "code": "no_spec",
                            "component": c.id,
                            "message": f"{c.id}: this project has no motor specification",
                        }
                    ]
                )
            locked = bool(p.get("locked", False))
            slip = 1.0 if locked else (slips or {}).get(c.id, 1.0)
            if not (0.0 <= slip <= 1.0):
                raise CircuitValidationError(
                    [
                        {
                            "code": "bad_param",
                            "component": c.id,
                            "message": f"{c.id}: slip {slip} outside [0, 1] (motoring only)",
                        }
                    ]
                )
            _expand_motor(c, equipment, f, dc, slip, N, new_node, series_z, net_items, built)
        elif c.type == "syncmachine3":
            if not isinstance(equipment, SyncSpec):
                raise CircuitValidationError(
                    [
                        {
                            "code": "no_spec",
                            "component": c.id,
                            "message": f"{c.id}: this project has no synchronous-machine spec",
                        }
                    ]
                )
            _expand_sync(
                c,
                equipment,
                f,
                dc,
                (sync_emf or {}).get(c.id, 0j),
                N,
                new_node,
                series_z,
                net_items,
                built,
            )
        elif c.type == "load3":
            kind = str(p.get("kind", "R"))
            conn = str(p.get("connection", "Y"))
            if kind not in ("R", "L", "C") or conn not in ("Y", "D"):
                raise CircuitValidationError(
                    [
                        {
                            "code": "bad_param",
                            "component": c.id,
                            "message": f"{c.id}: bad kind/connection",
                        }
                    ]
                )
            val = _f(p, "value", ct, c.id)
            z = _impedance(kind, val, omega)
            if conn == "Y":
                star = new_node()
                for t in ("1", "2", "3"):
                    _branch(N(c.id, t), star, z, f"{c.id}#{t}", net_items, series_z)
            else:
                for t1, t2 in (("1", "2"), ("2", "3"), ("3", "1")):
                    _branch(N(c.id, t1), N(c.id, t2), z, f"{c.id}#{t1}{t2}", net_items, series_z)
        elif c.type in ("resistor", "inductor", "capacitor"):
            key = {"resistor": "R", "inductor": "L", "capacitor": "C"}[c.type]
            val = _f(p, key, ct, c.id)
            z = _impedance(key, val, omega)
            _branch(N(c.id, "p"), N(c.id, "n"), z, c.id, net_items, series_z)
        elif c.type == "ammeter":
            net_items["vs"].append(VSource(N(c.id, "p"), N(c.id, "n"), 0j, f"{c.id}#I"))
            built.instruments[c.id] = {"type": "ammeter"}
        elif c.type == "voltmeter":
            built.instruments[c.id] = {"type": "voltmeter"}
        elif c.type == "wattmeter":
            net_items["vs"].append(VSource(N(c.id, "Ip"), N(c.id, "In"), 0j, f"{c.id}#I"))
            built.instruments[c.id] = {"type": "wattmeter"}

    n_nodes = counter[0]
    _check_voltage_loops(net_items["vs"], n_nodes)

    # Galvanic groups: which nodes have a defined potential relative to each other.
    guf = _UnionFind()
    for i in range(n_nodes):
        guf.add(str(i))
    for a in net_items["adm"]:
        guf.union(str(a.a), str(a.b))
    for nl in net_items["nl"]:
        guf.union(str(nl.a), str(nl.b))
    for s in net_items["vs"]:
        guf.union(str(s.a), str(s.b))
    for x in net_items["xf"]:
        guf.union(str(x.p1), str(x.p2))
        guf.union(str(x.s1), str(x.s2))
    for cpl in net_items["cpl"]:
        for a_, b_ in cpl.pairs:
            guf.union(str(a_), str(b_))
    group_ids: dict[str, int] = {}
    for i in range(n_nodes):
        r = guf.find(str(i))
        group_ids.setdefault(r, len(group_ids))
        built.group_of_node[i] = group_ids[r]
    pinned = {built.group_of_node[p.node] for p in net_items["pin"]}
    term_names: dict[int, list[str]] = {}
    for tkey, tnode in node_of_terminal.items():
        term_names.setdefault(tnode, []).append(tkey)
    for g in range(len(group_ids)):
        if g in pinned:
            continue
        nodes = sorted(n for n, gg in built.group_of_node.items() if gg == g)
        net_items["pin"].append(Pin(nodes[0], f"#float{g}"))
        names = sorted(t for n in nodes for t in term_names.get(n, []))
        if names:
            built.floating_groups.append(names)

    built.network = Network(
        n_nodes=n_nodes,
        admittances=net_items["adm"],
        nonlinear=net_items["nl"],
        vsources=net_items["vs"],
        transformers=net_items["xf"],
        pins=net_items["pin"],
        coupled=net_items["cpl"],
    )
    return built


def _impedance(kind: str, val: float, omega: float) -> complex:
    if kind == "R":
        return complex(val, 0)
    if kind == "L":
        return complex(0, omega * val)
    # capacitor
    if omega == 0:
        return complex(math.inf, 0)
    return complex(0, -1 / (omega * val))


def _branch(
    a: int,
    b: int,
    z: complex,
    name: str,
    net_items: dict[str, list[Any]],
    series_z: Callable[[int, int, complex, str], None],
) -> None:
    if math.isinf(z.real) or math.isinf(z.imag):
        return  # open circuit (capacitor at DC)
    series_z(a, b, z, name)


def _expand_transformer(
    c: Component,
    spec: TransformerSpec,
    f: float,
    dc: bool,
    N: Callable[[str, str], int],
    new_node: Callable[[], int],
    series_z: Callable[[int, int, complex, str], None],
    net_items: dict[str, list[Any]],
    built: Built,
) -> None:
    e = spec.ecm
    scale = f / spec.nameplate.f_n  # reactances are specified at rated frequency
    k = spec.turns_ratio
    e_ref = spec.U1_winding * (f / spec.nameplate.f_n) if not dc else 1.0
    phases = (("A", "a"), ("B", "b"), ("C", "c"))
    internals: dict[str, Any] = {"phases": {}, "R1": e.R1, "R2": e.R2, "R_fe": e.R_fe}
    for P, s in phases:
        p1, p2 = N(c.id, f"{P}1"), N(c.id, f"{P}2")
        s1, s2 = N(c.id, f"{s}1"), N(c.id, f"{s}2")
        if dc:
            # DC steady state: inductances are shorts, the magnetizing branch carries the full
            # DC current, nothing is transferred to the other winding. The terminal behaviour
            # of each winding is therefore just its resistance.
            series_z(p1, p2, complex(e.R1, 0), f"{c.id}#{P}#R1dc")
            series_z(s1, s2, complex(e.R2, 0), f"{c.id}#{s}#R2dc")
            internals["phases"][P] = {"dc": True, "i1": f"{c.id}#{P}#R1dc"}
            continue
        e1 = new_node()
        e2 = new_node()
        z1 = complex(e.R1, e.X1 * scale)
        z2 = complex(e.R2, e.X2 * scale)
        series_z(p1, e1, z1, f"{c.id}#{P}#Z1")
        series_z(e2, s1, z2, f"{c.id}#{s}#Z2")
        net_items["adm"].append(Admittance(e1, p2, complex(1 / e.R_fe, 0), f"{c.id}#{P}#Rfe"))

        xm_unsat = e.Xm_unsat * scale
        c_sat, n_sat = e.sat_c, e.sat_n
        # Saturation is a function of flux ∝ E/f; using E_ref scaled with f keeps it so.

        def y_m(
            vmag: float, xm_unsat: float = xm_unsat, c_sat: float = c_sat, n_sat: float = n_sat
        ) -> complex:
            xm = xm_unsat / (1.0 + c_sat * (vmag / e_ref) ** n_sat)
            return complex(0, -1 / xm)

        net_items["nl"].append(NonlinearShunt(e1, p2, y_m, f"{c.id}#{P}#Xm"))
        net_items["xf"].append(IdealTransformer(e1, p2, e2, s2, k, f"{c.id}#{P}#ideal"))
        internals["phases"][P] = {
            "e1": e1,
            "p2": p2,
            "e2": e2,
            "s1": s1,
            "p1": p1,
            "z1": z1,
            "z2": z2,
        }
    built.xfmr_internals[c.id] = internals


def _expand_motor(
    c: Component,
    spec: MotorSpec,
    f: float,
    dc: bool,
    slip: float,
    N: Callable[[str, str], int],
    new_node: Callable[[], int],
    series_z: Callable[[int, int, complex, str], None],
    net_items: dict[str, list[Any]],
    built: Built,
) -> None:
    """Per-winding steady-state T-equivalent with the rotor branch R2'/s + jX2'.

    Valid for a balanced, positive-sequence sinusoidal supply: each winding is then an
    independent impedance. Under unbalance the negative-sequence field sees slip (2 − s), which
    this per-winding model does not represent; `simulate` flags that case.
    """
    e = spec.ecm
    k = f / spec.nameplate.f_n  # reactances are specified at rated frequency
    meta: dict[str, Any] = {"slip": slip, "f": f, "dc": dc, "phases": {}, "spec": spec}
    for X in ("U", "V", "W"):
        p, q = N(c.id, f"{X}1"), N(c.id, f"{X}2")
        if dc:
            # DC: inductances are shorts, nothing couples to the rotor → winding resistance only.
            series_z(p, q, complex(e.R1, 0), f"{c.id}#{X}#R1dc")
            meta["phases"][X] = {"dc": True}
            continue
        node_e = new_node()
        series_z(p, node_e, complex(e.R1, e.X1 * k), f"{c.id}#{X}#Z1")
        net_items["adm"].append(Admittance(node_e, q, complex(1 / e.R_fe, 0), f"{c.id}#{X}#Rfe"))
        net_items["adm"].append(Admittance(node_e, q, 1 / complex(0, e.Xm * k), f"{c.id}#{X}#Xm"))
        if slip > 0:
            # s = 0 (synchronous speed): no rotor current — the branch is open.
            series_z(node_e, q, complex(e.R2p / slip, e.X2p * k), f"{c.id}#{X}#Z2")
        meta["phases"][X] = {"e": node_e, "q": q}
    built.motor_internals[c.id] = meta


A120 = complex(-0.5, math.sqrt(3) / 2)  # e^{j120°}


def sequence_impedance_matrix(z0: complex, z1: complex, z2: complex) -> Any:
    """Phase-domain impedance matrix (phases U, V, W; V lags U by 120°) from sequence
    impedances: Z_abc = A·diag(Z0, Z1, Z2)·A⁻¹."""
    import numpy as np

    a = A120
    A = np.array([[1, 1, 1], [1, a * a, a], [1, a, a * a]], dtype=np.complex128)
    return A @ np.diag([z0, z1, z2]).astype(np.complex128) @ np.linalg.inv(A)


def _expand_sync(
    c: Component,
    spec: SyncSpec,
    f: float,
    dc: bool,
    emf: complex,
    N: Callable[[str, str], int],
    new_node: Callable[[], int],
    series_z: Callable[[int, int, complex, str], None],
    net_items: dict[str, list[Any]],
    built: Built,
) -> None:
    """Each winding X1→X2 is: X2 —[EMF E_k]— e_k —[coupled Z_abc]— X1 (generator view).
    The positive-sequence EMF E_U = emf, E_V = a²·emf, E_W = a·emf. DC: winding resistances,
    and the field winding F1–F2 as its resistance."""
    import numpy as np

    e = spec.ecm
    if dc:
        for X in ("U", "V", "W"):
            series_z(N(c.id, f"{X}1"), N(c.id, f"{X}2"), complex(e.Ra, 0), f"{c.id}#{X}#Radc")
        series_z(N(c.id, "F1"), N(c.id, "F2"), complex(e.R_f, 0), f"{c.id}#F#Rdc")
        built.sync_internals[c.id] = {"dc": True}
        return
    k = f / spec.nameplate.f_n
    zabc = sequence_impedance_matrix(
        complex(e.Ra, e.X0 * k), complex(e.Ra, e.Xl * k), complex(e.Ra, e.X2 * k)
    )
    a = A120
    pattern = {"U": 1 + 0j, "V": a * a, "W": a}
    pairs: list[tuple[int, int]] = []
    for X in ("U", "V", "W"):
        node_e = new_node()
        net_items["vs"].append(VSource(node_e, N(c.id, f"{X}2"), emf * pattern[X], f"{c.id}#{X}#E"))
        pairs.append((node_e, N(c.id, f"{X}1")))
    cpl = CoupledAdmittance(pairs, np.linalg.inv(zabc), f"{c.id}#Zabc")
    net_items["cpl"].append(cpl)
    built.sync_internals[c.id] = {"dc": False, "f": f, "coupled": cpl, "spec": spec, "emf": emf}


def _check_voltage_loops(vsources: list[VSource], n_nodes: int) -> None:
    """A loop made only of voltage-type branches (sources, ammeters, ideal shorts) has no
    unique solution — e.g. an ammeter connected directly across the supply."""
    uf = _UnionFind()
    for s in vsources:
        if s.a == s.b:
            raise CircuitValidationError(
                [
                    {
                        "code": "shorted_source",
                        "component": s.name.split("#")[0],
                        "message": f"{s.name.split('#')[0]}: both terminals are on the same node "
                        "(short circuit across a source or ammeter)",
                    }
                ]
            )
        if not uf.union(str(s.a), str(s.b)):
            comp = s.name.split("#")[0]
            raise CircuitValidationError(
                [
                    {
                        "code": "voltage_loop",
                        "component": comp,
                        "message": f"{comp} closes a loop of sources/ammeters (e.g. an ammeter in "
                        "parallel with the supply, or a short circuit across the source)",
                    }
                ]
            )
    del n_nodes
