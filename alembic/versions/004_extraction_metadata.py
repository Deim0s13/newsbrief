"""Add extraction metadata columns to items table

Revision ID: 004_extraction_metadata
Revises: 003_import_status_tracking
Create Date: 2026-02-02

This migration adds columns to track content extraction method, quality,
and performance metrics. Part of v0.8.0 Content Extraction Pipeline Upgrade.

See ADR-0024 for extraction library selection rationale.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "004_extraction_metadata"
down_revision: Union[str, Sequence[str], None] = "003_import_status_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add extraction metadata columns to items table."""
    # extraction_method: which extractor was used
    # Values: 'trafilatura', 'readability', 'rss_summary', 'failed', 'legacy'
    op.add_column(
        "items",
        sa.Column(
            "extraction_method",
            sa.String(20),
            server_default="legacy",
            nullable=False,
        ),
    )

    # extraction_quality: quality score from 0.0 to 1.0
    op.add_column(
        "items",
        sa.Column("extraction_quality", sa.Float(), nullable=True),
    )

    # extraction_error: error message/reason if extraction failed
    op.add_column(
        "items",
        sa.Column("extraction_error", sa.Text(), nullable=True),
    )

    # extracted_at: timestamp when content was extracted
    op.add_column(
        "items",
        sa.Column("extracted_at", sa.DateTime(), nullable=True),
    )

    # extraction_time_ms: how long extraction took (for performance monitoring)
    op.add_column(
        "items",
        sa.Column("extraction_time_ms", sa.Integer(), nullable=True),
    )

    # Index on extraction_method for dashboard queries
    op.create_index(
        "idx_items_extraction_method",
        "items",
        ["extraction_method"],
    )

    # Composite index for quality analysis queries
    op.create_index(
        "idx_items_extraction_quality",
        "items",
        ["extraction_method", "extraction_quality"],
    )


def downgrade() -> None:
    """Remove extraction metadata columns from items table."""
    op.drop_index("idx_items_extraction_quality", table_name="items")
    op.drop_index("idx_items_extraction_method", table_name="items")
    op.drop_column("items", "extraction_time_ms")
    op.drop_column("items", "extracted_at")
    op.drop_column("items", "extraction_error")
    op.drop_column("items", "extraction_quality")
    op.drop_column("items", "extraction_method")
