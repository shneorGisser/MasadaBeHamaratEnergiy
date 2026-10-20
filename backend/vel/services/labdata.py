"""Import a transcribed lab report (vel.labdata) into a project as measurement sets.

The import goes through the same append-only entry path as typing the values by hand (unit
conversion, validation), and every entry carries a note saying where it came from."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from vel.errors import ApiError
from vel.labdata import DATASETS, Dataset, DTable
from vel.orm import MeasurementSet, Project
from vel.services import measurements as ms


def dataset_json(d: Dataset) -> dict[str, Any]:
    return {
        "id": d.id,
        "experiment_id": d.experiment_id,
        "title_he": d.title_he,
        "source_he": d.source_he,
        "tables": [
            {
                "index": i,
                "study_kind": t.study_kind,
                "label": t.label,
                "n_rows": len(t.rows),
                "conditions": t.conditions,
                "note": t.note,
            }
            for i, t in enumerate(d.tables)
        ],
    }


def _import_table(session: Session, p: Project, d: Dataset, t: DTable) -> MeasurementSet:
    md = ms.mdef(p.experiment_id, t.study_kind)
    idx = list(t.row_index) if t.row_index is not None else list(range(len(t.rows)))
    n_rows = len(md.row_labels) if md.rows == "fixed" else max(len(t.rows), 1)
    s = MeasurementSet(
        project_id=p.id,
        study_kind=t.study_kind,
        label=f"{d.title_he} · {t.label}",
        notes="\n".join(x for x in (f"מקור: {d.source_he}", t.note) if x),
        conditions=dict(t.conditions),
        n_rows=n_rows,
    )
    session.add(s)
    session.commit()
    session.refresh(s)
    for k, row in enumerate(t.rows):
        note = " · ".join(x for x in (f"מיובא: {d.title_he}, {t.label}", t.row_notes.get(k)) if x)
        for (key, unit), value in zip(t.columns, row, strict=True):
            if value is None:
                continue
            ms.add_entry(
                session,
                s,
                row_index=idx[k],
                quantity=key,
                value=float(value),
                unit=unit,
                instrument_range="",
                note=note,
            )
    return s


def import_dataset(
    session: Session,
    p: Project,
    dataset_id: str,
    study_kind: str | None = None,
    table_index: int | None = None,
) -> list[MeasurementSet]:
    d = DATASETS.get(dataset_id)
    if d is None:
        raise ApiError(404, "not_found", f"no dataset {dataset_id}")
    if d.experiment_id != p.experiment_id:
        raise ApiError(
            422, "experiment_mismatch", f"dataset {dataset_id} belongs to {d.experiment_id}"
        )
    tables = [
        t
        for i, t in enumerate(d.tables)
        if (study_kind is None or t.study_kind == study_kind)
        and (table_index is None or i == table_index)
    ]
    if not tables:
        raise ApiError(422, "no_tables", f"dataset {dataset_id} has no table for {study_kind}")
    return [_import_table(session, p, d, t) for t in tables]
