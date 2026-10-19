"""S3: measurement sets and append-only measurement entries.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "measurement_sets",
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
        sa.Column("lab_date", sa.String(20), nullable=False),
        sa.Column("instruments", sa.Text, nullable=False),
        sa.Column("notes", sa.Text, nullable=False),
        sa.Column("conditions", sa.JSON, nullable=False),
        sa.Column("n_rows", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "measurement_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "set_id",
            sa.String(36),
            sa.ForeignKey("measurement_sets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("row_index", sa.Integer, nullable=False),
        sa.Column("quantity", sa.String(60), nullable=False),
        sa.Column("value_si", sa.Float, nullable=False),
        sa.Column("entered_value", sa.Float, nullable=False),
        sa.Column("entered_unit", sa.String(20), nullable=False),
        sa.Column("instrument_range", sa.String(60), nullable=False),
        sa.Column("note", sa.Text, nullable=False),
        sa.Column(
            "supersedes_id", sa.String(36), sa.ForeignKey("measurement_entries.id"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("measurement_entries")
    op.drop_table("measurement_sets")
