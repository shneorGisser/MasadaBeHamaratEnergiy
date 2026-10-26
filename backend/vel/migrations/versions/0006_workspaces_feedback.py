"""Sharing: per-browser workspaces, project share links, feedback notes.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(
            sa.Column("workspace", sa.String(64), nullable=False, server_default="shared")
        )
        batch.add_column(sa.Column("share_token", sa.String(64), nullable=True))
        batch.create_index("ix_projects_workspace", ["workspace"])
        batch.create_unique_constraint("uq_projects_share_token", ["share_token"])
    op.create_table(
        "feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace", sa.String(64), nullable=False),
        sa.Column("page", sa.String(500), nullable=False, server_default=""),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False, server_default="other"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("contact", sa.String(200), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("feedback")
    with op.batch_alter_table("projects") as batch:
        batch.drop_constraint("uq_projects_share_token", type_="unique")
        batch.drop_index("ix_projects_workspace")
        batch.drop_column("share_token")
        batch.drop_column("workspace")
