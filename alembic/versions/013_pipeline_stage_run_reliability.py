"""Pipeline stage run retry/discards (#275 Phase 1).

Revision ID: 013_pipeline_stage_run_reliability
Revises: 012_pipeline_stage_run_targets
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013_pipeline_stage_run_reliability"
down_revision: Union[str, Sequence[str], None] = "012_pipeline_stage_run_targets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pipeline_stage_runs",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "pipeline_stage_runs",
        sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_pipeline_stage_runs_dead_letter",
        "pipeline_stage_runs",
        ["finished_at", "success", "discarded_at"],
        unique=False,
    )
    op.alter_column("pipeline_stage_runs", "attempts", server_default=None)


def downgrade() -> None:
    op.drop_index("idx_pipeline_stage_runs_dead_letter", table_name="pipeline_stage_runs")
    op.drop_column("pipeline_stage_runs", "discarded_at")
    op.drop_column("pipeline_stage_runs", "attempts")
