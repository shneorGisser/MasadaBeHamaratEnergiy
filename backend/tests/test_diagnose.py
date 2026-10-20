"""Automatic explanations of measured-vs-simulated differences (services/diagnose.py)."""

from __future__ import annotations

import math
from typing import Any

import pytest
from fastapi.testclient import TestClient

from vel.services.diagnose import explain


def pairs_of(
    sim: list[dict[str, float]], meas: list[dict[str, float]], units: dict[str, str]
) -> list[dict[str, Any]]:
    out = []
    for i, (s, m) in enumerate(zip(sim, meas, strict=True)):
        out.append(
            {
                "measured_row": i,
                "simulated_row": i,
                "unmatched_reason": None,
                "cells": [
                    {
                        "quantity": q,
                        "unit": units[q],
                        "measured": m.get(q),
                        "simulated": v,
                        "rel_error": None,
                    }
                    for q, v in s.items()
                ],
            }
        )
    return out


SIM = [{"U": 100.0 + 20 * i, "P": 10.0 + 7 * i, "I": 0.2 + 0.1 * i} for i in range(5)]
UNITS = {"U": "V", "P": "W", "I": "A"}


def codes(f: list[dict[str, Any]]) -> list[tuple[str, str | None, str | None]]:
    return [(x["code"], x.get("quantity"), x.get("known")) for x in f]


@pytest.mark.parametrize(
    ("q", "k", "known", "word"),
    [
        ("U", math.sqrt(3), "√3", "קווי"),
        ("P", 3.0, "3", "פאזה אחת"),
        ("I", 1e-3, "1/1000", "יחידה"),
        ("P", -1.0, "−1", "סימן"),
    ],
)
def test_recognised_factors(q: str, k: float, known: str, word: str) -> None:
    meas = [{**r, q: r[q] * k} for r in SIM]
    f = explain(pairs_of(SIM, meas, UNITS))
    assert ("systematic_factor", q, known) in codes(f)
    assert word in next(x["message"] for x in f if x.get("quantity") == q)


def test_unexplained_common_factor_is_merged() -> None:
    meas = [{**r, "U": r["U"] * 1.85, "I": r["I"] * 1.83} for r in SIM]
    f = explain(pairs_of(SIM, meas, UNITS))
    assert [x["code"] for x in f] == ["common_factor"]
    assert f[0]["factor"] == pytest.approx(1.84, abs=0.02)


def test_decimal_point_outlier_offset_and_swap() -> None:
    meas = [dict(r) for r in SIM]
    meas[2]["I"] = SIM[2]["I"] * 10  # decimal point
    f = explain(pairs_of(SIM, meas, UNITS))
    assert ("decimal_point", "I", None) in codes(f)
    off = [{**r, "U": r["U"] + 12.0} for r in SIM]
    assert "constant_offset" in [x["code"] for x in explain(pairs_of(SIM, off, UNITS))]
    sim2 = [{"A1": 1.0 + i, "A2": 5.0 + 3 * i} for i in range(3)]
    meas2 = [dict(r) for r in sim2]
    meas2[1] = {"A1": sim2[1]["A2"], "A2": sim2[1]["A1"]}
    f2 = explain(pairs_of(sim2, meas2, {"A1": "A", "A2": "A"}))
    assert ("swapped_columns", "A1,A2", None) in codes(f2)


def test_clean_table_has_no_findings() -> None:
    meas = [{q: v * (1 + 0.01 * ((i % 3) - 1)) for q, v in r.items()} for i, r in enumerate(SIM)]
    assert explain(pairs_of(SIM, meas, UNITS)) == []


def test_real_reports_comparison_and_probe(client: TestClient) -> None:
    """2025 short circuits of experiment 3: one common factor; the probe ranks the 2025
    parameter set first. 2025 load table of experiment 4: fails with the default machine, the
    probe finds the Δ-connected 2025 fit."""
    pid = client.post("/api/projects", json={"name": "d", "experiment_id": "synchronous"}).json()[
        "id"
    ]
    sets = client.post(
        f"/api/projects/{pid}/datasets/synchronous_2025/import",
        json={"study_kind": "short_circuit"},
    ).json()["sets"]
    sid = sets[0]["id"]
    run = client.post(f"/api/measurement-sets/{sid}/simulate").json()
    cmp_ = client.get(f"/api/comparison?run_id={run['id']}&set_id={sid}").json()
    assert "common_factor" in [x["code"] for x in cmp_["diagnosis"]]
    probe = client.post(f"/api/measurement-sets/{sid}/probe").json()["candidates"]
    assert probe[0]["id"] == "report_2025" and probe[0]["median_abs_rel_error"] < 0.05

    pid = client.post("/api/projects", json={"name": "w", "experiment_id": "wound_rotor"}).json()[
        "id"
    ]
    sid = client.post(
        f"/api/projects/{pid}/datasets/wound_rotor_2025/import", json={"study_kind": "load"}
    ).json()["sets"][0]["id"]
    run = client.post(f"/api/measurement-sets/{sid}/simulate").json()
    assert run["status"] == "constraint_violation"
    probe = client.post(f"/api/measurement-sets/{sid}/probe").json()["candidates"]
    assert probe[0]["id"] == "report_2025" and probe[0]["median_abs_rel_error"] < 0.05
    assert {c["id"]: c["status"] for c in probe}["project"] == "constraint_violation"
