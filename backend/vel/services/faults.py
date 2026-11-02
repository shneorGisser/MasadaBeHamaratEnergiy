"""Fault-diagnosis challenge: the bench is wired with one hidden fault (or none), the student
sees the instrument readings next to the readings the correct circuit gives, and has to say
what is wrong.

Why: in the real lab a wrong reading is the only symptom of a wiring mistake, and students
rarely learn to read it — they rewire until the numbers look right. Here every fault is a
real change to the circuit document, solved by the same solver as everything else, so the
symptoms are the physics, not a script. The explanation names the symptom to look for.

Faults are chosen among those that apply to the circuit (a star/delta swap needs a motor's six
terminals, a voltmeter fault needs a line-voltage voltmeter) and that the solver can solve;
"no fault" is always one of the options, and sometimes the answer.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from vel.engine.circuit import CircuitModel, TerminalRef, Wire

Mutator = Callable[[CircuitModel], CircuitModel | None]


@dataclass(frozen=True)
class Fault:
    id: str
    title_he: str
    explain_he: str
    apply: Mutator


def _copy(c: CircuitModel) -> CircuitModel:
    return CircuitModel.model_validate(c.model_dump(mode="json"))


def _of_type(c: CircuitModel, *types: str) -> list[str]:
    return [x.id for x in c.components if x.type in types]


def _rename_terminals(c: CircuitModel, comp: str, mapping: dict[str, str]) -> CircuitModel:
    out = _copy(c)

    def ren(t: TerminalRef) -> TerminalRef:
        if t.component == comp and t.terminal in mapping:
            return TerminalRef(component=comp, terminal=mapping[t.terminal])
        return t

    out.wires = [Wire(id=w.id, a=ren(w.a), b=ren(w.b)) for w in out.wires]
    return out


def _reconnect(c: CircuitModel, comp: str, term: str, to: TerminalRef) -> CircuitModel:
    """Unplug every cable from comp.term and plug one cable from there to `to`."""
    out = _copy(c)
    out.wires = [
        w
        for w in out.wires
        if not any(t.component == comp and t.terminal == term for t in (w.a, w.b))
    ]
    out.wires.append(
        Wire(id=f"fault_{comp}_{term}", a=TerminalRef(component=comp, terminal=term), b=to)
    )
    return out


def _source_net(c: CircuitModel, comp: str, term: str) -> str | None:
    """The supply line (L1/L2/L3/N) that comp.term is wired to, following cables, the closed
    contacts of a switch, ammeters and wattmeter current coils (all of zero impedance)."""
    src = _of_type(c, "source3")
    if not src:
        return None
    adj: dict[tuple[str, str], set[tuple[str, str]]] = {}

    def link(x: tuple[str, str], y: tuple[str, str]) -> None:
        adj.setdefault(x, set()).add(y)
        adj.setdefault(y, set()).add(x)

    for w in c.wires:
        link((w.a.component, w.a.terminal), (w.b.component, w.b.terminal))
    for sw in _of_type(c, "switch3"):
        for k in "123":
            link((sw, f"i{k}"), (sw, f"o{k}"))
    for a in _of_type(c, "ammeter"):  # zero-impedance current paths
        link((a, "p"), (a, "n"))
    for w in _of_type(c, "wattmeter"):
        link((w, "Ip"), (w, "In"))
    seen, todo = {(comp, term)}, [(comp, term)]
    while todo:
        x = todo.pop()
        if x[0] == src[0]:
            return x[1]
        for y in adj.get(x, ()):
            if y not in seen:
                seen.add(y)
                todo.append(y)
    return None


def voltmeter_ln(c: CircuitModel) -> CircuitModel | None:
    """A line-voltage voltmeter (L1–L2) with its second lead on N instead of L2."""
    src = _of_type(c, "source3")
    for v in _of_type(c, "voltmeter"):
        if src and _source_net(c, v, "p") == "L1" and _source_net(c, v, "n") == "L2":
            return _reconnect(c, v, "n", TerminalRef(component=src[0], terminal="N"))
    return None


def wattmeter_voltage_ll(c: CircuitModel) -> CircuitModel | None:
    """The wattmeter's voltage coil between L1 and L2 instead of L1 and N."""
    src = _of_type(c, "source3")
    for w in _of_type(c, "wattmeter"):
        if src and _source_net(c, w, "Vn") == "N":
            return _reconnect(c, w, "Vn", TerminalRef(component=src[0], terminal="L2"))
    return None


def wattmeter_reversed(c: CircuitModel) -> CircuitModel | None:
    w = _of_type(c, "wattmeter")
    if not w:
        return None
    return _rename_terminals(c, w[0], {"Ip": "In", "In": "Ip"})


def _motor_links(c: CircuitModel, m: str) -> list[Wire]:
    ends = {"U1", "V1", "W1", "U2", "V2", "W2"}
    return [
        w
        for w in c.wires
        if w.a.component == m and w.b.component == m and {w.a.terminal, w.b.terminal} <= ends
    ]


def star_delta_swap(c: CircuitModel) -> CircuitModel | None:
    """A motor wired in Δ gets the star links instead, and the other way round. The supply
    still reaches U1, V1, W1."""
    ms = _of_type(c, "motor3")
    if not ms:
        return None
    m = ms[0]
    links = _motor_links(c, m)
    pairs = {frozenset((w.a.terminal, w.b.terminal)) for w in links}
    star = {frozenset(("U2", "V2")), frozenset(("V2", "W2"))}
    delta = {frozenset(("U2", "V1")), frozenset(("V2", "W1")), frozenset(("W2", "U1"))}
    if star <= pairs:
        new = delta
    elif delta <= pairs:
        new = star
    else:
        return None
    out = _copy(c)
    out.wires = [w for w in out.wires if w not in links]
    for i, pr in enumerate(sorted(new, key=sorted)):
        a, b = sorted(pr)
        out.wires.append(
            Wire(
                id=f"fault{i}",
                a=TerminalRef(component=m, terminal=a),
                b=TerminalRef(component=m, terminal=b),
            )
        )
    return out


# Not offered, because the steady-state model cannot show them faithfully: a missing phase and a
# swapped phase sequence. The motor model is per winding and positive-sequence only (it flags
# unbalance), and the transformer's saturating branch does not converge on an open line. A
# challenge whose answer the model gets wrong would teach the wrong symptom.
FAULTS: tuple[Fault, ...] = (
    Fault(
        "wattmeter_reversed",
        "סליל הזרם של מד ההספק הפוך (Ip ↔ In)",
        "קריאת ההספק יוצאת שלילית, בערך המוחלט הנכון, ושאר המכשירים לא משתנים. במעבדה מהפכים "
        "את שני הכבלים של סליל הזרם, לא את סליל המתח.",
        wattmeter_reversed,
    ),
    Fault(
        "wattmeter_voltage_ll",
        "סליל המתח של מד ההספק חובר בין שתי פאזות (L1–L2) במקום פאזה–אפס",
        "המד מכפיל עכשיו מתח קווי בזרם הפאזה. המתח גדול פי √3 ומוזז ב-30°, ולכן הקריאה כבר "
        "אינה הספק הפאזה: היא יכולה להיות גדולה או קטנה מהנכון, ואף שלילית, לפי מקדם ההספק. "
        "סימן מזהה: 3·P לא מתאים ל-√3·U·I·cos φ של שאר המדידות.",
        wattmeter_voltage_ll,
    ),
    Fault(
        "voltmeter_ln",
        "מד המתח הקווי חובר בין פאזה לאפס",
        "הקריאה קטנה פי √3 מהמתח הקווי (220 במקום 380 V), ושאר המכשירים לא משתנים. זה המתח "
        "הפאזי, ולא תקלה במעגל עצמו.",
        voltmeter_ln,
    ),
    Fault(
        "star_delta_swap",
        "המנוע חובר בכוכב במקום במשולש (או להפך)",
        "כל ליפוף מקבל מתח קטן פי √3 בכוכב (או גדול פי √3 במשולש). הזרם הקווי והמומנט משתנים "
        "בערך פי 3, וההחלקה בעומס גדלה בכוכב. הזרם הקווי קטן מדי (כוכב) או גדול מדי (משולש) "
        "ביחס לשלט.",
        star_delta_swap,
    ),
)
NONE = Fault("none", "אין תקלה: המעגל מחובר נכון", "כל הקריאות מתאימות למעגל התקין.", lambda c: c)


def applicable(c: CircuitModel) -> list[Fault]:
    return [f for f in FAULTS if f.apply(c) is not None]


def pick(c: CircuitModel, rng: random.Random) -> Fault:
    opts = applicable(c)
    if not opts or rng.random() < 0.15:
        return NONE
    return rng.choice(opts)


def options(c: CircuitModel) -> list[dict[str, Any]]:
    return [{"id": f.id, "title_he": f.title_he} for f in (*applicable(c), NONE)]


def by_id(fid: str) -> Fault:
    for f in (*FAULTS, NONE):
        if f.id == fid:
            return f
    raise KeyError(fid)
