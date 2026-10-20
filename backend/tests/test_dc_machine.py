"""Experiments 5 and 6: DC machine model, studies and API.

D1–D3 are fit-quality regressions: the spec was fitted to these very tables (2025 reports), so
they show the model reproduces them — not an independent validation. D4–D12 are model-
independent physics and plumbing checks (balances, build-up, runaway, solver targets).
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from vel.engine.circuit import CircuitModel
from vel.engine.simulate import MechanicalError, operating_point
from vel.experiments import registry
from vel.experiments.common import with_param
from vel.experiments.dc_machine import studies, templates
from vel.experiments.dc_machine.modules import plausibility
from vel.experiments.dc_machine.spec import DCSpec, fitted_lab_dc_machine
from vel.experiments.transformer3ph.templates import _B

SPEC = fitted_lab_dc_machine()
W = 2 * math.pi / 60


def run(circuit: CircuitModel, spec: DCSpec = SPEC, **kw: object):  # type: ignore[no-untyped-def]
    return operating_point(circuit, spec, dc=True, **kw)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- D1–D3: lab data


@pytest.mark.parametrize(
    ("M", "n_lab", "i_lab"),
    [(0.0, 2058, 0.358), (0.5, 1990, 0.972), (1.0, 1895, 1.63), (1.2, 1852, 1.9)],
)
def test_D1_shunt_motor_reproduces_table_5_2_4(M: float, n_lab: float, i_lab: float) -> None:
    op = run(templates.motor(174.3, 0.0, m_load=M))
    assert op.readings["M"]["n"] == pytest.approx(n_lab, abs=30)
    assert op.readings["Aa"]["I"] == pytest.approx(i_lab, abs=0.05)


@pytest.mark.parametrize(
    ("kw", "M", "n_lab"),
    [
        ({"r_x": 30.0}, 0.0, 1952),
        ({"r_x": 30.0}, 0.6, 1580),
        ({"series": "cumulative"}, 0.0, 2026),
        ({"series": "cumulative"}, 1.0, 1663),
    ],
)
def test_D2_rx_and_compound_motor_reproduce_tables_5_2_5_and_2_8(
    kw: dict[str, object], M: float, n_lab: float
) -> None:
    u = 173.0 if "r_x" in kw else 174.0
    r_f = 0.0 if "r_x" in kw else 174 / 0.462 - SPEC.ecm.R_f
    op = run(templates.motor(u, r_f, m_load=M, **kw))  # type: ignore[arg-type]
    assert op.readings["M"]["n"] == pytest.approx(n_lab, abs=50)


@pytest.mark.parametrize(
    ("i_f", "e_lab"), [(0.1, 78), (0.15, 111), (0.2, 143), (0.25, 162), (0.27, 168)]
)
def test_D3_occ_reproduces_table_6_2_3_at_the_implied_speed(i_f: float, e_lab: float) -> None:
    base = templates.generator(2550.0, 0.0, studies.R_OPEN, closed=False)
    r = studies._field_rheostat(base, SPEC, i_f)
    op = run(with_param(base, "Rf", "R", r))
    assert op.readings["Af"]["I"] == pytest.approx(i_f, rel=1e-6)
    assert op.readings["U1"]["U"] == pytest.approx(e_lab, abs=6)


# --------------------------------------------------------------------------- D4–D8: physics


@pytest.mark.parametrize("M", [0.0, 0.7, 1.2])
def test_D4_motor_power_balance(M: float) -> None:
    op = run(templates.motor(174.0, 30.0, m_load=M))
    mech = op.internals["M.mech"]
    ia_motor = -mech["Ia"]
    # electrical: U_terminal·Ia = E·Ia + Ia²Ra + brush
    p_in = 174.0 * op.readings["Aa"]["I"]
    assert p_in == pytest.approx(
        mech["E_int"] * ia_motor + mech["P_cu_a"] + mech["P_brush"], rel=1e-9
    )
    # mechanical: P_em = P_shaft + P_rot, shaft = brake torque × ω
    p_shaft = M * mech["n"] * W
    assert -mech["P_em"] == pytest.approx(p_shaft + mech["P_rot"], rel=1e-9, abs=1e-9)


@pytest.mark.parametrize("r_load", [400.0, 150.0])
def test_D5_generator_power_balance(r_load: float) -> None:
    op = run(templates.generator(2800.0, 100.0, r_load))
    mech = op.internals["M.mech"]
    p_load = op.readings["U1"]["U"] * op.readings["Aa"]["I"]
    assert mech["P_em"] == pytest.approx(p_load + mech["P_cu_a"] + mech["P_brush"], rel=1e-9)
    # shaft torque read by the servo = electromagnetic + friction
    assert op.readings["M"]["M"] * 2800 * W == pytest.approx(mech["P_shaft_in"], rel=1e-9)


def _swap_field(c: CircuitModel) -> CircuitModel:
    doc = c.model_dump()
    for w in doc["wires"]:
        for end in ("a", "b"):
            if w[end]["component"] == "M" and w[end]["terminal"] in ("F1", "F2"):
                w[end]["terminal"] = "F2" if w[end]["terminal"] == "F1" else "F1"
    return CircuitModel.model_validate(doc)


def test_D6_shunt_generator_builds_up_only_with_the_right_field_polarity() -> None:
    good = run(templates.generator(2800.0, 80.0, studies.R_OPEN, excitation="shunt"))
    assert good.readings["U1"]["U"] > 200
    assert not good.warnings
    bad = run(_swap_field(templates.generator(2800.0, 80.0, studies.R_OPEN, excitation="shunt")))
    assert abs(bad.readings["U1"]["U"]) < 10  # stays at (below) the residual voltage
    assert any(w["code"] == "no_buildup" for w in bad.warnings)
    # above the critical field resistance it does not build up either
    crit = run(templates.generator(2800.0, 5000.0, studies.R_OPEN, excitation="shunt"))
    assert crit.readings["U1"]["U"] < 15


def test_D7_runaway_stall_and_reversal() -> None:
    with pytest.raises(MechanicalError) as e:
        run(templates.motor(174.0, studies.R_OPEN, m_load=0.1))  # field open
    assert e.value.status == "constraint_violation"
    with pytest.raises(MechanicalError):
        run(templates.motor(20.0, 0.0, m_load=1.5))  # cannot start
    stalled = run(templates.motor(20.0, 0.0, m_load=1.5), on_stall="stall")
    assert stalled.readings["M"]["n"] == 0
    assert any(w["code"] == "stalled" for w in stalled.warnings)
    # reversing the armature connection reverses the rotation
    doc = templates.motor(174.0, 0.0, m_load=0.3).model_dump()
    for w in doc["wires"]:
        for end in ("a", "b"):
            if w[end]["component"] == "M" and w[end]["terminal"] in ("A1", "A2"):
                w[end]["terminal"] = "A2" if w[end]["terminal"] == "A1" else "A1"
    rev = run(CircuitModel.model_validate(doc))
    fwd = run(templates.motor(174.0, 0.0, m_load=0.3))
    assert rev.readings["M"]["n"] == pytest.approx(-fwd.readings["M"]["n"], rel=1e-6)


def test_D8_series_motor_runs_away_unloaded_but_runs_loaded() -> None:
    b = _B()
    b.add("P", "source_dc", 0, 260, "ספק", U=174.0)
    b.add("M", "dcmachine", 640, 260, "מכונה", speed_mode="torque", M_load=0.0)
    b.add("Aa", "ammeter", 300, 100, "A1")
    b.w("P.P", "Aa.p").w("Aa.n", "M.A1").w("M.A2", "M.S1").w("M.S2", "P.N")
    unloaded = b.done()
    with pytest.raises(MechanicalError):
        run(unloaded)
    loaded = run(with_param(unloaded, "M", "M_load", 1.0))
    assert 0 < loaded.readings["M"]["n"] < SPEC.nameplate.n_max


# --------------------------------------------------------------------------- D9–D11: studies


def test_D9_resistance_test_shows_the_brush_drop() -> None:
    mod = registry.get("dc_motor")
    sd = mod.studies["dc_resistance"]
    circ = {k: v.model_dump() for k, v in sd.default_circuit(SPEC, "").items()}  # type: ignore[misc,union-attr]
    out = mod.execute("dc_resistance", SPEC, circ, {"I_targets": [0.7, 1.1, 1.6]})
    rows = out.result["tables"][0]["rows"]  # type: ignore[index]
    ra = [r["R"] for r in rows[:3]]
    assert ra[0] > ra[1] > ra[2] > SPEC.ecm.R_a  # U/I falls with current: constant brush drop
    assert [r["I"] for r in rows[:3]] == pytest.approx([0.7, 1.1, 1.6], rel=1e-6)
    assert rows[3]["R"] == pytest.approx(SPEC.ecm.R_s)
    assert rows[6]["R"] == pytest.approx(SPEC.ecm.R_f)


@pytest.mark.parametrize("mid", ["dc_motor", "dc_generator"])
def test_D10_every_default_study_runs(mid: str) -> None:
    mod = registry.get(mid)
    for kind, sd in mod.studies.items():
        circ = sd.default_circuit(SPEC, "") if sd.default_circuit else None
        doc = (
            {k: v.model_dump() for k, v in circ.items()}
            if isinstance(circ, dict)
            else (circ.model_dump() if circ is not None else None)
        )
        out = mod.execute(kind, SPEC, doc, sd.default_case(SPEC))
        assert out.status in ("success", "success_with_warnings"), (kind, out.error)


def test_D11_rheostat_solvers_hit_their_targets() -> None:
    mod = registry.get("dc_generator")
    out = mod.execute(
        "shunt_load",
        SPEC,
        None,
        {
            "n": 2800.0,
            "U0": 220.0,
            "excitation": "shunt",
            "connections": ["none"],
            "I_targets": [0.0, 0.5, 1.0, 5.0],
        },
    )
    rows = out.result["tables"][0]["rows"]  # type: ignore[index]
    assert rows[0]["U1"] == pytest.approx(220.0, rel=1e-6)
    assert rows[1]["Ia"] == pytest.approx(0.5, rel=1e-6)
    assert rows[2]["Ia"] == pytest.approx(1.0, rel=1e-6)
    assert rows[3].get("U1") is None and "אינו מסוגל" in rows[3]["note"]  # beyond collapse
    assert out.status == "success_with_warnings"
    m = registry.get("dc_motor").execute(
        "field_speed",
        SPEC,
        templates.motor(174.0, 0.0).model_dump(),
        {"U": 174.0, "M_load": 0.8, "If_targets": [0.45, 0.3, 0.9]},
    )
    r = m.result["tables"][0]["rows"]  # type: ignore[index]
    assert [x["If"] for x in r[:2]] == pytest.approx([0.45, 0.3], rel=1e-6)
    assert r[1]["n"] > r[0]["n"]  # weaker field → faster
    assert "גבוה מהמרבי" in r[2]["note"]


def test_D11b_plausibility_flags_the_2025_generator_tables() -> None:
    # 6/2.6 as written: the If row from column 5 on looks like the load current
    shunt = [
        {"If": a, "Ia": b, "U1": c}
        for a, b, c in [
            (0.48, 0, 220),
            (0.48, 0.168, 217),
            (0.47, 0.337, 214),
            (0.46, 0.5, 210),
            (0.42, 0.49, 205),
            (0.65, 0.42, 202),
            (0.81, 0.41, 199),
            (0.95, 0.41, 196),
            (1.7, 0.38, 167),
        ]
    ]
    assert any(w["code"] == "field_rises_with_load" for w in plausibility("shunt_load", shunt))
    # 6/2.7: both series polarities give the same voltage
    cmp_ = [{"pol": 1, "Ia": 1.28, "U1": 198}, {"pol": -1, "Ia": 1.28, "U1": 199}]
    assert any(w["code"] == "series_effect_missing" for w in plausibility("compound", cmp_))


# --------------------------------------------------------------------------- D12: API


def test_D12_api_journey(client: TestClient) -> None:
    for mid in ("dc_motor", "dc_generator"):
        p = client.post("/api/projects", json={"name": mid, "experiment_id": mid})
        assert p.status_code == 201, p.text
        pid = p.json()["id"]
        studies_ = client.get(f"/api/projects/{pid}/studies").json()
        assert {s["kind"] for s in studies_} >= {"insulation", "dc_resistance"}
    # motor: live point with a rheostat override, then a measured load table compared
    pid = client.post("/api/projects", json={"name": "m", "experiment_id": "dc_motor"}).json()["id"]
    live = client.post(
        f"/api/projects/{pid}/circuits/load/operating-point",
        json={"overrides": {"M": {"M_load": 0.5}, "Rf": {"R": 20.0}}},
    ).json()
    assert live["status"] == "success", live
    assert 1800 < live["readings"]["M"]["n"] < 2300
    s = client.post(
        f"/api/projects/{pid}/measurement-sets",
        json={
            "study_kind": "load",
            "label": "2.4",
            "n_rows": 3,
            "conditions": {"U": "174.3", "If": "0.48"},
        },
    ).json()
    sid = s["set"]["id"]
    for i, (i1, n, m) in enumerate([(0.358, 2058, 0.0), (0.972, 1990, 0.5), (1.63, 1895, 1.0)]):
        for q, v, unit in (("I1", i1, "A"), ("n", n, "rpm"), ("M", m, "N·m")):
            r = client.post(
                f"/api/measurement-sets/{sid}/entries",
                json={"row_index": i, "quantity": q, "value": v, "unit": unit},
            )
            assert r.status_code == 201, r.text
    sim = client.post(f"/api/measurement-sets/{sid}/simulate").json()
    assert sim["status"] in ("success", "success_with_warnings"), sim
    assert sim["input_snapshot"]["case"]["U"] == 174.3
    cmp_ = client.get(f"/api/comparison?run_id={sim['id']}&set_id={sid}").json()
    assert cmp_["summary"]["unmatched_rows"] == 0
    cells = [c for pr in cmp_["pairs"] for c in pr["cells"]]
    assert all(abs(c["rel_error"]) < 0.02 for c in cells if c["quantity"] == "n")
    # the no-load armature current is the model's weakest point (0.316 vs 0.358 A, ≈ 13 %)
    assert cmp_["summary"]["max_abs_rel_error"] < 0.15
    # reproduce, report, backup round trip
    rep = client.post(f"/api/runs/{sim['id']}/reproduce").json()
    assert rep["identical"] and rep["input_hash_matches"]
    rp = client.post(
        f"/api/projects/{pid}/reports",
        json={
            "title": "ניסוי 5",
            "sections": [{"study_kind": "load", "run_id": sim["id"], "set_id": sid}],
        },
    )
    assert rp.status_code == 201, rp.text
    html = client.get(f"/api/reports/{rp.json()['id']}/html").text
    assert "המכונה והנחות המודל" in html and "ρ<sub>s</sub>" in html
    exp = client.get(f"/api/projects/{pid}/export").json()
    imp = client.post("/api/projects/import", json=exp)
    assert imp.status_code == 201 and imp.json()["experiment_id"] == "dc_motor"
    presets = client.get("/api/experiments/dc_generator/presets").json()
    assert [x["id"] for x in presets] == ["lab_2025_fit", "assumed_03kw"]


def test_D13_descending_occ_branch_reproduces_table_6_2_3() -> None:
    """Hysteresis shape (one parameter, fitted to this table — a fit regression): the falling
    branch lies above the rising one in the middle and meets it at both ends."""
    mod = registry.get("dc_generator")
    i_f = [0, 0.1, 0.15, 0.17, 0.19, 0.2, 0.22, 0.25, 0.27]
    down = [7, 86.2, 120.2, 132, 142, 144, 155, 163, 169]
    circ = templates.generator(2550.0, 0.0, studies.R_OPEN, closed=False).model_dump()
    out = mod.execute("occ", SPEC, circ, {"n": 2550.0, "If_values": i_f})
    rows = out.result["tables"][0]["rows"]  # type: ignore[index]
    sim = [r["E_down"] for r in rows]
    assert max(abs(a - b) for a, b in zip(sim, down, strict=True)) < 4.0
    assert rows[0]["E_down"] == pytest.approx(rows[0]["E_up"])  # back to the remanence
    assert rows[-1]["E_down"] == pytest.approx(rows[-1]["E_up"])  # turning point
    assert rows[3]["E_down"] > rows[3]["E_up"] + 3
    assert any(w["code"] == "hysteresis_shape" for w in out.warnings)
    # without the parameter: one branch and an explicit warning
    flat = SPEC.model_copy(update={"occ": SPEC.occ.model_copy(update={"F_h": 0.0})})
    out0 = mod.execute("occ", flat, circ, {"n": 2550.0, "If_values": i_f})
    assert "E_down" not in out0.result["tables"][0]["rows"][1]  # type: ignore[index]
    assert any(w["code"] == "no_hysteresis" for w in out0.warnings)
