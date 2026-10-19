"""Studies, circuits and simulation runs (S1)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from vel.api.deps import SessionDep
from vel.api.projects import load_project
from vel.engine.netlist import catalog_json
from vel.errors import not_found
from vel.orm import SimulationRun
from vel.services import runs as svc

router = APIRouter(prefix="/api", tags=["runs"])


class StudyOut(BaseModel):
    kind: str
    title_he: str
    manual_ref: str
    default_case: dict[str, Any]
    variants: list[str]
    editable_circuit: bool


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    study_kind: str
    case: dict[str, Any]
    label: str = Field(default="", max_length=200)


class RunSummary(BaseModel):
    id: str
    project_id: str
    study_kind: str
    label: str
    status: str
    model_version: str
    input_hash: str
    n_warnings: int
    created_at: datetime


class RunOut(RunSummary):
    input_snapshot: dict[str, Any]
    warnings: list[Any]
    error: dict[str, Any] | None
    result: dict[str, Any] | None


class ResetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variant: str = ""


def _summary(r: SimulationRun) -> RunSummary:
    return RunSummary(
        id=r.id,
        project_id=r.project_id,
        study_kind=r.study_kind,
        label=r.label,
        status=r.status,
        model_version=r.model_version,
        input_hash=r.input_hash,
        n_warnings=len(r.warnings or []),
        created_at=r.created_at,
    )


def _full(r: SimulationRun) -> RunOut:
    return RunOut(
        **_summary(r).model_dump(),
        input_snapshot=r.input_snapshot,
        warnings=r.warnings or [],
        error=r.error,
        result=r.result,
    )


@router.get("/components")
def components() -> list[dict[str, Any]]:
    return catalog_json()


@router.get("/projects/{project_id}/studies", response_model=list[StudyOut])
def list_studies(project_id: str, session: SessionDep) -> list[StudyOut]:
    p = load_project(session, project_id)
    spec = svc.project_spec(p)
    studies = svc.module_of(p).studies
    return [
        StudyOut(
            kind=sd.kind,
            title_he=sd.title_he,
            manual_ref=sd.manual_ref,
            default_case=sd.default_case(spec),
            variants=list(sd.variants),
            editable_circuit=sd.editable_circuit,
        )
        for sd in studies.values()
    ]


@router.get("/projects/{project_id}/circuits/{kind}")
def get_circuit(project_id: str, kind: str, session: SessionDep) -> Any:
    p = load_project(session, project_id)
    return {"kind": kind, "circuit": svc.current_circuit(session, p, kind)}


@router.put("/projects/{project_id}/circuits/{kind}")
def put_circuit(project_id: str, kind: str, body: dict[str, Any], session: SessionDep) -> Any:
    p = load_project(session, project_id)
    return {"kind": kind, "circuit": svc.save_circuit(session, p, kind, body)}


@router.post("/projects/{project_id}/circuits/{kind}/reset")
def reset_circuit(project_id: str, kind: str, body: ResetBody, session: SessionDep) -> Any:
    p = load_project(session, project_id)
    doc = svc.template_circuit(p, kind, body.variant)
    if doc is None:
        return {"kind": kind, "circuit": None}
    return {"kind": kind, "circuit": svc.save_circuit(session, p, kind, doc)}


class LiveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


@router.post("/projects/{project_id}/circuits/{kind}/operating-point")
def live_operating_point(
    project_id: str, kind: str, body: LiveBody, session: SessionDep
) -> dict[str, Any]:
    """One steady-state solution of the stored circuit with temporary parameter overrides
    (variac setting, switch state) — used by the 3D bench. Not persisted."""
    p = load_project(session, project_id)
    return svc.live_point(session, p, kind, body.overrides)


@router.post("/projects/{project_id}/runs", response_model=RunOut, status_code=201)
def create_run(project_id: str, body: RunCreate, session: SessionDep) -> RunOut:
    p = load_project(session, project_id)
    return _full(svc.create_run(session, p, body.study_kind, body.case, body.label))


@router.get("/projects/{project_id}/runs", response_model=list[RunSummary])
def list_runs(
    project_id: str, session: SessionDep, study_kind: str | None = None
) -> list[RunSummary]:
    load_project(session, project_id)
    q = select(SimulationRun).where(SimulationRun.project_id == project_id)
    if study_kind:
        q = q.where(SimulationRun.study_kind == study_kind)
    rows = session.scalars(q.order_by(SimulationRun.created_at.desc())).all()
    return [_summary(r) for r in rows]


def load_run(session: SessionDep, run_id: str) -> SimulationRun:
    r = session.get(SimulationRun, run_id)
    if r is None:
        raise not_found("run", run_id)
    return r


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, session: SessionDep) -> RunOut:
    return _full(load_run(session, run_id))


@router.post("/runs/{run_id}/reproduce")
def reproduce_run(run_id: str, session: SessionDep) -> dict[str, Any]:
    return svc.reproduce(load_run(session, run_id))
