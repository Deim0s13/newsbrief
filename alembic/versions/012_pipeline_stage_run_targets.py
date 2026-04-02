"""Add target columns to pipeline_stage_runs (#274 replay).

Revision ID: 012_pipeline_stage_run_targets
Revises: 011_pipeline_stage_runs
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012_pipeline_stage_run_targets"
down_revision: Union[str, Sequence[str], None] = "011_pipeline_stage_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pipeline_stage_runs",
        sa.Column("target_type", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "pipeline_stage_runs",
        sa.Column("target_id", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pipeline_stage_runs", "target_id")
    op.drop_column("pipeline_stage_runs", "target_type")
