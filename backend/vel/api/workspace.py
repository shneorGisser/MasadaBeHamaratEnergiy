"""Per-browser workspaces: who may see which project, without accounts.

Why: a public deployment has no login. Without isolation, every visitor would see and edit
every other visitor's projects. Each browser instead gets an unguessable workspace token in a
cookie (set on its first API call); projects belong to the workspace that created them, and
every request that names a project, run, measurement set or report is checked against it.
A foreign id answers 404 exactly like a missing one, so ids cannot be probed.

Modes (VEL_WORKSPACES): "shared" (default; local single-user use — everything lives in one
workspace, behaviour unchanged) or "cookie" (deployments; set in the Dockerfiles).

The token is a capability: whoever holds it holds the workspace. That is what makes the
"open my workspace on another device" link work, and it is why the link is shown only to its
owner and the cookie is HttpOnly.
"""

from __future__ import annotations

import os
import re
import secrets
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Request, Response
from sqlalchemy.orm import Session

from vel.api.deps import get_session
from vel.errors import not_found
from vel.orm import MeasurementSet, Project, Report, SimulationRun

COOKIE = "vel_ws"
SHARED = "shared"
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{22,64}$")
MAX_AGE = 400 * 24 * 3600  # browsers cap cookie lifetime at 400 days

Mode = Literal["shared", "cookie"]


def mode_from_env() -> Mode:
    m = os.environ.get("VEL_WORKSPACES", SHARED).strip().lower()
    if m not in ("shared", "cookie"):
        raise ValueError(f"VEL_WORKSPACES must be 'shared' or 'cookie', not {m!r}")
    return m  # type: ignore[return-value]


def new_token() -> str:
    return secrets.token_urlsafe(24)  # 32 chars, 192 bits


def set_cookie(request: Request, response: Response, token: str) -> None:
    https = request.url.scheme == "https"
    response.set_cookie(
        COOKIE,
        token,
        max_age=MAX_AGE,
        httponly=True,
        secure=https,
        # inside an iframe (Hugging Face shows Spaces in one) only SameSite=None is sent
        samesite="none" if https else "lax",
        path="/",
    )


def install(app: FastAPI, mode: Mode) -> None:
    app.state.workspace_mode = mode

    @app.middleware("http")
    async def workspace_cookie(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # /api/health is polled from every page, also while /w adopts a workspace: a fresh
        # cookie on its response would race the adopted one and overwrite it
        if (
            mode == SHARED
            or not request.url.path.startswith("/api/")
            or (request.url.path == "/api/health")
        ):
            request.state.workspace = SHARED
            return await call_next(request)
        token = request.cookies.get(COOKIE, "")
        fresh = not TOKEN_RE.match(token)
        if fresh:
            token = new_token()
        request.state.workspace = token
        response = await call_next(request)
        already = any(
            k == b"set-cookie" and v.startswith(f"{COOKIE}=".encode())
            for k, v in response.raw_headers
        )
        if fresh and not already:  # an endpoint that set the cookie itself (adopt) wins
            set_cookie(request, response, token)
        return response


def current(request: Request) -> str:
    return str(getattr(request.state, "workspace", SHARED))


WorkspaceDep = Annotated[str, Depends(current)]


def _owner_project(session: Session, param: str, value: str) -> str | None:
    """The project id that owns the named object, or None if it does not exist."""
    if param == "project_id":
        return value if session.get(Project, value) is not None else None
    obj: SimulationRun | MeasurementSet | Report | None
    if param == "run_id":
        obj = session.get(SimulationRun, value)
    elif param == "set_id":
        obj = session.get(MeasurementSet, value)
    else:
        obj = session.get(Report, value)
    return None if obj is None else obj.project_id


# Every path or query parameter that names a stored object. tests/test_workspace.py fails if a
# route gains an id parameter that is neither here nor in UNSCOPED.
GUARDED = ("project_id", "run_id", "set_id", "report_id")
UNSCOPED = ("experiment_id", "kind", "dataset_id", "token", "path")


def guard(
    request: Request,
    workspace: WorkspaceDep,
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Router-wide dependency: 404 for any object outside the caller's workspace."""
    params = {**request.query_params, **request.path_params}
    for name in GUARDED:
        value = params.get(name)
        if not value:
            continue
        pid = _owner_project(session, name, str(value))
        p = session.get(Project, pid) if pid else None
        if p is None or p.workspace != workspace:
            raise not_found(name.removesuffix("_id"), str(value))


GuardDep = Depends(guard)
