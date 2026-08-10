"""Add historical story linking columns to stories (#258, ADR-0026).

Stores semantically related stories from the past N days (computed via
pgvector cosine similarity after embedding), plus a single "continues from"
pointer to the closest historical match above threshold.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "021_historical_story_links"
down_revision: Union[str, Sequence[str], None] = "020_confidence_warning"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stories", sa.Column("historical_links_json", sa.Text(), nullable=True)
    )
    op.add_column(
        "stories", sa.Column("continues_story_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "stories", sa.Column("continues_similarity", sa.Float(), nullable=True)
    )
    op.create_foreign_key(
        "fk_stories_continues_story_id",
        "stories",
        "stories",
        ["continues_story_id"],
        ["id"],
    )
    op.create_index(
        "idx_stories_continues_story_id",
        "stories",
        ["continues_story_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_stories_continues_story_id", table_name="stories")
    op.drop_constraint("fk_stories_continues_story_id", "stories", type_="foreignkey")
    op.drop_column("stories", "continues_similarity")
    op.drop_column("stories", "continues_story_id")
    op.drop_column("stories", "historical_links_json")
