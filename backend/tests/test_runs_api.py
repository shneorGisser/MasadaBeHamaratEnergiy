"""S1 integration: API → validation → solver → SQLite → retrieval → reproducibility."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def _project(client: TestClient) -> dict[str, Any]:
    r = client.post("/api/projects", json={"name": "S1", "experiment_id": "transformer3ph"})
    assert r.status_code == 201
    return r.json()


def test_studies_listed_with_defaults_from_spec(client: TestClient) -> None:
    p = _project(client)
    st = {s["kind"]: s for s in client.get(f"/api/projects/{p['id']}/studies").json()}
    assert set(st) >= {"insulation", "dc_resistance", "no_load", "short_circuit"}
    assert 380.0 in st["no_load"]["default_case"]["U_line_values"]
    assert st["no_load"]["variants"] == ["YY", "YD"]


def test_run_persisted_immutable_and_reproducible(client: TestClient) -> None:
    p = _project(client)
    pid = p["id"]
    r = client.post(
        f"/api/projects/{pid}/runs",
        json={"study_kind": "no_load", "case": {"U_line_values": [190, 380, 456]}, "label": "א"},
    )
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["status"] == "success_with_warnings"  # 456 V > 1.1 Un
    assert run["input_snapshot"]["spec"] == p["spec"]
    rows = run["result"]["tables"][0]["rows"]
    assert [round(x["U1L"], 6) for x in rows] == [190, 380, 456]
    p0_before = rows[1]["P0"]

    # change the project's transformer: the stored run must not change
    spec = p["spec"]
    spec2 = {**spec, "ecm": {**spec["ecm"], "R_fe": 1200}}
    assert client.patch(f"/api/projects/{pid}", json={"spec": spec2}).status_code == 200
    again = client.get(f"/api/runs/{run['id']}").json()
    assert again["result"]["tables"][0]["rows"][1]["P0"] == p0_before
    assert again["input_snapshot"]["spec"]["ecm"]["R_fe"] == 2400

    # a new run uses the new spec: core loss doubles (R_Fe halved)
    r2 = client.post(
        f"/api/projects/{pid}/runs",
        json={"study_kind": "no_load", "case": {"U_line_values": [380]}},
    ).json()
    assert r2["result"]["tables"][0]["rows"][0]["P0"] > 1.9 * p0_before * 0.99

    rep = client.post(f"/api/runs/{run['id']}/reproduce").json()
    assert rep["identical"] is True
    assert rep["input_hash_matches"] is True

    lst = client.get(f"/api/projects/{pid}/runs").json()
    assert [x["id"] for x in lst] == [r2["id"], run["id"]]


def test_failed_run_is_stored_as_failure(client: TestClient) -> None:
    pid = _project(client)["id"]
    r = client.post(
        f"/api/projects/{pid}/runs",
        json={"study_kind": "no_load", "case": {"U_line_values": [0]}},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "invalid_input"
    assert body["result"] is None


def test_unknown_study_404(client: TestClient) -> None:
    pid = _project(client)["id"]
    r = client.post(f"/api/projects/{pid}/runs", json={"study_kind": "x", "case": {}})
    assert r.status_code == 404


def test_circuit_roundtrip_and_validation(client: TestClient) -> None:
    pid = _project(client)["id"]
    c = client.get(f"/api/projects/{pid}/circuits/no_load").json()["circuit"]
    assert any(comp["type"] == "transformer3" for comp in c["components"])
    # reset to delta secondary
    d = client.post(f"/api/projects/{pid}/circuits/no_load/reset", json={"variant": "YD"}).json()
    assert any(
        w["a"] == {"component": "T", "terminal": "a2"}
        and w["b"] == {"component": "T", "terminal": "b1"}
        for w in d["circuit"]["wires"]
    )
    bad = {
        **c,
        "wires": [
            *c["wires"],
            {
                "id": "zz",
                "a": {"component": "T", "terminal": "Q9"},
                "b": {"component": "G", "terminal": "L1"},
            },
        ],
    }
    r = client.put(f"/api/projects/{pid}/circuits/no_load", json=bad)
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_circuit"
    assert client.put(f"/api/projects/{pid}/circuits/dc_resistance", json=c).status_code == 409


def test_all_default_studies_run(client: TestClient) -> None:
    pid = _project(client)["id"]
    studies = client.get(f"/api/projects/{pid}/studies").json()
    for s in studies:
        r = client.post(
            f"/api/projects/{pid}/runs", json={"study_kind": s["kind"], "case": s["default_case"]}
        ).json()
        assert r["status"] in ("success", "success_with_warnings"), (s["kind"], r["error"])


def test_live_operating_point_matches_study_and_validates(client: TestClient) -> None:
    pid = _project(client)["id"]
    live = client.post(
        f"/api/projects/{pid}/circuits/no_load/operating-point",
        json={"overrides": {"G": {"U_line": 380}}},
    ).json()
    assert live["status"] == "success" and live["persisted"] is False
    run = client.post(
        f"/api/projects/{pid}/runs",
        json={"study_kind": "no_load", "case": {"U_line_values": [380]}},
    ).json()
    row = run["result"]["tables"][0]["rows"][0]
    assert live["readings"]["A"]["I"] == row["I0"]
    assert live["readings"]["W"]["P"] == row["P_W"]

    opened = client.post(
        f"/api/projects/{pid}/circuits/no_load/operating-point",
        json={"overrides": {"S": {"closed": False}}},
    ).json()
    assert opened["readings"]["A"]["I"] == 0.0
    assert opened["readings"]["V2"]["U"] == 0.0

    bad = client.post(
        f"/api/projects/{pid}/circuits/no_load/operating-point",
        json={"overrides": {"T": {"R1": 0}}},
    )
    assert bad.status_code == 422
    assert (
        client.post(
            f"/api/projects/{pid}/circuits/no_load/operating-point",
            json={"overrides": {"ZZ": {"U_line": 1}}},
        ).status_code
        == 422
    )
    neg = client.post(
        f"/api/projects/{pid}/circuits/no_load/operating-point",
        json={"overrides": {"G": {"U_line": -5}}},
    ).json()
    assert neg["status"] == "invalid_circuit"
