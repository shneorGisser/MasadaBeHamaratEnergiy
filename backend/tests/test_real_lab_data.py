"""Validation against REAL lab data transcribed from a previous year's student report
(same course and lab transformer). The source is unverified; this file documents what the
model reproduces and which entries in the report are physically inconsistent.

Fit vs. validation: the series branch was fitted to the short-circuit table and the magnetizing
branch to the light capacitive-load rows (see spec.fitted_from_2025_report). The resistive-load
table below was NOT used for fitting, so it is an independent check of the model.
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from vel.experiments.transformer3ph import derive
from vel.experiments.transformer3ph.spec import fitted_from_2025_report
from vel.experiments.transformer3ph.studies import STUDIES, execute

S3 = math.sqrt(3)
SPEC = fitted_from_2025_report()

# Table 1.6, resistive load, U1ph = 220 V:
# (I1 [A], P1 [W] one phase, I2 [A], U2ph [V], cos φ, P2 [W])
R_LOAD = [
    (0.70, 150, 1.30, 95.8, 0.98, 138),
    (0.60, 130, 1.18, 103, 0.98, 121),
    (0.54, 120, 1.07, 104, 0.99, 111),
    (0.47, 102, 0.91, 105, 0.99, 96),
    (0.33, 72, 0.63, 107, 0.99, 68),
]
# Table 1.5 short circuit: (U_k as written, I1k, I2k, P one phase, cos φ)
SC = [
    (5.3, 0.090, 0.180, 0.2, 0.43),
    (10, 0.171, 0.34, 0.7, 0.43),
    (15.4, 0.26, 0.52, 1.74, 0.44),
    (20, 0.34, 0.68, 3.0, 0.44),
    (21, 0.35, 0.70, 3.3, 0.44),
]


def test_fitted_spec_reproduces_its_own_fit_point() -> None:
    """Sanity of the fit (not a validation): short-circuit at the report's rated row."""
    sd = STUDIES["short_circuit"]
    o = execute(
        "short_circuit",
        SPEC,
        sd.default_circuit(SPEC, "").model_dump(),  # type: ignore[union-attr]
        {"I_targets_pu": [1.0]},
    )
    assert o.status == "success", o.error
    assert o.result is not None
    row = o.result["tables"][0]["rows"][0]
    assert row["U_k"] / S3 == pytest.approx(21.0, rel=0.02)  # phase voltage, as in the report
    assert row["P_W"] == pytest.approx(3.3, rel=0.02)
    assert row["I2k"] == pytest.approx(0.70, rel=0.01)


def test_independent_validation_resistive_load() -> None:
    """Predict U2ph and I1 at the report's measured load currents and compare."""
    sd = STUDIES["load"]
    targets = [i2 / SPEC.I2n_line for (_, _, i2, _, _, _) in R_LOAD]
    o = execute(
        "load",
        SPEC,
        sd.default_circuit(SPEC, "").model_dump(),  # type: ignore[union-attr]
        {"load_kind": "R", "I2_targets_pu": targets, "include_no_load": False},
    )
    assert o.status in ("success", "success_with_warnings"), o.error
    assert o.result is not None
    rows = o.result["tables"][0]["rows"]
    errs_u2, errs_i1 = [], []
    for (i1_m, _p1, _i2, u2_m, _pf, _p2), r in zip(R_LOAD, rows, strict=True):
        errs_u2.append((u2_m - r["U2ph"]) / r["U2ph"])
        errs_i1.append((i1_m - r["I1"]) / r["I1"])
    # Observed (documented in docs/lab-data-2025.md): U2ph within ~5 %, I1 within ~6 %.
    assert max(abs(e) for e in errs_u2) < 0.06, errs_u2
    assert max(abs(e) for e in errs_i1) < 0.08, errs_i1
    # Trend: measured voltage drops with load like the model (regulation sign and order)
    assert R_LOAD[0][3] < R_LOAD[-1][3]
    assert rows[0]["U2ph"] < rows[-1]["U2ph"]


def test_report_inconsistencies_are_detected() -> None:
    """P2 = 138 W at U2ph·I2 = 95.8·1.3 = 124.5 VA is physically impossible (|P| ≤ S)."""
    rows = [
        {"U1L": 220 * S3, "I1": i1, "P1_W": p1, "U2ph": u2, "I2": i2, "P2_W": p2, "pf1": pf}
        for (i1, p1, i2, u2, pf, p2) in R_LOAD
    ]
    w = derive.plausibility("load", rows, SPEC)
    bad = {(x["row"], x["column"]) for x in w if x["code"] == "power_exceeds_apparent"}
    assert bad == {(0, "P2_W")}  # row 2: 121 W vs 121.5 VA — at the limit, not flagged


def test_short_circuit_line_vs_phase_is_flagged() -> None:
    """If the report's U_k is entered as a LINE voltage (what our table expects), cos φ = 0.44
    contradicts P/(U·I) — the check points the student to the line/phase ambiguity."""
    rows = [{"U_k": u, "I1k": i1, "I2k": i2, "P_W": p, "pf": pf} for (u, i1, i2, p, pf) in SC]
    w = derive.plausibility("short_circuit", rows, SPEC)
    assert any(x["code"] == "pf_inconsistent" for x in w)
    rows_phase = [{**r, "U_k": r["U_k"] * S3} for r in rows]
    w2 = derive.plausibility("short_circuit", rows_phase, SPEC)
    assert not any(x["code"] in ("pf_inconsistent", "power_exceeds_apparent") for x in w2)
    assert not any(x["code"] == "current_ratio" for x in w2)


def test_presets_endpoint(client: TestClient) -> None:
    presets = {p["id"]: p for p in client.get("/api/experiments/transformer3ph/presets").json()}
    assert presets["report_2025"]["spec"]["provenance"] == "fitted"
    assert presets["report_2025"]["spec"]["nameplate"]["S_n"] == pytest.approx(231)
