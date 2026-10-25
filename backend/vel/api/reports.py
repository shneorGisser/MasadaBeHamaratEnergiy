"""Guided mode and reports (S5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from vel.api.deps import SessionDep
from vel.api.projects import load_project
from vel.errors import ApiError, not_found
from vel.orm import Report
from vel.services import reports as svc

router = APIRouter(prefix="/api", tags=["reports"])


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")
    study_kind: str
    run_id: str | None = None
    set_id: str | None = None


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    sections: list[Section] = Field(min_length=1, max_length=20)
    student_discussion: str = Field(default="", max_length=50000)


class ReportSummary(BaseModel):
    id: str
    project_id: str
    title: str
    status: str
    created_at: datetime


class AckBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_id: str


def _summary(r: Report) -> ReportSummary:
    return ReportSummary(
        id=r.id, project_id=r.project_id, title=r.title, status=r.status, created_at=r.created_at
    )


def _load(session: SessionDep, rid: str) -> Report:
    r = session.get(Report, rid)
    if r is None:
        raise not_found("report", rid)
    return r


@router.get("/projects/{project_id}/guide")
def get_guide(project_id: str, session: SessionDep) -> dict[str, Any]:
    return svc.guide_status(session, load_project(session, project_id))


@router.post("/projects/{project_id}/guide/ack")
def ack(project_id: str, body: AckBody, session: SessionDep) -> dict[str, Any]:
    p = load_project(session, project_id)
    svc.acknowledge(session, p, body.step_id)
    return svc.guide_status(session, p)


@router.get("/projects/{project_id}/reports", response_model=list[ReportSummary])
def list_reports(project_id: str, session: SessionDep) -> list[ReportSummary]:
    load_project(session, project_id)
    q = select(Report).where(Report.project_id == project_id).order_by(Report.created_at.desc())
    return [_summary(r) for r in session.scalars(q)]


@router.post("/projects/{project_id}/reports", status_code=201)
def create_report(project_id: str, body: ReportCreate, session: SessionDep) -> dict[str, Any]:
    p = load_project(session, project_id)
    r = svc.create_report(
        session, p, body.title, [s.model_dump() for s in body.sections], body.student_discussion
    )
    return {**_summary(r).model_dump(mode="json"), "sources": r.sources}


@router.get("/reports/{report_id}")
def get_report(report_id: str, session: SessionDep) -> dict[str, Any]:
    r = _load(session, report_id)
    return {
        **_summary(r).model_dump(mode="json"),
        "sources": r.sources,
        "student_discussion": r.student_discussion,
    }


@router.get("/reports/{report_id}/html", response_class=HTMLResponse)
def report_html(report_id: str, session: SessionDep) -> HTMLResponse:
    return HTMLResponse(_load(session, report_id).html)


@router.get("/reports/{report_id}/docx")
def report_docx(report_id: str, session: SessionDep) -> Response:
    """Word export of the same immutable snapshot (Hebrew RTL, David 11, MATLAB appendix)."""
    from vel.services.report_docx import build_docx

    r = _load(session, report_id)
    snap = (r.sources or {}).get("snapshot")
    if not isinstance(snap, dict):
        raise ApiError(409, "no_snapshot", "this report has no stored snapshot")
    return Response(
        build_docx(snap),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="report-{r.id[:8]}.docx"'},
    )


@router.get("/reports/{report_id}/data.zip")
def report_data(report_id: str, session: SessionDep) -> Response:
    """All tables of the report as CSV — the full data behind the folded/thinned prints."""
    from vel.services.report_docx import report_data_zip

    r = _load(session, report_id)
    snap = (r.sources or {}).get("snapshot")
    if not isinstance(snap, dict):
        raise ApiError(409, "no_snapshot", "this report has no stored snapshot")
    return Response(
        report_data_zip(snap),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="report-{r.id[:8]}-data.zip"'},
    )


@router.get("/reports/{report_id}/pdf")
def report_pdf(report_id: str, session: SessionDep) -> Response:
    r = _load(session, report_id)
    return Response(
        svc.pdf(r),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report-{r.id[:8]}.pdf"'},
    )
