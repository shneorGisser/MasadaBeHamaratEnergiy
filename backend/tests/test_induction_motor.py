"""Experiment 2 — induction motor: reference checks for the model, studies and API.

M1  closed form: the MNA solution at an imposed slip equals an independent hand calculation of
    the per-phase T-circuit (≤ 1e-9 relative).
M2  energy balance: P_in = P_cu1 + P_fe + P_cu2 + P_fw + P2 at every load point (≤ 1e-9).
M3  torque balance: shaft torque = brake torque on the stable branch (s < s_cr).
M4  Y/Δ invariance: a Δ motor with 3× winding impedances behaves identically at the terminals.
M5  extraction formulas: from simulated readings, Z_k/r_k/x_k and Y0 equal the closed-form
    input impedance/admittance — the manual's formulas are exact for a balanced machine.
M6  failure states: brake above pull-out → constraint_violation (study) / stalled (live).
M7  inverter: V/f keeps synchronous speed ∝ f; low-frequency start draws less current.
M8  API journey: project, all studies, measurement set, comparison, report, reproduce, backup.
"""

from __future__ import annotations

import cmath
import math
from typing import Any

import pytest
from fastapi.testclient import TestClient

from vel.engine.simulate import operating_point, operating_point_at_slip
from vel.experiments import registry
from vel.experiments.common import with_param
from vel.experiments.induction_motor import templates
from vel.experiments.induction_motor.spec import MotorSpec, assumed_lab_motor
from vel.experiments.induction_motor.studies import execute

TIGHT = 1e-9


def closed_form(spec: MotorSpec, u_line: float, f: float, s: float) -> dict[str, float]:
    """Independent per-phase calculation (star equivalent of a Y motor)."""
    e, npl = spec.ecm, spec.nameplate
    k = f / npl.f_n
    v = u_line / math.sqrt(3)
    zm = 1 / (1 / e.R_fe + 1 / complex(0, e.Xm * k))
    z2 = complex(e.R2p / s, e.X2p * k)
    zp = zm * z2 / (zm + z2)
    zin = complex(e.R1, e.X1 * k) + zp
    i1 = v / zin
    i2 = i1 * zp / z2
    p_ag = 3 * abs(i2) ** 2 * e.R2p / s
    w_s = 2 * math.pi * (120 * f / npl.poles) / 60
    return {
        "I1": abs(i1),
        "P1": 3 * (v * i1.conjugate()).real,
        "M_em": p_ag / w_s,
        "pf": math.cos(cmath.phase(zin)),
        "Zin": abs(zin),
    }


def rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-30)


@pytest.mark.parametrize("s", [0.001, 0.03, 0.08, 0.3, 1.0])
@pytest.mark.parametrize("f", [20.0, 50.0, 60.0])
def test_M1_matches_closed_form(s: float, f: float) -> None:
    spec = assumed_lab_motor()
    c = templates.load_test(380.0, f, "Y")
    op = operating_point_at_slip(c, spec, s)
    ref = closed_form(spec, 380.0, f, s)
    assert rel(op.readings["A"]["I"] or 0, ref["I1"]) < TIGHT
    assert rel(3 * (op.readings["W"]["P"] or 0), ref["P1"]) < TIGHT
    assert rel(op.internals["M.mech"]["M_em"], ref["M_em"]) < TIGHT
    assert rel(op.readings["W"]["pf"] or 0, ref["pf"]) < TIGHT


@pytest.mark.parametrize("m_pu", [0.0, 0.3, 0.7, 1.0, 1.4])
def test_M2_M3_energy_and_torque_balance(m_pu: float) -> None:
    spec = assumed_lab_motor()
    m_load = m_pu * spec.M_n
    op = operating_point(templates.load_test(380.0, 50.0, "Y", m_load), spec)
    tot, mech = op.internals["M.total"], op.internals["M.mech"]
    p_in = op.internals["_sources"]["P_delivered"]
    losses = tot["P_cu1"] + tot["P_fe"] + tot["P_cu2"] + mech["P_fw"]
    assert rel(losses + mech["P2"], p_in) < TIGHT
    assert abs((op.readings["M"]["M"] or 0) - m_load) < 1e-9 * max(1.0, spec.M_n)
    # the displayed torque is the setting; the real balance is checked on the internals
    assert abs(mech["balance_residual"]) < 1e-9 * max(1.0, spec.M_n)
    assert abs(mech["M_em"] - mech["M_fw"] - m_load) < 1e-9 * max(1.0, spec.M_n)
    assert 0 < mech["s"] < mech["s_at_M_max"]  # stable branch
    # power seen by the "student": P2 = M·ω (the manual's 9.55 is 60/2π rounded)
    w = 2 * math.pi * mech["n"] / 60
    assert abs(mech["P2"] - m_load * w) < 1e-9 * max(1.0, mech["P2"])


def test_M4_star_delta_invariance() -> None:
    y = assumed_lab_motor()
    d = y.model_copy(deep=True)
    d.nameplate.connection = "D"
    for k in ("R1", "X1", "R2p", "X2p", "R_fe", "Xm"):
        setattr(d.ecm, k, 3 * getattr(y.ecm, k))
    for m in (0.0, 1.5, 2.5):
        oy = operating_point(templates.load_test(380.0, 50.0, "Y", m), y)
        od = operating_point(templates.load_test(380.0, 50.0, "D", m), d)
        for inst, q in (("A", "I"), ("W", "P"), ("M", "n")):
            assert rel(od.readings[inst][q] or 0, oy.readings[inst][q] or 0) < 1e-8


def test_M5_extraction_formulas_are_exact() -> None:
    spec = assumed_lab_motor()
    mod = registry.get("induction_motor")
    r = mod.execute(
        "locked_rotor", spec, templates.locked_rotor(30, 50, "Y"), {"I_targets_pu": [1.0]}
    )
    assert r.status == "success", r.error
    params = {p["key"]: p["value"] for p in r.result["parameters"]}  # type: ignore[index]
    ref = closed_form(spec, 380.0, 50.0, 1.0)
    e = spec.ecm
    zm = 1 / (1 / e.R_fe + 1 / complex(0, e.Xm))
    zin = complex(e.R1, e.X1) + zm * complex(e.R2p, e.X2p) / (zm + complex(e.R2p, e.X2p))
    assert rel(params["Z_k"], ref["Zin"]) < TIGHT
    assert rel(params["r_k"], zin.real) < TIGHT
    assert rel(params["x_k"], zin.imag) < TIGHT
    # the R2' estimate neglects the magnetizing branch: within 15 % of the model value, not exact
    assert rel(params["R2p_est"], e.R2p) < 0.15

    r0 = mod.execute("no_load", spec, templates.no_load(380, 50, "Y"), {"U_line_values": [380]})
    assert r0.status == "success", r0.error
    p0 = {p["key"]: p["value"] for p in r0.result["parameters"]}  # type: ignore[index]
    s0 = r0.result["tables"][0]["rows"][0]["slip"]  # type: ignore[index]
    assert rel(p0["Y0"], 1 / closed_form(spec, 380.0, 50.0, s0)["Zin"]) < 1e-8


def test_M6_pull_out_is_an_explicit_failure() -> None:
    spec = assumed_lab_motor()
    r = execute("load", spec, templates.load_test(380, 50, "Y"), {"M_targets": [3 * spec.M_n]})
    assert r.status == "constraint_violation"
    assert r.result is None
    assert "פריצה" in r.error["message"]  # type: ignore[index]
    op = operating_point(templates.load_test(380, 50, "Y", 3 * spec.M_n), spec, on_stall="stall")
    assert op.readings["M"]["n"] == 0
    assert op.warnings[0]["code"] == "stalled"


def test_M6_cannot_start_under_heavy_load_warning() -> None:
    spec = assumed_lab_motor()
    op_max = operating_point(templates.load_test(380, 50, "Y", 0.0), spec)
    m = 0.5 * (op_max.internals["M.mech"]["M_start"] + op_max.internals["M.mech"]["M_max"])
    op = operating_point(templates.load_test(380, 50, "Y", m), spec)
    assert any(w["code"] == "cannot_start_under_load" for w in op.warnings)


def test_M7_inverter_vf() -> None:
    spec = assumed_lab_motor()
    r = execute(
        "inverter",
        spec,
        templates.inverter(380, 50, "Y"),
        {"points": [{"f": f, "M": 1.0} for f in (20, 35, 50, 60)], "f_start": 10},
    )
    assert r.status == "success_with_warnings", r.error
    rows = r.result["tables"][0]["rows"]  # type: ignore[index]
    for row in rows:
        ns = 120 * row["f"] / 4
        assert 0 < row["n"] < ns
        assert abs(row["slip"] - (ns - row["n"]) / ns) < 1e-12
    # above f_n the voltage is limited to U_n (field weakening)
    assert rows[-1]["U_out"] == pytest.approx(380.0)
    start = r.result["tables"][1]["rows"]  # type: ignore[index]
    assert start[1]["I_start"] < start[0]["I_start"]


def test_dc_resistance_is_winding_resistance() -> None:
    spec = assumed_lab_motor()
    circuits = {w: templates.dc_winding(w).model_dump() for w, _ in templates.WINDINGS}
    r = execute("dc_resistance", spec, circuits, {"I_targets": [0.5]})
    for row in r.result["tables"][1]["rows"]:  # type: ignore[index]
        assert row["R_avg"] == pytest.approx(spec.ecm.R1, rel=1e-12)


def test_locked_switch_open_gives_no_current() -> None:
    spec = assumed_lab_motor()
    c = with_param(templates.locked_rotor(100, 50, "Y"), "S", "closed", False)
    r = execute("locked_rotor", spec, c.model_dump(), {"I_targets_pu": [0.5]})
    assert r.status in ("invalid_circuit", "solver_failure")


def test_spec_rejects_speed_above_synchronous() -> None:
    doc: dict[str, Any] = assumed_lab_motor().model_dump()
    doc["nameplate"]["n_n"] = 1500
    with pytest.raises(ValueError):
        MotorSpec.model_validate(doc)


# --------------------------------------------------------------------------- API journey


def test_M8_api_journey(client: TestClient) -> None:
    p = client.post("/api/projects", json={"name": "מנוע", "experiment_id": "induction_motor"})
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    assert p.json()["derived"]["n_sync"] == 1500
    kinds = [s["kind"] for s in client.get(f"/api/projects/{pid}/studies").json()]
    assert kinds == [
        "insulation",
        "dc_resistance",
        "no_load",
        "locked_rotor",
        "load",
        "inverter",
        "dol_start",
        "star_delta",
        "vf_start",
    ]
    # a transformer study does not exist here
    r = client.post(f"/api/projects/{pid}/runs", json={"study_kind": "vector_group", "case": {}})
    assert r.status_code == 404

    run = client.post(
        f"/api/projects/{pid}/runs",
        json={"study_kind": "load", "case": {"M_targets": [0.0, 1.0, 2.0, 2.5]}},
    ).json()
    assert run["status"] in ("success", "success_with_warnings"), run["error"]
    assert run["input_snapshot"]["spec"]["nameplate"]["P_n"] == 370
    assert "im-T-slip-1.0" in run["model_version"]
    rep = client.post(f"/api/runs/{run['id']}/reproduce").json()
    assert rep["identical"] and rep["input_hash_matches"]

    # live bench: brake and locked-rotor overrides
    live = client.post(
        f"/api/projects/{pid}/circuits/load/operating-point",
        json={"overrides": {"M": {"M_load": 2.0}}},
    ).json()
    assert live["status"] == "success" and live["readings"]["M"]["M"] == pytest.approx(2.0)
    stalled = client.post(
        f"/api/projects/{pid}/circuits/load/operating-point",
        json={"overrides": {"M": {"M_load": 50.0}}},
    ).json()
    assert stalled["status"] == "success_with_warnings"
    assert stalled["readings"]["M"]["n"] == 0

    # measured load table: values 3 % off the simulation at the same brake torques
    sim_rows = run["result"]["tables"][0]["rows"]
    s = client.post(
        f"/api/projects/{pid}/measurement-sets",
        json={"study_kind": "load", "label": "קבוצה 3", "n_rows": 4},
    ).json()
    sid = s["set"]["id"]
    for i, row in enumerate(sim_rows):
        for q, unit in (
            ("U1L", "V"),
            ("I1", "A"),
            ("P_W", "W"),
            ("pf", ""),
            ("n", "rpm"),
            ("M", "N·m"),
        ):
            v = row[q] * (1.03 if q in ("I1", "P_W") else 1.0)
            r = client.post(
                f"/api/measurement-sets/{sid}/entries",
                json={"row_index": i, "quantity": q, "value": v, "unit": unit},
            )
            assert r.status_code == 201, r.text
    view = client.get(f"/api/measurement-sets/{sid}").json()
    assert view["analysis"]["rows"][2]["P2"] == pytest.approx(sim_rows[2]["P2"], rel=1e-9)

    cmp_ = client.get(f"/api/comparison?run_id={run['id']}&set_id={sid}").json()
    assert cmp_["summary"]["unmatched_rows"] == 0
    errs = {c["quantity"]: c["rel_error"] for c in cmp_["pairs"][1]["cells"]}
    assert errs["I1"] == pytest.approx(0.03, rel=1e-9)
    assert errs["n"] == pytest.approx(0.0, abs=1e-12)

    sim2 = client.post(f"/api/measurement-sets/{sid}/simulate")
    assert sim2.status_code == 201
    assert sim2.json()["input_snapshot"]["case"]["M_targets"] == [r["M"] for r in sim_rows]

    guide = client.get(f"/api/projects/{pid}/guide").json()
    assert guide["total"] == 3 + 4 * 9
    rp = client.post(
        f"/api/projects/{pid}/reports",
        json={
            "title": "דו״ח ניסוי 2",
            "sections": [{"study_kind": "load", "run_id": run["id"], "set_id": sid}],
        },
    )
    assert rp.status_code == 201, rp.text
    html = client.get(f"/api/reports/{rp.json()['id']}/html").text
    assert "המנוע והנחות המודל" in html and "R2' [Ω]" in html

    exp = client.get(f"/api/projects/{pid}/export").json()
    assert exp["version"] == 2 and exp["project"]["spec"]["nameplate"]["poles"] == 4
    imp = client.post("/api/projects/import", json=exp)
    assert imp.status_code == 201 and imp.json()["experiment_id"] == "induction_motor"


def test_presets_per_experiment(client: TestClient) -> None:
    m = client.get("/api/experiments/induction_motor/presets").json()
    assert [x["id"] for x in m] == ["assumed_037kw"]
    t = client.get("/api/experiments/transformer3ph/presets").json()
    assert {x["id"] for x in t} == {"assumed_3kva", "report_2025"}
    ex = {e["id"]: e for e in client.get("/api/experiments").json()}
    assert ex["induction_motor"]["equipment_he"] == "המנוע"
