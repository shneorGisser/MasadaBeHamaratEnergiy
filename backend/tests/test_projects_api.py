"""S0 integration tests: API → validation → SQLite → retrieval."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from vel.main import create_app


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_experiments_listed(client: TestClient) -> None:
    r = client.get("/api/experiments")
    assert r.status_code == 200
    ids = [e["id"] for e in r.json()]
    assert "transformer3ph" in ids


def test_create_get_list_update_delete(client: TestClient) -> None:
    r = client.post(
        "/api/projects", json={"name": "  קבוצה 3  ", "experiment_id": "transformer3ph"}
    )
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["name"] == "קבוצה 3"
    assert p["spec"]["provenance"] == "assumed"
    assert abs(p["derived"]["turns_ratio"] - 380 / 220) < 1e-12

    r = client.get(f"/api/projects/{p['id']}")
    assert r.status_code == 200 and r.json()["id"] == p["id"]

    assert [x["id"] for x in client.get("/api/projects").json()] == [p["id"]]

    r = client.patch(f"/api/projects/{p['id']}", json={"notes": "שנאי בשולחן 4"})
    assert r.status_code == 200 and r.json()["notes"] == "שנאי בשולחן 4"

    assert client.delete(f"/api/projects/{p['id']}").status_code == 204
    assert client.get(f"/api/projects/{p['id']}").status_code == 404


def test_persistence_survives_restart(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'persist.sqlite3'}"
    with TestClient(create_app(url)) as c1:
        pid = c1.post(
            "/api/projects", json={"name": "A", "experiment_id": "transformer3ph"}
        ).json()["id"]
    with TestClient(create_app(url)) as c2:
        r = c2.get(f"/api/projects/{pid}")
        assert r.status_code == 200
        assert r.json()["name"] == "A"


def test_invalid_inputs(client: TestClient) -> None:
    r = client.post("/api/projects", json={"name": "", "experiment_id": "transformer3ph"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_input"

    r = client.post("/api/projects", json={"name": "x", "experiment_id": "nope"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_experiment"

    r = client.post("/api/projects", json={"name": "x", "experiment_id": "transformer3ph", "y": 1})
    assert r.status_code == 422

    assert client.get("/api/projects/does-not-exist").status_code == 404


def test_transformer_update_validated(client: TestClient) -> None:
    p = client.post("/api/projects", json={"name": "x", "experiment_id": "transformer3ph"}).json()
    spec = p["spec"]
    bad = {**spec, "nameplate": {**spec["nameplate"], "S_n": -5}}
    r = client.patch(f"/api/projects/{p['id']}", json={"spec": bad})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_spec"
    # unchanged after rejected update
    assert client.get(f"/api/projects/{p['id']}").json()["spec"] == spec

    implausible = {**spec, "ecm": {**spec["ecm"], "Xm_unsat": 2.0}}
    r = client.patch(f"/api/projects/{p['id']}", json={"spec": implausible})
    assert r.status_code == 422

    good = {**spec, "provenance": "nameplate", "nameplate": {**spec["nameplate"], "S_n": 5000}}
    r = client.patch(f"/api/projects/{p['id']}", json={"spec": good})
    assert r.status_code == 200
    assert r.json()["spec"]["nameplate"]["S_n"] == 5000
