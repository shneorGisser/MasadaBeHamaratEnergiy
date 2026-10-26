"""Our induction-motor transient engine against motulator's machine model (Aalto, MIT).

Different equivalent circuit (Γ vs T), different frame (αβ vs dq), different solver (LSODA vs
Radau), same physics: the DOL start must agree to solver tolerance. A 1e-5 bound leaves room
for tolerances. A modelling error (a wrong √2, √3 or 3/2, a frame-rotation sign) shows up as
1e-2 or more."""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("motulator", reason="pip install -e .[reference] to run the cross-check")

from vel.experiments.induction_motor.spec import ap3030_sheet_2026, assumed_lab_motor  # noqa: E402
from vel.reference.motulator_im import compare_dol  # noqa: E402

pytestmark = pytest.mark.reference


@pytest.mark.parametrize(
    ("label", "spec", "u", "brake"),
    [
        ("assumed 0.37 kW, no load", assumed_lab_motor(), 380.0, 0.0),
        ("assumed 0.37 kW, braked", assumed_lab_motor(), 380.0, 1.5),
        ("AP-3030 fit (per Y-equivalent), reduced voltage", ap3030_sheet_2026(), 220.0, 0.3),
    ],
)
def test_REF1_dol_start_matches_motulator(label: str, spec: Any, u: float, brake: float) -> None:
    if getattr(getattr(spec, "nameplate", None), "connection", "Y") == "D":
        # the reference is wired in Y: use the Y-equivalent of the Δ windings (Z/3)
        e = spec.ecm
        spec = spec.model_copy(
            update={
                "ecm": e.model_copy(
                    update={k: getattr(e, k) / 3 for k in ("R1", "X1", "R2p", "X2p", "Xm", "R_fe")}
                )
            }
        )
    r = compare_dol(spec, U_line=u, J=0.003, M_brake=brake, t_end=0.6)
    assert r["i_err_max"] < 1e-5, (label, r)
    assert r["M_err_max"] < 1e-5, (label, r)
    assert r["n_err_max"] < 1e-5, (label, r)


@pytest.mark.parametrize(
    ("label", "ramp", "brake"),
    [
        ("0→50 Hz in 0.5 s, 5 % boost, braked", (220.0, 50.0, 50.0, 0.5, 0.05), 0.8),
        ("0→30 Hz in 0.3 s, no boost", (220.0, 50.0, 30.0, 0.3, 0.0), 0.0),
    ],
)
def test_REF2_vf_start_matches_motulator(label: str, ramp: tuple[float, ...], brake: float) -> None:
    """The inverter (V/f) start: time-varying frequency and voltage, a kink at the ramp end."""
    from vel.engine.transient.induction import VfRamp
    from vel.reference.motulator_im import compare_vf

    u, fn, ft, tr, boost = ramp
    r = compare_vf(
        assumed_lab_motor(),
        VfRamp(U_n=u, f_n=fn, f_target=ft, t_ramp=tr, boost=boost),
        J=0.003,
        M_brake=brake,
        t_end=0.8,
    )
    assert max(r.values()) < 1e-5, (label, r)
