"""Circuit templates that reproduce the lab manual's wiring diagrams (figures 1.2–1.7).

Templates only produce an initial CircuitModel; once stored in the project the circuit is the
user's to edit (S2), and the solver always runs the stored circuit, never the template.
Layout coordinates are schematic-editor units (LTR drawing space).
"""

from __future__ import annotations

from typing import Any, Literal

from vel.engine.circuit import CircuitModel

SecondaryConn = Literal["Y", "D"]


class _B:
    def __init__(self) -> None:
        self.components: list[dict[str, Any]] = []
        self.wires: list[dict[str, Any]] = []
        self.layout: dict[str, dict[str, Any]] = {}

    def add(self, cid: str, typ: str, x: float, y: float, label: str = "", **params: Any) -> _B:
        self.components.append({"id": cid, "type": typ, "label": label, "params": params})
        self.layout[cid] = {"x": x, "y": y, "rot": 0}
        return self

    def w(self, a: str, b: str) -> _B:
        ca, ta = a.split(".")
        cb, tb = b.split(".")
        self.wires.append(
            {
                "id": f"w{len(self.wires) + 1}",
                "a": {"component": ca, "terminal": ta},
                "b": {"component": cb, "terminal": tb},
            }
        )
        return self

    def done(self) -> CircuitModel:
        return CircuitModel.model_validate(
            {"components": self.components, "wires": self.wires, "layout": self.layout}
        )


def _primary_feed(b: _B, u_line: float, f: float, *, line_voltmeter: bool = True) -> None:
    """Supply → 3-pole switch S → wattmeter (phase A) → ammeter → primary A1/B1/C1 (fig. 1.3)."""
    # Aligned so that S.o2 → T.B1 and S.o3 → T.C1 run nearly straight (switch y ≈ T y + 25).
    b.add("G", "source3", 0, 225, "רשת + וריאק", U_line=u_line, f=f)
    b.add("S", "switch3", 170, 225, "S", closed=True)
    b.add("W", "wattmeter", 320, 60, "W")
    b.add("A", "ammeter", 470, 60, "A")
    b.add("T", "transformer3", 640, 200, "שנאי")
    b.w("G.L1", "S.i1").w("G.L2", "S.i2").w("G.L3", "S.i3")
    b.w("S.o1", "W.Ip").w("W.In", "A.p").w("A.n", "T.A1")
    b.w("S.o2", "T.B1").w("S.o3", "T.C1")
    # primary star
    b.w("T.A2", "T.B2").w("T.B2", "T.C2")
    # wattmeter voltage coil across the phase-A winding (phase voltage)
    b.w("W.Vp", "T.A1").w("W.Vn", "T.A2")
    if line_voltmeter:
        b.add("V1", "voltmeter", 470, 420, "V1 (קווי)")
        b.w("V1.p", "T.A1").w("V1.n", "T.B1")


def _secondary(b: _B, conn: SecondaryConn) -> None:
    if conn == "Y":
        b.w("T.a2", "T.b2").w("T.b2", "T.c2")
    else:
        # delta: end of each winding to the start of the next (a2–b1, b2–c1, c2–a1)
        b.w("T.a2", "T.b1").w("T.b2", "T.c1").w("T.c2", "T.a1")


def no_load(u1n: float, f: float, conn: SecondaryConn = "Y") -> CircuitModel:
    """Figures 1.3/1.4: no-load test, primary in star, secondary in star or delta."""
    b = _B()
    _primary_feed(b, u1n, f)
    b.add("V1ph", "voltmeter", 640, 470, "V1 (פאזי)")
    b.w("V1ph.p", "T.A1").w("V1ph.n", "T.A2")
    _secondary(b, conn)
    b.add("V2", "voltmeter", 900, 120, "V2 (קווי)")
    b.w("V2.p", "T.a1").w("V2.n", "T.b1")
    b.add("V2ph", "voltmeter", 900, 300, "V2 (פאזי)")
    b.w("V2ph.p", "T.a1").w("V2ph.n", "T.a2")
    return b.done()


def short_circuit(u_start: float, f: float) -> CircuitModel:
    """Figure 1.5: star–star, secondary lines shorted together through ammeter A2."""
    b = _B()
    _primary_feed(b, u_start, f)
    _secondary(b, "Y")
    b.add("A2", "ammeter", 860, 200, "A2")
    b.w("T.a1", "A2.p").w("A2.n", "T.b1").w("T.c1", "T.b1")
    return b.done()


def dc_winding(winding: str, u: float = 1.0) -> CircuitModel:
    """Figure 1.2: DC supply → ammeter → one winding; voltmeter across the winding."""
    if winding not in ("A", "B", "C", "a", "b", "c"):
        raise ValueError(winding)
    b = _B()
    b.add("G", "source_dc", 0, 200, "ספק DC", U=u)
    b.add("A", "ammeter", 200, 100, "A")
    b.add("V", "voltmeter", 420, 300, "V")
    b.add("T", "transformer3", 620, 200, "שנאי")
    b.w("G.P", "A.p").w("A.n", f"T.{winding}1").w(f"T.{winding}2", "G.N")
    b.w("V.p", f"T.{winding}1").w("V.n", f"T.{winding}2")
    return b.done()


def load_test(u1n: float, f: float, kind: str = "R", value: float = 50.0) -> CircuitModel:
    """Figure 1.7: rated primary voltage; secondary star feeding a three-phase R/L/C load through
    switch S2, ammeter A2 and wattmeter W2 (phase a)."""
    b = _B()
    _primary_feed(b, u1n, f)
    _secondary(b, "Y")
    b.add("W2", "wattmeter", 860, 60, "W2")
    b.add("A2", "ammeter", 980, 60, "A2")
    b.add("S2", "switch3", 1100, 200, "S2", closed=True)
    b.add("L", "load3", 1260, 200, "עומס", kind=kind, connection="Y", value=value)
    b.w("T.a1", "W2.Ip").w("W2.In", "A2.p").w("A2.n", "S2.i1")
    b.w("T.b1", "S2.i2").w("T.c1", "S2.i3")
    b.w("S2.o1", "L.1").w("S2.o2", "L.2").w("S2.o3", "L.3")
    b.w("W2.Vp", "T.a1").w("W2.Vn", "T.a2")
    b.add("V2", "voltmeter", 900, 430, "V2 (קווי)")
    b.w("V2.p", "T.a1").w("V2.n", "T.b1")
    b.add("V2ph", "voltmeter", 1060, 430, "V2 (פאזי)")
    b.w("V2ph.p", "T.a1").w("V2ph.n", "T.a2")
    return b.done()


VG_VARIANTS = {
    # name: (secondary connection, order of windings taking the roles a,b,c, reversed, closure)
    "Yy-abc": ("Y", "abc", False, 1),
    "Yy-bca": ("Y", "bca", False, 1),
    "Yy-cab": ("Y", "cab", False, 1),
    "Yy-abc-rev": ("Y", "abc", True, 1),
    "Yd-abc-1": ("D", "abc", False, 1),
    "Yd-abc-2": ("D", "abc", False, 2),
}


def vector_group(u_line: float, f: float, variant: str = "Yy-abc") -> CircuitModel:
    """Section 6 (clock method): bridge A1 to the terminal that plays the role of a1 and measure
    U(aA–B1), U(aA–b1), U(B1–b1) with three voltmeters at a reduced line voltage (100 V).

    `order` says which physical winding plays a, b, c (e.g. "cab": winding c is wired as phase a).
    `reversed` swaps the start/end of every secondary winding. Delta closure 1: x2→y1
    (end of each winding to the start of the next); closure 2: x1→y2.
    """
    conn, order, rev, closure = VG_VARIANTS[variant]
    s_, e_ = ("2", "1") if rev else ("1", "2")
    w = [order[0], order[1], order[2]]
    b = _B()
    b.add("G", "source3", 0, 200, "רשת + וריאק", U_line=u_line, f=f)
    b.add("S", "switch3", 160, 200, "S", closed=True)
    b.add("T", "transformer3", 620, 200, "שנאי")
    b.w("G.L1", "S.i1").w("G.L2", "S.i2").w("G.L3", "S.i3")
    b.w("S.o1", "T.A1").w("S.o2", "T.B1").w("S.o3", "T.C1")
    b.w("T.A2", "T.B2").w("T.B2", "T.C2")
    starts = [f"T.{x}{s_}" for x in w]
    ends = [f"T.{x}{e_}" for x in w]
    if conn == "Y":
        b.w(ends[0], ends[1]).w(ends[1], ends[2])
        line = starts
    elif closure == 1:
        b.w(ends[0], starts[1]).w(ends[1], starts[2]).w(ends[2], starts[0])
        line = starts
    else:
        b.w(starts[0], ends[1]).w(starts[1], ends[2]).w(starts[2], ends[0])
        line = starts
    # bridge A1 ↔ (terminal playing a1) — common point "aA"
    b.w("T.A1", line[0])
    b.add("VaAB", "voltmeter", 420, 340, "U aA–B1")
    b.w("VaAB.p", "T.A1").w("VaAB.n", "T.B1")
    b.add("VaAb", "voltmeter", 860, 120, "U aA–b1")
    b.w("VaAb.p", "T.A1").w("VaAb.n", line[1])
    b.add("VBb", "voltmeter", 860, 340, "U B1–b1")
    b.w("VBb.p", "T.B1").w("VBb.n", line[1])
    return b.done()
