"""Station-level protection coordination: catalogue curves taken as pandapower evaluates them,
IEC 60255 relay constants, Dyn current transfer, and honest gaps outside the catalogue."""

from __future__ import annotations

import math

import pytest

from vel.engine.network.devices import Relay, fuse_curve, fuse_types
from vel.experiments.network.spec import typical_substation
from vel.experiments.network.studies import execute


def test_P1_idmt_relay_matches_iec_60255_reference_times() -> None:
    # textbook values at 10 × pick-up, TMS = 1
    assert Relay(100, 1.0).time(1000)[0] == pytest.approx(2.971, abs=1e-3)
    assert Relay(100, 1.0, "very_inverse").time(1000)[0] == pytest.approx(1.5)
    assert Relay(100, 1.0, "extremely_inverse").time(1000)[0] == pytest.approx(80 / 99)
    assert Relay(100, 1.0, "long_inverse").time(1000)[0] == pytest.approx(120 / 9)
    assert Relay(100, 0.5).time(90)[0] is None  # below pick-up
    assert Relay(100, 0.5, I_inst=2000, t_inst=0.04).time(5000)[0] == 0.04


def test_P2_fuse_curves_pass_through_the_catalogue_points_and_stop_at_its_ends() -> None:
    import pandapower as pp

    lib = pp.create_empty_network().std_types["fuse"]
    for name in ("HV 40A", "Siemens NH-2-1000"):
        d = lib[name]
        kind = "avg" if d["t_avg"] not in (0, "0") else "min"
        c = fuse_curve(name, kind)  # type: ignore[arg-type]
        for x, t in zip(d[f"x_{c.kind}"], d[f"t_{c.kind}"], strict=True):
            assert c.time(float(x))[0] == pytest.approx(float(t), rel=1e-6)
        assert c.time(0.99 * c.i_lo)[0] is None and c.time(1.01 * c.i_hi)[0] is None
    # pre-arcing minimum is never slower than total clearing
    lo, tot = fuse_curve("HV 40A", "min"), fuse_curve("HV 40A", "total")
    for i in (260.0, 300.0, 450.0, 530.0):
        assert lo.time(i)[0] <= tot.time(i)[0]  # type: ignore[operator]
    assert "HV 40A" in fuse_types("HV ") and "Siemens NH-2-1000" in fuse_types("Siemens NH")


def test_P3_coordination_study_on_the_typical_substation() -> None:
    spec = typical_substation()
    out = execute("coordination", spec, None, {})
    assert out.status == "success_with_warnings"
    res = out.result
    assert res is not None
    par = {p["key"]: p for p in res["parameters"]}
    # inrush: 12 × 16.5 A; HV 40A minimum melting time there is above 0.1 s
    assert par["In_mv"]["value"] == pytest.approx(630 / (math.sqrt(3) * 22), rel=1e-9)
    assert par["t_melt_inrush"]["value"] > 0.1
    backup = {r["fault"]: r for r in res["tables"][1]["rows"]}
    r3 = next(v for k, v in backup.items() if "תלת" in k and "מרבי" in k)
    r1 = next(v for k, v in backup.items() if "אדמה" in k)
    assert r3["I_mv"] == pytest.approx(r3["I_lv"] * 400 / 22000, rel=1e-12)  # Dyn, 3-phase
    assert r1["I_mv"] == pytest.approx(r1["I_lv"] * 400 / 22000 / math.sqrt(3), rel=1e-12)
    assert r1["t"] is None  # the MV fuse does not see an LV earth fault: a real, known gap
    codes = [w["code"] for w in out.warnings]
    assert "no_mv_backup" in codes
    sel = {r["pair"]: r for r in res["tables"][0]["rows"]}
    # Q1 (250 A MCB) clears faster than the 1000 A NH main everywhere up to Ik3 at B2
    assert sel["Q1 ← Siemens NH-2-1000"]["verdict"] == "סלקטיבי"
    # the NH main loses selectivity against the MV fuse at high currents: margin really ≤ 0 there
    lv_mv = sel["Siemens NH-2-1000 ← HV 40A"]
    assert lv_mv["I_fail"] is not None and lv_mv["margin"] <= 0


def test_P4_a_relay_main_is_graded_with_the_interval() -> None:
    spec = typical_substation()
    spec = spec.model_copy(
        update={"protection": spec.protection.model_copy(update={"lv_main": "relay", "R_tms": 0.5})}
    )
    res = execute("coordination", spec, None, {"cti": 0.3}).result
    assert res is not None
    q1 = next(r for r in res["tables"][0]["rows"] if r["pair"].startswith("Q1"))
    assert q1["need"] == 0.3
    # if declared selective, the smallest margin found really exceeds the interval
    if q1["verdict"] == "סלקטיבי":
        assert q1["margin"] > 0.3


def test_P5_unknown_fuse_is_rejected_by_the_spec() -> None:
    from pydantic import ValidationError

    doc = typical_substation().model_dump()
    doc["protection"]["F_MV"] = "HV 41A"
    with pytest.raises(ValidationError):
        type(typical_substation()).model_validate(doc)


def test_P6_the_spec_form_offers_exactly_the_library_fuses() -> None:
    import json
    import re
    from pathlib import Path

    src = (Path(__file__).parents[2] / "frontend/src/components/SpecForm.tsx").read_text()
    for const, prefix in (("HV_FUSES", "HV "), ("NH_FUSES", "Siemens NH")):
        m = re.search(rf"const {const} = (\[.*?\])\n", src)
        assert m, const
        assert [o["value"] for o in json.loads(m.group(1))] == fuse_types(prefix)
