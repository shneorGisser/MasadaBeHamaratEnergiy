"""Engineering reference tests R1–R5, R7, R9 (see planning doc, section F).

Expected values are derived independently of the solver: closed-form ideal-transformer
relations, conservation of energy, and a published textbook example.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.helpers import CB, ideal_spec, spec, yy_with_load
from vel.engine.netlist import CircuitValidationError
from vel.engine.simulate import operating_point
from vel.experiments.transformer3ph import analysis
from vel.experiments.transformer3ph.spec import assumed_lab_transformer
from vel.experiments.transformer3ph.studies import STUDIES, execute

TOL = 1e-9
# The "ideal" spec keeps R_Fe = X_m = 1e9 Ω (the schema requires a finite magnetizing branch),
# so ratios deviate from the ideal by ~I_m/I ≈ 1e-7. Tolerances below are set from that bound.
NEAR_IDEAL = 1e-6


# R1 — ideal transformer at no load: U2/U1 = n2/n1
@pytest.mark.parametrize("U1n,U2n", [(380, 220), (400, 400), (220, 24), (6000, 400)])
def test_R1_ideal_no_load_ratio(U1n: float, U2n: float) -> None:
    s = ideal_spec(U1n=U1n, U2n=U2n)
    op = operating_point(yy_with_load(None, U=U1n).model(), s)
    u1 = op.readings["V1"]["U"]
    u2 = op.readings["V2"]["U"]
    assert u1 is not None and u2 is not None
    assert u2 / u1 == pytest.approx(U2n / U1n, rel=TOL)
    # magnetizing current through 1e9 Ω ∥ j1e9 Ω at phase voltage
    i_m = (U1n / math.sqrt(3)) * math.sqrt(2) / 1e9
    assert op.readings["A1m"]["I"] == pytest.approx(i_m, rel=1e-6)


# R2 — ideal transformer with resistive load: I1/I2 = n2/n1, P_in = P_out
def test_R2_ideal_current_ratio_and_power() -> None:
    s = ideal_spec()
    R = 20.0
    op = operating_point(yy_with_load(R).model(), s)
    i1, i2 = op.readings["A1m"]["I"], op.readings["A2m"]["I"]
    assert i1 is not None and i2 is not None
    assert i1 / i2 == pytest.approx(220 / 380, rel=NEAR_IDEAL)
    U2ph = 220 / math.sqrt(3)
    assert i2 == pytest.approx(U2ph / R, rel=TOL)
    p_out = 3 * U2ph**2 / R
    assert op.internals["_sources"]["P_delivered"] == pytest.approx(p_out, rel=NEAR_IDEAL)
    assert 3 * (op.readings["W"]["P"] or 0) == pytest.approx(p_out, rel=NEAR_IDEAL)


# R3 — conservation of energy for arbitrary parameters and loads
@settings(max_examples=60, deadline=None)
@given(
    R1=st.floats(0.01, 5),
    X1=st.floats(0.01, 5),
    R2=st.floats(0.01, 5),
    X2=st.floats(0.01, 5),
    Rfe=st.floats(500, 20000),
    Xm=st.floats(300, 20000),
    c=st.floats(0, 3),
    load=st.floats(2, 500),
    U=st.floats(50, 450),
)
def test_R3_power_balance(
    R1: float,
    X1: float,
    R2: float,
    X2: float,
    Rfe: float,
    Xm: float,
    c: float,
    load: float,
    U: float,
) -> None:
    s = spec(
        R1=R1,
        X1=X1,
        R2=R2,
        X2=X2,
        R_fe=Rfe,
        Xm_unsat=max(Xm, 10 * math.hypot(R1, X1)) * (1 + c),
        sat_c=c,
    )
    b = yy_with_load(load, U=U)
    op0 = operating_point(b.model(), s)
    tot = op0.internals["T.total"]
    # load power from secondary line currents: balanced Y load, P = 3 |I2|² R
    i2 = op0.readings["A2m"]["I"]
    assert i2 is not None
    p_load = 3 * i2**2 * load
    p_src = op0.internals["_sources"]["P_delivered"]
    assert p_src == pytest.approx(tot["P_cu1"] + tot["P_cu2"] + tot["P_fe"] + p_load, rel=1e-9)


# R4 — textbook parameter extraction (single-phase data mapped onto one phase of a balanced Y)
def test_R4_chapman_example_2_2() -> None:
    """Chapman, Electric Machinery Fundamentals, 4th ed., Example 2-2 (20 kVA 8000/240 V).

    OC test (LV side): 240 V, 7.133 A, 400 W  → R_C ≈ 144 Ω, X_M ≈ 34.6 Ω (LV side)
    SC test (HV side): 489 V, 2.5 A, 240 W    → R_eq ≈ 38.4 Ω, X_eq ≈ 192 Ω (HV side)
    NOTE: values transcribed from the textbook; page copy pending verification by the
    product owner (documented in docs/test-log.md).
    """
    sq3 = math.sqrt(3)
    p = {x.key: x for x in analysis.no_load_parameters(240 * sq3, 7.133, 3 * 400, 1, 1, 1)}
    assert p["R_fe"].value == pytest.approx(144, rel=0.005)
    assert p["X_m"].value == pytest.approx(34.6, rel=0.005)
    k = {x.key: x for x in analysis.short_circuit_parameters(489 * sq3, 2.5, 3 * 240, 8000, 2.5)}
    assert k["r_k"].value == pytest.approx(38.4, rel=0.005)
    assert k["x_k"].value == pytest.approx(192, rel=0.005)
    assert k["cos_phik"].value == pytest.approx(0.196, abs=0.001)


# R5 — round trip: simulate tests with known parameters, extract, compare
def test_R5_round_trip_parameter_extraction() -> None:
    s = assumed_lab_transformer()
    nl = STUDIES["no_load"]
    o = execute("no_load", s, nl.default_circuit(s, "YY").model_dump(), nl.default_case(s))  # type: ignore[union-attr]
    assert o.status in ("success", "success_with_warnings"), o.error
    assert o.result is not None
    p = {x["key"]: x for x in o.result["parameters"]}
    e = s.ecm
    a = s.turns_ratio
    assert p["a_ph"]["value"] == pytest.approx(a, rel=0.005)
    assert p["R_fe"]["value"] == pytest.approx(e.R_fe, rel=0.02)
    xm_rated = e.Xm_unsat / (1 + e.sat_c)
    assert p["X_m"]["value"] == pytest.approx(xm_rated, rel=0.02)

    sc = STUDIES["short_circuit"]
    o = execute("short_circuit", s, sc.default_circuit(s, "").model_dump(), sc.default_case(s))  # type: ignore[union-attr]
    assert o.status == "success", o.error
    assert o.result is not None
    k = {x["key"]: x for x in o.result["parameters"]}
    assert k["r_k"]["value"] == pytest.approx(e.R1 + a**2 * e.R2, rel=0.02)
    assert k["x_k"]["value"] == pytest.approx(e.X1 + a**2 * e.X2, rel=0.02)
    # last point is at rated current exactly
    rows = o.result["tables"][0]["rows"]
    assert rows[-1]["I1k"] == pytest.approx(s.I1n_line, rel=1e-9)
    # documented manual-formula failure for this transformer (cos φk ≈ 0.6 > 0.577)
    assert k["x_k_manual"]["value"] is None
    assert k["x_k_manual"]["undefined_reason"]


# R7 — capacitive load raises the secondary voltage above no-load
def test_R7_capacitive_load_voltage_rise() -> None:
    s = assumed_lab_transformer()
    op_nl = operating_point(yy_with_load(None).model(), s)
    b = yy_with_load(None)
    b.add("L", "load3", kind="C", connection="Y", value=60e-6)
    b.wire("T.a1", "A2m.p").wire("A2m.n", "L.1").wire("T.b1", "L.2").wire("T.c1", "L.3")
    op_c = operating_point(b.model(), s)
    b2 = yy_with_load(None)
    b2.add("L", "load3", kind="L", connection="Y", value=0.05)
    b2.wire("T.a1", "A2m.p").wire("A2m.n", "L.1").wire("T.b1", "L.2").wire("T.c1", "L.3")
    op_l = operating_point(b2.model(), s)
    u_nl = op_nl.readings["V2"]["U"]
    u_c = op_c.readings["V2"]["U"]
    u_l = op_l.readings["V2"]["U"]
    assert u_nl is not None and u_c is not None and u_l is not None
    assert u_c > u_nl > u_l


# R9 — invalid circuits fail explicitly, never as a successful run
def test_R9_ammeter_across_supply_is_rejected() -> None:
    b = CB().add("G", "source3", U_line=380, f=50).add("A", "ammeter")
    b.wire("G.L1", "A.p").wire("A.n", "G.L2")
    with pytest.raises(CircuitValidationError) as ei:
        operating_point(b.model(), None)
    assert ei.value.issues[0]["code"] == "voltage_loop"


def test_R9_direct_short_between_phases() -> None:
    b = CB().add("G", "source3", U_line=380, f=50).wire("G.L1", "G.L2")
    with pytest.raises(CircuitValidationError) as ei:
        operating_point(b.model(), None)
    # L1–L2 shorted closes the loop L1 → N → L2 through two phase sources
    assert ei.value.issues[0]["code"] in {"shorted_source", "voltage_loop"}


def test_R9_unknown_terminal_and_type() -> None:
    b = CB().add("G", "source3").add("X", "flux_capacitor").wire("G.L9", "X.p")
    with pytest.raises(CircuitValidationError) as ei:
        operating_point(b.model(), None)
    codes = {i["code"] for i in ei.value.issues}
    assert {"unknown_type", "unknown_terminal"} <= codes


def test_R9_param_out_of_range() -> None:
    b = CB().add("G", "source3", U_line=380, f=50).add("R", "resistor", R=-5)
    b.wire("G.L1", "R.p").wire("R.n", "G.N")
    with pytest.raises(CircuitValidationError) as ei:
        operating_point(b.model(), None)
    assert ei.value.issues[0]["code"] == "param_out_of_range"


def test_R9_short_circuit_without_short_is_constraint_violation() -> None:
    s = assumed_lab_transformer()
    circ = STUDIES["no_load"].default_circuit(s, "YY").model_dump()  # type: ignore[union-attr]
    circ["components"].append({"id": "A2", "type": "ammeter", "params": {}})
    o = execute("short_circuit", s, circ, {"I_targets_pu": [1.0]})
    assert o.status == "constraint_violation"
    assert o.result is None


def test_R9_missing_instrument_binding() -> None:
    s = assumed_lab_transformer()
    circ = STUDIES["no_load"].default_circuit(s, "YY").model_dump()  # type: ignore[union-attr]
    circ["components"] = [c for c in circ["components"] if c["id"] != "V2ph"]
    circ["wires"] = [
        w for w in circ["wires"] if w["a"]["component"] != "V2ph" and w["b"]["component"] != "V2ph"
    ]
    o = execute("no_load", s, circ, {"U_line_values": [380]})
    assert o.status == "invalid_circuit"
    assert "V2ph" in (o.error or {})["message"]


def test_R9_invalid_case() -> None:
    s = assumed_lab_transformer()
    circ = STUDIES["no_load"].default_circuit(s, "YY").model_dump()  # type: ignore[union-attr]
    o = execute("no_load", s, circ, {"U_line_values": [-10]})
    assert o.status == "invalid_input"


def test_floating_voltmeter_reading_is_undefined_not_zero() -> None:
    s = assumed_lab_transformer()
    b = yy_with_load(None).add("VX", "voltmeter").wire("VX.p", "T.A1").wire("VX.n", "T.a1")
    op = operating_point(b.model(), s)
    assert op.readings["VX"]["U"] is None
    assert "VX.U" in op.undefined


def test_delta_primary_on_star_voltage_saturates() -> None:
    """Connecting the primary in delta on the star-rated supply puts √3× voltage on each
    winding; the saturating model must show a large rise in magnetizing current."""
    s = assumed_lab_transformer()
    op_y = operating_point(yy_with_load(None).model(), s)
    b = CB().add("G", "source3", U_line=380, f=50).add("T", "transformer3").add("A", "ammeter")
    b.wire("G.L1", "A.p").wire("A.n", "T.A1").wire("T.A2", "T.B1")
    b.wire("G.L2", "T.B1").wire("T.B2", "T.C1").wire("G.L3", "T.C1").wire("T.C2", "T.A1")
    op_d = operating_point(b.model(), s)
    i_y = op_y.readings["A1m"]["I"]
    i_d = op_d.readings["A"]["I"]
    assert i_y is not None and i_d is not None
    assert i_d > 10 * i_y


# R6 — vector groups from wiring topology. Expected clock numbers derived by hand from the
# phasor diagrams (IEC 60076-1 convention: clock = LV lag behind HV / 30°):
#   Yy abc → 0, Yy reversed → 6, Yy with b-c-a roles → 4, c-a-b roles → 8,
#   Yd with x2→y1 closure → 1, Yd with x1→y2 closure → 11.
@pytest.mark.parametrize(
    "variant,clock,candidates",
    [
        ("Yy-abc", 0, "0"),
        ("Yy-abc-rev", 6, "6"),
        ("Yy-bca", 4, "4 או 8"),
        ("Yy-cab", 8, "4 או 8"),
        ("Yd-abc-1", 1, "1 או 11"),
        ("Yd-abc-2", 11, "1 או 11"),
    ],
)
def test_R6_vector_groups(variant: str, clock: int, candidates: str) -> None:
    s = assumed_lab_transformer()
    sd = STUDIES["vector_group"]
    o = execute("vector_group", s, sd.default_circuit(s, variant).model_dump(), {"U_line": 100})  # type: ignore[union-attr]
    assert o.status == "success", o.error
    assert o.result is not None
    p = {x["key"]: x for x in o.result["parameters"]}
    assert p["clock_true"]["value"] == clock
    assert p["clock_candidates"]["note"] == candidates


def test_R6_cosine_law_matches_ideal_geometry() -> None:
    """Ideal Yy0, ratio 380/220, U_line = 100 V: with A1 bridged to a1, |B1–b1| = |AB| − |ab|."""
    s = ideal_spec()
    sd = STUDIES["vector_group"]
    o = execute("vector_group", s, sd.default_circuit(s, "Yy-abc").model_dump(), {"U_line": 100})  # type: ignore[union-attr]
    assert o.result is not None
    row = o.result["tables"][0]["rows"][0]
    assert row["U_aAB"] == pytest.approx(100, rel=1e-9)
    assert row["U_aAb"] == pytest.approx(100 * 220 / 380, rel=1e-6)
    assert row["U_Bb"] == pytest.approx(100 - 100 * 220 / 380, rel=1e-5)


def test_vector_group_without_bridge_is_explicit_failure() -> None:
    s = assumed_lab_transformer()
    c = STUDIES["vector_group"].default_circuit(s, "Yy-abc").model_dump()  # type: ignore[union-attr]
    c["wires"] = [
        w
        for w in c["wires"]
        if not (w["a"] == {"component": "T", "terminal": "A1"} and w["b"]["terminal"] == "a1")
    ]
    o = execute("vector_group", s, c, {"U_line": 100})
    assert o.status == "invalid_circuit"


# Load test: energy balance P1 = P2 + losses, regulation sign by load type
@pytest.mark.parametrize("kind", ["R", "L", "C"])
def test_load_study(kind: str) -> None:
    s = assumed_lab_transformer()
    sd = STUDIES["load"]
    o = execute(
        "load",
        s,
        sd.default_circuit(s, "").model_dump(),
        {"load_kind": kind, "I2_targets_pu": [0.5, 1.0]},
    )  # type: ignore[union-attr]
    assert o.status in ("success", "success_with_warnings"), o.error
    assert o.result is not None
    rows = o.result["tables"][0]["rows"]
    assert rows[0]["I2"] == pytest.approx(0, abs=1e-9)  # S2 open
    assert rows[-1]["I2"] == pytest.approx(s.I2n_line, rel=1e-9)
    if kind == "R":
        assert 0.9 < rows[-1]["eta"] < 1.0
        assert rows[-1]["dU_pct"] > 0
    if kind == "L":
        assert rows[-1]["dU_pct"] > rows[1]["dU_pct"] > 0
    if kind == "C":
        assert rows[-1]["dU_pct"] < 0  # voltage rise
