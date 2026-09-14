"""Add extracted_data table for structured data extraction

Revision ID: 034_extracted_data
Revises: 033_story_events
Create Date: 2026-09-13

Phase 1 of the Smart Data Extraction milestone (v0.9.3, #210, ADR-0023).
Adds a per-article ``extracted_data`` table holding structured data points
(statistics, quotes, claims, dates, amounts) pulled from article content by
an LLM call (``app/data_extraction.py``, #211).

``data_type`` taxonomy follows GitHub issue #210 (statistic/quote/claim/
date/amount) rather than the earlier ADR-0023 draft schema's
statistic/quote/location/date -- ``location`` is intentionally NOT one of
the supported types here: the existing NER pipeline (``app/entities.py``)
already extracts location *names* into ``items.entities_json`` /
the ``entities`` table (v0.9.0, #199), and true geographic tagging (with
coordinates, mapping UI) has no supporting infrastructure anywhere in this
codebase and is separately deferred to the v0.11.2 visualization milestone.
Adding a redundant, coordinate-less "location" data_type here would just
duplicate NER without adding value.

``data_value`` is JSONB (not a single Text/String column) because the
shape of a data point differs meaningfully by type -- e.g.
{"text": "3.4%", "unit": "percent"} for a statistic vs.
{"text": "...", "speaker": "Jane Smith, CEO"} for a quote -- and JSONB
allows querying by sub-key later (e.g. filter quotes by speaker) without a
second migration. This mirrors the ``entities.entity_metadata`` JSONB
column's rationale (v0.9.0) rather than the story_events module's Text/JSON
string convention (which stores a flat list of IDs with no need for
per-key querying).

No ``story_id`` column: aggregation across a story's supporting articles
(#213) is done via ``JOIN story_articles ON article_id``, the same pattern
``entity_mentions.story_id`` was introduced to avoid duplicating in v0.9.0
-- but since extracted_data doesn't need a fast story-scoped lookup path
the way entity mentions did (no per-story entity graph query), the extra
denormalized column isn't justified here.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "034_extracted_data"
down_revision: Union[str, Sequence[str], None] = "033_story_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "extracted_data",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "article_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("data_type", sa.String(length=20), nullable=False),
        sa.Column("data_value", postgresql.JSONB(), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column(
            "extraction_method",
            sa.String(length=20),
            nullable=False,
            server_default="llm",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_extracted_data_article", "extracted_data", ["article_id"])
    op.create_index("idx_extracted_data_type", "extracted_data", ["data_type"])


def downgrade() -> None:
    op.drop_index("idx_extracted_data_type", table_name="extracted_data")
    op.drop_index("idx_extracted_data_article", table_name="extracted_data")
    op.drop_table("extracted_data")
