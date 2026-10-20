"""Step-by-step wiring guide for a study circuit: which cable goes from which terminal to which,
in the order a student wires the bench.

The guide is derived from the same circuit document the solver and the schematic use, so it
cannot contradict the simulation. Order, as taught in the lab:

1. supplies off, variac at zero, switches open;
2. each current path ("power" cables), traced outward from its source's + / L1 terminal;
   paths without a source (a generator's armature, a rotor circuit) come after;
3. the voltage leads of voltmeters and wattmeter voltage coils last, in parallel;
4. count the cables, ask for the instructor's check before switching on.

Cable colours follow IEC 60445 for the supply nets (L1 brown, L2 black, L3 grey, N blue; DC +
red, − black); every other cable is "any colour". Until photos of the real terminal boards
exist, terminals are named as on the schematic.
"""

from __future__ import annotations

from typing import Any

from vel.engine.circuit import CircuitModel
from vel.engine.netlist import CATALOG

# terminals joined inside a component for the purpose of following a current path
_INTERNAL: dict[str, tuple[tuple[str, ...], ...]] = {
    "source_dc": (("P", "N"),),
    "source3": (("L1", "L2", "L3", "N"),),
    "switch3": (("i1", "o1"), ("i2", "o2"), ("i3", "o3")),
    "resistor": (("p", "n"),),
    "inductor": (("p", "n"),),
    "capacitor": (("p", "n"),),
    "ammeter": (("p", "n"),),
    "wattmeter": (("Ip", "In"),),
    "load3": (("1", "2", "3"),),
    "transformer3": (
        ("A1", "A2"),
        ("B1", "B2"),
        ("C1", "C2"),
        ("a1", "a2"),
        ("b1", "b2"),
        ("c1", "c2"),
    ),
    "motor3": (("U1", "U2"), ("V1", "V2"), ("W1", "W2")),
    "syncmachine3": (("U1", "U2"), ("V1", "V2"), ("W1", "W2"), ("F1", "F2")),
    "woundmotor3": (("U1", "U2"), ("V1", "V2"), ("W1", "W2"), ("R1", "R2", "R3")),
    "dcmachine": (("A1", "A2"), ("F1", "F2"), ("S1", "S2")),
}

# winding / circuit names by machine terminal prefix
_WINDING: dict[str, dict[str, str]] = {
    "dcmachine": {"A": "עוגן", "F": "עירור מקבילי", "S": "עירור טורי"},
    "syncmachine3": {"U": "סטטור", "V": "סטטור", "W": "סטטור", "F": "עירור (רוטור)"},
    "woundmotor3": {"U": "סטטור", "V": "סטטור", "W": "סטטור", "R": "רוטור (טבעות)"},
    "motor3": {"U": "סטטור", "V": "סטטור", "W": "סטטור"},
    "transformer3": {
        "A": "ליפוף ראשוני",
        "B": "ליפוף ראשוני",
        "C": "ליפוף ראשוני",
        "a": "ליפוף משני",
        "b": "ליפוף משני",
        "c": "ליפוף משני",
    },
}

_MEASURE_TERMINALS = {
    ("voltmeter", "p"),
    ("voltmeter", "n"),
    ("wattmeter", "Vp"),
    ("wattmeter", "Vn"),
}

# IEC 60445 colours of supply conductors
_COLOURS = {
    ("source3", "L1"): ("חום", "#7b4a2a"),
    ("source3", "L2"): ("שחור", "#1b1b1b"),
    ("source3", "L3"): ("אפור", "#8a8f94"),
    ("source3", "N"): ("כחול", "#1f5fbf"),
    ("source_dc", "P"): ("אדום", "#c0392b"),
    ("source_dc", "N"): ("שחור", "#1b1b1b"),
}
_ANY = ("כל צבע", "#5d6d7e")


class _UF:
    def __init__(self) -> None:
        self.p: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: str, b: str) -> None:
        self.p[self.find(a)] = self.find(b)


def _end(c: CircuitModel, ref: Any) -> dict[str, Any]:
    comp = c.component(ref.component)
    ct = CATALOG.get(comp.type)
    return {
        "component": comp.id,
        "label": comp.label or comp.id,
        "type": comp.type,
        "type_he": ct.label_he if ct else comp.type,
        "terminal": ref.terminal,
    }


def _advice(end: dict[str, Any]) -> list[str]:
    """Polarity and placement of an instrument terminal (set-up of other parts: see before)."""
    t, term, cid = end["type"], end["terminal"], end["component"]
    if t == "ammeter":
        side = "החיובי (p) — הצד שממנו מגיע הזרם" if term == "p" else "השלילי (n) — לכיוון הצרכן"
        return [f"מד הזרם {cid} בטור; כאן ההדק {side}"]
    if t == "wattmeter" and term in ("Ip", "In"):
        return [f"סליל הזרם של {cid} בטור; Ip הוא הצד של המקור"]
    if t == "wattmeter":
        return [f"סליל המתח של {cid} במקביל; Vp לאותה פאזה שבה סליל הזרם"]
    if t == "voltmeter":
        return [f"מד המתח {cid} במקביל ({'+' if term == 'p' else '−'})"]
    return []


def _group(order: list[tuple[Any, str]], windings: list[str], sources: list[str]) -> dict[str, Any]:
    title = "מעגל " + (" + ".join(sources) if sources else "ללא מקור (מוזן מהמכונה)")
    if windings:
        title += " → " + ", ".join(windings)
    return {"title_he": title, "kind": "power", "wires": order}


def _setup(c: CircuitModel) -> list[str]:
    out = []
    for comp in c.components:
        name = comp.label or comp.id
        if comp.type == "source3":
            out.append(f"{name}: מנותק, הווריאק במינימום")
        elif comp.type == "source_dc":
            out.append(f"{name}: כבוי, המתח במינימום")
        elif comp.type == "switch3":
            out.append(f"{comp.id} ({name}): פתוח בזמן החיבור")
        elif comp.type == "resistor":
            r = comp.params.get("R")
            val = "פתוח (אינסוף)" if isinstance(r, (int, float)) and r >= 1e6 else f"{r} Ω"
            out.append(f"{name}: לכוון לפני ההפעלה ({val} בתנאי הניסוי)")
        elif comp.type in ("motor3", "woundmotor3", "dcmachine", "syncmachine3"):
            out.append(f"{name}: הציר חופשי, הבלם/הסרוו במצב אפס")
    return out


def guide(circuit: CircuitModel) -> dict[str, Any]:
    c = circuit
    comps = {x.id: x for x in c.components}

    def node(cid: str, t: str) -> str:
        return f"{cid}.{t}"

    def is_measure(w: Any) -> bool:
        return any((comps[e.component].type, e.terminal) in _MEASURE_TERMINALS for e in (w.a, w.b))

    # nets (all cables) for the colour of each cable
    nets = _UF()
    for w in c.wires:
        nets.union(node(w.a.component, w.a.terminal), node(w.b.component, w.b.terminal))
    net_colour: dict[str, tuple[str, str]] = {}
    for comp in c.components:
        for (typ, term), col in _COLOURS.items():
            if comp.type == typ and term in CATALOG[typ].terminals:
                net_colour.setdefault(nets.find(node(comp.id, term)), col)

    power = [w for w in c.wires if not is_measure(w)]
    measure = [w for w in c.wires if is_measure(w)]

    # adjacency over power cables + component internals (to follow current paths). A
    # supply's terminals are NOT joined internally: a path starts at + / L1 and ends at − / N.
    adj: dict[str, list[tuple[str, Any]]] = {}

    def link(a: str, b: str, w: Any) -> None:
        adj.setdefault(a, []).append((b, w))
        adj.setdefault(b, []).append((a, w))

    for w in power:
        link(node(w.a.component, w.a.terminal), node(w.b.component, w.b.terminal), w)
    for comp in c.components:
        if comp.type in ("source3", "source_dc"):
            continue
        for grp in _INTERNAL.get(comp.type, ()):
            for t in grp[1:]:
                link(node(comp.id, grp[0]), node(comp.id, t), None)

    def is_sink(n: str, start: str) -> bool:
        """A path from a supply terminal ends at a machine terminal or another supply terminal:
        "from L1 through the switch, wattmeter and ammeter to U1", then the next phase."""
        if n == start:
            return False
        typ = comps[n.split(".", 1)[0]].type
        return typ in ("source3", "source_dc", "load3") or CATALOG[typ].category == "machine"

    def trace(
        starts: list[str], sinks: bool = True
    ) -> tuple[list[tuple[Any, str]], list[str], list[str], set[str]]:
        """Depth-first from each start in turn: the order in which a student follows a path
        from the supply through every series element. Returns (cable, end it was reached from)
        pairs, the windings and supplies met, and the machine terminals reached."""
        order: list[tuple[Any, str]] = []
        windings: list[str] = []
        sources: list[str] = []
        reached: set[str] = set()

        def note(n: str) -> None:
            cid, term = n.split(".", 1)
            comp = comps[cid]
            if comp.type in ("source3", "source_dc") and (comp.label or comp.id) not in sources:
                sources.append(comp.label or comp.id)
            wname = _WINDING.get(comp.type, {}).get(term[:1])
            if wname and wname not in windings:
                windings.append(wname)
            if CATALOG[comp.type].category == "machine":
                reached.add(n)

        for st in starts:
            if st not in adj:
                continue
            seen: set[str] = set()
            # (node, cable that leads to it, node it was reached from): a cable is recorded
            # when the walk actually goes along it, so one path is finished before the next
            stack: list[tuple[str, Any, str]] = [(st, None, st)]
            while stack:
                n, via, frm = stack.pop()
                if via is not None:
                    if via.id in done:
                        continue
                    done.add(via.id)
                    order.append((via, frm))
                if n in seen:
                    continue
                seen.add(n)
                note(n)
                if sinks and is_sink(n, st):
                    continue
                stack.extend(reversed([(m, w, n) for m, w in adj.get(n, [])]))
        return order, windings, sources, reached

    done: set[str] = set()
    groups: list[dict[str, Any]] = []
    for comp in c.components:
        if comp.type == "source_dc":
            starts = [node(comp.id, "P"), node(comp.id, "N")]
        elif comp.type == "source3":
            starts = [node(comp.id, t) for t in ("L1", "L2", "L3", "N")]
        else:
            continue
        order, windings, sources, reached = trace(starts)
        # the bridges at the machine (star point, series winding …) belong to this circuit
        more, w2, _, _ = trace(sorted(reached), sinks=False)
        order += more
        windings += [x for x in w2 if x not in windings]
        if order:
            groups.append(_group(order, windings, sources))
    # circuits fed by a machine (secondary, rotor, generator armature): from its winding starts
    comp_order = {x.id: i for i, x in enumerate(c.components)}
    while any(w.id not in done for w in power):
        ends = {
            node(e.component, e.terminal)
            for w in power
            if w.id not in done
            for e in (w.a, w.b)
            if CATALOG[comps[e.component].type].category == "machine"
        }
        if ends:
            first = min(ends, key=lambda n: (comp_order[n.split(".")[0]], n.split(".")[1][:1]))
            cid = first.split(".")[0]
            starts = sorted(
                (n for n in ends if n.startswith(cid + ".")),
                key=lambda n: (not n.endswith("1"), n.split(".")[1]),
            )
        else:
            w0 = next(w for w in power if w.id not in done)
            starts = [node(w0.a.component, w0.a.terminal)]
        order, windings, sources, reached = trace(starts)
        more, w2, _, _ = trace(sorted(reached), sinks=False)
        order += more
        windings += [x for x in w2 if x not in windings]
        if not order:  # isolated leftovers: take them as they are
            order, windings, sources, _ = trace(starts, sinks=False)
        if not order:
            break
        groups.append(_group(order, windings, sources))
    if measure:
        groups.append(
            {
                "title_he": "חיבורי מדידת מתח (במקביל) — אחרונים",
                "kind": "measure",
                "wires": [(w, node(w.a.component, w.a.terminal)) for w in measure],
            }
        )

    steps: list[dict[str, Any]] = []
    out_groups: list[dict[str, Any]] = []
    for gi, g in enumerate(groups):
        first_step = len(steps)
        for w, came_from in g["wires"]:
            a, b = _end(c, w.a), _end(c, w.b)
            if came_from != node(w.a.component, w.a.terminal):
                a, b = b, a  # "from" = the end the path reached first
            colour = net_colour.get(nets.find(node(w.a.component, w.a.terminal)), _ANY)
            steps.append(
                {
                    "index": len(steps) + 1,
                    "wire_id": w.id,
                    "group": gi,
                    "kind": g["kind"],
                    "from": a,
                    "to": b,
                    "colour_he": colour[0],
                    "colour": colour[1],
                    "advice": list(dict.fromkeys(_advice(a) + _advice(b))),
                }
            )
        out_groups.append(
            {
                "index": gi,
                "title_he": g["title_he"],
                "kind": g["kind"],
                "steps": [first_step, len(steps)],
            }
        )

    before = [
        "כל מתגי האספקה במעבדה מנותקים",
        *_setup(c),
        "כבלים תקינים בלבד; תקע הבננה יושב עד הסוף",
    ]
    after = [
        f"ספור: {len(steps)} כבלים בסך הכול ({len(steps) - len(measure)} במעגלי הזרם, "
        f"{len(measure)} למדידת מתח)",
        "עבור על המעגל מול הסכמה, כבל אחר כבל",
        "בקש בדיקת מדריך — אין להפעיל לפני אישורו",
    ]
    return {"groups": out_groups, "steps": steps, "before": before, "after": after}
