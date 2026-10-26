"""Sharing a deployment with friends: workspace link, project share links, feedback.

* Workspace link — the owner's own token, to open the same workspace on another device.
* Project share link — a separate random token per project. Opening it shows the project's
  name; "copy" clones the project (spec, circuits, runs, measurements) into the visitor's own
  workspace. The original is never exposed for editing, and the owner can revoke the link.
* Feedback — free text from the in-app button, read by the operator on /feedback with the
  VEL_ADMIN_TOKEN key. Without that variable the list is not reachable at all.
"""

from __future__ import annotations

import hmac
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from vel.api.deps import SessionDep
from vel.api.projects import ProjectOut, load_project, to_out
from vel.api.workspace import TOKEN_RE, GuardDep, WorkspaceDep, new_token, set_cookie
from vel.errors import ApiError, not_found
from vel.experiments import registry
from vel.orm import Feedback, Project
from vel.services.backup import export_project, import_project

router = APIRouter(prefix="/api", tags=["sharing"], dependencies=[GuardDep])

FEEDBACK_PER_HOUR = 30


class WorkspaceOut(BaseModel):
    mode: str
    token: str | None


class AdoptBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=22, max_length=64)


@router.get("/workspace", response_model=WorkspaceOut)
def get_workspace(request: Request, workspace: WorkspaceDep) -> WorkspaceOut:
    mode = request.app.state.workspace_mode
    return WorkspaceOut(mode=mode, token=workspace if mode == "cookie" else None)


@router.post("/workspace", status_code=204)
def adopt_workspace(body: AdoptBody, request: Request) -> Response:
    """Open an existing workspace in this browser (the "my workspace" link of another device)."""
    if request.app.state.workspace_mode != "cookie":
        raise ApiError(409, "single_workspace", "this server runs a single shared workspace")
    if not TOKEN_RE.match(body.token):
        raise ApiError(422, "bad_token", "not a workspace token")
    response = Response(status_code=204)
    set_cookie(request, response, body.token)
    return response


class ShareOut(BaseModel):
    token: str


@router.post("/projects/{project_id}/share", response_model=ShareOut)
def share_project(project_id: str, session: SessionDep) -> ShareOut:
    p = load_project(session, project_id)
    if not p.share_token:
        p.share_token = new_token()
        session.commit()
    return ShareOut(token=str(p.share_token))


@router.delete("/projects/{project_id}/share", status_code=204)
def unshare_project(project_id: str, session: SessionDep) -> Response:
    p = load_project(session, project_id)
    p.share_token = None
    session.commit()
    return Response(status_code=204)


def _shared(session: SessionDep, token: str) -> Project:
    p = None
    if TOKEN_RE.match(token):
        p = session.scalars(select(Project).where(Project.share_token == token)).first()
    if p is None:
        raise not_found("shared project", token)
    return p


@router.get("/shared/{token}")
def shared_info(token: str, session: SessionDep) -> dict[str, Any]:
    p = _shared(session, token)
    return {
        "name": p.name,
        "experiment_id": p.experiment_id,
        "experiment_title_he": registry.get(p.experiment_id).title_he,
        "updated_at": p.updated_at,
    }


@router.post("/shared/{token}/copy", response_model=ProjectOut, status_code=201)
def copy_shared(token: str, session: SessionDep, workspace: WorkspaceDep) -> ProjectOut:
    p = _shared(session, token)
    doc = export_project(session, p)
    return to_out(import_project(session, doc, workspace, suffix=" (עותק)"))


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)
    kind: Literal["bug", "idea", "question", "other"] = "other"
    page: str = Field(default="", max_length=500)
    project_id: str | None = Field(default=None, max_length=36)
    contact: str = Field(default="", max_length=200)


@router.post("/feedback", status_code=201)
def send_feedback(
    body: FeedbackIn,
    session: SessionDep,
    workspace: WorkspaceDep,
    user_agent: str = Header(default=""),
) -> dict[str, str]:
    since = datetime.now(UTC) - timedelta(hours=1)
    recent = session.scalar(
        select(func.count())
        .select_from(Feedback)
        .where(Feedback.workspace == workspace, Feedback.created_at >= since)
    )
    if (recent or 0) >= FEEDBACK_PER_HOUR:
        raise ApiError(429, "too_many", "too much feedback from this browser in the last hour")
    f = Feedback(
        workspace=workspace,
        page=body.page,
        project_id=body.project_id,
        kind=body.kind,
        message=body.message.strip(),
        contact=body.contact.strip(),
        user_agent=user_agent[:300],
    )
    session.add(f)
    session.commit()
    return {"id": f.id}


@router.get("/feedback")
def list_feedback(
    session: SessionDep, x_admin_token: str = Header(default="")
) -> list[dict[str, Any]]:
    key = os.environ.get("VEL_ADMIN_TOKEN", "")
    if not key or not hmac.compare_digest(key.encode(), x_admin_token.encode()):
        raise not_found("page", "feedback")
    rows = session.scalars(select(Feedback).order_by(Feedback.created_at.desc())).all()
    return [
        {
            "id": f.id,
            "created_at": f.created_at,
            "kind": f.kind,
            "message": f.message,
            "contact": f.contact,
            "page": f.page,
            "project_id": f.project_id,
            # a short, stable label per browser — never the token itself
            "from": hmac.new(key.encode(), f.workspace.encode(), "sha256").hexdigest()[:8],
            "user_agent": f.user_agent,
        }
        for f in rows
    ]
