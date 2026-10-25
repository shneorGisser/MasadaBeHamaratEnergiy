"""The vlab scripting API (frontend/src/scripting/prelude.py), exercised in CPython with a fake
JS bridge: failures must raise, malformed plots must be rejected, helpers must find data."""

from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path

import pytest

PRELUDE = Path(__file__).parents[2] / "frontend" / "src" / "scripting" / "prelude.py"


def _load(run_response: dict, plots: list):  # type: ignore[no-untyped-def,type-arg]
    js = types.ModuleType("_vlab_js")

    async def studies() -> str:
        return json.dumps([{"kind": "load_flow", "default_case": {"scales": [1.0]}}])

    async def run(study: str, case: str, label: str) -> str:
        js.last = (study, json.loads(case), label)  # type: ignore[attr-defined]
        return json.dumps(run_response)

    js.studies = studies  # type: ignore[attr-defined]
    js.run = run  # type: ignore[attr-defined]
    js.plot = plots.append  # type: ignore[attr-defined]
    sys.modules["_vlab_js"] = js
    mod = types.ModuleType("vlab")
    exec(PRELUDE.read_text(), mod.__dict__)
    return mod, js


OK = {
    "status": "success",
    "result": {
        "tables": [{"id": "sweep", "rows": [{"k": 0.5, "u": 99.0}, {"k": 1.0, "u": 98.0}]}],
        "parameters": [{"key": "dU", "value": 2.0}],
    },
}


def test_run_merges_defaults_and_helpers_find_data() -> None:
    vlab, js = _load(OK, [])
    r = asyncio.run(vlab.run("load_flow", label="x", scales=[0.5, 1.0]))
    assert js.last == ("load_flow", {"scales": [0.5, 1.0]}, "x")
    assert vlab.column(r, "u", "sweep") == [99.0, 98.0]
    assert vlab.table(r)[0]["k"] == 0.5 and vlab.param(r, "dU") == 2.0
    with pytest.raises(KeyError):
        vlab.table(r, "nope")
    with pytest.raises(KeyError):
        asyncio.run(vlab.run("no_such_study"))


def test_failed_run_raises_instead_of_returning_nothing() -> None:
    vlab, _ = _load({"status": "invalid_input", "error": {"message": "bad scales"}}, [])
    with pytest.raises(vlab.RunFailed, match="bad scales"):
        asyncio.run(vlab.run("load_flow"))


def test_plot_validates_lengths_and_serialises() -> None:
    plots: list[str] = []
    vlab, _ = _load(OK, plots)
    vlab.plot([1, 2], [3, None], labels=["a"], title="t")
    spec = json.loads(plots[0])
    assert spec["series"] == [{"name": "a", "y": [3.0, None]}] and spec["x"] == [1.0, 2.0]
    with pytest.raises(ValueError):
        vlab.plot([1, 2], [1])
    with pytest.raises(ValueError):
        vlab.plot([1, 2])
