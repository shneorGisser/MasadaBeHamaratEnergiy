"""Projects API (S0)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from vel.api.deps import SessionDep
from vel.errors import ApiError, not_found
from vel.experiments import registry
from vel.orm import Project

router = APIRouter(prefix="/api", tags=["projects"])


class ExperimentOut(BaseModel):
    id: str
    version: int
    title_he: str
    summary_he: str
    manual_ref: str
    equipment_he: str
    studies: list[str]


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    experiment_id: str


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=20000)
    spec: dict[str, Any] | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    experiment_id: str
    experiment_version: int
    spec: dict[str, Any]
    derived: dict[str, float]
    notes: str
    created_at: datetime
    updated_at: datetime


def _derived(spec_json: dict[str, Any], experiment_id: str) -> dict[str, float]:
    module = registry.get(experiment_id)
    return {k: float(v) for k, v in module.derived_spec(module.spec(spec_json)).items()}


def to_out(p: Project) -> ProjectOut:
    return ProjectOut(
        id=p.id,
        name=p.name,
        experiment_id=p.experiment_id,
        experiment_version=p.experiment_version,
        spec=p.spec_json,
        derived=_derived(p.spec_json, p.experiment_id),
        notes=p.notes,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def load_project(session: Session, project_id: str) -> Project:
    p = session.get(Project, project_id)
    if p is None:
        raise not_found("project", project_id)
    return p


@router.get("/experiments", response_model=list[ExperimentOut])
def list_experiments() -> list[ExperimentOut]:
    return [
        ExperimentOut(
            id=m.id,
            version=m.version,
            title_he=m.title_he,
            summary_he=m.summary_he,
            manual_ref=m.manual_ref,
            equipment_he=m.equipment_he,
            studies=list(m.studies),
        )
        for m in registry.all_modules()
    ]


@router.get("/experiments/{experiment_id}/presets")
def list_presets(experiment_id: str) -> list[dict[str, Any]]:
    try:
        module = registry.get(experiment_id)
    except KeyError as exc:
        raise ApiError(404, "not_found", f"no experiment {experiment_id}") from exc
    return [
        {"id": k, "label_he": label, "spec": fn().model_dump(mode="json")}
        for k, (label, fn) in module.presets.items()
    ]


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(session: SessionDep) -> list[ProjectOut]:
    rows = session.scalars(select(Project).order_by(Project.updated_at.desc())).all()
    return [to_out(p) for p in rows]


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, session: SessionDep) -> ProjectOut:
    try:
        module = registry.get(body.experiment_id)
    except KeyError as exc:
        raise ApiError(422, "unknown_experiment", str(exc)) from exc
    p = Project(
        name=body.name.strip(),
        experiment_id=module.id,
        experiment_version=module.version,
        spec_json=module.default_spec().model_dump(mode="json"),
        circuits_json={},
        notes="",
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return to_out(p)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: str, session: SessionDep) -> ProjectOut:
    return to_out(load_project(session, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: str, body: ProjectUpdate, session: SessionDep) -> ProjectOut:
    p = load_project(session, project_id)
    if body.name is not None:
        p.name = body.name.strip()
    if body.notes is not None:
        p.notes = body.notes
    if body.spec is not None:
        module = registry.get(p.experiment_id)
        try:
            spec = module.spec_model.model_validate(body.spec)
        except ValidationError as exc:
            raise ApiError(
                422,
                "invalid_spec",
                f"Equipment specification for {p.experiment_id} is invalid",
                [
                    {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                    for e in exc.errors(include_url=False, include_context=False)
                ],
            ) from exc
        p.spec_json = spec.model_dump(mode="json")
    session.commit()
    session.refresh(p)
    return to_out(p)


@router.get("/projects/{project_id}/export")
def export_project(project_id: str, session: SessionDep) -> dict[str, Any]:
    from vel.services.backup import export_project as _export

    return _export(session, load_project(session, project_id))


@router.post("/projects/import", response_model=ProjectOut, status_code=201)
def import_project(body: dict[str, Any], session: SessionDep) -> ProjectOut:
    from vel.services.backup import import_project as _import

    return to_out(_import(session, body))


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, session: SessionDep) -> Response:
    p = load_project(session, project_id)
    session.delete(p)
    session.commit()
    return Response(status_code=204)
