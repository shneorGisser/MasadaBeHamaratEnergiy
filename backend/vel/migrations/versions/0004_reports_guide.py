"""S5: reports (immutable snapshots) and guided-mode state.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("sources", sa.JSON, nullable=False),
        sa.Column("student_discussion", sa.Text, nullable=False),
        sa.Column("html", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    with op.batch_alter_table("projects") as b:
        b.add_column(sa.Column("guide_state", sa.JSON, nullable=False, server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("projects") as b:
        b.drop_column("guide_state")
    op.drop_table("reports")
