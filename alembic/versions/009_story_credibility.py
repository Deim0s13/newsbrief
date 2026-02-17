"""Add credibility fields to stories table.

Revision ID: 009_story_credibility
Revises: 008_source_credibility
Create Date: 2026-02-17

Adds source credibility integration to stories for synthesis weighting.
Tracks aggregate credibility score and flags for low-credibility stories.

Part of Issue #198: Integrate credibility scores into story synthesis
See ADR-0028: Source Credibility Architecture
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "009_story_credibility"
down_revision: str = "008_source_credibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add credibility fields to stories table
    op.add_column(
        "stories",
        sa.Column(
            "source_credibility_score",
            sa.Float(),
            nullable=True,
            comment="Weighted average credibility of sources (0.0-1.0)",
        ),
    )
    op.add_column(
        "stories",
        sa.Column(
            "low_credibility_warning",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="True if all sources have credibility < 0.5",
        ),
    )
    op.add_column(
        "stories",
        sa.Column(
            "sources_excluded",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Count of ineligible sources filtered from synthesis",
        ),
    )

    # Add index for querying by credibility
    op.create_index(
        "idx_stories_credibility",
        "stories",
        ["source_credibility_score"],
    )
    op.create_index(
        "idx_stories_low_cred_warning",
        "stories",
        ["low_credibility_warning"],
    )


def downgrade() -> None:
    # Remove indexes
    op.drop_index("idx_stories_low_cred_warning", table_name="stories")
    op.drop_index("idx_stories_credibility", table_name="stories")

    # Remove columns
    op.drop_column("stories", "sources_excluded")
    op.drop_column("stories", "low_credibility_warning")
    op.drop_column("stories", "source_credibility_score")
