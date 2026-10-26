"""Calibration recovers known parameters from synthetic measurements, reports what the data
cannot separate, and never saves anything by itself."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from vel.experiments import registry
from vel.services.measurements import mdef


def _measure(
    client: TestClient, pid: str, kind: str, true_spec: dict[str, Any], base: dict[str, Any]
) -> str:
    """Simulate with the 'true' machine, enter its readings as a measurement set, then put the
    project back on the base spec — the lab situation: the model is off, the readings are real."""
    exp = client.get(f"/api/projects/{pid}").json()["experiment_id"]
    assert client.patch(f"/api/projects/{pid}", json={"spec": true_spec}).status_code == 200
    case = next(x for x in client.get(f"/api/projects/{pid}/studies").json() if x["kind"] == kind)[
        "default_case"
    ]
    run = client.post(f"/api/projects/{pid}/runs", json={"study_kind": kind, "case": case}).json()
    assert run["result"], run
    rows = run["result"]["tables"][0]["rows"]
    d = mdef(exp, kind)
    n = len(d.row_labels) if d.row_labels else len(rows)
    st = client.post(
        f"/api/projects/{pid}/measurement-sets",
        json={"study_kind": kind, "label": "סינתטי", "n_rows": n},
    ).json()
    sid = st["set"]["id"]
    for i, r in enumerate(rows[:n]):
        for c in d.columns:
            v = r.get(c.key)
            if isinstance(v, (int, float)):
                res = client.post(
                    f"/api/measurement-sets/{sid}/entries",
                    json={"row_index": i, "quantity": c.key, "value": v, "unit": c.unit},
                )
                assert res.status_code == 201, res.text
    assert client.patch(f"/api/projects/{pid}", json={"spec": base}).status_code == 200
    return sid


def test_C1_short_circuit_recovers_R_and_X(client: TestClient) -> None:
    pid = client.post(
        "/api/projects", json={"name": "כיול", "experiment_id": "transformer3ph"}
    ).json()["id"]
    base = client.get(f"/api/projects/{pid}").json()["spec"]
    true = {**base, "ecm": {**base["ecm"]}}
    for k, f in (("R1", 1.3), ("R2", 1.3), ("X1", 0.8), ("X2", 0.8)):
        true["ecm"][k] = base["ecm"][k] * f
    sid = _measure(client, pid, "short_circuit", true, base)
    out = client.post(f"/api/measurement-sets/{sid}/calibrate", json={}).json()
    f = {"+".join(k["paths"]): k["factor"] for k in out["knobs"]}
    assert f["ecm.R1+ecm.R2"] == pytest.approx(1.3, rel=1e-3)
    assert f["ecm.X1+ecm.X2"] == pytest.approx(0.8, rel=1e-3)
    assert out["after"]["rms_rel"] < 1e-4 < out["before"]["rms_rel"]
    assert out["proposed_spec"]["provenance"] == "fitted"
    assert "כויל לסט המדידות" in out["proposed_spec"]["provenance_note"]
    # nothing was saved
    assert client.get(f"/api/projects/{pid}").json()["spec"]["ecm"]["R1"] == base["ecm"]["R1"]


def test_C2_no_load_recovers_the_magnetising_branch(client: TestClient) -> None:
    pid = client.post(
        "/api/projects", json={"name": "כיול2", "experiment_id": "induction_motor"}
    ).json()["id"]
    base = client.get(f"/api/projects/{pid}").json()["spec"]
    true = {
        **base,
        "ecm": {**base["ecm"], "Xm": base["ecm"]["Xm"] * 1.15, "R_fe": base["ecm"]["R_fe"] * 0.85},
    }
    sid = _measure(client, pid, "no_load", true, base)
    out = client.post(
        f"/api/measurement-sets/{sid}/calibrate", json={"knobs": [["ecm.Xm"], ["ecm.R_fe"]]}
    ).json()
    f = {"+".join(k["paths"]): k["factor"] for k in out["knobs"]}
    assert f["ecm.Xm"] == pytest.approx(1.15, rel=2e-3)
    assert f["ecm.R_fe"] == pytest.approx(0.85, rel=2e-3)


def test_C3_inseparable_knobs_are_flagged_and_bad_requests_refused(client: TestClient) -> None:
    pid = client.post(
        "/api/projects", json={"name": "כיול3", "experiment_id": "transformer3ph"}
    ).json()["id"]
    base = client.get(f"/api/projects/{pid}").json()["spec"]
    true = {
        **base,
        "ecm": {**base["ecm"], "R1": base["ecm"]["R1"] * 1.2, "R2": base["ecm"]["R2"] * 1.2},
    }
    sid = _measure(client, pid, "short_circuit", true, base)
    # R1 and R2 separately: a short-circuit test sees only R1 + R2' → correlated (or singular)
    out = client.post(
        f"/api/measurement-sets/{sid}/calibrate", json={"knobs": [["ecm.R1"], ["ecm.R2"]]}
    ).json()
    codes = {w["code"] for w in out["warnings"]}
    assert codes & {"correlated", "not_identifiable"}, out["warnings"]
    bad = client.post(f"/api/measurement-sets/{sid}/calibrate", json={"knobs": [["ecm.nope"]]})
    assert bad.status_code == 422


def test_C5_every_default_knob_points_at_a_positive_spec_field() -> None:
    from vel.services.calibration import DEFAULT_KNOBS

    for exp, studies in DEFAULT_KNOBS.items():
        m = registry.get(exp)
        doc = m.default_spec().model_dump(mode="json")
        for kind, knobs in studies.items():
            assert kind in m.studies, (exp, kind)
            assert kind in m.measure_defs, (exp, kind)
            for paths in knobs:
                for p in paths:
                    sec, key = p.split(".")
                    assert isinstance(doc[sec][key], (int, float)) and doc[sec][key] > 0, (exp, p)


def test_C6_real_sheet_2026_predicts_the_load_test(client: TestClient) -> None:
    """The experiment-2 sheet photographed at the bench (vel.labdata induction_motor_2026):
    no-load and locked-rotor calibration alone predict the independent load test's input
    power and current within ≈ 10 %. The slip stays over-predicted — the R1/R2' split is not
    fixed by these tests (no DC-resistance row on the sheet); the test pins that honestly."""
    pid = client.post(
        "/api/projects", json={"name": "ex2", "experiment_id": "induction_motor"}
    ).json()["id"]
    sids = {
        k: client.post(
            f"/api/projects/{pid}/datasets/induction_motor_2026/import", json={"study_kind": k}
        ).json()["sets"][0]["id"]
        for k in ("no_load", "locked_rotor", "load")
    }
    spec = client.get(f"/api/projects/{pid}").json()["spec"]
    for k in ("no_load", "locked_rotor"):
        out = client.post(f"/api/measurement-sets/{sids[k]}/calibrate", json={}).json()
        assert out["after"]["rms_rel"] < 0.06 < out["before"]["rms_rel"], k
        for knob in out["knobs"]:
            for path, v in knob["after"].items():
                sec, key = path.split(".")
                spec[sec][key] = v
    # the real motor's rotor resistance is far above the default machine's
    assert 2.4 < spec["ecm"]["R2p"] / 20.0 < 3.1
    assert client.patch(f"/api/projects/{pid}", json={"spec": spec}).status_code == 200
    run = client.post(f"/api/measurement-sets/{sids['load']}/simulate").json()
    cmp_ = client.get(f"/api/comparison?run_id={run['id']}&set_id={sids['load']}").json()
    err: dict[str, list[float]] = {}
    for p in cmp_["pairs"]:
        for cell in p["cells"]:
            if cell["rel_error"] is not None:
                err.setdefault(cell["quantity"], []).append(abs(cell["rel_error"]))
    assert max(err["P1"]) < 0.1 and max(err["I1"]) < 0.12 and max(err["pf"]) < 0.08
    assert max(err["slip"]) > 0.3  # known gap, see docs/lab-data-2026-exp2.md
