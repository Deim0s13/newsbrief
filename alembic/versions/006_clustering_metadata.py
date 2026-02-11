"""Add clustering metadata storage for 'Why Grouped' feature.

Revision ID: 006
Revises: 005
Create Date: 2026-02-10

Adds:
- clustering_metadata_json column to stories table for storing clustering
  decision data (shared entities, keywords, similarity scores)

Part of Issue #232: Add 'Why grouped together' explanation panel
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "006_clustering_metadata"
down_revision: str = "005_llm_quality_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add clustering_metadata_json column to stories table."""
    op.add_column(
        "stories",
        sa.Column(
            "clustering_metadata_json",
            sa.Text(),
            nullable=True,
            comment="JSON storing clustering decision data: shared entities, keywords, similarity scores",
        ),
    )


def downgrade() -> None:
    """Remove clustering_metadata_json column from stories table."""
    op.drop_column("stories", "clustering_metadata_json")
