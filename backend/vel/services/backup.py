"""Project export / import (backup and recovery, moving a project between machines).

Import creates NEW ids for everything and remaps internal references (run → project,
entry → set, correction → superseded entry). Run snapshots, hashes and report snapshots are
copied verbatim, so imported runs stay reproducible and reports stay byte-identical.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from vel.errors import ApiError
from vel.experiments import registry
from vel.orm import MeasurementEntry, MeasurementSet, Project, Report, SimulationRun

FORMAT = "virtual-energy-lab/project"
VERSION = 1


def _iso(d: datetime) -> str:
    return d.isoformat()


def export_project(session: Session, p: Project) -> dict[str, Any]:
    runs = session.scalars(
        select(SimulationRun)
        .where(SimulationRun.project_id == p.id)
        .order_by(SimulationRun.created_at)
    )
    sets = list(
        session.scalars(
            select(MeasurementSet)
            .where(MeasurementSet.project_id == p.id)
            .order_by(MeasurementSet.created_at)
        )
    )
    reports = session.scalars(
        select(Report).where(Report.project_id == p.id).order_by(Report.created_at)
    )
    out_sets = []
    for s in sets:
        entries = session.scalars(
            select(MeasurementEntry)
            .where(MeasurementEntry.set_id == s.id)
            .order_by(MeasurementEntry.created_at, MeasurementEntry.id)
        )
        out_sets.append(
            {
                "id": s.id,
                "study_kind": s.study_kind,
                "label": s.label,
                "lab_date": s.lab_date,
                "instruments": s.instruments,
                "notes": s.notes,
                "conditions": s.conditions,
                "n_rows": s.n_rows,
                "created_at": _iso(s.created_at),
                "entries": [
                    {
                        "id": e.id,
                        "row_index": e.row_index,
                        "quantity": e.quantity,
                        "value_si": e.value_si,
                        "entered_value": e.entered_value,
                        "entered_unit": e.entered_unit,
                        "instrument_range": e.instrument_range,
                        "note": e.note,
                        "supersedes_id": e.supersedes_id,
                        "created_at": _iso(e.created_at),
                    }
                    for e in entries
                ],
            }
        )
    return {
        "format": FORMAT,
        "version": VERSION,
        "project": {
            "id": p.id,
            "name": p.name,
            "experiment_id": p.experiment_id,
            "experiment_version": p.experiment_version,
            "transformer": p.transformer_json,
            "circuits": p.circuits_json,
            "notes": p.notes,
            "guide_state": p.guide_state,
            "created_at": _iso(p.created_at),
        },
        "runs": [
            {
                "id": r.id,
                "study_kind": r.study_kind,
                "label": r.label,
                "input_snapshot": r.input_snapshot,
                "input_hash": r.input_hash,
                "model_version": r.model_version,
                "status": r.status,
                "warnings": r.warnings,
                "error": r.error,
                "result": r.result,
                "created_at": _iso(r.created_at),
            }
            for r in runs
        ],
        "measurement_sets": out_sets,
        "reports": [
            {
                "id": r.id,
                "status": r.status,
                "title": r.title,
                "sources": r.sources,
                "student_discussion": r.student_discussion,
                "html": r.html,
                "created_at": _iso(r.created_at),
            }
            for r in reports
        ],
    }


def new() -> str:
    return str(uuid.uuid4())


def import_project(session: Session, doc: dict[str, Any]) -> Project:
    if doc.get("format") != FORMAT or doc.get("version") != VERSION:
        raise ApiError(422, "bad_format", f"expected {FORMAT} v{VERSION}")
    pj = doc["project"]
    try:
        module = registry.get(pj["experiment_id"])
        module.spec_model.model_validate(pj["transformer"])
    except Exception as exc:
        raise ApiError(422, "bad_project", f"project data is invalid: {exc}") from exc
    p = Project(
        id=new(),
        name=f"{pj['name']} (שוחזר)",
        experiment_id=pj["experiment_id"],
        experiment_version=pj["experiment_version"],
        transformer_json=pj["transformer"],
        circuits_json=pj.get("circuits") or {},
        notes=pj.get("notes", ""),
        guide_state=pj.get("guide_state") or {},
    )
    session.add(p)
    session.flush()
    for r in doc.get("runs", []):
        session.add(
            SimulationRun(
                id=new(),
                project_id=p.id,
                study_kind=r["study_kind"],
                label=r["label"],
                input_snapshot=r["input_snapshot"],
                input_hash=r["input_hash"],
                model_version=r["model_version"],
                status=r["status"],
                warnings=r["warnings"],
                error=r["error"],
                result=r["result"],
                created_at=datetime.fromisoformat(r["created_at"]),
            )
        )
    for s in doc.get("measurement_sets", []):
        ms = MeasurementSet(
            id=new(),
            project_id=p.id,
            study_kind=s["study_kind"],
            label=s["label"],
            lab_date=s["lab_date"],
            instruments=s["instruments"],
            notes=s["notes"],
            conditions=s["conditions"],
            n_rows=s["n_rows"],
            created_at=datetime.fromisoformat(s["created_at"]),
        )
        session.add(ms)
        session.flush()
        idmap: dict[str, str] = {}
        for e in s["entries"]:
            nid = new()
            idmap[e["id"]] = nid
            session.add(
                MeasurementEntry(
                    id=nid,
                    set_id=ms.id,
                    row_index=e["row_index"],
                    quantity=e["quantity"],
                    value_si=e["value_si"],
                    entered_value=e["entered_value"],
                    entered_unit=e["entered_unit"],
                    instrument_range=e["instrument_range"],
                    note=e["note"],
                    supersedes_id=idmap.get(e["supersedes_id"]) if e["supersedes_id"] else None,
                    created_at=datetime.fromisoformat(e["created_at"]),
                )
            )
            session.flush()
    for r in doc.get("reports", []):
        session.add(
            Report(
                id=new(),
                project_id=p.id,
                status=r["status"],
                title=r["title"],
                sources=r["sources"],
                student_discussion=r["student_discussion"],
                html=r["html"],
                created_at=datetime.fromisoformat(r["created_at"]),
            )
        )
    session.commit()
    session.refresh(p)
    return p
