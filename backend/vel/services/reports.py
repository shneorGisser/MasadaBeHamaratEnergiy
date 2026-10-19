"""Guided-mode status and immutable laboratory reports.

A report stores a full snapshot of every number it shows (runs, measurement values at the time
of publication, comparison). Later corrections or new runs never change a published report.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from vel.errors import ApiError
from vel.experiments.transformer3ph import guide
from vel.experiments.transformer3ph.spec import TransformerSpec
from vel.experiments.transformer3ph.studies import MODEL_VERSION, STUDIES
from vel.orm import MeasurementSet, Project, Report, SimulationRun
from vel.services import measurements as ms

OK = ("success", "success_with_warnings")


# --------------------------------------------------------------------------- guide


def guide_status(session: Session, p: Project) -> dict[str, Any]:
    runs = list(session.scalars(select(SimulationRun).where(SimulationRun.project_id == p.id)))
    sets = list(session.scalars(select(MeasurementSet).where(MeasurementSet.project_id == p.id)))
    n_reports = len(list(session.scalars(select(Report.id).where(Report.project_id == p.id))))
    acks = set((p.guide_state or {}).get("acknowledged", []))
    out = []
    for st in guide.steps():
        done = False
        detail = ""
        if st.kind == "ack":
            done = st.id in acks
        elif st.kind == "spec":
            done = p.transformer_json.get("provenance") != "assumed" or st.id in acks
            if done and p.transformer_json.get("provenance") == "assumed":
                detail = "ממשיכים עם ערכים מוערכים (אושר)"
        elif st.kind == "simulate":
            done = any(r.study_kind == st.study and r.status in OK for r in runs)
        elif st.kind == "measure":
            complete = 0
            for s in sets:
                if s.study_kind != st.study:
                    continue
                rows, _ = ms.raw_rows(session, s)
                keys = [c.key for c in ms.mdef(s.study_kind).columns]
                complete = max(
                    complete, sum(1 for r in rows if all(r.get(k) is not None for k in keys))
                )
            done = complete >= 1
            detail = f"{complete} שורות מלאות" if complete else ""
        elif st.kind == "compare":
            has_run = any(r.study_kind == st.study and r.status in OK for r in runs)
            has_set = any(s.study_kind == st.study for s in sets)
            done = has_run and has_set
        elif st.kind == "report":
            done = n_reports > 0
        out.append(
            {
                "id": st.id,
                "kind": st.kind,
                "title_he": st.title_he,
                "body_he": st.body_he,
                "study": st.study,
                "done": done,
                "detail": detail,
            }
        )
    return {"steps": out, "done": sum(1 for s in out if s["done"]), "total": len(out)}


def acknowledge(session: Session, p: Project, step_id: str) -> None:
    valid = {s.id for s in guide.steps() if s.kind in ("ack", "spec")}
    if step_id not in valid:
        raise ApiError(
            422, "not_acknowledgeable", f"step {step_id} is completed by data, not by a click"
        )
    state = dict(p.guide_state or {})
    acks = list(dict.fromkeys([*state.get("acknowledged", []), step_id]))
    p.guide_state = {**state, "acknowledged": acks}
    session.commit()


# --------------------------------------------------------------------------- reports


def build_snapshot(
    session: Session, p: Project, sections: list[dict[str, Any]], title: str, discussion: str
) -> dict[str, Any]:
    out_sections = []
    for sec in sections:
        kind = sec.get("study_kind")
        if kind not in STUDIES:
            raise ApiError(422, "unknown_study", f"unknown study {kind}")
        run = session.get(SimulationRun, sec.get("run_id")) if sec.get("run_id") else None
        if run is not None and (run.project_id != p.id or run.study_kind != kind):
            raise ApiError(
                422, "bad_run", f"run {run.id} does not belong to {kind} in this project"
            )
        mset = session.get(MeasurementSet, sec.get("set_id")) if sec.get("set_id") else None
        if mset is not None and (mset.project_id != p.id or mset.study_kind != kind):
            raise ApiError(422, "bad_set", f"measurement set does not belong to {kind}")
        if run is None and mset is None:
            raise ApiError(422, "empty_section", f"section {kind} needs a run or a measurement set")
        entry: dict[str, Any] = {
            "study_kind": kind,
            "title_he": STUDIES[kind].title_he,
            "manual_ref": STUDIES[kind].manual_ref,
        }
        if run is not None:
            entry["run"] = {
                "id": run.id,
                "status": run.status,
                "label": run.label,
                "input_hash": run.input_hash,
                "model_version": run.model_version,
                "created_at": run.created_at.isoformat(),
                "case": run.input_snapshot.get("case"),
                "circuit_summary": _circuit_summary(run.input_snapshot.get("circuit")),
                "transformer": run.input_snapshot.get("transformer"),
                "warnings": run.warnings,
                "error": run.error,
                "result": run.result,
            }
        if mset is not None:
            rows, missing = ms.raw_rows(session, mset)
            spec = TransformerSpec.model_validate(p.transformer_json)
            view = ms.set_view(session, mset, spec)
            entry["measurements"] = {
                "set": ms.set_json(mset),
                "columns": view["definition"]["columns"],
                "derived_columns": view["derived_columns"],
                "rows": rows,
                "missing": missing,
                "analysis": view["analysis"],
                "entry_ids": {k: v["entry_id"] for k, v in view["cells"].items()},
                "corrected_cells": [k for k, v in view["cells"].items() if v["versions"] > 1],
            }
        if run is not None and mset is not None and run.result is not None:
            rows, _ = ms.raw_rows(session, mset)
            entry["comparison"] = ms.compare(run, mset, rows, "simulation")
        out_sections.append(entry)
    return {
        "title": title,
        "project": {"id": p.id, "name": p.name},
        "experiment": {"id": p.experiment_id, "version": p.experiment_version},
        "transformer": p.transformer_json,
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "discussion": discussion,
        "sections": out_sections,
    }


def _circuit_summary(c: Any) -> dict[str, Any] | None:
    if not isinstance(c, dict) or "components" not in c:
        return None
    return {
        "components": [f"{x['id']} ({x['type']})" for x in c["components"]],
        "n_wires": len(c.get("wires", [])),
    }


def _fmt(v: Any, sig: int = 4) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "כן" if v else "לא"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (int, float)):
        if v == 0:
            return "0"
        a = abs(v)
        if a >= 1e6 or a < 1e-3:
            return f"{v:.{sig - 1}e}"
        import math

        digits = max(0, sig - 1 - math.floor(math.log10(a)))
        return f"{v:.{min(digits, 6)}f}"
    return str(v)


def _pct(v: Any) -> str:
    return "—" if v is None else f"{100 * v:.2f}%"


_ENV = Environment(autoescape=select_autoescape(default=True, default_for_string=True))
_ENV.filters["f"] = _fmt
_ENV.filters["pct"] = _pct

TEMPLATE = _ENV.from_string(
    (Path(__file__).parent / "report_template.html").read_text(encoding="utf-8")
)


def render(snapshot: dict[str, Any]) -> str:
    return TEMPLATE.render(s=snapshot)


def create_report(
    session: Session, p: Project, title: str, sections: list[dict[str, Any]], discussion: str
) -> Report:
    snap = build_snapshot(session, p, sections, title, discussion)
    r = Report(
        project_id=p.id,
        status="published",
        title=title,
        sources={"sections": sections, "snapshot": snap},
        student_discussion=discussion,
        html=render(snap),
    )
    session.add(r)
    session.commit()
    session.refresh(r)
    return r


def chromium_path() -> str | None:
    for cand in (
        os.environ.get("VEL_CHROMIUM"),
        "/opt/pw-browsers/chromium",
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("google-chrome"),
    ):
        if cand and Path(cand).exists():
            return cand
    return None


def pdf(report: Report) -> bytes:
    exe = chromium_path()
    if exe is None:
        raise ApiError(
            501,
            "pdf_unavailable",
            "no Chromium found for PDF rendering; use print from the browser",
        )
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "report.html"
        out = Path(tmp) / "report.pdf"
        src.write_text(report.html, encoding="utf-8")
        cmd = [
            exe,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={out}",
            src.as_uri(),
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
        if not out.exists():
            raise ApiError(500, "pdf_failed", "PDF rendering failed", proc.stderr.decode()[-500:])
        return out.read_bytes()
