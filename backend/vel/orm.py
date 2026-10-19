"""ORM tables.

Mutable state: Project (and its current circuit / study cases, stored as JSON documents).
Immutable records (SimulationRun, MeasurementEntry, published Report) are append-only;
the API layer never issues UPDATE on them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from vel.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    experiment_id: Mapped[str] = mapped_column(String(100))
    experiment_version: Mapped[int] = mapped_column(Integer)
    # Canonical, versioned domain documents (validated by pydantic before storage).
    transformer_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    circuits_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class SimulationRun(Base):
    """Immutable record of one executed study. Never updated after insert."""

    __tablename__ = "simulation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    study_kind: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(200), default="")
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    input_hash: Mapped[str] = mapped_column(String(64))
    model_version: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(40))
    warnings: Mapped[list[Any]] = mapped_column(JSON, default=list)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MeasurementSet(Base):
    __tablename__ = "measurement_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    study_kind: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(200), default="")
    lab_date: Mapped[str] = mapped_column(String(20), default="")
    instruments: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    n_rows: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MeasurementEntry(Base):
    """Append-only. A correction inserts a new row that points at the row it supersedes."""

    __tablename__ = "measurement_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    set_id: Mapped[str] = mapped_column(ForeignKey("measurement_sets.id", ondelete="CASCADE"))
    row_index: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[str] = mapped_column(String(60))
    value_si: Mapped[float] = mapped_column()
    entered_value: Mapped[float] = mapped_column()
    entered_unit: Mapped[str] = mapped_column(String(20))
    instrument_range: Mapped[str] = mapped_column(String(60), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    supersedes_id: Mapped[str | None] = mapped_column(
        ForeignKey("measurement_entries.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20))  # draft | published
    title: Mapped[str] = mapped_column(String(200))
    sources: Mapped[dict[str, Any]] = mapped_column(JSON)
    student_discussion: Mapped[str] = mapped_column(Text, default="")
    html: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
