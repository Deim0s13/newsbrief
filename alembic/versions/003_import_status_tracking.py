"""Add status and progress tracking to import_history

Revision ID: 003_import_status_tracking
Revises: 002_import_tracking
Create Date: 2026-02-02

This migration adds status tracking for async OPML imports,
allowing the UI to poll for completion and show progress.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003_import_status_tracking"
down_revision: Union[str, Sequence[str], None] = "002_import_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add status and progress columns to import_history."""
    # Add status column: 'processing', 'completed', 'failed'
    op.add_column(
        "import_history",
        sa.Column(
            "status",
            sa.String(20),
            server_default="completed",
            nullable=False,
        ),
    )

    # Add total_feeds column to track expected count for progress
    op.add_column(
        "import_history",
        sa.Column("total_feeds", sa.Integer(), server_default="0"),
    )

    # Add processed_feeds column to track progress
    op.add_column(
        "import_history",
        sa.Column("processed_feeds", sa.Integer(), server_default="0"),
    )

    # Add completed_at timestamp (separate from imported_at which is start time)
    op.add_column(
        "import_history",
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    # Add error_message for failed imports
    op.add_column(
        "import_history",
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    # Create index on status for efficient polling queries
    op.create_index("idx_import_history_status", "import_history", ["status"])


def downgrade() -> None:
    """Remove status and progress columns from import_history."""
    op.drop_index("idx_import_history_status", table_name="import_history")
    op.drop_column("import_history", "error_message")
    op.drop_column("import_history", "completed_at")
    op.drop_column("import_history", "processed_feeds")
    op.drop_column("import_history", "total_feeds")
    op.drop_column("import_history", "status")
