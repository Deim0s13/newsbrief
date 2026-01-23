"""Add import_history and failed_imports tables

Revision ID: 002_import_tracking
Revises: 001_initial
Create Date: 2026-01-23

This migration adds tables for tracking OPML feed imports
and handling failed feed imports.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002_import_tracking"
down_revision: Union[str, Sequence[str], None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create import tracking tables."""
    # Import history table - tracks OPML imports
    op.create_table(
        "import_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "imported_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("filename", sa.Text()),
        sa.Column("feeds_added", sa.Integer(), server_default="0"),
        sa.Column("feeds_updated", sa.Integer(), server_default="0"),
        sa.Column("feeds_skipped", sa.Integer(), server_default="0"),
        sa.Column("feeds_failed", sa.Integer(), server_default="0"),
        sa.Column("validation_enabled", sa.Boolean(), server_default="1"),
    )
    op.create_index("idx_import_history_date", "import_history", ["imported_at"])

    # Failed imports table - tracks feeds that failed validation
    op.create_table(
        "failed_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "import_id",
            sa.Integer(),
            sa.ForeignKey("import_history.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("feed_url", sa.Text(), nullable=False),
        sa.Column("feed_name", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("status", sa.String(20), server_default="'pending'"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime()),
        sa.Column("resolved_feed_id", sa.Integer(), sa.ForeignKey("feeds.id")),
    )
    op.create_index("idx_failed_imports_import_id", "failed_imports", ["import_id"])
    op.create_index("idx_failed_imports_status", "failed_imports", ["status"])


def downgrade() -> None:
    """Drop import tracking tables."""
    op.drop_table("failed_imports")
    op.drop_table("import_history")
