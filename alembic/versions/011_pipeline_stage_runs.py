"""Add pipeline_stage_runs for ADR-0029 / GitHub #274.

Revision ID: 011_pipeline_stage_runs
Revises: 010_processing_state
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_pipeline_stage_runs"
down_revision: Union[str, Sequence[str], None] = "010_processing_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_stage_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_group_id", sa.String(length=36), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("stats_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_pipeline_stage_runs_run_group",
        "pipeline_stage_runs",
        ["run_group_id"],
        unique=False,
    )
    op.create_index(
        "idx_pipeline_stage_runs_stage_started",
        "pipeline_stage_runs",
        ["stage", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_pipeline_stage_runs_stage_started", table_name="pipeline_stage_runs"
    )
    op.drop_index("idx_pipeline_stage_runs_run_group", table_name="pipeline_stage_runs")
    op.drop_table("pipeline_stage_runs")
