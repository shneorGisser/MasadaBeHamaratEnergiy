"""FastAPI application factory."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from vel import __version__
from vel.api import projects
from vel.db import Database, default_database_url
from vel.errors import install_handlers
from vel.migrate import upgrade


def create_app(database_url: str | None = None, static_dir: Path | None = None) -> FastAPI:
    db = Database(database_url or default_database_url())
    upgrade(db.engine)

    app = FastAPI(title="Virtual Energy Lab", version=__version__)
    app.state.db = db
    install_handlers(app)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    app.include_router(projects.router)

    static = static_dir or (
        Path(os.environ["VEL_STATIC_DIR"]) if "VEL_STATIC_DIR" in os.environ else None
    )
    if static and static.is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            candidate = static / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static / "index.html")

    return app
