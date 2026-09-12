"""Add story_events table and story lifecycle tracking columns

Revision ID: 033_story_events
Revises: 032_coverage_gaps
Create Date: 2026-09-08

Phase 1 of the Story Evolution & Timeline milestone (v0.9.2, #206,
ADR-0023). Adds a `story_events` table for discrete, timestamped events in
a story's lifecycle (broke/update/development/correction/resolved) plus
lightweight lifecycle-tracking columns on `stories` itself.

`story_status` is deliberately a new column, separate from the existing
`status` (active/superseded/archived/held -- pipeline/publish lifecycle,
ADR-0004/#287) and `processing_state` (ADR-0030 orchestration state).
`story_status` tracks *narrative* development (breaking/developing/
established) and is derived by simple recency/update-count rules in
app/story_events.py, not LLM-classified.

`source_articles` on story_events stores article IDs as a JSON array
(consistent with the rest of the codebase's *_json Text column convention,
e.g. stories.topics_json) rather than a native ARRAY -- there's no need for
per-element SQL querying, and Text keeps this consistent with the
serialize_story_json_field()/deserialize_story_json_field() helpers already
used throughout stories.py.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "033_story_events"
down_revision: Union[str, Sequence[str], None] = "032_coverage_gaps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "story_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "story_id",
            sa.Integer(),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("event_title", sa.String(length=255), nullable=True),
        sa.Column("event_description", sa.Text(), nullable=True),
        sa.Column("source_articles_json", sa.Text(), nullable=True),
        sa.Column(
            "significance_score",
            sa.Float(),
            nullable=False,
            server_default="0.5",
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_story_events_story", "story_events", ["story_id"])
    op.create_index("idx_story_events_occurred", "story_events", ["occurred_at"])

    op.add_column(
        "stories",
        sa.Column(
            "story_status",
            sa.String(length=20),
            nullable=False,
            server_default="breaking",
        ),
    )
    op.add_column(
        "stories",
        sa.Column("first_reported_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "stories",
        sa.Column("last_major_update", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "stories",
        sa.Column("update_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("stories", "update_count")
    op.drop_column("stories", "last_major_update")
    op.drop_column("stories", "first_reported_at")
    op.drop_column("stories", "story_status")
    op.drop_index("idx_story_events_occurred", table_name="story_events")
    op.drop_index("idx_story_events_story", table_name="story_events")
    op.drop_table("story_events")
