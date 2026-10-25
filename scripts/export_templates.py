"""Write every template circuit (and the component catalog) to the frontend's test fixture.

The frontend's router test draws each template and audits the drawing; the fixture is what it
draws. Run after changing a template: `.venv/bin/python scripts/export_templates.py`.
backend/tests/test_template_fixture.py fails when the fixture is stale."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "frontend" / "src" / "schematic" / "__fixtures__" / "templates.json"


def build() -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "backend"))
    from vel.engine.netlist import catalog_json
    from vel.experiments import registry

    templates = []
    for m in registry.all_modules():
        spec = m.default_spec()
        for kind, s in m.studies.items():
            if not (s.editable_circuit and s.default_circuit):
                continue
            for v in s.variants or ("",):
                c = s.default_circuit(spec, v)
                name = f"{m.id}/{kind}" + (f"/{v}" if v else "")
                templates.append({"name": name, "circuit": c.model_dump(mode="json")})
    return {"catalog": catalog_json(), "templates": templates}


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


if __name__ == "__main__":
    FIXTURE.write_text(render(build()), encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(ROOT)}")
