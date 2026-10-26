"""Workspaces isolate visitors of a public deployment; share links copy, never expose;
feedback reaches only the operator."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from vel.api.workspace import COOKIE, GUARDED, UNSCOPED
from vel.main import create_app


@pytest.fixture()
def app(db_url: str) -> Any:
    return create_app(db_url, workspaces="cookie")


@pytest.fixture()
def alice(app: Any) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def bob(app: Any) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _project_with_everything(c: TestClient) -> dict[str, str]:
    pid = c.post(
        "/api/projects", json={"name": "של אליס", "experiment_id": "transformer3ph"}
    ).json()["id"]
    case = next(x for x in c.get(f"/api/projects/{pid}/studies").json() if x["kind"] == "no_load")
    run = c.post(
        f"/api/projects/{pid}/runs", json={"study_kind": "no_load", "case": case["default_case"]}
    ).json()
    st = c.post(
        f"/api/projects/{pid}/measurement-sets",
        json={"study_kind": "no_load", "label": "x", "n_rows": 1},
    ).json()["set"]
    rep = c.post(
        f"/api/projects/{pid}/reports",
        json={"title": "ד", "sections": [{"study_kind": "no_load", "run_id": run["id"]}]},
    ).json()
    return {"project": pid, "run": run["id"], "set": st["id"], "report": rep["id"]}


def test_WS1_every_id_route_is_guarded(app: Any) -> None:
    """A new route with an id parameter must be added to GUARDED (or consciously to UNSCOPED)."""
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path.startswith("/api/"):
            for name in re.findall(r"{(\w+)(?::\w+)?}", r.path):
                assert name in GUARDED or name in UNSCOPED, (r.path, name)


def test_WS2_a_second_browser_sees_nothing_of_the_first(alice: TestClient, bob: TestClient) -> None:
    ids = _project_with_everything(alice)
    assert alice.cookies.get(COOKIE) and alice.cookies.get(COOKIE) != bob.cookies.get(COOKIE)
    assert [p["id"] for p in alice.get("/api/projects").json()] == [ids["project"]]
    assert bob.get("/api/projects").json() == []
    pid = ids["project"]
    for method, url in [
        ("get", f"/api/projects/{pid}"),
        ("patch", f"/api/projects/{pid}"),
        ("delete", f"/api/projects/{pid}"),
        ("get", f"/api/projects/{pid}/export"),
        ("get", f"/api/projects/{pid}/runs"),
        ("post", f"/api/projects/{pid}/share"),
        ("get", f"/api/runs/{ids['run']}"),
        ("post", f"/api/runs/{ids['run']}/reproduce"),
        ("get", f"/api/measurement-sets/{ids['set']}"),
        ("post", f"/api/measurement-sets/{ids['set']}/entries"),
        ("get", f"/api/reports/{ids['report']}"),
        ("get", f"/api/reports/{ids['report']}/docx"),
        ("get", f"/api/comparison?run_id={ids['run']}&set_id={ids['set']}"),
    ]:
        kw = {"json": {}} if method in ("post", "patch") else {}
        res = getattr(bob, method)(url, **kw)
        assert res.status_code == 404, (method, url, res.status_code)
    # and nothing of Alice's was touched
    assert alice.get(f"/api/projects/{pid}").status_code == 200


def test_WS3_the_workspace_link_opens_the_same_workspace(
    alice: TestClient, bob: TestClient
) -> None:
    pid = _project_with_everything(alice)["project"]
    token = alice.get("/api/workspace").json()["token"]
    assert bob.post("/api/workspace", json={"token": token}).status_code == 204
    assert [p["id"] for p in bob.get("/api/projects").json()] == [pid]
    assert bob.post("/api/workspace", json={"token": "x" * 10}).status_code == 422


def test_WS4_share_link_copies_into_the_visitors_workspace(
    alice: TestClient, bob: TestClient
) -> None:
    ids = _project_with_everything(alice)
    token = alice.post(f"/api/projects/{ids['project']}/share").json()["token"]
    assert alice.post(f"/api/projects/{ids['project']}/share").json()["token"] == token  # stable
    info = bob.get(f"/api/shared/{token}").json()
    assert info["name"] == "של אליס" and info["experiment_id"] == "transformer3ph"
    copy = bob.post(f"/api/shared/{token}/copy").json()
    assert copy["id"] != ids["project"] and copy["name"] == "של אליס (עותק)"
    assert [p["id"] for p in bob.get("/api/projects").json()] == [copy["id"]]
    assert len(bob.get(f"/api/projects/{copy['id']}/runs").json()) == 1
    # Bob's copy is his; Alice's original is untouched and still not his
    assert bob.patch(f"/api/projects/{copy['id']}", json={"name": "של בוב"}).status_code == 200
    assert alice.get(f"/api/projects/{ids['project']}").json()["name"] == "של אליס"
    # revoked link stops working
    assert alice.delete(f"/api/projects/{ids['project']}/share").status_code == 204
    assert bob.get(f"/api/shared/{token}").status_code == 404
    assert bob.post(f"/api/shared/{token}/copy").status_code == 404


def test_WS5_feedback_is_stored_and_readable_only_with_the_admin_key(
    alice: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    res = alice.post(
        "/api/feedback",
        json={"message": "הכפתור לא עובד", "kind": "bug", "page": "/projects/x", "contact": "a@b"},
    )
    assert res.status_code == 201
    assert alice.post("/api/feedback", json={"message": ""}).status_code == 422
    monkeypatch.delenv("VEL_ADMIN_TOKEN", raising=False)
    assert alice.get("/api/feedback").status_code == 404  # no key configured: not reachable
    monkeypatch.setenv("VEL_ADMIN_TOKEN", "k" * 32)
    assert alice.get("/api/feedback", headers={"X-Admin-Token": "wrong"}).status_code == 404
    rows = alice.get("/api/feedback", headers={"X-Admin-Token": "k" * 32}).json()
    assert rows[0]["message"] == "הכפתור לא עובד" and rows[0]["kind"] == "bug"
    token = alice.get("/api/workspace").json()["token"]
    assert token not in str(rows)  # the operator never sees workspace tokens


def test_WS6_shared_mode_keeps_single_user_behaviour(client: TestClient) -> None:
    pid = client.post(
        "/api/projects", json={"name": "a", "experiment_id": "transformer3ph"}
    ).json()["id"]
    assert client.get("/api/workspace").json() == {"mode": "shared", "token": None}
    assert COOKIE not in client.cookies
    with TestClient(client.app) as other:
        assert [p["id"] for p in other.get("/api/projects").json()] == [pid]
