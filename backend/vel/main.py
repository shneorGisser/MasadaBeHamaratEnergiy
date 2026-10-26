"""FastAPI application factory."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from vel import __version__
from vel.api import measurements, projects, reports, runs, sharing, workspace
from vel.db import Database, default_database_url
from vel.errors import install_handlers
from vel.migrate import upgrade


def create_app(
    database_url: str | None = None,
    static_dir: Path | None = None,
    workspaces: workspace.Mode | None = None,
) -> FastAPI:
    db = Database(database_url or default_database_url())
    upgrade(db.engine)

    app = FastAPI(title="Virtual Energy Lab", version=__version__)
    app.state.db = db
    install_handlers(app)
    workspace.install(app, workspaces or workspace.mode_from_env())

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(projects.router)
    app.include_router(runs.router)
    app.include_router(measurements.router)
    app.include_router(reports.router)
    app.include_router(sharing.router)

    static = static_dir or (
        Path(os.environ["VEL_STATIC_DIR"]) if "VEL_STATIC_DIR" in os.environ else None
    )
    if static and static.is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")
        root = static.resolve()

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            # resolve first: an encoded "../" must not reach files outside the static dir
            candidate = (root / path).resolve()
            if path and candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(root / "index.html")

    return app
