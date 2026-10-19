"""Circuit templates for experiments 5 and 6 (DC machine), after the manual's figures.

Component ids are shared by all templates so the study runners can address them:
M the machine, P the DC supply (armature side), Rf the field rheostat, Af the field ammeter
(A2 in the manual), Aa the armature ammeter (A1), U1 the terminal voltmeter, Rx the extra
armature resistance (R נוסף, motor), RL the load rheostat and S4 its switch (generator).

Series field (compound): "cumulative" means the series MMF adds to the shunt MMF in the mode
the template is for. For a motor the armature current enters A1, so S1→S2 in the return path
is cumulative; for a generator the current leaves A1, so A1→S1, S2→load is cumulative.
"""

from __future__ import annotations

from typing import Literal

from vel.engine.circuit import CircuitModel
from vel.experiments.transformer3ph.templates import _B

Series = Literal["none", "cumulative", "differential"]
Winding = Literal["armature", "series", "shunt"]
WINDINGS: tuple[tuple[Winding, str], ...] = (
    ("armature", "עוגן A1–A2"),
    ("series", "עירור טורי S1–S2"),
    ("shunt", "עירור מקבילי F1–F2"),
)
FIELD_SUPPLY = 220.0  # V: the separate field supply of the generator tests (fig. 2.2)


def _field_from(b: _B, plus: str, minus: str, r_rheo: float) -> None:
    """+ → Rf (rheostat) → Af → F1 ; F2 → −."""
    b.add("Rf", "resistor", 150, 40, "ריאוסטט עירור", R=r_rheo)
    b.add("Af", "ammeter", 330, 40, "A2 (עירור)")
    b.w(plus, "Rf.p").w("Rf.n", "Af.p").w("Af.n", "M.F1").w("M.F2", minus)


def motor(
    u: float, r_field: float, *, r_x: float = 0.0, series: Series = "none", m_load: float = 0.0
) -> CircuitModel:
    """Figures 3.2 (shunt) and 3.6 (compound): supply P → Rx → A1 → armature; the shunt field
    across the supply through its rheostat; U1 across the supply; brake on the shaft."""
    b = _B()
    b.add("P", "source_dc", 0, 260, "ספק DC", U=u)
    b.add("M", "dcmachine", 640, 260, "מכונת DC + בלם", speed_mode="torque", M_load=m_load)
    b.add("U1", "voltmeter", 430, 470, "U1")
    b.add("Rx", "resistor", 300, 160, "R נוסף", R=r_x)
    b.add("Aa", "ammeter", 470, 160, "A1 (עוגן)")
    _field_from(b, "P.P", "P.N", r_field)
    b.w("P.P", "Rx.p").w("Rx.n", "Aa.p").w("Aa.n", "M.A1")
    # U1.n joins the armature return at the machine (same node as P.N): keeps its drawn wire
    # apart from the field return F2 → P.N
    b.w("U1.p", "P.P")
    ret = {"none": "M.A2", "cumulative": "M.S2", "differential": "M.S1"}[series]
    if series == "cumulative":
        b.w("M.A2", "M.S1")
    elif series == "differential":
        b.w("M.A2", "M.S2")
    b.w(ret, "P.N").w("U1.n", ret)
    return b.done()


def generator(
    n: float,
    r_field: float,
    r_load: float,
    *,
    excitation: Literal["separate", "shunt"] = "separate",
    series: Series = "none",
    closed: bool = True,
) -> CircuitModel:
    """Figures 2.2 (separately excited), 2.6 (shunt) and 2.8 (compound): the servo drives the
    machine at n; A1 → [series field] → S4 → Aa → RL → A2; U1 across the armature terminals.
    Separate excitation: own 220 V supply Pf → Rf → Af → F1–F2. Shunt: the field circuit is
    fed from the armature terminals (it must build up from the remanence)."""
    b = _B()
    b.add("M", "dcmachine", 640, 260, "מכונת DC (מונעת ע״י סרוו)", speed_mode="speed", n_set=n)
    b.add("U1", "voltmeter", 860, 300, "U1")
    b.add("S4", "switch3", 760, 60, "S4", closed=closed)
    b.add("Aa", "ammeter", 900, 60, "A1 (עומס)")
    b.add("RL", "resistor", 1040, 260, "ריאוסטט עומס", R=r_load)
    out = "M.A1"
    if series == "cumulative":
        b.w("M.A1", "M.S1")
        out = "M.S2"
    elif series == "differential":
        b.w("M.A1", "M.S2")
        out = "M.S1"
    b.w(out, "S4.i1").w("S4.o1", "Aa.p").w("Aa.n", "RL.p").w("RL.n", "M.A2")
    b.w("U1.p", out).w("U1.n", "RL.n")
    if excitation == "separate":
        b.add("Pf", "source_dc", 0, 260, "ספק עירור", U=FIELD_SUPPLY)
        _field_from(b, "Pf.P", "Pf.N", r_field)
    else:
        # short shunt: the field sits across the armature, so at no load the series winding
        # carries nothing and both series polarities start from the same V1 (as in table 2.7)
        _field_from(b, "M.A1", "M.A2", r_field)
    return b.done()


def grid_parallel(u: float, n: float, r_field: float) -> CircuitModel:
    """Generator in parallel with the DC network (manual, method item 6): the servo holds the
    speed, the network P sets the terminal voltage, Aa shows which way power flows."""
    b = _B()
    b.add("P", "source_dc", 0, 260, "רשת DC", U=u)
    b.add("M", "dcmachine", 640, 260, "מכונת DC (מונעת ע״י סרוו)", speed_mode="speed", n_set=n)
    b.add("U1", "voltmeter", 430, 470, "U1")
    b.add("Aa", "ammeter", 470, 160, "A1 (מהרשת)")
    _field_from(b, "P.P", "P.N", r_field)
    # drawn like the motor bench: Aa reads network → machine (positive = motoring); the study
    # reports Ia = −reading so that positive means the machine delivers power
    b.w("P.P", "Aa.p").w("Aa.n", "M.A1").w("M.A2", "P.N")
    b.w("U1.p", "P.P").w("U1.n", "M.A2")
    return b.done()


def dc_winding(winding: Winding, u: float = 1.0) -> CircuitModel:
    """Figure 2.1/3.1: the 0–25 V supply → ammeter → winding, voltmeter across it. The machine
    stands still (n = 0), so the armature reading includes the brush drop."""
    terms = {"armature": ("A1", "A2"), "series": ("S1", "S2"), "shunt": ("F1", "F2")}
    t1, t2 = terms[winding]
    b = _B()
    b.add("P", "source_dc", 0, 260, "ספק 0–25 V", U=u)
    b.add("A", "ammeter", 220, 120, "A")
    b.add("V", "voltmeter", 420, 420, "V")
    b.add("M", "dcmachine", 640, 260, "מכונת DC (עומדת)", speed_mode="speed", n_set=0.0)
    b.w("P.P", "A.p").w("A.n", f"M.{t1}").w(f"M.{t2}", "P.N")
    b.w("V.p", f"M.{t1}").w("V.n", f"M.{t2}")
    return b.done()
