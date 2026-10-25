"""The wiring check compares nets, not cables: the same joints wired differently pass, a missing
joint and an extra one are reported with the evidence."""

from __future__ import annotations

from fastapi.testclient import TestClient

from vel.engine.circuit import CircuitModel
from vel.experiments import registry
from vel.services.wiring_check import check, compare, nets

MOD = registry.get("transformer3ph")
SPEC = MOD.default_spec()


def _tpl(kind: str, variant: str = "") -> CircuitModel:
    return MOD.studies[kind].default_circuit(SPEC, variant)  # type: ignore[misc,return-value]


def _clean(r: dict) -> bool:  # type: ignore[type-arg]
    return not any(
        r[k]
        for k in (
            "missing_components",
            "extra_components",
            "missing_connections",
            "extra_connections",
        )
    )


def test_W1_template_matches_itself_and_rewiring_the_same_nets_passes() -> None:
    t = _tpl("load")
    assert _clean(compare(t, t))
    # rewire every net as a star from its first terminal: other cables, the same joints
    doc = t.model_dump(mode="json")
    groups: dict[str, list[str]] = {}
    for term, root in nets(t).items():
        groups.setdefault(root, []).append(term)
    doc["wires"] = []
    for k, terms in enumerate(groups.values()):
        terms.sort(reverse=True)
        hub = terms[0].split(".")
        for j, other in enumerate(terms[1:]):
            o = other.split(".")
            doc["wires"].append(
                {
                    "id": f"s{k}_{j}",
                    "a": {"component": hub[0], "terminal": hub[1]},
                    "b": {"component": o[0], "terminal": o[1]},
                }
            )
    rewired = CircuitModel.model_validate(doc)
    assert {w.id for w in rewired.wires}.isdisjoint({w.id for w in t.wires})
    assert _clean(compare(rewired, t))


def test_W2_a_missing_and_an_extra_connection_are_reported() -> None:
    t = _tpl("load")
    doc = t.model_dump(mode="json")
    removed = doc["wires"].pop(0)
    a, b = removed["a"], removed["b"]
    r = compare(CircuitModel.model_validate(doc), t)
    assert len(r["missing_connections"]) == 1
    groups = r["missing_connections"][0]["student_groups"]
    assert any(f"{a['component']}.{a['terminal']}" in g for g in groups)
    assert any(f"{b['component']}.{b['terminal']}" in g for g in groups)
    # a short: L1 to L2 at the source
    doc = t.model_dump(mode="json")
    doc["wires"].append(
        {
            "id": "short",
            "a": {"component": "G", "terminal": "L1"},
            "b": {"component": "G", "terminal": "L2"},
        }
    )
    r = compare(CircuitModel.model_validate(doc), t)
    assert len(r["extra_connections"]) == 1 and r["missing_connections"] == []


def test_W3_the_closest_variant_is_chosen() -> None:
    variants = MOD.studies["vector_group"].variants
    templates = {v: _tpl("vector_group", v) for v in variants}
    for v in variants:
        res = check(templates[v], templates)
        assert res["variant"] == v and res["matches"], v


def test_W4_api(client: TestClient) -> None:
    pid = client.post(
        "/api/projects", json={"name": "ח", "experiment_id": "transformer3ph"}
    ).json()["id"]
    ok = client.get(f"/api/projects/{pid}/circuits/load/check").json()
    assert ok["matches"] and ok["messages"] == []
    doc = client.get(f"/api/projects/{pid}/circuits/load").json()["circuit"]
    doc["wires"] = doc["wires"][1:]
    assert client.put(f"/api/projects/{pid}/circuits/load", json=doc).status_code == 200
    bad = client.get(f"/api/projects/{pid}/circuits/load/check").json()
    assert not bad["matches"] and bad["messages"][0].startswith("חסר חיבור")
