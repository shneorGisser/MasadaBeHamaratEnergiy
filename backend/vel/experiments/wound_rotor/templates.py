"""Circuit templates for experiment 4 (figures 4-2, 4-3, 4-6 of the lab manual).

Motor circuits (fig. 4-3): supply → S1 → wattmeter + ammeter on line U → stator U1, V1, W1;
line voltmeter V1; the slip rings R1–R3 go to the rotor starter Rst (a three-phase resistor in
star). "Starter at zero" is drawn as the rings shorted together.
"""

from __future__ import annotations

from typing import Literal

from vel.engine.circuit import CircuitModel
from vel.experiments.transformer3ph.templates import _B

Conn = Literal["Y", "D"]


def _stator(b: _B, conn: Conn) -> None:
    if conn == "Y":
        b.w("M.U2", "M.V2").w("M.V2", "M.W2")
    else:
        b.w("M.U2", "M.V1").w("M.V2", "M.W1").w("M.W2", "M.U1")


def _feed(b: _B, u_line: float, f: float, label: str = "רשת + וריאק") -> None:
    b.add("G", "source3", 0, 225, label, U_line=u_line, f=f)
    b.add("S", "switch3", 170, 225, "S1", closed=True)
    b.add("W", "wattmeter", 320, 60, "W")
    b.add("A", "ammeter", 470, 60, "A1")
    b.add("V1", "voltmeter", 470, 420, "V1 (קווי)")
    b.w("G.L1", "S.i1").w("G.L2", "S.i2").w("G.L3", "S.i3")
    b.w("S.o1", "W.Ip").w("W.In", "A.p").w("A.n", "M.U1")
    b.w("S.o2", "M.V1").w("S.o3", "M.W1")
    b.w("W.Vp", "M.U1").w("W.Vn", "G.N")
    b.w("V1.p", "M.U1").w("V1.n", "M.V1")


def motor(
    u_line: float,
    f: float,
    conn: Conn,
    *,
    r_ext: float | None = None,
    locked: bool = False,
    label: str = "רשת + וריאק",
) -> CircuitModel:
    """Fig. 4-3. r_ext None → rings shorted (starter at zero); otherwise starter Rst per phase."""
    b = _B()
    b.add("M", "woundmotor3", 660, 200, "מכונה + בלם", M_load=0.0, locked=locked)
    _feed(b, u_line, f, label)
    _stator(b, conn)
    if r_ext is None:
        b.w("M.R1", "M.R2").w("M.R2", "M.R3")
    else:
        b.add("Rst", "load3", 900, 420, "מתנע Rst", kind="R", connection="Y", value=r_ext)
        b.w("M.R1", "Rst.1").w("M.R2", "Rst.2").w("M.R3", "Rst.3")
    return b.done()


def rotor_open(u_line: float, f: float, conn: Conn) -> CircuitModel:
    """Table 4.3: rings disconnected from the starter, voltmeter V2 across R1–R2."""
    b = _B()
    b.add("M", "woundmotor3", 660, 200, "מכונה", speed_mode="speed", n_set=0.0)
    _feed(b, u_line, f)
    _stator(b, conn)
    b.add("V2", "voltmeter", 900, 420, "V2 (רוטור)")
    b.w("V2.p", "M.R1").w("V2.n", "M.R2")
    return b.done()


def regulator(u_line: float, f: float) -> CircuitModel:
    """Fig. 4-6, induction regulator: the supply feeds the rotor through the rings (shunt), each
    stator winding is in series between the supply line and the output (S4→S1 = U2→U1);
    U1 reads the supply, U2 the output line voltage. Rotor locked at an adjustable angle."""
    b = _B()
    b.add("M", "woundmotor3", 660, 200, "מכונה (רוטור נעול)", locked=True, angle=0.0)
    b.add("G", "source3", 0, 225, "רשת + וריאק", U_line=u_line, f=f)
    b.add("S", "switch3", 170, 225, "S1", closed=True)
    b.add("V1", "voltmeter", 320, 420, "U1 (כניסה)")
    b.add("V2", "voltmeter", 900, 420, "U2 (יציאה)")
    b.w("G.L1", "S.i1").w("G.L2", "S.i2").w("G.L3", "S.i3")
    b.w("S.o1", "M.R1").w("S.o2", "M.R2").w("S.o3", "M.R3")
    b.w("M.R1", "M.U2").w("M.R2", "M.V2").w("M.R3", "M.W2")
    b.w("V1.p", "M.R1").w("V1.n", "M.R2")
    b.w("V2.p", "M.U1").w("V2.n", "M.V1")
    return b.done()


STATOR = (("U", "סטטור U1–U2"), ("V", "סטטור V1–V2"), ("W", "סטטור W1–W2"))
ROTOR = (("R12", "רוטור R1–R2"), ("R23", "רוטור R2–R3"), ("R31", "רוטור R3–R1"))
WINDINGS = STATOR + ROTOR


def dc_winding(winding: str, u: float = 1.0) -> CircuitModel:
    """Fig. 4-2: DC supply → ammeter → a stator winding, or between two slip rings (two rotor
    phases in series, since the rotor star point is internal)."""
    terms = {
        "U": ("U1", "U2"),
        "V": ("V1", "V2"),
        "W": ("W1", "W2"),
        "R12": ("R1", "R2"),
        "R23": ("R2", "R3"),
        "R31": ("R3", "R1"),
    }
    if winding not in terms:
        raise ValueError(winding)
    t1, t2 = terms[winding]
    b = _B()
    b.add("P", "source_dc", 0, 200, "ספק DC", U=u)
    b.add("A", "ammeter", 200, 100, "A")
    b.add("V", "voltmeter", 420, 300, "V")
    b.add("M", "woundmotor3", 620, 200, "מכונה")
    b.w("P.P", "A.p").w("A.n", f"M.{t1}").w(f"M.{t2}", "P.N")
    b.w("V.p", f"M.{t1}").w("V.n", f"M.{t2}")
    return b.done()
