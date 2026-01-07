"""Initial schema - all tables for NewsBrief

Revision ID: 001_initial
Revises:
Create Date: 2026-01-06

This migration creates all tables from scratch.
For existing SQLite databases, run: alembic stamp head
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables."""
    # Feeds table
    op.create_table(
        "feeds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text()),
        sa.Column("etag", sa.Text()),
        sa.Column("last_modified", sa.Text()),
        sa.Column("robots_allowed", sa.Integer(), server_default="1"),
        sa.Column("disabled", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
        sa.Column("last_fetch_at", sa.DateTime()),
        sa.Column("last_success_at", sa.DateTime()),
        sa.Column("fetch_count", sa.Integer(), server_default="0"),
        sa.Column("success_count", sa.Integer(), server_default="0"),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0"),
        sa.Column("last_response_time_ms", sa.Integer()),
        sa.Column("avg_response_time_ms", sa.Integer()),
        sa.Column("last_error", sa.Text()),
        sa.Column("health_score", sa.Float(), server_default="100.0"),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.Text()),
        sa.Column("priority", sa.Integer(), server_default="1"),
        sa.Column("last_modified_check", sa.DateTime()),
        sa.Column("etag_check", sa.DateTime()),
    )
    op.create_index("idx_feeds_health_score", "feeds", ["health_score"])

    # Items table
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("feed_id", sa.Integer(), sa.ForeignKey("feeds.id"), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("url_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("published", sa.DateTime()),
        sa.Column("author", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("content", sa.Text()),
        sa.Column("content_hash", sa.Text()),
        sa.Column("ai_summary", sa.Text()),
        sa.Column("ai_model", sa.Text()),
        sa.Column("ai_generated_at", sa.DateTime()),
        sa.Column("structured_summary_json", sa.Text()),
        sa.Column("structured_summary_model", sa.Text()),
        sa.Column("structured_summary_content_hash", sa.Text()),
        sa.Column("structured_summary_generated_at", sa.DateTime()),
        sa.Column("ranking_score", sa.Float(), server_default="0.0"),
        sa.Column("topic", sa.Text()),
        sa.Column("topic_confidence", sa.Float(), server_default="0.0"),
        sa.Column("source_weight", sa.Float(), server_default="1.0"),
        sa.Column("entities_json", sa.Text()),
        sa.Column("entities_extracted_at", sa.DateTime()),
        sa.Column("entities_model", sa.Text()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("idx_items_published", "items", ["published"])
    op.create_index("idx_items_content_hash", "items", ["content_hash"])
    op.create_index("idx_items_ranking_score", "items", ["ranking_score"])
    op.create_index("idx_items_topic", "items", ["topic"])
    op.create_index(
        "idx_items_ranking_composite", "items", ["topic", "ranking_score", "published"]
    )
    op.create_index(
        "idx_structured_summary_cache",
        "items",
        ["structured_summary_content_hash", "structured_summary_model"],
    )

    # Stories table
    op.create_table(
        "stories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("synthesis", sa.Text(), nullable=False),
        sa.Column("key_points_json", sa.Text()),
        sa.Column("why_it_matters", sa.Text()),
        sa.Column("topics_json", sa.Text()),
        sa.Column("entities_json", sa.Text()),
        sa.Column("article_count", sa.Integer(), server_default="0"),
        sa.Column("importance_score", sa.Float(), server_default="0.0"),
        sa.Column("freshness_score", sa.Float(), server_default="0.0"),
        sa.Column("quality_score", sa.Float(), server_default="0.5"),
        sa.Column("cluster_method", sa.String(50)),
        sa.Column("story_hash", sa.String(64), unique=True),
        sa.Column("generated_at", sa.DateTime()),
        sa.Column("first_seen", sa.DateTime()),
        sa.Column("last_updated", sa.DateTime()),
        sa.Column("time_window_start", sa.DateTime()),
        sa.Column("time_window_end", sa.DateTime()),
        sa.Column("model", sa.String(50)),
        sa.Column("status", sa.String(20), server_default="'active'"),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column("previous_version_id", sa.Integer(), sa.ForeignKey("stories.id")),
    )
    op.create_index("idx_stories_generated_at", "stories", ["generated_at"])
    op.create_index("idx_stories_importance", "stories", ["importance_score"])
    op.create_index("idx_stories_status", "stories", ["status"])
    op.create_index("idx_stories_previous_version", "stories", ["previous_version_id"])

    # Story-Articles junction table
    op.create_table(
        "story_articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "story_id",
            sa.Integer(),
            sa.ForeignKey("stories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "article_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relevance_score", sa.Float(), server_default="1.0"),
        sa.Column("is_primary", sa.Boolean(), server_default="0"),
        sa.Column("added_at", sa.DateTime()),
        sa.UniqueConstraint("story_id", "article_id", name="uq_story_article"),
    )
    op.create_index("idx_story_articles_story", "story_articles", ["story_id"])
    op.create_index("idx_story_articles_article", "story_articles", ["article_id"])

    # Synthesis cache table
    op.create_table(
        "synthesis_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cache_key", sa.String(64), nullable=False, unique=True),
        sa.Column("article_ids_json", sa.Text(), nullable=False),
        sa.Column("model", sa.String(50), nullable=False),
        sa.Column("synthesis", sa.Text(), nullable=False),
        sa.Column("key_points_json", sa.Text()),
        sa.Column("why_it_matters", sa.Text()),
        sa.Column("topics_json", sa.Text()),
        sa.Column("entities_json", sa.Text()),
        sa.Column("token_count_input", sa.Integer()),
        sa.Column("token_count_output", sa.Integer()),
        sa.Column("generation_time_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("expires_at", sa.DateTime()),
        sa.Column("invalidated_at", sa.DateTime()),
    )
    op.create_index("idx_synthesis_cache_key", "synthesis_cache", ["cache_key"])
    op.create_index("idx_synthesis_cache_expires", "synthesis_cache", ["expires_at"])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("synthesis_cache")
    op.drop_table("story_articles")
    op.drop_table("stories")
    op.drop_table("items")
    op.drop_table("feeds")
