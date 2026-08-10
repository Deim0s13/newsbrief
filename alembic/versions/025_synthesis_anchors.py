"""Add stories.synthesis_anchors_json for light RAG anchor tracking (#259, ADR-0026).

Records which historical stories (if any) were injected into the synthesis
prompt as continuity anchors, for the #262 evaluation and operator review.
Distinct from ``historical_links_json`` (#258), which is computed *after*
synthesis by comparing the new story's own embedding against history.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "025_synthesis_anchors"
down_revision: Union[str, Sequence[str], None] = "024_semantic_dedup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stories", sa.Column("synthesis_anchors_json", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("stories", "synthesis_anchors_json")
