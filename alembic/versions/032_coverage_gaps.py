"""Add stories.coverage_gaps_json column (#229, ADR-0023, v0.9.1).

Phase 3 of the Multi-Perspective Synthesis milestone: rule-based (no LLM)
viewpoint gap detection across a story's cluster, based on the per-article
perspective tags already cached by #203 (see app/perspective_gaps.py
detect_perspective_gaps()).

Null/empty-list is the common case -- most clusters either have no
applicable perspective at all, or already show some balance across sides.
Currently only populated by the direct synthesis strategy (<=8 articles
per cluster), consistent with #204's scoping.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "032_coverage_gaps"
down_revision: Union[str, Sequence[str], None] = "031_consensus_divergence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stories", sa.Column("coverage_gaps_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("stories", "coverage_gaps_json")
