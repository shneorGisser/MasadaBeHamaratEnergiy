"""Experiment 3 — synchronous machine: reference checks for the model, studies and API.

G1  OCC fit reproduces the student's measured open-circuit table (ascending branch).
G2  unsaturated faults equal the sequence-network closed forms
    Ik3 = E/|Z1|, Ik2 = √3·E/|Z1+Z2|, Ik1 = 3E/|Z1+Z2+Z0| (≤ 1e-9).
G3  extraction round trip: Xs, X2, X0 from simulated short circuits equal the spec (linear).
G4  resistive load, linear machine: V = E·R/(R + Ra + jXs) per phase (≤ 1e-9).
G5  energy balance (island and grid): mechanical in = electrical out + copper + friction.
G6  saturation: the solved air-gap EMF lies on the OCC of the resultant MMF.
G7  speed: EMF and frequency proportional to n.
G8  remanence: reversed field first cancels the residual voltage.
G9  V-curves: minimum armature current at unity power factor; out of step is explicit.
G10 Potier extraction from a simulated zero-power-factor characteristic recovers X_l and k_a.
G11 the student's real tables: inconsistent short-circuit points and a reversed descending
    OCC column are flagged automatically.
G12 API journey.
"""

from __future__ import annotations

import cmath
import math
from typing import Any

import pytest
from fastapi.testclient import TestClient

from vel.engine.simulate import MechanicalError, operating_point
from vel.experiments.synchronous import derive, templates
from vel.experiments.synchronous.spec import SyncSpec, fitted_lab_machine
from vel.experiments.synchronous.studies import execute

S3 = math.sqrt(3)
TIGHT = 1e-9


def linear_spec() -> SyncSpec:
    s = fitted_lab_machine().model_copy(deep=True)
    s.occ.I_s = 1e6  # no saturation inside the operating range
    s.occ.m = 2
    s.ecm.P_fw = 0.0
    return s


def rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-30)


# --------------------------------------------------------------------------- G1


IF_MEAS = [0, 0.25, 0.5, 0.7, 0.97, 1.22, 1.47, 1.73, 1.96, 2.25, 2.5]
EF_UP = [5.4, 72.6, 138, 184, 237, 280, 308, 332, 348, 362, 371.5]


def test_G1_occ_reproduces_measured_table() -> None:
    spec = fitted_lab_machine()
    r = execute(
        "open_circuit",
        spec,
        templates.generator(1, 1500, "Y", closed=False).model_dump(),
        {"If_values": IF_MEAS},
    )
    assert r.status == "success_with_warnings", r.error  # hysteresis warning only
    sim = [row["Ef"] for row in r.result["tables"][0]["rows"]]  # type: ignore[index]
    errs = [abs(a - b) for a, b in zip(sim, EF_UP, strict=True)]
    assert max(errs) < 2.0  # V, line; the fit's rms is 0.45 V per winding
    assert sum(e * e for e in errs) / len(errs) < 1.0


# --------------------------------------------------------------------------- G2, G3


def closed_form_faults(spec: SyncSpec, i_f: float) -> dict[str, float]:
    e = spec.occ.a * (i_f + spec.occ.F_res)
    ra, xs = spec.ecm.Ra, spec.Xs_unsat
    z1 = complex(ra, xs)
    z2 = complex(ra, spec.ecm.X2)
    z0 = complex(ra, spec.ecm.X0)
    return {"Ik3": e / abs(z1), "Ik2": S3 * e / abs(z1 + z2), "Ik1": 3 * e / abs(z1 + z2 + z0)}


@pytest.mark.parametrize("i_f", [0.3, 1.0, 2.0])
def test_G2_faults_match_sequence_networks(i_f: float) -> None:
    spec = linear_spec()
    ref = closed_form_faults(spec, i_f)
    for fault in ("3", "2", "1"):
        c = templates.short_circuit(fault, i_f, 1500, "Y")
        op = operating_point(c, spec)
        assert rel(op.readings["A"]["I"] or 0, ref[f"Ik{fault}"]) < TIGHT, fault


def test_G3_extraction_round_trip() -> None:
    spec = linear_spec()
    circuits = {f: templates.short_circuit(f, 0, 1500, "Y").model_dump() for f in "321"}
    r = execute("short_circuit", spec, circuits, {"If_values": [0.4, 0.8, 1.2]})
    assert r.status == "success", r.error
    p = {x["key"]: x["value"] for x in r.result["parameters"]}  # type: ignore[index]
    assert rel(p["Xs"], spec.Xs_unsat) < 1e-9
    assert rel(p["X2"], spec.ecm.X2) < 1e-9
    assert rel(p["X0"], spec.ecm.X0) < 1e-9


# --------------------------------------------------------------------------- G4, G5, G6


def test_G4_resistive_load_closed_form() -> None:
    spec = linear_spec()
    r_load, i_f = 900.0, 1.0
    c = templates.generator(i_f, 1500, "Y", load_kind="R", load_value=r_load)
    op = operating_point(c, spec)
    e = spec.occ.a * (i_f + spec.occ.F_res)
    v = e * r_load / abs(complex(r_load + spec.ecm.Ra, spec.Xs_unsat))
    assert rel(op.readings["V1"]["U"] or 0, S3 * v) < TIGHT
    assert rel(op.readings["A"]["I"] or 0, v / r_load) < TIGHT
    assert rel(3 * (op.readings["W"]["P"] or 0), 3 * v * v / r_load) < TIGHT


@pytest.mark.parametrize("kind,value", [("R", 600.0), ("L", 1.5), ("C", 4e-6)])
def test_G5_G6_island_energy_balance_and_saturation(kind: str, value: float) -> None:
    spec = fitted_lab_machine()
    op = operating_point(
        templates.generator(2.0, 1500, "Y", load_kind=kind, load_value=value), spec
    )
    mech, elec = op.internals["G.mech"], op.internals["G.elec"]
    p_load = 3 * (op.readings["W"]["P"] or 0)
    assert rel(mech["P_mech_in"], p_load + elec["P_cu"] + mech["P_fw"]) < 1e-9
    # the air-gap EMF is on the OCC of the resultant MMF
    assert rel(mech["E_r"], spec.occ.emf(mech["F_r"])) < 1e-9


def test_G5_grid_energy_balance() -> None:
    spec = fitted_lab_machine()
    c = templates.motor_on_grid(400, 50, "Y", 3.0, 120.0)
    op = operating_point(c, spec)
    mech, elec = op.internals["G.mech"], op.internals["G.elec"]
    p_grid = op.internals["_sources"]["P_delivered"]
    assert rel(p_grid, 120.0 + mech["P_fw"] + elec["P_cu"]) < 1e-9
    assert rel(mech["P_shaft_out"], 120.0) < 1e-9
    assert (op.readings["G"]["delta_deg"] or 0) < 0  # motor: EMF lags the terminal voltage


# --------------------------------------------------------------------------- G7, G8


def test_G7_speed_scales_emf_and_frequency() -> None:
    spec = fitted_lab_machine()
    full = operating_point(templates.generator(1.0, 1500, "Y", closed=False), spec)
    half = operating_point(templates.generator(1.0, 750, "Y", closed=False), spec)
    assert half.readings["G"]["f"] == pytest.approx(25.0)
    assert rel(half.readings["V1"]["U"] or 0, 0.5 * (full.readings["V1"]["U"] or 0)) < 1e-12


def test_G8_reversed_field_cancels_remanence() -> None:
    spec = fitted_lab_machine()
    u = {}
    for i_f in (0.0, -spec.occ.F_res, -0.01, 0.01):
        op = operating_point(templates.generator(i_f, 1500, "Y", closed=False), spec)
        u[i_f] = op.readings["V1"]["U"] or 0.0
    assert u[-spec.occ.F_res] < 1e-9
    assert u[-0.01] < u[0.0] < u[0.01]


# --------------------------------------------------------------------------- G9, G10


def test_G9_v_curve_minimum_at_unity_pf_and_out_of_step() -> None:
    spec = fitted_lab_machine()
    pts = [{"P": 100.0, "If": i / 4} for i in range(8, 28)]
    r = execute(
        "v_curves", spec, templates.motor_on_grid(400, 50, "Y", 2, 0).model_dump(), {"points": pts}
    )
    rows = [x for x in r.result["tables"][0]["rows"] if x["state"] == "סינכרוני"]  # type: ignore[index]
    best = min(rows, key=lambda x: x["Ia"])
    assert best["pf"] > 0.97
    chars = [x["char"] for x in rows]
    assert chars[0] == "השראי" and chars[-1] == "קיבולי"  # under- → over-excited
    with pytest.raises(MechanicalError) as e:
        operating_point(templates.motor_on_grid(400, 50, "Y", 0.3, 300.0), spec)
    assert e.value.status == "constraint_violation"


def test_G10_potier_from_simulated_zpf() -> None:
    spec = fitted_lab_machine()
    r = execute(
        "zpf",
        spec,
        templates.generator(1, 1500, "Y", load_kind="L").model_dump(),
        {"I_const": 0.4, "If_values": [4.0, 3.5, 3.0, 2.5, 2.0]},
    )
    assert r.status == "success", r.error
    p = {x["key"]: x["value"] for x in r.result["parameters"]}  # type: ignore[index]
    # Ra is neglected by the Potier construction → a few-percent bias is expected, not more
    assert rel(p["Xl_potier"], spec.ecm.Xl) < 0.05
    assert rel(p["k_a"], spec.ecm.k_a) < 0.02


# --------------------------------------------------------------------------- G11


def test_G11_real_short_circuit_table_flags_inconsistent_points() -> None:
    spec = fitted_lab_machine()
    rows: list[dict[str, Any]] = [
        {"If": i, "Ik3": a, "Ik2": b, "Ik1": c}
        for i, a, b, c in [
            (0, 3.8e-3, 5.7e-3, 10e-3),
            (0.4, 0.1, 0.136, 0.2),
            (0.6, 0.14, 0.2, 0.3),
            (0.8, 0.19, 0.27, 0.4),
            (1.0, 0.4, 0.335, 0.495),
            (1.3, 0.58, 0.44, 0.65),
        ]
    ]
    _, params, warnings = derive.short_circuit(rows, spec)
    flagged = {(w["row"], w["column"]) for w in warnings if w["code"] == "sc_nonlinear"}
    assert flagged == {(4, "Ik3"), (5, "Ik3")}
    p = {x.key: x.value for x in params}
    assert p["Xs"] == pytest.approx(674, rel=0.02)
    assert p["X2"] == pytest.approx(151, rel=0.05)


def test_G11_reversed_descending_column_is_flagged() -> None:
    spec = fitted_lab_machine()
    down_as_written = [5.4, 360, 347, 330, 308, 277, 235, 194, 140, 74, 371.5]
    rows = [
        {"If": i, "Ef_up": u, "Ef_down": d}
        for i, u, d in zip(IF_MEAS, EF_UP, down_as_written, strict=True)
    ]
    codes = {w["code"] for w in derive.plausibility("open_circuit", rows, spec)}
    assert "occ_down_reversed" in codes
    assert "occ_not_monotonic" not in codes  # the ascending branch is fine


# --------------------------------------------------------------------------- G12


def test_G12_api_journey(client: TestClient) -> None:
    p = client.post("/api/projects", json={"name": "סינכרונית", "experiment_id": "synchronous"})
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    assert p.json()["spec"]["provenance"] == "fitted"
    studies = client.get(f"/api/projects/{pid}/studies").json()
    assert [s["kind"] for s in studies] == [
        "insulation",
        "dc_resistance",
        "open_circuit",
        "short_circuit",
        "load_characteristic",
        "regulation",
        "zpf",
        "v_curves",
        "sudden_sc",
    ]
    for st in studies:
        r = client.post(
            f"/api/projects/{pid}/runs", json={"study_kind": st["kind"], "case": st["default_case"]}
        ).json()
        assert r["status"] in ("success", "success_with_warnings"), (st["kind"], r["error"])

    # the student's open-circuit table, entered as measured, compared at the same If
    s = client.post(
        f"/api/projects/{pid}/measurement-sets",
        json={"study_kind": "open_circuit", "label": "טבלה 6.3", "n_rows": 11},
    ).json()
    sid = s["set"]["id"]
    for i, (i_f, e) in enumerate(zip(IF_MEAS, EF_UP, strict=True)):
        for q, v, unit in (("If", i_f, "A"), ("Ef_up", e, "V")):
            assert (
                client.post(
                    f"/api/measurement-sets/{sid}/entries",
                    json={"row_index": i, "quantity": q, "value": v, "unit": unit},
                ).status_code
                == 201
            )
    run = client.post(f"/api/measurement-sets/{sid}/simulate").json()
    cmp_ = client.get(f"/api/comparison?run_id={run['id']}&set_id={sid}").json()
    assert cmp_["summary"]["unmatched_rows"] == 0
    errs = [
        c["rel_error"] for pr in cmp_["pairs"][1:] for c in pr["cells"] if c["quantity"] == "Ef_up"
    ]
    assert max(abs(e) for e in errs) < 0.012  # ≤ 1.2 % above If = 0

    live = client.post(
        f"/api/projects/{pid}/circuits/open_circuit/operating-point",
        json={"overrides": {"G": {"I_f": 0.97}}},
    ).json()
    assert live["readings"]["V1"]["U"] == pytest.approx(238.46, abs=0.05)
    rep = client.post(
        f"/api/projects/{pid}/reports",
        json={
            "title": "ניסוי 3",
            "sections": [{"study_kind": "open_circuit", "run_id": run["id"], "set_id": sid}],
        },
    )
    assert rep.status_code == 201, rep.text
    html = client.get(f"/api/reports/{rep.json()['id']}/html").text
    assert "המכונה והנחות המודל" in html


def test_island_with_open_load_and_phase_reading() -> None:
    spec = fitted_lab_machine()
    op = operating_point(templates.generator(1.0, 1500, "Y", closed=False), spec)
    assert op.readings["A"]["I"] == pytest.approx(0, abs=1e-12)
    assert cmath.isfinite(complex(op.readings["V1"]["U"] or 0))


def test_line_neutral_fault_requires_star() -> None:
    with pytest.raises(ValueError):
        templates.short_circuit("1", 1.0, 1500, "D")


def test_live_override_of_field(client: TestClient) -> None:
    pid = client.post("/api/projects", json={"name": "x", "experiment_id": "synchronous"}).json()[
        "id"
    ]
    r = client.post(
        f"/api/projects/{pid}/circuits/v_curves/operating-point",
        json={"overrides": {"G": {"I_f": 0.2, "P_shaft": 250.0}}},
    ).json()
    assert r["status"] == "constraint_violation"
    assert "סנכרון" in r["error"]["message"]


# --------------------------------------------------------------------------- G13: 2025 report

IF_2025 = [0.17, 0.24, 0.35, 0.43, 0.5, 0.64, 0.7, 0.82, 0.91]
EF_2025 = [49.5, 65, 94, 119, 136, 165, 187, 204, 226]


def test_G13_2025_occ_is_an_independent_check_of_the_2026_fit() -> None:
    """Not fitted to these points: the 2025 report's OCC (same machine) against the 2026 fit."""
    r = execute(
        "open_circuit",
        fitted_lab_machine(),
        templates.generator(1, 1500, "Y", closed=False).model_dump(),
        {"If_values": IF_2025},
    )
    sim = [row["Ef"] for row in r.result["tables"][0]["rows"]]  # type: ignore[index]
    assert max(abs(a - b) for a, b in zip(sim, EF_2025, strict=True)) < 6.0  # V line


def test_G13_report_2025_preset_reproduces_its_short_circuits() -> None:
    from vel.experiments.synchronous.spec import report_2025_machine

    spec = report_2025_machine()
    circuits = {f: templates.short_circuit(f, 1.0, 1500, "Y").model_dump() for f in "321"}
    r = execute("short_circuit", spec, circuits, {"If_values": [0.6, 1.0, 1.6]})
    rows = r.result["tables"][0]["rows"]  # type: ignore[index]
    assert [x["Ik3"] for x in rows] == pytest.approx([0.25, 0.44, 0.71], abs=0.03)
