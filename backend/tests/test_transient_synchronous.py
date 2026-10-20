"""Sudden three-phase short circuit of the synchronous machine (time domain).

Checked against two independent references: the steady-state model's sustained short-circuit
current, and the analytic IEEE Std 115 envelope of the AC component (whose time-constant
formulas are approximations valid for R ≪ X, hence the few-percent tolerance). The transient
reactances and time constants are assumed; X''d defaults to the measured X2."""

from __future__ import annotations

import math

import numpy as np
import pytest

from vel.engine.transient.synchronous import (
    SmDynamics,
    ieee_envelope,
    saturate,
    sudden_short_circuit,
    synchronize,
)
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


# --- T1.5b: synchronisation to the grid ---------------------------------------------------


def _sync(m: SmDynamics, **kw: float):  # type: ignore[no-untyped-def]
    base = dict(
        poles=4, J=0.02, P_fw=0.0, V_rms=230.0, E_rms=230.0, E_fd_rms=230.0,
        delta0_deg=0.0, df=0.0, P_drive=0.0, t_end=0.5,
    )  # fmt: skip
    base.update(kw)
    return synchronize(m, **base)  # type: ignore[arg-type]


def test_TS5_perfect_closing_draws_no_current() -> None:
    r = _sync(_m(SPEC.ecm.Ra))
    assert r.i_peak < 1e-6 * 230.0 / X2
    assert r.pulled_in and r.n[-1] == pytest.approx(1500.0, abs=1e-6)


def test_TS6_lossless_generator_settles_on_the_power_angle_curve() -> None:
    m = _m(1e-9 * X2)
    p = 60.0
    r = _sync(m, P_drive=p, t_end=12.0)
    assert r.pulled_in and r.settled
    # cylindrical, R → 0: P = 3·E·V·sin δ / Xd
    delta = math.degrees(math.asin(p * m.Xd / (3 * 230.0 * 230.0)))
    assert r.delta_final == pytest.approx(delta, abs=0.01)
    assert r.p_final == pytest.approx(p, rel=1e-3)


def test_TS7_phase_error_sets_the_closing_current() -> None:
    m = _m(SPEC.ecm.Ra)
    peaks = [_sync(m, delta0_deg=a, t_end=0.2).i_peak for a in (10.0, 30.0, 60.0)]
    assert peaks[0] < peaks[1] < peaks[2]
    for a, pk in zip((10.0, 30.0, 60.0), peaks, strict=True):
        i2 = math.sqrt(2) * 2 * 230.0 * math.sin(math.radians(a) / 2) / m.Xd2
        assert 0.9 * i2 < pk < 2.2 * i2, a


def test_TS8_saturate_keeps_the_rotor_circuits() -> None:
    m = _m(SPEC.ecm.Ra)
    assert saturate(m, 1.0) is m
    s = saturate(m, 0.4)
    s.check()
    assert s.Xd - s.Xl == pytest.approx(0.4 * (m.Xd - m.Xl))
    # the rotor leakages shield X'd and X''d: the further from the air gap, the less they move
    # (−57 % / −27 % / −17 % here — the assumed X''d of this small machine is not far above Xl)
    rel = [1 - s.Xd / m.Xd, 1 - s.Xd1 / m.Xd1, 1 - s.Xd2 / m.Xd2]
    assert rel[0] > rel[1] > rel[2] > 0
    assert s.Td01 < m.Td01
    with pytest.raises(ValueError):
        saturate(m, 0.0)


@pytest.mark.parametrize("p_drive", [0.0, 100.0, -100.0])
def test_TS9_study_meets_the_steady_state_model(p_drive: float) -> None:
    case = MOD.studies["synchronize"].default_case(SPEC) | {"P_drive": p_drive}
    out = MOD.execute("synchronize", SPEC, None, case)
    assert out.status == "success_with_warnings", out.error
    codes = {w["code"] for w in out.warnings}
    assert "engines_disagree" not in codes and "pole_slip" not in codes, codes
    p = {x["key"]: x["value"] for x in out.result["parameters"]}  # type: ignore[index]
    assert abs(p["I_check"]) < 2e-3 and abs(p["P_check"]) < 0.1
    assert [t["id"] for t in out.result["tables"]] == ["summary", "swing", "trace"]  # type: ignore[index]


def test_TS10_overload_slips_poles_and_is_reported() -> None:
    case = MOD.studies["synchronize"].default_case(SPEC) | {"P_drive": 2000.0, "t_end": 3.0}
    out = MOD.execute("synchronize", SPEC, None, case)
    codes = {w["code"] for w in out.warnings}
    assert {"pole_slip", "no_steady_state"} <= codes
    p = {x["key"]: x["value"] for x in out.result["parameters"]}  # type: ignore[index]
    assert p["I_check"] is None
