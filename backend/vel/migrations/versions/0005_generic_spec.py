"""D2: projects hold the equipment spec of any experiment (transformer, motor, …).

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.alter_column("transformer_json", new_column_name="spec_json")


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.alter_column("spec_json", new_column_name="transformer_json")
