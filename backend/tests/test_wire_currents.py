"""Current in every cable (wires are zero-volt branches of the MNA network).

Checks that need no model: the cable on an ammeter terminal carries the ammeter's current, a
voltmeter's leads carry none, and a cable that closes a loop of cables (an ideal parallel path)
reports "undefined" instead of an arbitrary split."""

from __future__ import annotations

import pytest

from vel.engine.circuit import CircuitModel
from vel.engine.simulate import operating_point
from vel.experiments.dc_machine import templates as dc
from vel.experiments.transformer3ph.spec import TransformerSpec

from .test_wiring import all_template_circuits


def _solve(c: CircuitModel, spec: object):  # type: ignore[no-untyped-def]
    types = {x.type for x in c.components}
    is_dc = "source3" not in types and bool(types & {"source_dc", "dcmachine"})
    return operating_point(c, spec, dc=is_dc, on_stall="stall", wire_currents=True), is_dc


def _spec_for(name: str):  # type: ignore[no-untyped-def]
    from vel.experiments import registry

    return registry.get(name.split(".")[0]).default_spec()


def test_cables_on_instruments_carry_the_instrument_current() -> None:
    solved = checked = 0
    for name, c in all_template_circuits():
        try:
            op, is_dc = _solve(c, _spec_for(name))
        except Exception:  # noqa: BLE001 — some templates need case parameters to be solvable
            continue
        solved += 1
        assert set(op.wire_currents) == {w.id for w in c.wires}, name
        types = {x.id: x.type for x in c.components}
        ends: dict[str, list[tuple[str, int]]] = {}
        for w in c.wires:
            ends.setdefault(w.a.key(), []).append((w.id, +1))  # current leaves terminal a
            ends.setdefault(w.b.key(), []).append((w.id, -1))
        for key, ws in ends.items():
            comp, term = key.split(".", 1)
            if len(ws) != 1 or op.wire_currents[ws[0][0]] is None:
                continue
            i_w = op.wire_currents[ws[0][0]]["I"]  # type: ignore[index]
            if types[comp] == "voltmeter" or (types[comp] == "wattmeter" and term[0] == "V"):
                assert abs(i_w) < 1e-9, (name, key)
                checked += 1
            elif types[comp] == "ammeter":
                i_a = op.readings[comp]["I"]
                assert i_a is not None
                assert abs(i_w) == pytest.approx(abs(i_a), rel=1e-6, abs=1e-12), (name, key)
                checked += 1
    assert solved > 40 and checked > 150


def test_dc_series_loop_carries_one_current_in_every_cable() -> None:
    c = dc.dc_winding("series", 10.0)
    op, is_dc = _solve(c, _spec_for("dc_motor.x"))
    assert is_dc
    volt = {x.id for x in c.components if x.type == "voltmeter"}
    series = [w.id for w in c.wires if not {w.a.component, w.b.component} & volt]
    vals = [op.wire_currents[w]["I"] for w in series]  # type: ignore[index]
    assert len(vals) >= 3
    assert {round(abs(x), 9) for x in vals} == {round(abs(vals[0]), 9)}
    assert abs(vals[0]) > 0


def test_redundant_parallel_cable_is_reported_undefined_and_changes_nothing() -> None:
    from vel.experiments.transformer3ph import templates as tr
    from vel.experiments.transformer3ph.spec import assumed_lab_transformer

    spec: TransformerSpec = assumed_lab_transformer()
    base = tr.no_load(380.0, 50.0)
    w0 = base.wires[0]
    doubled = base.model_copy(update={"wires": [*base.wires, w0.model_copy(update={"id": "dup"})]})
    op1, _ = _solve(base, spec)
    op2, _ = _solve(doubled, spec)
    assert op2.wire_currents["dup"] is None
    assert op2.wire_currents[w0.id] == op1.wire_currents[w0.id]
    assert op2.readings == op1.readings


def test_cable_branches_change_no_reading_and_are_off_by_default() -> None:
    from vel.experiments.induction_motor import templates as im

    spec = _spec_for("induction_motor.x")
    c = im.load_test(380.0, 50.0, "D", m_load=1.0)
    plain = operating_point(c, spec)
    wired = operating_point(c, spec, wire_currents=True)
    assert plain.wire_currents == {}
    assert set(wired.wire_currents) == {w.id for w in c.wires}
    for iid, r in plain.readings.items():
        for q, v in r.items():
            if v is not None:
                assert wired.readings[iid][q] == pytest.approx(v, rel=1e-6, abs=1e-9), (iid, q)
