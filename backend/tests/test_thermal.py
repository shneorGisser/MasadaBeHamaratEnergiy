"""Winding temperature: copper resistances at T_op in the load tests, cold in the resistance
measurement, and no change at all for specs and runs that do not set it."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from vel.experiments import registry
from vel.experiments.thermal import COPPER, Thermal, at_operating_temperature
from vel.services.runs import execute_snapshot


def test_TH1_copper_factor() -> None:
    assert Thermal(T_ref=20, T_op=75).factor == pytest.approx((235 + 75) / (235 + 20))
    assert Thermal().factor == 1.0


@pytest.mark.parametrize("exp", sorted(COPPER))
def test_TH2_every_machine_scales_its_copper_and_only_that(exp: str) -> None:
    m = registry.get(exp)
    spec = m.default_spec()
    hot = spec.model_copy(update={"thermal": Thermal(T_ref=20, T_op=95)})
    out, warn = at_operating_temperature(exp, hot, "load")
    k = (235 + 95) / (235 + 20)
    for f in COPPER[exp]:
        assert getattr(out.ecm, f) == pytest.approx(getattr(spec.ecm, f) * k)
    others = set(type(spec.ecm).model_fields) - set(COPPER[exp])
    assert all(getattr(out.ecm, f) == getattr(spec.ecm, f) for f in others)
    assert warn and warn["code"] == "winding_temperature"
    # cold studies and the default keep the spec as it is
    assert at_operating_temperature(exp, hot, "dc_resistance")[0] is hot
    assert at_operating_temperature(exp, spec, "load")[0] is spec


def test_TH3_short_circuit_copper_loss_rises_by_the_factor() -> None:
    m = registry.get("transformer3ph")
    spec = m.default_spec()
    case = m.studies["short_circuit"].default_case(spec)
    circuit = m.studies["short_circuit"].default_circuit(spec, "")
    snap = {
        "experiment_id": "transformer3ph",
        "study_kind": "short_circuit",
        "circuit": circuit.model_dump(mode="json"),  # type: ignore[union-attr]
        "case": case,
    }
    cold = execute_snapshot({**snap, "spec": spec.model_dump(mode="json")})
    hot_spec = spec.model_copy(update={"thermal": Thermal(T_ref=20, T_op=75)})
    hot = execute_snapshot({**snap, "spec": hot_spec.model_dump(mode="json")})
    assert hot.warnings[0]["code"] == "winding_temperature"
    rc = {p["key"]: p["value"] for p in cold.result["parameters"]}  # type: ignore[index]
    rh = {p["key"]: p["value"] for p in hot.result["parameters"]}  # type: ignore[index]
    key = next(k for k in rc if k.lower().startswith("r_k") or k == "rk")
    assert rh[key] / rc[key] == pytest.approx((235 + 75) / (235 + 20), rel=2e-3)


def test_TH4_old_spec_without_thermal_validates(client: TestClient) -> None:
    m = registry.get("induction_motor")
    doc = m.default_spec().model_dump(mode="json")
    doc.pop("thermal")
    assert m.spec(doc).thermal.factor == 1.0
