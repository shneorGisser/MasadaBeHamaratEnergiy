"""Sudden three-phase short circuit of the synchronous machine (time domain).

Checked against two independent references: the steady-state model's sustained short-circuit
current, and the analytic IEEE Std 115 envelope of the AC component (whose time-constant
formulas are approximations valid for R ≪ X, hence the few-percent tolerance). The transient
reactances and time constants are assumed; X''d defaults to the measured X2."""

from __future__ import annotations

import math

import numpy as np
import pytest

from vel.engine.transient.synchronous import SmDynamics, ieee_envelope, sudden_short_circuit
from vel.experiments import registry

MOD = registry.get("synchronous")
SPEC = MOD.default_spec()
X2 = SPEC.ecm.X2


def _m(r: float) -> SmDynamics:
    xs = SPEC.Xs_unsat
    return SmDynamics(r, SPEC.ecm.Xl, xs, xs, 1.5 * X2, X2, X2, 0.3, 0.02, 0.03, 50.0)


@pytest.mark.parametrize("r", [0.02 * X2, SPEC.ecm.Ra])
def test_TS1_ac_envelope_follows_ieee_115(r: float) -> None:
    m = _m(r)
    res = sudden_short_circuit(m, E_rms=60.0, angle_deg=0.0, t_end=1.5)
    for t in (0.05, 0.1, 0.3, 1.0):
        k = int(round(t / 1e-4))
        ref = ieee_envelope(m, 60.0, res.t[k : k + 1])[0]
        assert res.i_ac_env[k] == pytest.approx(ref, rel=0.03), t


def test_TS2_sustained_current_and_initial_subtransient() -> None:
    m = _m(SPEC.ecm.Ra)
    res = sudden_short_circuit(m, E_rms=60.0, angle_deg=0.0, t_end=2.0)
    assert res.i_sustained_rms == pytest.approx(60.0 / math.hypot(m.R, m.Xd), rel=1e-5)
    # first cycle: the AC part starts at √2·E/X''d; with the DC offset the peak lies between
    # that and twice it (the sub-transient part decays within that cycle, so not at the top)
    first = float(np.max(np.abs(res.i_abc[:, : int(0.02 / 1e-4)])))
    i2 = math.sqrt(2) * 60.0 / m.Xd2
    assert i2 < first < 2 * i2
    # the field current kicks up and returns
    assert res.if_ratio.max() > 1.5 and res.if_ratio[-1] == pytest.approx(1.0, abs=0.02)


def test_TS3_rotor_angle_sets_the_dc_offset_not_the_ac_part() -> None:
    m = _m(0.02 * X2)
    peaks = [
        float(np.max(np.abs(sudden_short_circuit(m, E_rms=60.0, angle_deg=a, t_end=0.05).i_abc[0])))
        for a in (0.0, 90.0)
    ]
    # θ0 = 0: the d-axis on phase A, the flux linking A is maximal → full offset in phase A
    assert peaks[0] > 1.6 * peaks[1]


def test_TS4_study_checks_both_references() -> None:
    out = MOD.execute("sudden_sc", SPEC, None, MOD.studies["sudden_sc"].default_case(SPEC))
    assert out.status == "success_with_warnings", out.error
    codes = {w["code"] for w in out.warnings}
    assert "transient_parameters_assumed" in codes and "engines_disagree" not in codes
    p = {x["key"]: x["value"] for x in out.result["parameters"]}  # type: ignore[index]
    assert abs(p["Ik_check"]) < 1e-3 and abs(p["env_check"]) < 0.05
    bad = MOD.execute("sudden_sc", SPEC, None, {"Xd2": 20.0})  # below Xl: inconsistent
    assert bad.status == "invalid_input"
