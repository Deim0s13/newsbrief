"""Add processing_state to items and stories (ADR-0030, GitHub #273).

Revision ID: 010_processing_state
Revises: 009_story_credibility
Create Date: 2026-03-18

Pipeline position is separate from stories.status (active/archived).
Backfill rules match docs/adr/0030-article-story-processing-states.md.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "010_processing_state"
down_revision: Union[str, Sequence[str], None] = "009_story_credibility"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column("processing_state", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "stories",
        sa.Column("processing_state", sa.String(length=32), nullable=True),
    )

    bind = op.get_bind()

    bind.execute(
        text(
            """
            UPDATE stories SET processing_state = CASE
              WHEN status = 'archived' THEN 'archived'
              WHEN COALESCE(article_count, 0) > 0
                   OR length(trim(COALESCE(synthesis, ''))) > 0 THEN 'published'
              ELSE 'candidate'
            END
            """
        )
    )

    bind.execute(
        text(
            """
            UPDATE items SET processing_state = CASE
              WHEN EXISTS (
                SELECT 1 FROM story_articles sa WHERE sa.article_id = items.id
              ) THEN 'clustered'
              WHEN entities_json IS NOT NULL AND trim(entities_json) != '' THEN 'enriched'
              WHEN extracted_at IS NOT NULL THEN 'extracted'
              WHEN extraction_method IS NOT NULL AND extraction_method != 'legacy'
                THEN 'extracted'
              WHEN (content IS NOT NULL AND trim(content) != '')
                OR (summary IS NOT NULL AND trim(summary) != '') THEN 'fetched'
              ELSE 'fetched'
            END
            """
        )
    )

    op.alter_column(
        "items",
        "processing_state",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default=sa.text("'fetched'"),
    )
    op.alter_column(
        "stories",
        "processing_state",
        existing_type=sa.String(length=32),
        nullable=False,
        server_default=sa.text("'candidate'"),
    )

    op.create_index(
        "idx_items_processing_state",
        "items",
        ["processing_state"],
        unique=False,
    )
    op.create_index(
        "idx_stories_processing_state",
        "stories",
        ["processing_state"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_stories_processing_state", table_name="stories")
    op.drop_index("idx_items_processing_state", table_name="items")
    op.drop_column("stories", "processing_state")
    op.drop_column("items", "processing_state")
