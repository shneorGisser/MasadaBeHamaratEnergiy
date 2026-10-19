"""S1: immutable simulation runs.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("study_kind", sa.String(50), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("input_snapshot", sa.JSON, nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("warnings", sa.JSON, nullable=False),
        sa.Column("error", sa.JSON, nullable=True),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("simulation_runs")
