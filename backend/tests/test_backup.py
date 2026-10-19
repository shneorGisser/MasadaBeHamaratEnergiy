"""Export → import round trip keeps runs reproducible, corrections chained, reports identical."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.test_reports_guide import _setup


def test_export_import_round_trip(client: TestClient) -> None:
    pid, sid, rid = _setup(client)
    client.post(
        f"/api/measurement-sets/{sid}/entries",
        json={"row_index": 0, "quantity": "I0", "value": 0.4, "unit": "A"},
    )  # a correction
    rep = client.post(
        f"/api/projects/{pid}/reports",
        json={"title": "R", "sections": [{"study_kind": "no_load", "run_id": rid, "set_id": sid}]},
    ).json()
    doc = client.get(f"/api/projects/{pid}/export").json()
    assert doc["format"] == "virtual-energy-lab/project"

    r = client.post("/api/projects/import", json=doc)
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["id"] != pid and new["name"].endswith("(שוחזר)")

    runs = client.get(f"/api/projects/{new['id']}/runs").json()
    assert len(runs) == 1 and runs[0]["id"] != rid
    assert runs[0]["input_hash"] == client.get(f"/api/runs/{rid}").json()["input_hash"]
    assert client.post(f"/api/runs/{runs[0]['id']}/reproduce").json()["identical"] is True

    sets = client.get(f"/api/projects/{new['id']}/measurement-sets").json()
    view = client.get(f"/api/measurement-sets/{sets[0]['id']}").json()
    assert view["cells"]["0:I0"]["value"] == 0.4 and view["cells"]["0:I0"]["versions"] == 2
    hist = [h for h in view["history"] if h["quantity"] == "I0"]
    assert hist[1]["supersedes_id"] == hist[0]["id"]

    reps = client.get(f"/api/projects/{new['id']}/reports").json()
    assert (
        client.get(f"/api/reports/{reps[0]['id']}/html").text
        == client.get(f"/api/reports/{rep['id']}/html").text
    )


def test_import_rejects_garbage(client: TestClient) -> None:
    assert client.post("/api/projects/import", json={"format": "x"}).status_code == 422
    bad = {
        "format": "virtual-energy-lab/project",
        "version": 1,
        "project": {
            "name": "x",
            "experiment_id": "transformer3ph",
            "experiment_version": 1,
            "transformer": {"nonsense": True},
        },
    }
    assert client.post("/api/projects/import", json=bad).status_code == 422
