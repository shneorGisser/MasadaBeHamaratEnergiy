"""Experiment 4 — wound-rotor induction machine.

W1  rings shorted: the explicit rotor (ideal transformer k, R2, X2) equals the referred
    T-circuit with R2' = k²R2, X2' = k²X2 (≤ 1e-9).
W2  external rotor resistance: closed form with k²(R2 + R_ext); the rotor ammeter reads the
    actual rotor current k·I2'; a voltmeter across the starter reads the slip-frequency value.
W3  energy balance, including the split of s·P_ag between rotor winding and starter.
W4  open rotor: U2 = |E1|/k at standstill, ∝ |s| and f2 = |s|·f when turned by hand.
W5  induction regulator: closed form U2 = √3·|V + k·e^{j(p/2)α}·V_s|.
W6  above synchronism the machine generates (P1 < 0, driving torque) and still draws Q.
W7  a turning rotor connected to the supply side is rejected (two frequencies).
W8  the nameplate fit reproduces the stator nameplate and the 107 V open-rotor voltage.
W9  API journey.
"""

from __future__ import annotations

import cmath
import math

import pytest
from fastapi.testclient import TestClient

from vel.engine.netlist import CircuitValidationError
from vel.engine.simulate import operating_point, operating_point_at_slip
from vel.experiments.common import with_param
from vel.experiments.wound_rotor import templates
from vel.experiments.wound_rotor.spec import WoundSpec, nameplate_fit
from vel.experiments.wound_rotor.studies import execute

S3 = math.sqrt(3)
TIGHT = 1e-9


def rel(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-30)


def t_circuit(spec: WoundSpec, u_line: float, s: float, r_ext: float = 0.0) -> dict[str, complex]:
    e = spec.ecm
    v = u_line / S3
    zm = 1 / (1 / e.R_fe + 1 / complex(0, e.Xm))
    z2 = complex(e.k**2 * (e.R2 + r_ext) / s, e.k**2 * e.X2)
    zp = zm * z2 / (zm + z2)
    i1 = v / (complex(e.R1, e.X1) + zp)
    e1 = i1 * zp
    i2p = e1 / z2
    return {"I1": i1, "E1": e1, "I2p": i2p, "V": complex(v)}


@pytest.mark.parametrize("s", [0.01, 0.0933, 0.5, 1.0])
def test_W1_explicit_rotor_equals_referred_t_circuit(s: float) -> None:
    spec = nameplate_fit()
    op = operating_point_at_slip(templates.motor(400, 50, "Y"), spec, s)
    ref = t_circuit(spec, 400, s)
    assert rel(op.readings["A"]["I"] or 0, abs(ref["I1"])) < TIGHT
    assert rel(op.internals["M.U"]["I2"], spec.ecm.k * abs(ref["I2p"])) < TIGHT
    p1 = 3 * (ref["V"] * ref["I1"].conjugate()).real
    assert rel(3 * (op.readings["W"]["P"] or 0), p1) < TIGHT


def test_W2_external_resistance_and_rotor_instruments() -> None:
    spec = nameplate_fit()
    r_ext, s = 4.0, 0.2
    c = templates.motor(400, 50, "Y", r_ext=r_ext)
    # instruments in the rotor circuit: ammeter in ring R1, voltmeter across the starter R1–R2
    c = c.model_copy(deep=True)
    c.wires = [w for w in c.wires if not (w.a.component == "M" and w.a.terminal == "R1")]
    from vel.engine.circuit import CircuitModel

    doc = c.model_dump()
    doc["components"] += [
        {"id": "A2", "type": "ammeter", "label": "", "params": {}},
        {"id": "V2", "type": "voltmeter", "label": "", "params": {}},
    ]
    doc["wires"] += [
        {
            "id": "x1",
            "a": {"component": "M", "terminal": "R1"},
            "b": {"component": "A2", "terminal": "p"},
        },
        {
            "id": "x2",
            "a": {"component": "A2", "terminal": "n"},
            "b": {"component": "Rst", "terminal": "1"},
        },
        {
            "id": "x3",
            "a": {"component": "V2", "terminal": "p"},
            "b": {"component": "Rst", "terminal": "1"},
        },
        {
            "id": "x4",
            "a": {"component": "V2", "terminal": "n"},
            "b": {"component": "Rst", "terminal": "2"},
        },
    ]
    c2 = CircuitModel.model_validate(doc)
    op = operating_point_at_slip(c2, spec, s)
    ref = t_circuit(spec, 400, s, r_ext)
    i2 = spec.ecm.k * abs(ref["I2p"])
    assert rel(op.readings["A"]["I"] or 0, abs(ref["I1"])) < TIGHT
    assert rel(op.readings["A2"]["I"] or 0, i2) < TIGHT
    assert rel(op.readings["V2"]["U"] or 0, S3 * i2 * r_ext) < TIGHT
    assert op.readings["V2"]["f"] == pytest.approx(s * 50)


@pytest.mark.parametrize("r_ext", [0.0, 2.0, 6.0])
def test_W3_energy_balance_with_starter(r_ext: float) -> None:
    spec = nameplate_fit()
    c = templates.motor(400, 50, "Y", r_ext=r_ext if r_ext else None)
    op = operating_point(with_param(c, "M", "M_load", 0.8 * spec.M_n), spec)
    tot, mech = op.internals["M.total"], op.internals["M.mech"]
    p_in = op.internals["_sources"]["P_delivered"]
    assert rel(tot["P_cu1"] + tot["P_fe"] + tot["P_ag"], p_in) < 1e-9
    s = mech["s"]
    assert rel(tot["P_cu2_winding"] + tot["P_rotor_external"], s * tot["P_ag"]) < 1e-9
    i2 = op.internals["M.U"]["I2"]
    assert tot["P_rotor_external"] == pytest.approx(3 * i2 * i2 * r_ext, abs=1e-9)
    assert (op.readings["M"]["M"] or 0) == pytest.approx(0.8 * spec.M_n)


def test_W3_more_rotor_resistance_lowers_speed_at_same_torque() -> None:
    spec = nameplate_fit()
    speeds = []
    for r in (None, 1.0, 3.0, 6.0):
        op = operating_point(
            with_param(templates.motor(400, 50, "Y", r_ext=r), "M", "M_load", spec.M_n), spec
        )
        speeds.append(op.readings["M"]["n"] or 0)
    assert speeds == sorted(speeds, reverse=True)


def test_W4_open_rotor_ratio_and_hand_turning() -> None:
    spec = nameplate_fit()
    e = spec.ecm
    zm = 1 / (1 / e.R_fe + 1 / complex(0, e.Xm))
    e1 = (400 / S3) * zm / (complex(e.R1, e.X1) + zm)
    c = templates.rotor_open(400, 50, "Y")
    u2 = {}
    for n in (0.0, 30.0, -30.0):
        op = operating_point(with_param(c, "M", "n_set", n), spec)
        u2[n] = op.readings["V2"]["U"] or 0
        s = 1 - n / 1500
        assert rel(u2[n], abs(s) * S3 * abs(e1) / e.k) < TIGHT
        assert op.readings["V2"]["f"] == pytest.approx(abs(s) * 50)
    assert u2[30.0] < u2[0.0] < u2[-30.0]


@pytest.mark.parametrize("alpha", [0.0, 30.0, 90.0, 200.0])
def test_W5_regulator_closed_form(alpha: float) -> None:
    spec = nameplate_fit()
    e = spec.ecm
    v = 100 / S3
    zm = 1 / (1 / e.R_fe + 1 / complex(0, e.Xm))
    z_rot = complex(e.R2, e.X2) + zm / e.k**2
    i_r = v / z_rot
    v_s = v - i_r * complex(e.R2, e.X2)
    e1 = e.k * cmath.exp(1j * math.radians(2 * alpha)) * v_s
    op = operating_point(with_param(templates.regulator(100, 50), "M", "angle", alpha), spec)
    assert rel(op.readings["V2"]["U"] or 0, S3 * abs(v + e1)) < TIGHT
    assert op.readings["V1"]["U"] == pytest.approx(100.0)


def test_W6_generator_above_synchronism() -> None:
    spec = nameplate_fit()
    r = execute(
        "generator",
        spec,
        templates.motor(400, 50, "Y").model_dump(),
        {"n_values": [1450.0, 1550.0]},
    )
    rows = r.result["tables"][0]["rows"]  # type: ignore[index]
    assert rows[0]["P1"] > 0 and rows[0]["mode"] == "מנוע"
    assert rows[1]["P1"] < 0 and rows[1]["mode"] == "מחולל"
    assert rows[1]["M"] < 0  # the prime mover must drive the shaft
    assert rows[1]["Q1"] > 0  # still magnetized from the grid


def test_W7_turning_rotor_on_the_supply_is_rejected() -> None:
    spec = nameplate_fit()
    c = with_param(templates.regulator(100, 50), "M", "locked", False)
    with pytest.raises(CircuitValidationError) as e:
        operating_point_at_slip(c, spec, 0.5)
    assert e.value.issues[0]["code"] == "rotor_circuit_not_isolated"


def test_W8_nameplate_fit_reproduces_the_plate() -> None:
    spec = nameplate_fit()
    op = operating_point(with_param(templates.motor(400, 50, "Y"), "M", "M_load", spec.M_n), spec)
    assert op.readings["M"]["n"] == pytest.approx(1360, abs=0.5)
    assert op.readings["A"]["I"] == pytest.approx(0.83, rel=1e-3)
    assert op.readings["W"]["pf"] == pytest.approx(0.70, rel=1e-3)
    op = operating_point(templates.rotor_open(400, 50, "Y"), spec)
    assert op.readings["V2"]["U"] == pytest.approx(107, rel=1e-3)


def test_dc_resistance_reads_stator_and_ring_to_ring() -> None:
    spec = nameplate_fit()
    circuits = {w: templates.dc_winding(w).model_dump() for w, _ in templates.WINDINGS}
    r = execute("dc_resistance", spec, circuits, {"I_targets": [0.3]})
    summ = {x["winding"]: x["R_avg"] for x in r.result["tables"][1]["rows"]}  # type: ignore[index]
    assert summ["סטטור U1–U2"] == pytest.approx(spec.ecm.R1)
    assert summ["רוטור R1–R2"] == pytest.approx(2 * spec.ecm.R2)
    p = {x["key"]: x["value"] for x in r.result["parameters"]}  # type: ignore[index]
    assert p["R2_phase"] == pytest.approx(spec.ecm.R2)


def test_W9_api_journey(client: TestClient) -> None:
    p = client.post("/api/projects", json={"name": "רוטור מלופף", "experiment_id": "wound_rotor"})
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    studies = client.get(f"/api/projects/{pid}/studies").json()
    for st in studies:
        r = client.post(
            f"/api/projects/{pid}/runs", json={"study_kind": st["kind"], "case": st["default_case"]}
        ).json()
        assert r["status"] in ("success", "success_with_warnings"), (st["kind"], r["error"])
    live = client.post(
        f"/api/projects/{pid}/circuits/regulator/operating-point",
        json={"overrides": {"M": {"angle": 90.0}}},
    ).json()
    assert live["status"] == "success"
    run = client.post(
        f"/api/projects/{pid}/runs",
        json={"study_kind": "load_rext", "case": {"M_targets": [0.5, 1.0, 1.5], "R_ext": 3.0}},
    ).json()
    rows = run["result"]["tables"][0]["rows"]
    s = client.post(
        f"/api/projects/{pid}/measurement-sets",
        json={"study_kind": "load_rext", "label": "4.7", "n_rows": 3, "conditions": {"R_ext": "3"}},
    ).json()
    sid = s["set"]["id"]
    for i, row in enumerate(rows):
        for q, unit in (
            ("U1L", "V"),
            ("I1", "A"),
            ("P_W", "W"),
            ("pf", ""),
            ("n", "rpm"),
            ("M", "N·m"),
        ):
            assert (
                client.post(
                    f"/api/measurement-sets/{sid}/entries",
                    json={"row_index": i, "quantity": q, "value": row[q], "unit": unit},
                ).status_code
                == 201
            )
    sim = client.post(f"/api/measurement-sets/{sid}/simulate").json()
    assert sim["input_snapshot"]["case"]["R_ext"] == 3.0
    cmp_ = client.get(f"/api/comparison?run_id={sim['id']}&set_id={sid}").json()
    assert cmp_["summary"]["max_abs_rel_error"] == pytest.approx(0, abs=1e-9)
