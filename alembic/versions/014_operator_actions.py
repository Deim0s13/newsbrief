"""Operator audit log for pipeline admin actions (#277).

Revision ID: 014_operator_actions
Revises: 013_pipeline_stage_run_reliability
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014_operator_actions"
down_revision: Union[str, Sequence[str], None] = "013_pipeline_stage_run_reliability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operator_actions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("operator_label", sa.String(length=256), nullable=True),
        sa.Column("client_ip", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_operator_actions_created", "operator_actions", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_operator_actions_created", table_name="operator_actions")
    op.drop_table("operator_actions")
