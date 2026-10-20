"""Time-domain induction machine (5th-order dq model) against the steady-state phasor solver.

These are model-independent consistency checks between two engines that share one spec: a
transient must settle on the operating point the phasor solver gives (with R_Fe removed, since
the dq model has no iron loss), and a rotor held still must carry the locked-rotor current.
No lab transient data exist yet for this motor, so nothing here is a validation against
measurement."""

from __future__ import annotations

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from vel.engine.simulate import operating_point
from vel.engine.transient.induction import dol_start
from vel.experiments import registry
from vel.experiments.induction_motor import templates
from vel.experiments.induction_motor.spec import MotorSpec, assumed_lab_motor

SPEC = assumed_lab_motor()
NO_FE = SPEC.model_copy(update={"ecm": SPEC.ecm.model_copy(update={"R_fe": 1e9})})


def _with_conn(spec: MotorSpec, conn: str) -> MotorSpec:
    return spec.model_copy(
        update={"nameplate": spec.nameplate.model_copy(update={"connection": conn})}
    )


@pytest.mark.parametrize(
    ("conn", "u", "m"), [("Y", 380.0, 0.0), ("Y", 380.0, 1.5), ("D", 220.0, 1.0)]
)
def test_TI1_start_settles_on_the_phasor_operating_point(conn: str, u: float, m: float) -> None:
    r = dol_start(SPEC, U_line=u, f=50.0, connection=conn, J=0.003, M_brake=m, t_end=1.2)  # type: ignore[arg-type]
    op = operating_point(templates.load_test(u, 50.0, conn, m_load=m), NO_FE)  # type: ignore[arg-type]
    assert r.n_final == pytest.approx(op.readings["M"]["n"], abs=0.01)
    assert r.i_line_rms_final == pytest.approx(op.readings["A"]["I"], rel=1e-4)
    # the instantaneous line current is a sinusoid of that RMS value by the end
    last = np.abs(r.i_line[-80:])  # last 20 ms = one period
    assert last.max() == pytest.approx(math.sqrt(2) * r.i_line_rms_final, rel=5e-3)


def test_TI2_rotor_held_still_carries_the_locked_rotor_current() -> None:
    r = dol_start(SPEC, U_line=100.0, f=50.0, connection="Y", J=1e4, t_end=0.4)
    op = operating_point(templates.locked_rotor(100.0, 50.0, "Y"), NO_FE)
    assert abs(r.n[-1]) < 1.0
    assert r.i_line_rms[-1] == pytest.approx(op.readings["A"]["I"], rel=1e-3)


def test_TI3_switching_angle_moves_the_peak_not_the_rms_inrush() -> None:
    peaks, starts = [], []
    for a in (0.0, 45.0, 90.0):
        r = dol_start(SPEC, U_line=380.0, f=50.0, connection="Y", J=0.003, t_end=0.05, angle_deg=a)
        peaks.append(r.i_peak)
        starts.append(float(r.i_line_rms[40]))  # 10 ms in
    assert max(peaks) / min(peaks) > 1.05
    i_lr = operating_point(templates.locked_rotor(380.0, 50.0, "Y"), NO_FE).readings["A"]["I"]
    assert i_lr is not None
    for p in peaks:  # an asymmetric RL inrush: between √2 and 2√2 times the symmetric RMS
        assert math.sqrt(2) * 0.8 * i_lr < p < 2 * math.sqrt(2) * i_lr


def test_TI4_study_and_api(client: TestClient) -> None:
    mod = registry.get("induction_motor")
    spec = mod.default_spec()
    out = mod.execute("dol_start", spec, None, mod.studies["dol_start"].default_case(spec))
    assert out.status == "success_with_warnings", out.error
    codes = {w["code"] for w in out.warnings}
    assert "inertia_assumed" in codes and "engines_disagree" not in codes
    params = {p["key"]: p for p in out.result["parameters"]}  # type: ignore[index]
    assert abs(params["dn_check"]["value"]) < 0.05
    assert params["I_peak"]["value"] > params["I_final"]["value"] * 3
    trace = out.result["tables"][1]  # type: ignore[index]
    assert trace["id"] == "trace" and len(trace["rows"]) > 3000
    # a too-short simulation says so instead of reporting an unsettled "final" speed
    short = mod.execute("dol_start", spec, None, {"t_end": 0.05})
    assert "not_settled" in {w["code"] for w in short.warnings}
    pid = client.post("/api/projects", json={"name": "dol", "experiment_id": "induction_motor"})
    run = client.post(
        f"/api/projects/{pid.json()['id']}/runs",
        json={"study_kind": "dol_start", "case": {"t_end": 0.6, "J": 0.003}},
    )
    assert run.status_code == 201, run.text
    assert run.json()["status"] in ("success", "success_with_warnings")


def test_TI5_star_delta_third_of_the_current_then_settles_in_delta() -> None:
    from vel.engine.transient.induction import star_delta_start

    u = SPEC.U_winding  # windings at their rating once in delta
    sd = star_delta_start(SPEC, U_line=u, f=50.0, J=0.003, t_switch=0.4, t_dead=0.05, t_end=1.0)
    dol = dol_start(SPEC, U_line=u, f=50.0, connection="D", J=0.003, t_end=0.05)
    # the classic result: in star the line current is a third of the direct delta start
    k = 40  # 10 ms
    assert sd.i_line_rms[k] / dol.i_line_rms[k] == pytest.approx(1 / 3, rel=0.02)
    op = operating_point(templates.load_test(u, 50.0, "D", m_load=0.0), NO_FE)
    assert sd.n_final == pytest.approx(op.readings["M"]["n"], abs=0.01)
    assert sd.i_line_rms_final == pytest.approx(op.readings["A"]["I"], rel=1e-4)
    assert [e["label"] for e in sd.events] == ["מעבר (מנותק)", "משולש"]
    # during the dead time no current flows and the motor coasts
    dead = (sd.t > 0.401) & (sd.t < 0.449)
    assert np.all(sd.i_line[dead] == 0) and np.all(np.diff(sd.n[dead]) <= 1e-9)


def test_TI6_star_delta_study_warns_on_early_changeover(client: TestClient) -> None:
    mod = registry.get("induction_motor")
    spec = mod.default_spec()
    ok = mod.execute("star_delta", spec, None, mod.studies["star_delta"].default_case(spec))
    codes = {w["code"] for w in ok.warnings}
    assert ok.status == "success_with_warnings" and "engines_disagree" not in codes
    assert "early_changeover" not in codes
    early = mod.execute("star_delta", spec, None, {"t_switch": 0.02, "t_dead": 0.0, "t_end": 0.8})
    assert "early_changeover" in {w["code"] for w in early.warnings}
    over = mod.execute("star_delta", spec, None, {"U_line": 380.0, "t_end": 1.2})
    assert "winding_overvoltage" in {w["code"] for w in over.warnings}
    bad = mod.execute("star_delta", spec, None, {"t_switch": 1.0, "t_end": 1.0})
    assert bad.status == "invalid_input"
