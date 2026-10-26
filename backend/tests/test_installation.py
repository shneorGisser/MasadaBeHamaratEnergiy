"""Experiment 8: installation tests (fault loop, MCB, RCD, insulation, earth, continuity).

I1–I3 compare with the 2025 report. Z_L, Z_PE and τ were fitted to these very tables, so I2
and I3 are fit regressions; I1 is a genuine prediction (line voltages from the phase voltages).
I4–I8 are model-independent physics and standard criteria; I9–I10 the API.
"""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from vel.engine import installation as ph
from vel.experiments import registry
from vel.experiments.installation.module import plausibility
from vel.experiments.installation.spec import InstallSpec, assumed_nominal, lab_2025
from vel.experiments.installation.studies import MCB_2025

MOD = registry.get("installation")
SPEC = lab_2025()
T_2025 = [2.57, 8.1, 2.8, 3.8, 9.8, 2.2, 1.81, 2.02, 12.5]


def run(kind: str, spec: InstallSpec = SPEC, **case: object):  # type: ignore[no-untyped-def]
    doc = {**MOD.studies[kind].default_case(spec), **case}
    out = MOD.execute(kind, spec, None, doc)
    assert out.status in ("success", "success_with_warnings"), out.error
    return out


def with_(spec: InstallSpec, section: str, **kw: object) -> InstallSpec:
    return spec.model_copy(update={section: getattr(spec, section).model_copy(update=kw)})


# --------------------------------------------------------------------------- 2025 report


def test_I1_line_voltages_follow_from_the_phase_voltages() -> None:
    v = ph.voltages(SPEC)
    for pair, lab in (("L1-L2", 405), ("L2-L3", 407), ("L3-L1", 405)):
        assert v[pair] == pytest.approx(lab, abs=1.5)  # the readings' resolution is 1 V
    assert plausibility("grid_voltages", [{"U": x} for x in (234, 234, 235, 405, 407, 405)]) == []
    # a line voltage written as a phase voltage is caught
    bad = plausibility("grid_voltages", [{"U": x} for x in (234, 234, 235, 234, 407, 405)])
    assert [w["code"] for w in bad] == ["line_voltage_inconsistent"]


def test_I2_loops_reproduce_the_report_and_its_impossible_LN_zeros_are_flagged() -> None:
    for loop, lab in (("L1-PE", 0.16), ("L2-PE", 0.16), ("L3-PE", 0.15), ("L1-L2", 0.12)):
        assert ph.loop_impedance(SPEC, loop) == pytest.approx(lab, abs=0.0101)
    rows = [{"Z": z} for z in (0, 0, 0, 0.16, 0.16, 0.15, 0.12)]
    w = plausibility("fault_loop", rows)
    assert [x["row"] for x in w] == [0, 1, 2] and {x["code"] for x in w} == {"loop_below_phase"}


def test_I3_mcb_thermal_fit_and_curve_class() -> None:
    sim = [ph.mcb_trip(SPEC.mcb, a, b)[0] for a, b in MCB_2025]
    logs = [math.log(t / s) for t, s in zip(T_2025, sim, strict=True)]  # type: ignore[arg-type]
    assert abs(sum(logs) / len(logs)) < 0.05  # τ is the geometric-mean fit
    rms = math.sqrt(sum(x * x for x in logs) / len(logs))
    assert rms < 0.3  # ≈ 24 % scatter: one τ for every rating, no thermal memory
    # type B is ruled out: it must trip magnetically (< 0.1 s) at 5·In, the 3 A unit took 2.8 s at
    # 6.1·In and the 6 A unit 2.2 s at 7.5·In — both below the C limit of 10·In
    assert all(b / a < 10 for a, b in MCB_2025) and any(b / a > 5 for a, b in MCB_2025)


# --------------------------------------------------------------------------- physics


def test_I4_mcb_meets_iec_60898_points() -> None:
    m = SPEC.mcb
    assert ph.mcb_trip(m, 16, 1.13 * 16) == (None, "none")
    t, mode = ph.mcb_trip(m, 16, 1.45 * 16)
    assert mode == "thermal" and t is not None and t < 3600
    t, _ = ph.mcb_trip(m, 16, 2.55 * 16)
    assert t is not None and 1 < t < 60
    assert ph.mcb_trip(m, 16, 10 * 16) == (m.t_mag, "magnetic")
    # a warm breaker trips sooner, and the inverse function is consistent
    assert ph.mcb_trip(m, 1, 3, theta0=2.0)[0] < ph.mcb_trip(m, 1, 3)[0]  # type: ignore[operator]
    k5 = ph.mcb_current_for_time(m, 5.0)
    assert ph.mcb_trip(m, 1, k5)[0] == pytest.approx(5.0)


def test_I5_rcd_sees_only_the_residual_current() -> None:
    out = run("rcd")
    rows = {r["mult"]: r for r in out.result["tables"][0]["rows"]}  # type: ignore[index]
    assert rows[0.5]["t"] is None and rows[0.5]["verdict"] == "עומד"
    assert rows[1.0]["t"] <= 300 and rows[5.0]["t"] <= 40
    principle = out.result["tables"][1]["rows"]  # type: ignore[index]
    to_earth, l_n, short = principle
    assert to_earth["trips"] == "מנתק"
    # 230 mA through a person between L and N — and the toroid sees nothing
    assert l_n["I_loop"] > 200 and l_n["I_res"] == 0 and l_n["trips"] == "לא מנתק"
    assert short["trips"] == "לא מנתק"
    # a type S device is judged on its own window
    s_type = with_(SPEC, "rcd", t_delay=0.15)
    r1 = next(r for r in run("rcd", s_type).result["tables"][0]["rows"] if r["mult"] == 1.0)  # type: ignore[index]
    assert r1["limit"].startswith("130") and r1["verdict"] == "עומד"
    # a device that trips above IΔn fails
    lazy = run("rcd", with_(SPEC, "rcd", k_trip=1.2))
    assert any(w["code"] == "rcd_fails" for w in lazy.warnings)


def test_I6_megger_charging_guard_and_display_limit() -> None:
    r_is, r_su, c, r_s = 500e6, 5000e6, 2e-9, 500e3
    r_p = r_is * r_su / (r_is + r_su)
    late, _ = ph.megger_reading(r_is, r_su, c, r_s, 500, 60, guard=False)
    assert late == pytest.approx(r_p, rel=1e-9)
    guarded, _ = ph.megger_reading(r_is, r_su, c, r_s, 500, 60, guard=True)
    assert guarded == pytest.approx(r_is, rel=1e-9)
    early, _ = ph.megger_reading(r_is, r_su, c, r_s, 500, 1e-4, guard=False)
    assert early < 0.1 * late  # the charging current dominates the first instants
    # above the display limit the megger shows its limit, and the run says so
    out = run("insulation", with_(SPEC, "insulation", R_pf=5000.0, R_su=1e6))
    assert out.result["tables"][0]["rows"][0]["ph1"] == 999  # type: ignore[index]
    assert any(w["code"] == "display_limit" for w in out.warnings)


def test_I7_fall_of_potential_62_percent_rule() -> None:
    golden = (math.sqrt(5) - 1) / 2  # 0.618…
    # far from the rod (r13 ≫ L) the 62 % point gives R_g; close to it the rule drifts
    assert ph.fall_of_potential(SPEC, 50.0, golden * 50) == pytest.approx(SPEC.R_g, rel=1e-4)
    assert abs(ph.fall_of_potential(SPEC, 3.0, golden * 3) / SPEC.R_g - 1) > 0.005
    for r13 in (5.0, 20.0, 80.0):
        xs = [f * r13 for f in (0.2, 0.4, 0.6, 0.8)]
        rs = [ph.fall_of_potential(SPEC, r13, x) for x in xs]
        assert rs == sorted(rs)
    far = run("earth", r13=60.0)
    assert not [w for w in far.warnings if w["code"] in ("no_plateau", "electrode_too_close")]
    near = run("earth", r13=3.0)
    assert {"no_plateau", "electrode_too_close"} <= {w["code"] for w in near.warnings}
    # TT condition: R_A·IΔn ≤ 50 V
    wet = run("earth", with_(SPEC, "earth", rho=200000.0, rod_d=0.016))
    assert any(w["code"] == "touch_voltage" for w in wet.warnings)


def test_I8_continuity_and_fault_loop_criteria() -> None:
    out = run("continuity")
    row = out.result["tables"][0]["rows"][0]  # type: ignore[index]
    assert row["R"] == pytest.approx(0.0178 * 5 / 16 + 0.01) and row["verdict"] == "עומד"
    loose = run("continuity", R_extra=0.1)
    assert loose.result["tables"][0]["rows"][0]["verdict"] == "לא עומד"  # type: ignore[index]
    # the manual's example: a B-type MCB needs Z ≤ 230/(5·In)
    b16 = assumed_nominal()
    assert b16.Z_max == pytest.approx(230 / 80)
    weak = with_(b16, "network", Z_PE=3.0)
    rows = run("fault_loop", weak).result["tables"][0]["rows"]  # type: ignore[index]
    assert [r["verdict"] for r in rows if r["loop"].endswith("PE")] == ["לא עומד"] * 3
    assert all(r["verdict"] == "עומד" for r in rows if not r["loop"].endswith("PE"))


def test_I9_every_default_study_runs_for_every_preset() -> None:
    for _, (_, make) in MOD.presets.items():
        spec = make()
        for kind in MOD.studies:
            out = MOD.execute(kind, spec, None, MOD.studies[kind].default_case(spec))
            assert out.status in ("success", "success_with_warnings"), (kind, out.error)
            assert out.result and out.result["tables"][0]["rows"]
    assert MOD.execute("mcb_trip", SPEC, None, {"points": []}).status == "invalid_input"
    assert MOD.execute("nope", SPEC, None, {}).status == "unsupported"


# --------------------------------------------------------------------------- API


def test_I10_api_journey(client: TestClient) -> None:
    pid = client.post("/api/projects", json={"name": "8", "experiment_id": "installation"})
    assert pid.status_code == 201, pid.text
    pid = pid.json()["id"]
    kinds = {s["kind"] for s in client.get(f"/api/projects/{pid}/studies").json()}
    assert kinds == set(MOD.studies)
    sets = client.post(f"/api/projects/{pid}/datasets/installation_2025/import", json={}).json()
    by_kind = {s["study_kind"]: s["id"] for s in sets["sets"]}
    results = {}
    for kind, sid in by_kind.items():
        sim = client.post(f"/api/measurement-sets/{sid}/simulate").json()
        assert sim["status"] in ("success", "success_with_warnings"), sim
        results[kind] = client.get(f"/api/comparison?run_id={sim['id']}&set_id={sid}").json()
    volts = [c for p in results["grid_voltages"]["pairs"] for c in p["cells"]]
    assert max(abs(c["rel_error"]) for c in volts) < 0.005
    loops = results["fault_loop"]
    codes = [w["code"] for w in loops["measured_analysis"]["warnings"]]
    assert codes.count("loop_below_phase") == 3
    mcb = results["mcb_trip"]
    assert mcb["summary"]["unmatched_rows"] == 0
    t_cells = [c for p in mcb["pairs"] for c in p["cells"] if c["quantity"] == "t"]
    assert len(t_cells) == 9 and max(abs(c["rel_error"]) for c in t_cells) < 0.6
    # an earth set without the distance r13 cannot be simulated — explicitly
    s = client.post(
        f"/api/projects/{pid}/measurement-sets",
        json={"study_kind": "earth", "label": "x", "n_rows": 2},
    ).json()
    for i, x in enumerate((10, 20)):
        client.post(
            f"/api/measurement-sets/{s['set']['id']}/entries",
            json={"row_index": i, "quantity": "x", "value": x, "unit": "m"},
        )
    r = client.post(f"/api/measurement-sets/{s['set']['id']}/simulate")
    assert r.status_code == 422 and r.json()["error"]["code"] == "missing_condition"
    # report (HTML + Word) and backup round trip
    run_id = client.post(
        f"/api/projects/{pid}/runs", json={"study_kind": "rcd", "case": {"multiples": [0.5, 1, 5]}}
    ).json()["id"]
    rp = client.post(
        f"/api/projects/{pid}/reports",
        json={"title": "ניסוי 8", "sections": [{"study_kind": "rcd", "run_id": run_id}]},
    )
    assert rp.status_code == 201, rp.text
    html = client.get(f"/api/reports/{rp.json()['id']}/html").text
    assert "הרשת, ההגנות והנחות המודל" in html and "עקרון הטורואיד" in html
    assert client.get(f"/api/reports/{rp.json()['id']}/docx").status_code == 200
    exp = client.get(f"/api/projects/{pid}/export").json()
    imp = client.post("/api/projects/import", json=exp)
    assert imp.status_code == 201 and imp.json()["experiment_id"] == "installation"
    assert client.get(f"/api/projects/{pid}/circuits/rcd/wiring").status_code in (404, 409)
