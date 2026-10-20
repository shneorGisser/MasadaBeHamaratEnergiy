"""S5: guided-mode status from real data; immutable reports; PDF rendering."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vel.services.reports import chromium_path


def _setup(client: TestClient) -> tuple[str, str, str]:
    pid = client.post(
        "/api/projects", json={"name": "S5", "experiment_id": "transformer3ph"}
    ).json()["id"]
    sid = client.post(
        f"/api/projects/{pid}/measurement-sets",
        json={"study_kind": "no_load", "label": "מעבדה", "n_rows": 1},
    ).json()["set"]["id"]
    vals = {
        "U1L": 380,
        "U1ph": 219.5,
        "U2L": 221,
        "U2ph": 127.4,
        "I0": 0.38,
        "P_W": 21.5,
        "pf": 0.26,
    }
    for q, v in vals.items():
        client.post(
            f"/api/measurement-sets/{sid}/entries",
            json={
                "row_index": 0,
                "quantity": q,
                "value": v,
                "unit": "" if q == "pf" else {"U": "V", "I": "A", "P": "W"}[q[0]],
            },
        )
    rid = client.post(f"/api/measurement-sets/{sid}/simulate").json()["id"]
    return pid, sid, rid


def test_guide_progress_follows_data(client: TestClient) -> None:
    pid = client.post(
        "/api/projects", json={"name": "G", "experiment_id": "transformer3ph"}
    ).json()["id"]
    g = client.get(f"/api/projects/{pid}/guide").json()
    assert g["done"] == 0 and g["total"] == 2 + 7 * 4 + 1
    ids = [s["id"] for s in g["steps"]]
    assert ids[0] == "safety" and ids[-1] == "report"
    # data-driven steps cannot be ticked by a click
    r = client.post(f"/api/projects/{pid}/guide/ack", json={"step_id": "no_load.simulate"})
    assert r.status_code == 422
    g = client.post(f"/api/projects/{pid}/guide/ack", json={"step_id": "safety"}).json()
    assert next(s for s in g["steps"] if s["id"] == "safety")["done"] is True
    client.post(
        f"/api/projects/{pid}/runs",
        json={"study_kind": "no_load", "case": {"U_line_values": [380]}},
    )
    g = client.get(f"/api/projects/{pid}/guide").json()
    st = {s["id"]: s for s in g["steps"]}
    assert st["no_load.simulate"]["done"] is True
    assert st["no_load.measure"]["done"] is False
    assert st["short_circuit.simulate"]["done"] is False


def test_report_is_immutable_snapshot(client: TestClient) -> None:
    pid, sid, rid = _setup(client)
    rep = client.post(
        f"/api/projects/{pid}/reports",
        json={
            "title": "דו״ח ניסוי 1",
            "sections": [{"study_kind": "no_load", "run_id": rid, "set_id": sid}],
            "student_discussion": "הזרם הנמדד גבוה מהמודל, כנראה בגלל...",
        },
    )
    assert rep.status_code == 201, rep.text
    rep_id = rep.json()["id"]
    html = client.get(f"/api/reports/{rep_id}/html").text
    assert 'dir="rtl"' in html and "David" in html
    assert "0.3800" in html  # measured I0
    assert "הזרם הנמדד גבוה מהמודל" in html
    assert "פרמטרי השנאי מוערכים" in html

    # correct a measurement and change the spec afterwards — the report must not change
    client.post(
        f"/api/measurement-sets/{sid}/entries",
        json={"row_index": 0, "quantity": "I0", "value": 0.5, "unit": "A"},
    )
    p = client.get(f"/api/projects/{pid}").json()
    spec = p["spec"]
    client.patch(
        f"/api/projects/{pid}", json={"spec": {**spec, "ecm": {**spec["ecm"], "R_fe": 999}}}
    )
    assert client.get(f"/api/reports/{rep_id}/html").text == html
    snap = client.get(f"/api/reports/{rep_id}").json()["sources"]["snapshot"]
    assert snap["sections"][0]["measurements"]["rows"][0]["I0"] == 0.38

    g = client.get(f"/api/projects/{pid}/guide").json()
    assert {s["id"]: s for s in g["steps"]}["report"]["done"] is True


def test_report_without_discussion_says_so(client: TestClient) -> None:
    pid, sid, rid = _setup(client)
    rep = client.post(
        f"/api/projects/{pid}/reports",
        json={"title": "ללא דיון", "sections": [{"study_kind": "no_load", "set_id": sid}]},
    ).json()
    html = client.get(f"/api/reports/{rep['id']}/html").text
    assert "המערכת אינה מנסחת הסבר לפערים" in html
    assert "אין סימולציה בדו״ח" in html


def test_report_validation(client: TestClient) -> None:
    pid, sid, rid = _setup(client)
    bad = client.post(
        f"/api/projects/{pid}/reports",
        json={"title": "x", "sections": [{"study_kind": "short_circuit", "run_id": rid}]},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "bad_run"
    empty = client.post(
        f"/api/projects/{pid}/reports", json={"title": "x", "sections": [{"study_kind": "load"}]}
    )
    assert empty.status_code == 422


@pytest.mark.skipif(chromium_path() is None, reason="no Chromium — PDF rendering NOT tested")
def test_report_pdf(client: TestClient) -> None:
    pid, sid, rid = _setup(client)
    rep = client.post(
        f"/api/projects/{pid}/reports",
        json={
            "title": "PDF",
            "sections": [{"study_kind": "no_load", "run_id": rid, "set_id": sid}],
        },
    ).json()
    r = client.get(f"/api/reports/{rep['id']}/pdf")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    assert len(r.content) > 5000
