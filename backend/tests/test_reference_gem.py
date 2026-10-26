"""Our DC-machine transient against gym-electric-motor's shunt-motor model (Paderborn, MIT),
on the linear core both share (vel.reference.gem_dc explains the set-up)."""

from __future__ import annotations

import pytest

pytest.importorskip("gym_electric_motor", reason="pip install -e .[reference] to run it")

from vel.experiments.dc_machine.spec import fitted_lab_dc_machine  # noqa: E402
from vel.reference.gem_dc import compare_shunt_start  # noqa: E402

pytestmark = pytest.mark.reference


@pytest.mark.parametrize(
    ("label", "steps", "brake"),
    [
        ("three-step starter, braked", [(30.0, 0.5), (10.0, 1.0), (0.0, 2.5)], 0.5),
        ("direct start, no load", [(0.0, 1.5)], 0.0),
    ],
)
def test_REF3_shunt_start_matches_gem(
    label: str, steps: list[tuple[float, float]], brake: float
) -> None:
    r = compare_shunt_start(
        fitted_lab_dc_machine(),
        U=220.0,
        r_rheo=0.0,
        steps=steps,
        J=0.01,
        L_a=0.05,
        L_f0=20.0,
        M_brake=brake,
    )
    assert max(r["i_err_max"], r["n_err_max"], r["M_err_max"]) < 1e-5, (label, r)
