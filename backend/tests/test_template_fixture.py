"""The frontend draws and audits every template from a fixture; it must match the templates."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "export_templates.py"


def test_template_fixture_is_current() -> None:
    spec = importlib.util.spec_from_file_location("export_templates", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.FIXTURE.read_text(encoding="utf-8") == mod.render(mod.build()), (
        "template fixture is stale: run .venv/bin/python scripts/export_templates.py"
    )
