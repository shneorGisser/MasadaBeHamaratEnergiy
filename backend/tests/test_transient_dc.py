"""DC machine in the time domain (shunt-generator build-up, shunt-motor start) against the
steady-state DC solver — both engines use the same fitted machine model. The inductances and
the inertia are assumed; they set how fast things happen, not where they settle."""

from __future__ import annotations

import pytest

from vel.engine.simulate import operating_point
from vel.engine.transient.dcmachine import shunt_buildup, shunt_motor_start
from vel.experiments import registry
from vel.experiments.dc_machine import templates
from vel.experiments.dc_machine.spec import fitted_lab_dc_machine
from vel.experiments.dc_machine.transient import L_A_ASSUMED, L_F0_ASSUMED

SPEC = fitted_lab_dc_machine()


@pytest.mark.parametrize("r_rheo", [0.0, 150.0, 300.0, 1500.0])
def test_TD1_buildup_ends_where_the_steady_state_solver_says(r_rheo: float) -> None:
    r = shunt_buildup(SPEC, n=2800, r_rheo=r_rheo, L_a=L_A_ASSUMED, L_f0=L_F0_ASSUMED, t_end=8.0)
    op = operating_point(
        templates.generator(2800, r_rheo, 1e9, excitation="shunt", closed=False), SPEC, dc=True
    )
    assert r.u[-1] == pytest.approx(op.readings["U1"]["U"], rel=1e-6)
    # the voltage rises monotonically from the remanence (no overshoot in a first-order loop)
    assert all(b >= a - 1e-9 for a, b in zip(r.u, r.u[1:], strict=False))


def test_TD2_critical_field_resistance_separates_buildup_from_none() -> None:
    mod = registry.get("dc_generator")
    out = mod.execute("buildup", SPEC, None, {"R_rheo": 0.0})
    r_crit = {p["key"]: p["value"] for p in out.result["parameters"]}["R_crit"]  # type: ignore[index]
    below = mod.execute("buildup", SPEC, None, {"R_rheo": r_crit - 100, "t_end": 20.0})
    # (the remanence keeps a small, amplified voltage just above the critical value)
    above = mod.execute("buildup", SPEC, None, {"R_rheo": r_crit + 1000, "t_end": 20.0})
    assert "no_buildup" not in {w["code"] for w in below.warnings}
    assert "no_buildup" in {w["code"] for w in above.warnings}
    # close to the critical resistance the build-up is much slower
    t_fast = {p["key"]: p["value"] for p in out.result["parameters"]}["t_90"]  # type: ignore[index]
    t_slow = {p["key"]: p["value"] for p in below.result["parameters"]}["t_90"]  # type: ignore[index]
    assert t_slow > 2 * t_fast


def test_TD3_motor_start_settles_and_the_starter_limits_the_inrush() -> None:
    kw = {"U": 174.0, "r_rheo": 0.0, "J": 0.003, "L_a": L_A_ASSUMED, "L_f0": L_F0_ASSUMED}
    with_st = shunt_motor_start(SPEC, steps=[(30.0, 0.5), (10.0, 1.0), (0.0, 2.5)], **kw)  # type: ignore[arg-type]
    direct = shunt_motor_start(SPEC, steps=[(0.0, 2.5)], **kw)  # type: ignore[arg-type]
    op = operating_point(templates.motor(174.0, 0.0), SPEC, dc=True)
    for r in (with_st, direct):
        assert r.n[-1] == pytest.approx(op.readings["M"]["n"], abs=0.01)
        assert r.i_a[-1] == pytest.approx(op.readings["Aa"]["I"], rel=1e-5)
    assert max(with_st.i_a) < 0.5 * max(direct.i_a)
    # switched on together with the armature, the field rises with its own time constant —
    # and the motor never turns backwards while the field is weak
    both = shunt_motor_start(SPEC, steps=[(30.0, 0.5), (0.0, 2.0)], field_first=False, **kw)  # type: ignore[arg-type]
    k = int(0.05 / (both.t[1] - both.t[0]))
    assert both.i_f[k] < 0.5 * both.i_f[-1]
    assert min(both.n) > -1e-6 and min(with_st.n) > -1e-6
    assert both.n[-1] == pytest.approx(op.readings["M"]["n"], abs=0.01)


def test_TD4_studies_report_assumptions_and_agree() -> None:
    for mid, kind in (("dc_motor", "motor_start"), ("dc_generator", "buildup")):
        mod = registry.get(mid)
        out = mod.execute(kind, SPEC, None, mod.studies[kind].default_case(SPEC))
        codes = {w["code"] for w in out.warnings}
        assert out.status == "success_with_warnings", out.error
        assert "transient_parameters_assumed" in codes and "engines_disagree" not in codes
