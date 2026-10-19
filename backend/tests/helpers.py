from __future__ import annotations

from typing import Any

from vel.engine.circuit import CircuitModel
from vel.experiments.transformer3ph.spec import (
    EquivalentCircuit,
    Insulation,
    Nameplate,
    TransformerSpec,
)


class CB:
    """Tiny circuit builder for tests."""

    def __init__(self) -> None:
        self.c: list[dict[str, Any]] = []
        self.w: list[dict[str, Any]] = []

    def add(self, cid: str, typ: str, **params: Any) -> CB:
        self.c.append({"id": cid, "type": typ, "params": params})
        return self

    def wire(self, a: str, b: str) -> CB:
        ca, ta = a.split(".")
        cb, tb = b.split(".")
        self.w.append(
            {
                "id": f"w{len(self.w)}",
                "a": {"component": ca, "terminal": ta},
                "b": {"component": cb, "terminal": tb},
            }
        )
        return self

    def model(self) -> CircuitModel:
        return CircuitModel.model_validate({"components": self.c, "wires": self.w})


def spec(
    *,
    U1n: float = 380,
    U2n: float = 220,
    S_n: float = 3000,
    primary: str = "Y",
    secondary: str = "Y",
    R1: float = 0.72,
    X1: float = 0.97,
    R2: float = 0.24,
    X2: float = 0.32,
    R_fe: float = 2400,
    Xm_unsat: float = 1240,
    sat_c: float = 1.0,
    sat_n: float = 8,
) -> TransformerSpec:
    return TransformerSpec(
        nameplate=Nameplate(
            S_n=S_n,
            U1n=U1n,
            U2n=U2n,
            f_n=50,
            primary=primary,
            secondary=secondary,  # type: ignore[arg-type]
        ),
        ecm=EquivalentCircuit(
            R1=R1, X1=X1, R2=R2, X2=X2, R_fe=R_fe, Xm_unsat=Xm_unsat, sat_c=sat_c, sat_n=sat_n
        ),
        insulation=Insulation(
            primary_core_Mohm=100, secondary_core_Mohm=100, primary_secondary_Mohm=100
        ),
    )


def ideal_spec(**kw: Any) -> TransformerSpec:
    return spec(R1=0, X1=0, R2=0, X2=0, R_fe=1e9, Xm_unsat=1e9, sat_c=0, **kw)


def yy_with_load(load_R: float | None, U: float = 380.0, secondary_conn: str = "Y") -> CB:
    b = CB()
    b.add("G", "source3", U_line=U, f=50).add("T", "transformer3")
    b.add("W", "wattmeter").add("A1m", "ammeter").add("A2m", "ammeter")
    b.add("V1", "voltmeter").add("V2", "voltmeter")
    b.wire("G.L1", "W.Ip").wire("W.In", "A1m.p").wire("A1m.n", "T.A1")
    b.wire("G.L2", "T.B1").wire("G.L3", "T.C1").wire("T.A2", "T.B2").wire("T.B2", "T.C2")
    b.wire("W.Vp", "T.A1").wire("W.Vn", "T.A2")
    b.wire("V1.p", "T.A1").wire("V1.n", "T.A2")
    if secondary_conn == "Y":
        b.wire("T.a2", "T.b2").wire("T.b2", "T.c2")
    else:
        b.wire("T.a2", "T.b1").wire("T.b2", "T.c1").wire("T.c2", "T.a1")
    b.wire("V2.p", "T.a1").wire("V2.n", "T.a2")
    if load_R is not None:
        b.add("L", "load3", kind="R", connection="Y", value=load_R)
        b.wire("T.a1", "A2m.p").wire("A2m.n", "L.1").wire("T.b1", "L.2").wire("T.c1", "L.3")
    return b
