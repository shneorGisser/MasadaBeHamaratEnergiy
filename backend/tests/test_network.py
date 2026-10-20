"""Network module: pandapower against our own solver, and both against hand calculation.

Nothing here is validated against measurement — the network data are assumed. What is checked:
two independent implementations agree to rounding, the IEC 60909 numbers follow the formulas
written out by hand, and the physics has the right direction."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from vel.engine.network import direct, pp_model
from vel.experiments import registry
from vel.experiments.network.spec import BUSES, typical_substation

SPEC = typical_substation()
MOD = registry.get("network")


def _scaled(k: float):  # type: ignore[no-untyped-def]
    lo = SPEC.loads
    return SPEC.model_copy(
        update={"loads": lo.model_copy(update={"P2_kW": lo.P2_kW * k, "P3_kW": lo.P3_kW * k})}
    )


@pytest.mark.parametrize("k", [0.0, 1.0, 4.0])
def test_N1_load_flow_engines_agree(k: float) -> None:
    sp = _scaled(k)
    a, b = direct.load_flow(sp), pp_model.load_flow(sp)
    for bus in BUSES:
        assert abs(a.U[bus] - b.U[bus]) < 1e-10
    for x in ("T", "C1", "C2"):
        assert a.I_branch[x] == pytest.approx(b.I_branch[x], rel=1e-9, abs=1e-9)
        assert a.loading[x] == pytest.approx(b.loading[x], rel=1e-9, abs=1e-9)
    assert a.P_loss_kW == pytest.approx(b.P_loss_kW, rel=1e-8, abs=1e-9)


@pytest.mark.parametrize("case", ["max", "min"])
def test_N2_short_circuit_engines_agree(case: str) -> None:
    a, b = direct.short_circuit(SPEC, case), pp_model.short_circuit(SPEC, case)
    for q in ("Ik3", "ip", "Ith", "Ik1"):
        for bus in BUSES:
            assert getattr(a, q)[bus] == pytest.approx(getattr(b, q)[bus], rel=1e-9), (q, bus)


def test_N3_main_board_by_hand() -> None:
    """I''k3 at B1, maximum: grid + K_T·Z_T, written out from IEC 60909-0."""
    g, t = SPEC.grid, SPEC.trafo
    zq = 1.1 * (22e3) ** 2 / 250e6 * (400 / 22e3) ** 2  # referred to 400 V
    xq = zq / math.sqrt(1 + 0.1**2)
    zt = 0.06 * 400**2 / 630e3
    rt = 6.5e3 / 630e3 * 400**2 / 630e3
    xt = math.sqrt(zt**2 - rt**2)
    kt = 0.95 * 1.1 / (1 + 0.6 * xt / (400**2 / 630e3))
    z = complex(0.1 * xq + kt * rt, xq + kt * xt)
    ik = 1.1 * 400 / (math.sqrt(3) * abs(z)) / 1e3
    assert direct.short_circuit(SPEC, "max").Ik3["B1"] == pytest.approx(ik, rel=1e-12)
    kappa = 1.02 + 0.98 * math.exp(-3 * z.real / z.imag)
    assert direct.short_circuit(SPEC, "max").ip["B1"] == pytest.approx(
        kappa * math.sqrt(2) * ik, rel=1e-12
    )
    assert g.Sk_max_MVA == 250 and t.uk == 6  # the numbers above are for this preset


def test_N4_physics_directions() -> None:
    lf = [direct.load_flow(_scaled(k)) for k in (0.0, 1.0, 2.0)]
    u3 = [abs(r.U["B3"]) for r in lf]
    assert u3[0] > u3[1] > u3[2]
    assert abs(lf[0].U["B3"]) == pytest.approx(1.0, abs=1e-3)  # no load: only the magnetising
    mx, mn = direct.short_circuit(SPEC, "max"), direct.short_circuit(SPEC, "min")
    lv = BUSES[1:]
    assert all(mx.Ik3[a] > mx.Ik3[b] for a, b in zip(lv, lv[1:], strict=False))
    assert all(mn.Ik3[b] < mx.Ik3[b] and mn.Ik1[b] < mx.Ik1[b] for b in BUSES)
    assert mx.Ik1["B3"] < mx.Ik3["B3"]  # far from the transformer Z0 of the cable dominates
    assert mx.Ik1["B1"] > mx.Ik3["B1"]  # Dyn terminals: Z0 = K_T·Z_T carries no grid share


def test_N5_studies_report_engine_agreement_and_warnings() -> None:
    for kind in ("load_flow", "short_circuit"):
        out = MOD.execute(kind, SPEC, None, MOD.studies[kind].default_case(SPEC))
        assert out.status == "success_with_warnings", out.error
        codes = {w["code"] for w in out.warnings}
        assert codes == {"assumed_network"}, codes
        p = {x["key"]: x["value"] for x in out.result["parameters"]}  # type: ignore[index]
        assert p["engines_dev"] < 1e-9
    long = SPEC.model_copy(
        update={
            "cable2": SPEC.cable2.model_copy(update={"L_m": 400.0}),
            "loads": SPEC.loads.model_copy(update={"P3_kW": 40.0}),
        }
    )
    codes = {w["code"] for w in MOD.execute("load_flow", long, None, {}).warnings}
    assert {"voltage_drop", "overload"} <= codes
    bad = MOD.execute("load_flow", SPEC, None, {"scales": [-1.0]})
    assert bad.status == "invalid_input"


def test_N6_api_project_runs_and_measurements(client: TestClient) -> None:
    p = client.post("/api/projects", json={"name": "רשת", "experiment_id": "network"})
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    kinds = [s["kind"] for s in client.get(f"/api/projects/{pid}/studies").json()]
    assert kinds == ["load_flow", "short_circuit"]
    r = client.post(f"/api/projects/{pid}/runs", json={"study_kind": "short_circuit", "case": {}})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "success_with_warnings"
    guide = client.get(f"/api/projects/{pid}/guide").json()
    assert guide["total"] == 3 + 4 * 2
