"""Wound-rotor start through a rotor starter (time domain): physics and phasor-solver checks."""

from __future__ import annotations

import pytest

from vel.engine.simulate import operating_point
from vel.engine.transient.induction import Segment, simulate
from vel.experiments import registry
from vel.experiments.wound_rotor import templates
from vel.experiments.wound_rotor.transient import default_steps, im_params

MOD = registry.get("wound_rotor")
SPEC = MOD.default_spec()


def _start(r_ext: float, t_end: float = 1.5):  # type: ignore[no-untyped-def]
    u_w = SPEC.nameplate.U_n / 3**0.5
    seg = Segment(t_end, u_w, 0.0, "Y", R2_extra=SPEC.ecm.k**2 * r_ext)
    # a rotor held still (J huge) until the rotor flux transient (Lr/R2 ≈ 0.1 s) has decayed
    return simulate(im_params(SPEC), [seg], f=50.0, J=1e9)


def test_TW1_starter_raises_torque_and_lowers_current_at_standstill() -> None:
    r_pull = default_steps(SPEC)[0]["R"]
    shorted, starter = _start(0.0), _start(r_pull)
    # the starting current falls, and with R2' + k²·R_st = X1 + X2' the torque rises to pull-out
    assert starter.i_line_rms[-1] < 0.8 * shorted.i_line_rms[-1]
    assert starter.M_em[-1] > 1.5 * shorted.M_em[-1]
    # …and matches the phasor solver's locked rotor with that starter
    circ = templates.motor(SPEC.nameplate.U_n, 50.0, "Y", r_ext=r_pull, locked=True)
    no_fe = SPEC.model_copy(update={"ecm": SPEC.ecm.model_copy(update={"R_fe": 1e9})})
    op = operating_point(circ, no_fe)
    assert starter.i_line_rms[-1] == pytest.approx(op.readings["A"]["I"], rel=1e-5)


def test_TW2_study_steps_settle_on_the_phasor_point() -> None:
    out = MOD.execute("starter_start", SPEC, None, MOD.studies["starter_start"].default_case(SPEC))
    assert out.status == "success_with_warnings", out.error
    codes = {w["code"] for w in out.warnings}
    assert "engines_disagree" not in codes and "not_settled" not in codes
    p = {x["key"]: x["value"] for x in out.result["parameters"]}  # type: ignore[index]
    assert abs(p["dn_check"]) < 0.05
    events = next(t for t in out.result["tables"] if t["id"] == "events")  # type: ignore[index]
    assert len(events["rows"]) == 2
    bad = MOD.execute(
        "starter_start", SPEC, None, {"points": [{"R": 5, "t": 1}, {"R": 0, "t": 0.5}]}
    )
    assert bad.status == "invalid_input"
