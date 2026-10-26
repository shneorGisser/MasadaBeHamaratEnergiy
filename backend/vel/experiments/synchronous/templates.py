"""Circuit templates for experiment 3 (figures 6-2 and 6-3 of the lab manual).

Generator: the machine G is driven by the servo motor at n_drive (no grid); its field current
is a component parameter (the DC supply + field rheostat + A2 of fig. 6-3 set it). Line U
carries wattmeter W and ammeter A1, voltmeter U1 reads the line voltage U–V, switch S3
connects the three-phase load. Motor (V-curves): the same machine on the grid through S.
"""

from __future__ import annotations

from typing import Literal

from vel.engine.circuit import CircuitModel
from vel.experiments.transformer3ph.templates import _B

Conn = Literal["Y", "D"]


def _connect(b: _B, conn: Conn) -> None:
    if conn == "Y":
        b.w("G.U2", "G.V2").w("G.V2", "G.W2")
    else:
        b.w("G.U2", "G.V1").w("G.V2", "G.W1").w("G.W2", "G.U1")


def _machine(b: _B, i_f: float, n: float, p_shaft: float = 0.0) -> None:
    b.add("G", "syncmachine3", 660, 200, "מכונה סינכרונית", I_f=i_f, n_drive=n, P_shaft=p_shaft)


def generator(
    i_f: float,
    n: float,
    conn: Conn,
    *,
    load_kind: str = "R",
    load_value: float = 1000.0,
    closed: bool = True,
) -> CircuitModel:
    """Figure 6-3: G → A1, W (line U) → S3 → three-phase load; U1 across U–V. The current coil
    is oriented from the generator towards the load, so delivered power reads positive."""
    b = _B()
    _machine(b, i_f, n)
    # power flows right to left (G → meters → S3 → load): the meters and the load are drawn
    # mirrored so their terminals face the way the current comes from
    b.add("L", "load3", 0, 220, "עומס תלת-פזי", flip=True, kind=load_kind, connection="Y",
          value=load_value)  # fmt: skip
    b.add("S", "switch3", 170, 220, "S3", closed=closed)
    b.add("W", "wattmeter", 320, 60, "W", flip=True)
    b.add("A", "ammeter", 470, 60, "A1", flip=True)
    b.add("V1", "voltmeter", 470, 420, "U1 (קווי)")
    b.w("L.1", "S.i1").w("L.2", "S.i2").w("L.3", "S.i3")
    b.w("G.U1", "A.p").w("A.n", "W.Ip").w("W.In", "S.o1")
    b.w("S.o2", "G.V1").w("S.o3", "G.W1")
    b.w("W.Vp", "G.U1").w("W.Vn", "G.U2")
    b.w("V1.p", "G.U1").w("V1.n", "G.V1")
    _connect(b, conn)
    return b.done()


FAULTS = (("3", "קצר תלת-פזי"), ("2", "קצר דו-פזי"), ("1", "קצר חד-פזי (פאזה–אפס)"))


def short_circuit(fault: str, i_f: float, n: float, conn: Conn) -> CircuitModel:
    """Table 6.4: line U through A1 shorted to V and W (3), to V only (2), or to the star
    point (1, terminals S4-S5-S6 joined = U2-V2-W2)."""
    if fault not in ("3", "2", "1"):
        raise ValueError(fault)
    b = _B()
    _machine(b, i_f, n)
    b.add("A", "ammeter", 400, 60, "A1")
    b.w("G.U1", "A.p")
    if fault == "3":
        b.w("A.n", "G.V1").w("G.V1", "G.W1")
    elif fault == "2":
        b.w("A.n", "G.V1")
    else:
        if conn != "Y":
            raise ValueError("a line–neutral fault needs a star-connected machine")
        b.w("A.n", "G.U2")
    _connect(b, conn)
    return b.done()


def motor_on_grid(u_line: float, f: float, conn: Conn, i_f: float, p_shaft: float) -> CircuitModel:
    """V-curves: grid (variac) → S → W, A1 (line U) → machine; U1 across U–V. On the grid the
    speed is synchronous; n_drive is not used."""
    b = _B()
    _machine(b, i_f, 1500.0, p_shaft)
    b.add("N", "source3", 0, 225, "רשת + וריאק", U_line=u_line, f=f)
    b.add("S", "switch3", 170, 225, "S", closed=True)
    b.add("W", "wattmeter", 320, 60, "W")
    b.add("A", "ammeter", 470, 60, "A1")
    b.add("V1", "voltmeter", 470, 420, "U1 (קווי)")
    b.w("N.L1", "S.i1").w("N.L2", "S.i2").w("N.L3", "S.i3")
    b.w("S.o1", "W.Ip").w("W.In", "A.p").w("A.n", "G.U1")
    b.w("S.o2", "G.V1").w("S.o3", "G.W1")
    b.w("W.Vp", "G.U1").w("W.Vn", "N.N")
    b.w("V1.p", "G.U1").w("V1.n", "G.V1")
    _connect(b, conn)
    return b.done()


WINDINGS = (
    ("U", "סטטור U1–U2"),
    ("V", "סטטור V1–V2"),
    ("W", "סטטור W1–W2"),
    ("F", "רוטור (עירור) F1–F2"),
)


def dc_winding(winding: str, u: float = 1.0) -> CircuitModel:
    """Figure 6-2: DC supply → ammeter → one winding; voltmeter across it."""
    if winding not in ("U", "V", "W", "F"):
        raise ValueError(winding)
    t1, t2 = ("F1", "F2") if winding == "F" else (f"{winding}1", f"{winding}2")
    b = _B()
    b.add("P", "source_dc", 0, 200, "ספק DC 0–25 V", U=u)
    b.add("A", "ammeter", 200, 100, "A")
    b.add("V", "voltmeter", 420, 300, "V")
    b.add("G", "syncmachine3", 620, 200, "מכונה סינכרונית")
    b.w("P.P", "A.p").w("A.n", f"G.{t1}").w(f"G.{t2}", "P.N")
    b.w("V.p", f"G.{t1}").w("V.n", f"G.{t2}")
    return b.done()
