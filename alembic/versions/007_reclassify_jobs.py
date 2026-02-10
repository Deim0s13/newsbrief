"""Add reclassify_jobs table for async topic reclassification tracking.

Revision ID: 007
Revises: 006
Create Date: 2026-02-10

Creates:
- reclassify_jobs table for tracking async reclassification job status

Part of Issue #248: UI for article topic reclassification
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "007_reclassify_jobs"
down_revision: str = "006_clustering_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create reclassify_jobs table."""
    op.create_table(
        "reclassify_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            default="pending",
            comment="Job status: pending, running, completed, cancelled, failed",
        ),
        sa.Column(
            "total_articles",
            sa.Integer(),
            nullable=False,
            default=0,
            comment="Total articles to process",
        ),
        sa.Column(
            "processed_articles",
            sa.Integer(),
            nullable=False,
            default=0,
            comment="Articles processed so far",
        ),
        sa.Column(
            "changed_articles",
            sa.Integer(),
            nullable=False,
            default=0,
            comment="Articles with topic changed",
        ),
        sa.Column(
            "error_count",
            sa.Integer(),
            nullable=False,
            default=0,
            comment="Number of processing errors",
        ),
        sa.Column(
            "batch_size",
            sa.Integer(),
            nullable=False,
            default=100,
            comment="Batch size configuration",
        ),
        sa.Column(
            "use_llm",
            sa.Boolean(),
            nullable=False,
            default=True,
            comment="Whether to use LLM for classification",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            comment="Job creation timestamp",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Job start timestamp",
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Job completion timestamp",
        ),
        sa.Column(
            "error_message",
            sa.Text(),
            nullable=True,
            comment="Error message if job failed",
        ),
    )

    # Index for querying recent/active jobs
    op.create_index(
        "idx_reclassify_jobs_status",
        "reclassify_jobs",
        ["status"],
    )
    op.create_index(
        "idx_reclassify_jobs_created",
        "reclassify_jobs",
        ["created_at"],
    )


def downgrade() -> None:
    """Drop reclassify_jobs table."""
    op.drop_index("idx_reclassify_jobs_created", table_name="reclassify_jobs")
    op.drop_index("idx_reclassify_jobs_status", table_name="reclassify_jobs")
    op.drop_table("reclassify_jobs")
