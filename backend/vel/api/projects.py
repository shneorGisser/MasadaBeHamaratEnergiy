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


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    experiment_id: str


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=20000)
    transformer: dict[str, Any] | None = None


class ProjectOut(BaseModel):
    id: str
    name: str
    experiment_id: str
    experiment_version: int
    transformer: dict[str, Any]
    derived: dict[str, float]
    notes: str
    created_at: datetime
    updated_at: datetime


def _derived(spec_json: dict[str, Any], experiment_id: str) -> dict[str, float]:
    module = registry.get(experiment_id)
    spec = module.spec_model.model_validate(spec_json)
    keys = ("U1_winding", "U2_winding", "turns_ratio", "I1n_line", "I2n_line")
    return {k: float(getattr(spec, k)) for k in keys if hasattr(spec, k)}


def to_out(p: Project) -> ProjectOut:
    return ProjectOut(
        id=p.id,
        name=p.name,
        experiment_id=p.experiment_id,
        experiment_version=p.experiment_version,
        transformer=p.transformer_json,
        derived=_derived(p.transformer_json, p.experiment_id),
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
        )
        for m in registry.all_modules()
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
        transformer_json=module.default_spec().model_dump(mode="json"),
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
    if body.transformer is not None:
        module = registry.get(p.experiment_id)
        try:
            spec = module.spec_model.model_validate(body.transformer)
        except ValidationError as exc:
            raise ApiError(
                422,
                "invalid_transformer",
                "Transformer specification is invalid",
                [
                    {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                    for e in exc.errors(include_url=False, include_context=False)
                ],
            ) from exc
        p.transformer_json = spec.model_dump(mode="json")
    session.commit()
    session.refresh(p)
    return to_out(p)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, session: SessionDep) -> Response:
    p = load_project(session, project_id)
    session.delete(p)
    session.commit()
    return Response(status_code=204)
