"""Add stories.complexity_score for numeric cluster complexity (#280, ADR-0026).

Extends the existing binary ``classify_cluster_path``/``synthesis_path``
routing (still the source of truth for routing decisions) with a
finer-grained, advisory-only 0.0-1.0 score blending article count, source
divergence, recency spread, entity density, and semantic spread. Intended
for operator review and the #262 evaluation, not for routing.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "027_cluster_complexity_score"
down_revision: Union[str, Sequence[str], None] = "026_context_anchors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stories", sa.Column("complexity_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("stories", "complexity_score")
