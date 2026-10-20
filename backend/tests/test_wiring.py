"""Wiring guide (services/wiring.py): every cable exactly once, current paths before voltage
leads, paths traced from the supply, IEC supply colours."""

from __future__ import annotations

from fastapi.testclient import TestClient

from vel.experiments import registry
from vel.experiments.dc_machine import templates as dc
from vel.services.wiring import guide


def all_template_circuits():  # type: ignore[no-untyped-def]
    for mod in registry.all_modules():
        spec = mod.default_spec()
        for kind, sd in mod.studies.items():
            if sd.default_circuit is None:
                continue
            for v in sd.variants or ("",):
                c = sd.default_circuit(spec, v)
                for cc in c.values() if isinstance(c, dict) else [c]:
                    yield f"{mod.id}.{kind}.{v}", cc


def test_every_template_cable_appears_once_and_voltage_leads_last() -> None:
    n = 0
    for name, c in all_template_circuits():
        g = guide(c)
        ids = [s["wire_id"] for s in g["steps"]]
        assert sorted(ids) == sorted(w.id for w in c.wires), name
        kinds = [s["kind"] for s in g["steps"]]
        assert kinds == sorted(kinds, key=lambda k: k == "measure"), name  # measure only at the end
        for s in g["steps"]:
            ends = {
                (s["from"]["type"], s["from"]["terminal"]),
                (s["to"]["type"], s["to"]["terminal"]),
            }
            is_v = bool(
                ends
                & {("voltmeter", "p"), ("voltmeter", "n"), ("wattmeter", "Vp"), ("wattmeter", "Vn")}
            )
            assert is_v == (s["kind"] == "measure"), (name, s)
        n += 1
    assert n > 50


def test_dc_motor_paths_are_traced_from_plus_through_the_instruments() -> None:
    g = guide(dc.motor(174, 0, series="cumulative"))
    path = [
        (s["from"]["component"], s["from"]["terminal"], s["to"]["component"], s["to"]["terminal"])
        for s in g["steps"]
    ]
    assert path[:3] == [("P", "P", "Rf", "p"), ("Rf", "n", "Af", "p"), ("Af", "n", "M", "F1")]
    assert path[3:6] == [("P", "P", "Rx", "p"), ("Rx", "n", "Aa", "p"), ("Aa", "n", "M", "A1")]
    assert g["steps"][0]["colour_he"] == "אדום"
    assert any("בטור" in a for a in g["steps"][1]["advice"])
    assert g["groups"][-1]["kind"] == "measure"
    assert "11 כבלים" in g["after"][0]


def test_three_phase_colours_and_star_bridges_after_the_phases() -> None:
    mod = registry.get("induction_motor")
    c = mod.studies["load"].default_circuit(mod.default_spec(), "")  # type: ignore[misc]
    g = guide(c)  # type: ignore[arg-type]
    first = g["steps"][0]
    assert (first["from"]["terminal"], first["colour_he"]) == ("L1", "חום")
    colours = {
        s["from"]["terminal"]: s["colour_he"] for s in g["steps"] if s["from"]["type"] == "source3"
    }
    assert colours.get("L2") == "שחור" and colours.get("L3") == "אפור"


def test_api(client: TestClient) -> None:
    pid = client.post("/api/projects", json={"name": "w", "experiment_id": "dc_motor"}).json()["id"]
    r = client.get(f"/api/projects/{pid}/circuits/load/wiring")
    assert r.status_code == 200 and len(r.json()["steps"]) == 10  # shunt: no series cables
    assert client.get(f"/api/projects/{pid}/circuits/dc_resistance/wiring").status_code == 409
