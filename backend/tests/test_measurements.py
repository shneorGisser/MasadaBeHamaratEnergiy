"""S3: measurement entry (units, append-only corrections), analysis and comparison (R10)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from vel.services.measurements import _rel
from vel.units import UnitError, convert


# R10 — units and error definitions
def test_R10_unit_conversion() -> None:
    assert convert(362.3, "mA", "A") == pytest.approx(0.3623)
    assert convert(0.5, "kΩ", "Ω") == pytest.approx(500)
    assert convert(500, "MΩ", "MΩ") == 500
    with pytest.raises(UnitError):
        convert(1, "mA", "V")
    with pytest.raises(UnitError):
        convert(float("nan"), "V", "V")
    with pytest.raises(UnitError):
        convert(1, "furlong", "V")


def test_R10_error_definitions() -> None:
    assert _rel(105.0, 100.0, "simulation") == (5.0, 0.05, None)
    a, r, why = _rel(105.0, 100.0, "measurement")
    assert a == 5.0 and r == pytest.approx(5 / 105)
    assert _rel(None, 1.0, "simulation")[2] == "חסרה מדידה"
    a, r, why = _rel(0.001, 0.0, "simulation")
    assert r is None and why is not None and "אפס" in why
    assert _rel(1.0, None, "simulation")[1] is None


def _project(client: TestClient) -> str:
    return client.post(
        "/api/projects", json={"name": "S3", "experiment_id": "transformer3ph"}
    ).json()["id"]


def _enter(client: TestClient, sid: str, row: int, q: str, v: float, unit: str) -> dict[str, Any]:
    r = client.post(
        f"/api/measurement-sets/{sid}/entries",
        json={"row_index": row, "quantity": q, "value": v, "unit": unit},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_entry_units_corrections_and_missing(client: TestClient) -> None:
    pid = _project(client)
    s = client.post(
        f"/api/projects/{pid}/measurement-sets",
        json={"study_kind": "no_load", "label": "קבוצה 3", "lab_date": "2026-10-12", "n_rows": 3},
    ).json()
    sid = s["set"]["id"]
    assert len(s["missing"]) == 3 * 7

    v = _enter(client, sid, 0, "I0", 362.3, "mA")
    assert v["cells"]["0:I0"]["value"] == pytest.approx(0.3623)
    assert v["cells"]["0:I0"]["entered_unit"] == "mA"

    bad = client.post(
        f"/api/measurement-sets/{sid}/entries",
        json={"row_index": 0, "quantity": "I0", "value": 1, "unit": "V"},
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_unit"
    assert (
        client.post(
            f"/api/measurement-sets/{sid}/entries",
            json={"row_index": 9, "quantity": "I0", "value": 1, "unit": "A"},
        ).status_code
        == 422
    )

    # correction: appends a new entry; the old one remains in history
    v = _enter(client, sid, 0, "I0", 0.36, "A")
    assert v["cells"]["0:I0"]["value"] == 0.36
    assert v["cells"]["0:I0"]["versions"] == 2
    hist = [h for h in v["history"] if h["quantity"] == "I0"]
    assert len(hist) == 2 and hist[1]["supersedes_id"] == hist[0]["id"]
    assert hist[0]["entered_value"] == 362.3  # original kept verbatim

    # rows that still hold data cannot be removed
    assert client.patch(f"/api/measurement-sets/{sid}", json={"n_rows": 0}).status_code == 422
    r = client.patch(f"/api/measurement-sets/{sid}", json={"n_rows": 2})
    assert r.status_code == 200 and r.json()["set"]["n_rows"] == 2


def _fill_from_run(
    client: TestClient,
    sid: str,
    rows: list[dict[str, Any]],
    keys: list[str],
    scale: dict[str, float],
) -> None:
    for i, row in enumerate(rows):
        for k in keys:
            if row.get(k) is not None:
                _enter(
                    client,
                    sid,
                    i,
                    k,
                    row[k] * scale.get(k, 1.0),
                    "" if k.startswith("pf") else {"U": "V", "I": "A", "P": "W"}[k[0]],
                )


def test_measured_equals_simulated_gives_zero_error_and_same_parameters(client: TestClient) -> None:
    pid = _project(client)
    keys = ["U1L", "U1ph", "U2L", "U2ph", "I0", "P_W", "pf"]
    s = client.post(
        f"/api/projects/{pid}/measurement-sets", json={"study_kind": "no_load", "n_rows": 3}
    ).json()
    sid = s["set"]["id"]
    ref = client.post(
        f"/api/projects/{pid}/runs",
        json={"study_kind": "no_load", "case": {"U_line_values": [300, 380, 420]}},
    ).json()
    sim_rows = ref["result"]["tables"][0]["rows"]
    # "measurements": exact simulated values, except I0 is 5 % higher
    _fill_from_run(client, sid, sim_rows, keys, {"I0": 1.05})

    run = client.post(f"/api/measurement-sets/{sid}/simulate").json()
    assert run["status"] in ("success", "success_with_warnings")
    assert run["input_snapshot"]["case"]["U_line_values"] == pytest.approx([300, 380, 420])

    cmp_ = client.get(f"/api/comparison?run_id={run['id']}&set_id={sid}").json()
    assert cmp_["summary"]["unmatched_rows"] == 0
    for pair in cmp_["pairs"]:
        cells = {c["quantity"]: c for c in pair["cells"]}
        assert cells["I0"]["rel_error"] == pytest.approx(0.05, rel=1e-9)
        assert cells["U2L"]["rel_error"] == pytest.approx(0.0, abs=1e-12)
        assert cells["P0"]["rel_error"] == pytest.approx(0.0, abs=1e-12)
    params = {p["key"]: p for p in cmp_["parameters"]}
    # g_m does not depend on I0 → identical; Y_m scales with I0 → +5 %
    assert params["g_m"]["rel_error"] == pytest.approx(0.0, abs=1e-12)
    assert params["Y_m"]["rel_error"] == pytest.approx(0.05, rel=1e-9)
    assert params["R_fe"]["theory"] == pytest.approx(2400)


def test_unmatched_and_missing_are_explicit(client: TestClient) -> None:
    pid = _project(client)
    sid = client.post(
        f"/api/projects/{pid}/measurement-sets", json={"study_kind": "no_load", "n_rows": 2}
    ).json()["set"]["id"]
    _enter(client, sid, 0, "U1L", 250, "V")
    _enter(client, sid, 0, "I0", 0.13, "A")
    _enter(client, sid, 1, "I0", 0.2, "A")
    run = client.post(
        f"/api/projects/{pid}/runs",
        json={"study_kind": "no_load", "case": {"U_line_values": [380]}},
    ).json()
    c = client.get(f"/api/comparison?run_id={run['id']}&set_id={sid}").json()
    assert c["pairs"][0]["simulated_row"] is None
    assert "±2%" in c["pairs"][0]["unmatched_reason"]
    assert c["pairs"][1]["unmatched_reason"].startswith("חסרה מדידת U1L")
    assert c["summary"]["max_abs_rel_error"] is None


def test_zero_reference_is_undefined_in_load_comparison(client: TestClient) -> None:
    pid = _project(client)
    sid = client.post(
        f"/api/projects/{pid}/measurement-sets",
        json={"study_kind": "load", "n_rows": 2, "conditions": {"load_kind": "R"}},
    ).json()["set"]["id"]
    for k, v, u in [("I2", 0, "A"), ("U2L", 219, "V"), ("P2_W", 0.1, "W")]:
        _enter(client, sid, 0, k, v, u)
    for k, v, u in [("I2", 7.8, "A"), ("U2L", 213, "V")]:
        _enter(client, sid, 1, k, v, u)
    run = client.post(f"/api/measurement-sets/{sid}/simulate").json()
    assert run["input_snapshot"]["case"]["include_no_load"] is True
    c = client.get(f"/api/comparison?run_id={run['id']}&set_id={sid}").json()
    row0 = {x["quantity"]: x for x in c["pairs"][0]["cells"]}
    assert row0["P2_W"]["rel_error"] is None
    assert "אפס" in row0["P2_W"]["undefined_reason"]
    row1 = {x["quantity"]: x for x in c["pairs"][1]["cells"]}
    # I2 is the operating-point key: the pairing makes it equal, so it is not a compared cell
    assert "I2" not in row1
    assert c["pairs"][1]["match_value"].startswith("I2=")
    assert row1["U2L"]["measured"] == 213


def test_comparison_rejects_mismatched_kinds(client: TestClient) -> None:
    pid = _project(client)
    sid = client.post(
        f"/api/projects/{pid}/measurement-sets", json={"study_kind": "short_circuit"}
    ).json()["set"]["id"]
    run = client.post(
        f"/api/projects/{pid}/runs",
        json={"study_kind": "no_load", "case": {"U_line_values": [380]}},
    ).json()
    r = client.get(f"/api/comparison?run_id={run['id']}&set_id={sid}")
    assert r.status_code == 422 and r.json()["error"]["code"] == "kind_mismatch"


def test_fixed_tables_and_vector_group_from_measurements(client: TestClient) -> None:
    pid = _project(client)
    v = client.post(
        f"/api/projects/{pid}/measurement-sets", json={"study_kind": "vector_group"}
    ).json()
    assert v["set"]["n_rows"] == 1
    sid = v["set"]["id"]
    # Yd1-like measurement: |AB| = 100, |ab| = 57.9, angle 30° → |Bb| by cosine law
    import math

    ab = 57.9
    bb = math.sqrt(100**2 + ab**2 - 2 * 100 * ab * math.cos(math.radians(30)))
    for q, val in (("U_aAB", 100), ("U_aAb", ab), ("U_Bb", bb)):
        out = _enter(client, sid, 0, q, val, "V")
    params = {p["key"]: p for p in out["analysis"]["parameters"]}
    assert params["theta"]["value"] == pytest.approx(30, abs=1e-6)
    assert params["clock_candidates"]["note"] == "1 או 11"
    dc = client.post(
        f"/api/projects/{pid}/measurement-sets", json={"study_kind": "dc_resistance"}
    ).json()
    assert dc["set"]["n_rows"] == 18
