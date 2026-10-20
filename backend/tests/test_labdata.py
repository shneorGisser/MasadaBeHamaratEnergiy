"""Transcribed lab reports: every table fits its experiment's measurement definition, imports
through the normal entry path, and can be simulated at its own operating points and compared."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vel.experiments import registry
from vel.labdata import DATASETS
from vel.units import convert


@pytest.mark.parametrize("dataset_id", sorted(DATASETS))
def test_tables_fit_their_definitions(dataset_id: str) -> None:
    d = DATASETS[dataset_id]
    mod = registry.get(d.experiment_id)
    for t in d.tables:
        md = mod.measure_defs[t.study_kind]
        cols = {c.key: c.unit for c in md.columns}
        for key, unit in t.columns:
            assert key in cols, (t.label, key)
            convert(1.0, unit, cols[key])  # raises on an incompatible unit
        assert set(t.conditions) <= set(md.condition_keys), t.label
        assert all(len(r) == len(t.columns) for r in t.rows), t.label
        if md.rows == "fixed":
            idx = t.row_index or tuple(range(len(t.rows)))
            assert max(idx) < len(md.row_labels), t.label


def test_import_simulate_compare_every_table(client: TestClient) -> None:
    for d in DATASETS.values():
        listed = client.get(f"/api/experiments/{d.experiment_id}/datasets").json()
        assert d.id in {x["id"] for x in listed}
        pid = client.post("/api/projects", json={"name": d.id, "experiment_id": d.experiment_id})
        pid = pid.json()["id"]
        r = client.post(f"/api/projects/{pid}/datasets/{d.id}/import", json={})
        assert r.status_code == 201, r.text
        sets = r.json()["sets"]
        assert len(sets) == len(d.tables)
        for s, t in zip(sets, d.tables, strict=True):
            view = client.get(f"/api/measurement-sets/{s['id']}").json()
            n_values = sum(v is not None for row in t.rows for v in row)
            assert len(view["cells"]) == n_values, t.label
            assert all("מיובא" in h["note"] for h in view["history"]), t.label
            sim = client.post(f"/api/measurement-sets/{s['id']}/simulate")
            assert sim.status_code == 201, (t.label, sim.text)
            run = sim.json()
            if run["status"] in ("success", "success_with_warnings"):
                cmp_ = client.get(f"/api/comparison?run_id={run['id']}&set_id={s['id']}")
                assert cmp_.status_code == 200, (t.label, cmp_.text)


def test_import_rejects_other_experiment(client: TestClient) -> None:
    pid = client.post("/api/projects", json={"name": "x", "experiment_id": "dc_motor"}).json()["id"]
    r = client.post(f"/api/projects/{pid}/datasets/transformer_2025/import", json={})
    assert r.status_code == 422
    r = client.post(
        f"/api/projects/{pid}/datasets/dc_motor_2025/import", json={"study_kind": "load"}
    )
    assert r.status_code == 201 and len(r.json()["sets"]) == 1
