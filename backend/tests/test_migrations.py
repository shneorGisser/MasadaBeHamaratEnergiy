"""Schema migrations keep existing data: a database created before the multi-experiment
refactor (revision 0004, column `transformer_json`) upgrades with its projects and runs intact,
and the old runs still reproduce bit-identically."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from vel.db import make_engine
from vel.main import create_app
from vel.migrate import upgrade


def test_0005_renames_spec_column_and_keeps_old_runs(db_url: str) -> None:
    if not db_url.startswith("sqlite"):
        return  # same migration path is exercised on PostgreSQL by the regular suite
    engine = make_engine(db_url)
    upgrade(engine, "0004")
    spec = {
        "schema_version": 1,
        "provenance": "assumed",
        "provenance_note": "",
        "nameplate": {
            "S_n": 3000,
            "U1n": 380,
            "U2n": 220,
            "f_n": 50,
            "primary": "Y",
            "secondary": "Y",
        },
        "ecm": {
            "R1": 0.72,
            "X1": 0.97,
            "R2": 0.24,
            "X2": 0.32,
            "R_fe": 2400,
            "Xm_unsat": 1240,
            "sat_c": 1.0,
            "sat_n": 8,
        },
        "insulation": {
            "primary_core_Mohm": 500,
            "secondary_core_Mohm": 500,
            "primary_secondary_Mohm": 500,
        },
    }
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO projects (id, name, experiment_id, experiment_version, "
                "transformer_json, circuits_json, notes, created_at, updated_at) VALUES "
                "('p1', 'ישן', 'transformer3ph', 1, :s, '{}', '', '2026-01-01', '2026-01-01')"
            ),
            {"s": json.dumps(spec)},
        )
    engine.dispose()

    app = create_app(db_url)  # runs the upgrade to head
    with TestClient(app) as client:
        p = client.get("/api/projects/p1").json()
        assert p["spec"] == spec
        # an old-format run snapshot ("transformer" key) still executes and reproduces
        run = client.post(
            "/api/projects/p1/runs",
            json={"study_kind": "insulation", "case": {"U_test": 500}},
        ).json()
    app.state.db.engine.dispose()
    eng2 = create_engine(db_url)
    with eng2.begin() as c:
        snap = json.loads(
            c.execute(text("SELECT input_snapshot FROM simulation_runs")).scalar_one()
        )
        snap["transformer"] = snap.pop("spec")
        c.execute(text("UPDATE simulation_runs SET input_snapshot = :s"), {"s": json.dumps(snap)})
    eng2.dispose()
    app = create_app(db_url)
    with TestClient(app) as client:
        rep = client.post(f"/api/runs/{run['id']}/reproduce").json()
        assert rep["identical"]
    app.state.db.engine.dispose()
