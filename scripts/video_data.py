"""Data for the explanation videos (videos/data.json), computed by the lab's own studies.

Why: a curve in a video must be the curve the simulation draws, and a measured point must be a
real student reading. So the videos never compute physics of their own beyond the textbook
definitions they explain (for example, the sum of three phase MMFs in the rotating-field
video). Every model curve here comes from a study run through the same API the app uses, and
every measured point comes from vel.labdata.

Run from backend/:  ../.venv/bin/python ../scripts/video_data.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from vel.labdata import get
from vel.main import create_app

OUT = Path(__file__).resolve().parents[1] / "videos" / "data.json"


def table_rows(t: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(r) for r in t["rows"]]


def measured(
    dataset: str, kind: str, label: str | None = None
) -> list[dict[str, float]]:
    for t in get(dataset).tables:
        if t.study_kind == kind and (label is None or t.label == label):
            keys = [k for k, _ in t.columns]
            return [
                {k: v for k, v in zip(keys, r, strict=True) if v is not None}  # type: ignore[misc]
                for r in t.rows
            ]
    raise KeyError((dataset, kind, label))


def main() -> None:
    out: dict[str, Any] = {
        "source": "vel studies via the API; measured points from vel.labdata"
    }
    with TestClient(create_app(f"sqlite:///{tempfile.mkdtemp()}/v.db")) as c:

        def project(exp: str, preset: str | None = None) -> str:
            pid = c.post(
                "/api/projects", json={"name": "video", "experiment_id": exp}
            ).json()["id"]
            if preset:
                spec = next(
                    p
                    for p in c.get(f"/api/experiments/{exp}/presets").json()
                    if p["id"] == preset
                )["spec"]
                assert (
                    c.patch(f"/api/projects/{pid}", json={"spec": spec}).status_code
                    == 200
                )
            return pid

        def run(pid: str, kind: str, case: dict[str, Any]) -> dict[str, Any]:
            r = c.post(
                f"/api/projects/{pid}/runs", json={"study_kind": kind, "case": case}
            ).json()
            assert r["status"].startswith("success"), r
            return dict(r["result"])

        def params(res: dict[str, Any]) -> dict[str, float]:
            return {
                p["key"]: p["value"]
                for p in res["parameters"]
                if p.get("value") is not None
            }

        # ---------------------------------------------------- induction motor (experiment 2)
        pid = project("induction_motor", "ap3030_sheet_2026")
        spec = c.get(f"/api/projects/{pid}").json()["spec"]
        meas = measured("induction_motor_2026", "load")
        res = run(
            pid,
            "load",
            {
                "M_targets": [m["M"] for m in meas],
                "U_line": 380.0,
                "torque_speed_curve": True,
            },
        )
        out["induction"] = {
            "nameplate": spec["nameplate"],
            "ecm": spec["ecm"],
            "provenance_note": spec["provenance_note"],
            "load": table_rows(res["tables"][0]),
            "torque_speed": table_rows(res["tables"][1]),
            "parameters": params(res),
            "measured_load": meas,
        }

        # ---------------------------------------------------- synchronous machine (experiment 3)
        pid = project("synchronous")
        spec = c.get(f"/api/projects/{pid}").json()["spec"]
        occ = run(
            pid, "open_circuit", {"If_values": [round(0.1 * k, 2) for k in range(26)]}
        )
        scc = run(
            pid, "short_circuit", {"If_values": [0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4]}
        )
        pts = [
            {"P": p, "If": round(i, 2)}
            for p in (0.0, 100.0, 200.0)
            for i in [1.0 + 0.3 * k for k in range(18)]
        ]
        vc = run(pid, "v_curves", {"U_line": None, "points": pts})
        out["synchronous"] = {
            "nameplate": spec["nameplate"],
            "occ": table_rows(occ["tables"][0]),
            "scc": table_rows(scc["tables"][0]),
            "scc_parameters": params(scc),
            "v_curves": table_rows(vc["tables"][0]),
            "measured_occ": measured("synchronous_2026", "open_circuit"),
            "measured_scc": measured("synchronous_2026", "short_circuit"),
        }

        # ---------------------------------------------------- transformer (experiment 1)
        pid = project(
            "transformer3ph", "report_2025"
        )  # the transformer the 2025 table was measured on
        spec = c.get(f"/api/projects/{pid}").json()["spec"]
        nl = run(pid, "no_load", {"U_line_values": [40.0 * k for k in range(2, 13)]})
        sc = run(
            pid, "short_circuit", {"I_targets_pu": [0.1 * k for k in range(1, 11)]}
        )
        out["transformer"] = {
            "nameplate": spec["nameplate"],
            "ecm": spec["ecm"],
            "no_load": table_rows(nl["tables"][0]),
            "no_load_parameters": params(nl),
            "short_circuit": table_rows(sc["tables"][0]),
            "short_circuit_parameters": params(sc),
            "measured_short_circuit": measured("transformer_2025", "short_circuit"),
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float))
    print("written", OUT)


if __name__ == "__main__":
    main()
