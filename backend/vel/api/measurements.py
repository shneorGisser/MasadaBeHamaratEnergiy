"""Measurement sets, entries (append-only) and comparison (S3)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from vel.api.deps import SessionDep
from vel.api.projects import load_project
from vel.api.runs import RunOut, _full, load_run
from vel.api.workspace import GuardDep
from vel.errors import ApiError
from vel.labdata import by_experiment
from vel.orm import MeasurementSet
from vel.services import labdata as labdata_svc
from vel.services import measurements as ms
from vel.services import runs as runs_svc

router = APIRouter(prefix="/api", tags=["measurements"], dependencies=[GuardDep])


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


class CalibrateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # each knob: spec paths scaled together ("ecm.R1"); None = the study's defaults
    knobs: list[list[str]] | None = Field(default=None, max_length=6)


@router.post("/measurement-sets/{set_id}/calibrate")
def calibrate(set_id: str, body: CalibrateBody, session: SessionDep) -> dict[str, Any]:
    """Least-squares fit of a few spec parameters to this set. Returns a proposed spec;
    nothing is saved."""
    from vel.services.calibration import calibrate as run

    s = ms.load_set(session, set_id)
    return run(session, s, body.knobs)


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


class DatasetImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    study_kind: str | None = None
    table_index: int | None = Field(default=None, ge=0)


@router.get("/experiments/{experiment_id}/datasets")
def list_datasets(experiment_id: str) -> list[dict[str, Any]]:
    """Transcribed lab reports (previous years, the user's own) that can be imported."""
    return [labdata_svc.dataset_json(d) for d in by_experiment(experiment_id)]


@router.post("/projects/{project_id}/datasets/{dataset_id}/import", status_code=201)
def import_dataset(
    project_id: str, dataset_id: str, body: DatasetImport, session: SessionDep
) -> dict[str, Any]:
    p = load_project(session, project_id)
    sets = labdata_svc.import_dataset(session, p, dataset_id, body.study_kind, body.table_index)
    return {"sets": [ms.set_json(s) for s in sets]}


@router.post("/measurement-sets/{set_id}/probe")
def probe(set_id: str, session: SessionDep) -> dict[str, Any]:
    """Simulate the measured points with every parameter set of the experiment and rank them
    (nothing is persisted: the probe answers "which machine/setup fits this table")."""
    from vel.services.diagnose import probe_presets

    s = ms.load_set(session, set_id)
    p = ms.project_of(session, s)
    rows, _ = ms.raw_rows(session, s)
    circuit = runs_svc.current_circuit(session, p, s.study_kind)
    return {
        "set_id": s.id,
        "candidates": probe_presets(
            p.experiment_id, s.study_kind, s.conditions or {}, rows, p.spec_json, circuit
        ),
    }
