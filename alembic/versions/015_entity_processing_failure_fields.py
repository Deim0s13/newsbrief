"""Per-entity pipeline failure metadata on items and stories (#293 M1, ADR-0030).

Revision ID: 015_entity_processing_failure_fields
Revises: 014_operator_actions

Adds nullable columns alongside processing_state: human-readable error, timestamp,
stage key, and optional link to pipeline_stage_runs.run_group_id.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015_entity_processing_failure_fields"
down_revision: Union[str, Sequence[str], None] = "014_operator_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in ("items", "stories"):
        op.add_column(
            table,
            sa.Column("processing_error", sa.Text(), nullable=True),
        )
        op.add_column(
            table,
            sa.Column("processing_failed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            table,
            sa.Column("failure_stage", sa.String(length=64), nullable=True),
        )
        op.add_column(
            table,
            sa.Column(
                "last_failed_run_group_id",
                sa.String(length=36),
                nullable=True,
            ),
        )

    op.create_index(
        "idx_items_processing_failed_at",
        "items",
        ["processing_failed_at"],
        unique=False,
        postgresql_where=sa.text("processing_state = 'failed'"),
    )
    op.create_index(
        "idx_stories_processing_failed_at",
        "stories",
        ["processing_failed_at"],
        unique=False,
        postgresql_where=sa.text("processing_state = 'failed'"),
    )


def downgrade() -> None:
    op.drop_index(
        "idx_stories_processing_failed_at",
        table_name="stories",
        postgresql_where=sa.text("processing_state = 'failed'"),
    )
    op.drop_index(
        "idx_items_processing_failed_at",
        table_name="items",
        postgresql_where=sa.text("processing_state = 'failed'"),
    )
    for table in ("stories", "items"):
        op.drop_column(table, "last_failed_run_group_id")
        op.drop_column(table, "failure_stage")
        op.drop_column(table, "processing_failed_at")
        op.drop_column(table, "processing_error")
