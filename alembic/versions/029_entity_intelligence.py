"""Add entities + entity_mentions relational tables (#199, ADR-0023, v0.9.0).

Introduces the normalized entity graph described in ADR-0023: a canonical
``entities`` table (deduplicated by name + type) and an ``entity_mentions``
junction table linking entities to the articles (and, once clustered,
stories) that mention them.

This is additive only. The existing per-article LLM extraction and its
``items.entities_json`` / ``stories.entities_json`` caches (v0.6.1) are
untouched and continue to power clustering similarity as before; the new
tables are populated by a normalization step that consumes that already
-extracted output (see ``app/entity_normalization.py``).

Two pragmatic additions on top of ADR-0023's own sketch:
- ``entities.last_seen`` (the ADR only lists ``first_seen``, but entity
  profile pages (#201) need both).
- A unique index on ``(lower(canonical_name), entity_type)`` for
  find-or-create dedup, and a unique constraint on
  ``entity_mentions(entity_id, article_id)`` so re-processing an article
  (e.g. during backfill or repeat clustering passes) is idempotent.

``sentiment_score`` / ``avg_sentiment`` ship now (schema-complete) but stay
nullable and unpopulated in this pass -- the current LLM extraction prompt
doesn't produce per-entity sentiment.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "029_entity_intelligence"
down_revision: Union[str, Sequence[str], None] = "028_widen_model_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column(
            "aliases",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("mention_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_sentiment", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_entities_canonical_type",
        "entities",
        [sa.text("lower(canonical_name)"), "entity_type"],
        unique=True,
    )
    op.create_index("idx_entities_type", "entities", ["entity_type"], unique=False)
    op.create_index(
        "idx_entities_mention_count", "entities", ["mention_count"], unique=False
    )

    op.create_table(
        "entity_mentions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("story_id", sa.Integer(), nullable=True),
        sa.Column("mention_context", sa.Text(), nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("prominence_score", sa.Float(), nullable=True),
        sa.Column(
            "mentioned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["entities.id"],
            name="fk_entity_mentions_entity_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["items.id"],
            name="fk_entity_mentions_article_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["story_id"],
            ["stories.id"],
            name="fk_entity_mentions_story_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "entity_id", "article_id", name="uq_entity_mentions_entity_article"
        ),
    )
    op.create_index(
        "idx_entity_mentions_entity_id", "entity_mentions", ["entity_id"], unique=False
    )
    op.create_index(
        "idx_entity_mentions_article_id",
        "entity_mentions",
        ["article_id"],
        unique=False,
    )
    op.create_index(
        "idx_entity_mentions_story_id", "entity_mentions", ["story_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_entity_mentions_story_id", table_name="entity_mentions")
    op.drop_index("idx_entity_mentions_article_id", table_name="entity_mentions")
    op.drop_index("idx_entity_mentions_entity_id", table_name="entity_mentions")
    op.drop_table("entity_mentions")

    op.drop_index("idx_entities_mention_count", table_name="entities")
    op.drop_index("idx_entities_type", table_name="entities")
    op.drop_index("idx_entities_canonical_type", table_name="entities")
    op.drop_table("entities")
