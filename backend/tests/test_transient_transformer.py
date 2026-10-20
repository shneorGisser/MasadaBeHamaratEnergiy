"""Transformer energisation (time domain): the inrush model against the phasor no-load model
and against the physics of switching instant and remanence. No measured inrush exists yet;
the IPST 2011 benchmark (Chiesa et al.) is the planned external check."""

from __future__ import annotations

import numpy as np
import pytest

from vel.engine.simulate import operating_point
from vel.engine.transient.transformer import energise
from vel.experiments import registry
from vel.experiments.transformer3ph import templates

MOD = registry.get("transformer3ph")
SPEC = MOD.default_spec()


def _i0_phasor(spec):  # type: ignore[no-untyped-def]
    return operating_point(templates.no_load(380.0, 50.0), spec).readings["A"]["I"]


def test_TT1_linear_core_matches_the_phasor_model_exactly() -> None:
    lin = SPEC.model_copy(update={"ecm": SPEC.ecm.model_copy(update={"sat_c": 0.0})})
    r = energise(lin, U_line=380.0, angle_deg=0.0, remanence=0.0, t_end=0.1, steady_start=True)
    assert r.i0_rms_fund == pytest.approx(_i0_phasor(lin), rel=1e-4)


def test_TT2_saturated_core_agrees_at_rated_flux_with_a_neutral() -> None:
    r = energise(
        SPEC, U_line=380.0, angle_deg=0.0, remanence=0.0, t_end=0.1, steady_start=True, neutral=True
    )
    assert r.i0_rms_fund == pytest.approx(_i0_phasor(SPEC), rel=5e-3)
    # without the neutral the third-harmonic magnetising current cannot flow: the flux is no
    # longer sinusoidal and the fundamental moves away from the phasor (sinusoidal-flux) model
    nn = energise(SPEC, U_line=380.0, angle_deg=0.0, remanence=0.0, t_end=0.1, steady_start=True)
    assert abs(nn.i0_rms_fund / _i0_phasor(SPEC) - 1) > 0.01


def test_TT3_switching_instant_and_remanence_set_the_inrush() -> None:
    def peak_a(angle: float, rem: float) -> float:
        r = energise(SPEC, U_line=380.0, angle_deg=angle, remanence=rem, t_end=0.06, neutral=True)
        return float(np.max(np.abs(r.i_line[0])))

    steady = energise(
        SPEC,
        U_line=380.0,
        angle_deg=0.0,
        remanence=0.0,
        t_end=0.06,
        steady_start=True,
        neutral=True,
    ).i0_peak_steady
    at_peak, at_zero, at_zero_rem = peak_a(90.0, 0.0), peak_a(0.0, 0.0), peak_a(0.0, 0.6)
    # switching phase A at its voltage peak: its flux starts on the steady sinusoid, no inrush
    assert at_peak < 1.5 * steady
    # at the voltage zero the flux would need a full DC offset: deep saturation
    assert at_zero > 5 * at_peak
    # remanence in the same direction adds to the offset
    assert at_zero_rem > 1.5 * at_zero


def test_TT4_study() -> None:
    out = MOD.execute("inrush", SPEC, None, MOD.studies["inrush"].default_case(SPEC))
    assert out.status == "success_with_warnings", out.error
    p = {x["key"]: x["value"] for x in out.result["parameters"]}  # type: ignore[index]
    assert p["I_peak_pu_noload"] > 20 and p["t_decay"] is not None
    assert "remanence_assumed" in {w["code"] for w in out.warnings}
