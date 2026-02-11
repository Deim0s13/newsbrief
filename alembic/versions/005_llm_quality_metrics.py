"""Add LLM quality metrics tracking.

Revision ID: 005
Revises: 004
Create Date: 2026-02-09

Creates:
- llm_metrics table for tracking per-operation LLM quality metrics
- Additional columns on stories table for quality breakdown storage

Part of Issue #105: Add output quality metrics and tracking
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005_llm_quality_metrics"
down_revision: str = "004_extraction_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create llm_metrics table for historical tracking
    op.create_table(
        "llm_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "operation_type",
            sa.String(50),
            nullable=False,
            comment="Type: synthesis, entity_extraction, topic_classification",
        ),
        sa.Column("model", sa.String(50), comment="LLM model used"),
        # Timing
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("generation_time_ms", sa.Integer(), comment="Time to generate in ms"),
        # Parse metrics
        sa.Column(
            "parse_success", sa.Boolean(), default=True, comment="Did parsing succeed"
        ),
        sa.Column(
            "parse_strategy",
            sa.String(30),
            comment="Strategy used: direct, markdown_block, brace_match, etc.",
        ),
        sa.Column(
            "repairs_applied",
            sa.Text(),
            comment="JSON array of repair types applied",
        ),
        sa.Column("retry_count", sa.Integer(), default=0, comment="Number of retries"),
        # Quality scores
        sa.Column(
            "quality_score",
            sa.Float(),
            comment="Overall quality score 0.0-1.0",
        ),
        sa.Column(
            "quality_breakdown",
            sa.Text(),
            comment="JSON breakdown of quality components",
        ),
        # Token usage
        sa.Column("token_count_input", sa.Integer(), comment="Input tokens"),
        sa.Column("token_count_output", sa.Integer(), comment="Output tokens"),
        # Context
        sa.Column(
            "story_id",
            sa.Integer(),
            sa.ForeignKey("stories.id", ondelete="SET NULL"),
            nullable=True,
            comment="Associated story if applicable",
        ),
        sa.Column(
            "article_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="SET NULL"),
            nullable=True,
            comment="Associated article if applicable",
        ),
        sa.Column("article_count", sa.Integer(), comment="Number of articles processed"),
        # Error tracking
        sa.Column("error_category", sa.String(50), comment="Error category if failed"),
        sa.Column("error_message", sa.Text(), comment="Error details if failed"),
    )

    # Create indexes for common queries
    op.create_index(
        "idx_llm_metrics_created_at", "llm_metrics", ["created_at"]
    )
    op.create_index(
        "idx_llm_metrics_operation", "llm_metrics", ["operation_type"]
    )
    op.create_index(
        "idx_llm_metrics_quality", "llm_metrics", ["quality_score"]
    )
    op.create_index(
        "idx_llm_metrics_success", "llm_metrics", ["parse_success"]
    )

    # Add new columns to stories table for quality breakdown
    op.add_column(
        "stories",
        sa.Column(
            "quality_breakdown_json",
            sa.Text(),
            comment="JSON breakdown of quality score components",
        ),
    )
    op.add_column(
        "stories",
        sa.Column(
            "title_source",
            sa.String(20),
            comment="Title source: llm or fallback",
        ),
    )
    op.add_column(
        "stories",
        sa.Column(
            "parse_strategy",
            sa.String(30),
            comment="JSON parsing strategy used",
        ),
    )


def downgrade() -> None:
    # Remove columns from stories
    op.drop_column("stories", "parse_strategy")
    op.drop_column("stories", "title_source")
    op.drop_column("stories", "quality_breakdown_json")

    # Drop indexes
    op.drop_index("idx_llm_metrics_success", table_name="llm_metrics")
    op.drop_index("idx_llm_metrics_quality", table_name="llm_metrics")
    op.drop_index("idx_llm_metrics_operation", table_name="llm_metrics")
    op.drop_index("idx_llm_metrics_created_at", table_name="llm_metrics")

    # Drop table
    op.drop_table("llm_metrics")
