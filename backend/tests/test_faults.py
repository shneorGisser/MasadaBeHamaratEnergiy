"""Fault challenge: each fault is a real change of the circuit, solved by the same solver, and
its textbook symptom shows in the readings."""

from __future__ import annotations

import math
from typing import Any

import pytest
from fastapi.testclient import TestClient


def _project(client: TestClient, exp: str) -> str:
    return client.post("/api/projects", json={"name": "תקלה", "experiment_id": exp}).json()["id"]


def _quiz_for(client: TestClient, pid: str, kind: str, fault: str) -> dict[str, Any]:
    for seed in range(400):
        q = client.post(
            f"/api/projects/{pid}/circuits/{kind}/fault-quiz", json={"seed": seed}
        ).json()
        if q["answer"] == fault:
            return q
    raise AssertionError(f"no seed produced {fault}")


def test_F1_options_follow_the_circuit(client: TestClient) -> None:
    pid = _project(client, "induction_motor")
    q = client.post(f"/api/projects/{pid}/circuits/load/fault-quiz", json={"seed": 1}).json()
    ids = {o["id"] for o in q["options"]}
    assert {
        "wattmeter_reversed",
        "wattmeter_voltage_ll",
        "voltmeter_ln",
        "star_delta_swap",
        "none",
    } <= ids
    tid = _project(client, "transformer3ph")
    q = client.post(f"/api/projects/{tid}/circuits/no_load/fault-quiz", json={"seed": 1}).json()
    ids = {o["id"] for o in q["options"]}
    assert "star_delta_swap" not in ids  # no motor
    assert "voltmeter_ln" in ids
    # the same seed gives the same challenge
    q2 = client.post(f"/api/projects/{tid}/circuits/no_load/fault-quiz", json={"seed": 1}).json()
    assert q2["answer"] == q["answer"] and q2["observed"] == q["observed"]


def test_F2_symptoms(client: TestClient) -> None:
    pid = _project(client, "induction_motor")
    w = _quiz_for(client, pid, "load", "wattmeter_reversed")
    assert w["observed"]["W"]["P"] == pytest.approx(-w["expected"]["W"]["P"], rel=1e-9)
    v = _quiz_for(client, pid, "load", "voltmeter_ln")
    assert v["observed"]["V1"]["U"] == pytest.approx(
        v["expected"]["V1"]["U"] / math.sqrt(3), rel=1e-6
    )
    d = _quiz_for(client, pid, "load", "star_delta_swap")
    assert d["observed"]["A"]["I"] > 2.5 * d["expected"]["A"]["I"]  # the default motor is Y
    n = _quiz_for(client, pid, "load", "none")
    assert n["observed"] == n["expected"]


def test_F3_wattmeter_on_line_voltage(client: TestClient) -> None:
    """P_read = Re(U_12·I_1*) instead of Re(U_1N·I_1*): magnitude √3 larger, 30° shifted."""
    pid = _project(client, "induction_motor")
    q = _quiz_for(client, pid, "load", "wattmeter_voltage_ll")
    e, o = q["expected"]["W"], q["observed"]["W"]
    assert not math.isclose(o["P"], e["P"], rel_tol=0.05)
    assert (
        abs(o["P"])
        < math.sqrt(3) * q["expected"]["V1"]["U"] / math.sqrt(3) * q["expected"]["A"]["I"] * 1.01
    )
