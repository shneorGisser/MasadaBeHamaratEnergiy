"""Measurement sets, entries (append-only) and comparison (S3)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from vel.api.deps import SessionDep
from vel.api.projects import load_project
from vel.api.runs import RunOut, _full, load_run
from vel.errors import ApiError
from vel.orm import MeasurementSet
from vel.services import measurements as ms
from vel.services import runs as runs_svc

router = APIRouter(prefix="/api", tags=["measurements"])


class SetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    study_kind: str
    label: str = Field(default="", max_length=200)
    lab_date: str = Field(default="", max_length=20)
    instruments: str = Field(default="", max_length=5000)
    notes: str = Field(default="", max_length=20000)
    conditions: dict[str, Any] = Field(default_factory=dict)
    n_rows: int | None = Field(default=None, ge=1, le=60)


class SetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str | None = Field(default=None, max_length=200)
    lab_date: str | None = Field(default=None, max_length=20)
    instruments: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=20000)
    conditions: dict[str, Any] | None = None
    n_rows: int | None = Field(default=None, ge=1, le=60)


class EntryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_index: int = Field(ge=0)
    quantity: str
    value: float
    unit: str
    instrument_range: str = Field(default="", max_length=60)
    note: str = Field(default="", max_length=2000)


@router.get("/projects/{project_id}/measurement-sets")
def list_sets(
    project_id: str, session: SessionDep, study_kind: str | None = None
) -> list[dict[str, Any]]:
    load_project(session, project_id)
    q = select(MeasurementSet).where(MeasurementSet.project_id == project_id)
    if study_kind:
        q = q.where(MeasurementSet.study_kind == study_kind)
    return [ms.set_json(s) for s in session.scalars(q.order_by(MeasurementSet.created_at.desc()))]


@router.post("/projects/{project_id}/measurement-sets", status_code=201)
def create_set(project_id: str, body: SetCreate, session: SessionDep) -> dict[str, Any]:
    p = load_project(session, project_id)
    d = ms.mdef(p.experiment_id, body.study_kind)
    n_rows = len(d.row_labels) if d.rows == "fixed" else body.n_rows or 6
    unknown = set(body.conditions) - set(d.condition_keys)
    if unknown:
        raise ApiError(422, "unknown_condition", f"unknown conditions: {sorted(unknown)}")
    s = MeasurementSet(
        project_id=p.id,
        study_kind=body.study_kind,
        label=body.label,
        lab_date=body.lab_date,
        instruments=body.instruments,
        notes=body.notes,
        conditions=body.conditions,
        n_rows=n_rows,
    )
    session.add(s)
    session.commit()
    session.refresh(s)
    return ms.set_view(session, s)


@router.get("/measurement-sets/{set_id}")
def get_set(set_id: str, session: SessionDep) -> dict[str, Any]:
    s = ms.load_set(session, set_id)
    return ms.set_view(session, s)


@router.patch("/measurement-sets/{set_id}")
def update_set(set_id: str, body: SetUpdate, session: SessionDep) -> dict[str, Any]:
    """Metadata only. Measured values are never edited in place (see /entries)."""
    s = ms.load_set(session, set_id)
    d = ms.mdef(ms.project_of(session, s).experiment_id, s.study_kind)
    for k in ("label", "lab_date", "instruments", "notes"):
        v = getattr(body, k)
        if v is not None:
            setattr(s, k, v)
    if body.conditions is not None:
        unknown = set(body.conditions) - set(d.condition_keys)
        if unknown:
            raise ApiError(422, "unknown_condition", f"unknown conditions: {sorted(unknown)}")
        s.conditions = body.conditions
    if body.n_rows is not None:
        if d.rows == "fixed":
            raise ApiError(409, "fixed_rows", "this table has a fixed number of rows")
        current, _ = ms.current_entries(session, s)
        if any(r >= body.n_rows for r, _q in current):
            raise ApiError(409, "rows_in_use", "cannot remove rows that contain measurements")
        s.n_rows = body.n_rows
    session.commit()
    return ms.set_view(session, s)


@router.post("/measurement-sets/{set_id}/entries", status_code=201)
def add_entry(set_id: str, body: EntryCreate, session: SessionDep) -> dict[str, Any]:
    s = ms.load_set(session, set_id)
    ms.add_entry(
        session,
        s,
        row_index=body.row_index,
        quantity=body.quantity,
        value=body.value,
        unit=body.unit,
        instrument_range=body.instrument_range,
        note=body.note,
    )
    return ms.set_view(session, s)


@router.post("/measurement-sets/{set_id}/simulate", response_model=RunOut, status_code=201)
def simulate_at_measured_points(set_id: str, session: SessionDep) -> RunOut:
    s = ms.load_set(session, set_id)
    p = ms.project_of(session, s)
    rows, _ = ms.raw_rows(session, s)
    case = ms.matching_case(session, s, rows)
    label = f"בנקודות המדידה של: {s.label or s.id[:8]}"
    return _full(runs_svc.create_run(session, p, s.study_kind, case, label))


@router.get("/comparison")
def comparison(
    run_id: str,
    set_id: str,
    session: SessionDep,
    reference: Literal["simulation", "measurement"] = "simulation",
) -> dict[str, Any]:
    run = load_run(session, run_id)
    s = ms.load_set(session, set_id)
    if run.project_id != s.project_id:
        raise ApiError(422, "project_mismatch", "run and set belong to different projects")
    rows, _ = ms.raw_rows(session, s)
    return ms.compare(session, run, s, rows, reference)
