"""The measurement coach asks about readings that look like a known slip (×1000, one phase
vs total, a decimal point) or that break the trend of the table — and stays quiet on good data."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def _set(client: TestClient) -> tuple[str, str]:
    pid = client.post(
        "/api/projects", json={"name": "c", "experiment_id": "induction_motor"}
    ).json()["id"]
    spec = next(
        p
        for p in client.get("/api/experiments/induction_motor/presets").json()
        if p["id"] == "ap3030_sheet_2026"
    )["spec"]
    assert client.patch(f"/api/projects/{pid}", json={"spec": spec}).status_code == 200
    sid = client.post(
        f"/api/projects/{pid}/datasets/induction_motor_2026/import", json={"study_kind": "load"}
    ).json()["sets"][0]["id"]
    return pid, sid


def _hints(client: TestClient, sid: str) -> list[dict[str, Any]]:
    r = client.get(f"/api/measurement-sets/{sid}/coach").json()
    assert r["status"] == "ok", r
    return list(r["hints"])


def test_CO1_good_table_no_questions(client: TestClient) -> None:
    _, sid = _set(client)
    assert _hints(client, sid) == []
    # nothing was saved: the coach is not a run
    pid = client.get(f"/api/measurement-sets/{sid}").json()["set"]["project_id"]
    assert client.get(f"/api/projects/{pid}/runs").json() == []


def test_CO2_milliamps_and_one_phase_power_are_recognised(client: TestClient) -> None:
    _, sid = _set(client)
    client.post(
        f"/api/measurement-sets/{sid}/entries",
        json={"row_index": 2, "quantity": "I1", "value": 550, "unit": "A"},
    )
    client.post(
        f"/api/measurement-sets/{sid}/entries",
        json={"row_index": 4, "quantity": "P_W", "value": 345, "unit": "W"},
    )
    h = {(x["row"], x["quantity"]): x for x in _hints(client, sid)}
    assert h[(2, "I1")]["kind"] == "factor" and h[(2, "I1")]["factor"] == "1000"
    assert abs(h[(2, "I1")]["suggested"] - 0.55) < 0.01
    assert h[(4, "P_W")]["factor"] == "3" and "פאזה אחת" in h[(4, "P_W")]["message"]
    assert not h[(4, "P_W")]["whole_column"]


def test_CO3_a_row_off_the_trend(client: TestClient) -> None:
    _, sid = _set(client)
    client.post(
        f"/api/measurement-sets/{sid}/entries",
        json={"row_index": 3, "quantity": "I1", "value": 0.82, "unit": "A"},
    )
    h = [x for x in _hints(client, sid) if x["quantity"] == "I1"]
    assert [(x["row"], x["kind"]) for x in h] == [(3, "trend")]
    assert "לפני שמפרקים" in h[0]["message"]
