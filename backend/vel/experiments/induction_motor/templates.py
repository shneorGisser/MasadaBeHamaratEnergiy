"""Circuit templates for experiment 2 (figures 4-2 and 4-3 of the lab manual).

Supply → S1 → wattmeter + ammeter on line L1 → motor terminals U1, V1, W1; line voltmeter
between U1 and V1. The motor is connected as its nameplate says (Y: U2–V2–W2 joined;
Δ: U2–V1, V2–W1, W2–U1). The wattmeter voltage coil is taken to the supply neutral, so it
reads one phase of a balanced load in either connection (P_total = 3·P).
"""

from __future__ import annotations

from typing import Literal

from vel.engine.circuit import CircuitModel
from vel.experiments.transformer3ph.templates import _B

Conn = Literal["Y", "D"]


def _feed(b: _B, u_line: float, f: float, conn: Conn, label: str = "רשת + וריאק") -> None:
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
    if conn == "Y":
        b.w("M.U2", "M.V2").w("M.V2", "M.W2")
    else:
        b.w("M.U2", "M.V1").w("M.V2", "M.W1").w("M.W2", "M.U1")


def _motor(b: _B, *, m_load: float = 0.0, locked: bool = False) -> None:
    b.add("M", "motor3", 660, 200, "מנוע + בלם", M_load=m_load, locked=locked)


def no_load(u_line: float, f: float, conn: Conn) -> CircuitModel:
    """Figure 4-3 with the brake released: the shaft carries only friction and windage."""
    b = _B()
    _motor(b)
    _feed(b, u_line, f, conn)
    return b.done()


def locked_rotor(u_start: float, f: float, conn: Conn) -> CircuitModel:
    """Locked-rotor ("short-circuit") test: rotor held, voltage raised from zero."""
    b = _B()
    _motor(b, locked=True)
    _feed(b, u_start, f, conn)
    return b.done()


def load_test(u_line: float, f: float, conn: Conn, m_load: float = 0.0) -> CircuitModel:
    """Figure 4-3: rated voltage, magnetic-powder brake loads the shaft."""
    b = _B()
    _motor(b, m_load=m_load)
    _feed(b, u_line, f, conn)
    return b.done()


def inverter(u_line: float, f: float, conn: Conn) -> CircuitModel:
    """Figure 4-5: the variac is replaced by the inverter output (fundamental only)."""
    b = _B()
    _motor(b)
    _feed(b, u_line, f, conn, label="אינוורטר (יסודית)")
    return b.done()


WINDINGS = (("U", "ליפוף U1–U2"), ("V", "ליפוף V1–V2"), ("W", "ליפוף W1–W2"))


def dc_winding(winding: str, u: float = 1.0) -> CircuitModel:
    """Figure 4-2: DC supply → ammeter → one winding; voltmeter across the winding."""
    if winding not in ("U", "V", "W"):
        raise ValueError(winding)
    b = _B()
    b.add("G", "source_dc", 0, 200, "ספק DC", U=u)
    b.add("A", "ammeter", 200, 100, "A")
    b.add("V", "voltmeter", 420, 300, "V")
    b.add("M", "motor3", 620, 200, "מנוע")
    b.w("G.P", "A.p").w("A.n", f"M.{winding}1").w(f"M.{winding}2", "G.N")
    b.w("V.p", f"M.{winding}1").w("V.n", f"M.{winding}2")
    return b.done()
