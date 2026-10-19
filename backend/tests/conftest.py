from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from vel.main import create_app

# Set VEL_TEST_PG_URL (e.g. postgresql+psycopg://vel:vel@localhost/postgres) to run every API
# test against a fresh PostgreSQL database instead of SQLite — the Cloud SQL path.
PG_ADMIN_URL = os.environ.get("VEL_TEST_PG_URL")


@pytest.fixture()
def db_url(tmp_path: Path) -> Iterator[str]:
    if not PG_ADMIN_URL:
        yield f"sqlite:///{tmp_path / 'test.sqlite3'}"
        return
    name = f"vel_test_{uuid.uuid4().hex[:12]}"
    admin = create_engine(PG_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{name}"'))
    base = PG_ADMIN_URL.rsplit("/", 1)[0]
    try:
        yield f"{base}/{name}"
    finally:
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture()
def client(db_url: str) -> Iterator[TestClient]:
    app = create_app(db_url)
    with TestClient(app) as c:
        yield c
    app.state.db.engine.dispose()
