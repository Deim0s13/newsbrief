"""Widen alembic_version.version_num — revision IDs from 013 onward exceed VARCHAR(32).

Revision ID: 012b_alembic_version_widen
Revises: 012_pipeline_stage_run_targets
Create Date: 2026-04-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012b_alembic_version_widen"
down_revision: Union[str, Sequence[str], None] = "012_pipeline_stage_run_targets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=128),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=128),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
