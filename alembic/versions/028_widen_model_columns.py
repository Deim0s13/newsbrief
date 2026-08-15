"""Widen model name columns from VARCHAR(50) to Text (#339).

`stories.model`, `synthesis_cache.model`, and `llm_metrics.model` were
VARCHAR(50), sized for short Ollama tags like ``qwen2.5:14b``. oMLX/MLX
model IDs (e.g. ``lmstudio-community--Qwen3-30B-A3B-Instruct-2507-MLX-4bit``,
56 chars) exceed that width, causing every story insert to fail with
``StringDataRightTruncation`` during the #339 end-to-end validation run -
113 clusters were synthesized but 0 stories were persisted.

Widens all three to Text, matching the existing convention already used
for `items.ai_model`, `items.structured_summary_model`, and
`items.entities_model` in the same models.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "028_widen_model_columns"
down_revision: Union[str, Sequence[str], None] = "027_cluster_complexity_score"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("stories", "model", type_=sa.Text(), existing_type=sa.String(50))
    op.alter_column(
        "synthesis_cache", "model", type_=sa.Text(), existing_type=sa.String(50)
    )
    op.alter_column(
        "llm_metrics", "model", type_=sa.Text(), existing_type=sa.String(50)
    )


def downgrade() -> None:
    op.alter_column("stories", "model", type_=sa.String(50), existing_type=sa.Text())
    op.alter_column(
        "synthesis_cache", "model", type_=sa.String(50), existing_type=sa.Text()
    )
    op.alter_column(
        "llm_metrics", "model", type_=sa.String(50), existing_type=sa.Text()
    )
