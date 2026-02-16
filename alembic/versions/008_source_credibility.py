"""Add source credibility table.

Revision ID: 008_source_credibility
Revises: 007_reclassify_jobs
Create Date: 2026-02-16

Creates source_credibility table for storing external credibility ratings
(MBFC, etc.) with support for multiple providers and future internal signals.

Part of Issue #196: Create source_credibility database schema
See ADR-0028: Source Credibility Architecture
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "008_source_credibility"
down_revision: str = "007_reclassify_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create source_credibility table
    op.create_table(
        "source_credibility",
        # Primary key
        sa.Column("id", sa.Integer(), primary_key=True),
        # Core identification
        sa.Column(
            "domain",
            sa.String(255),
            unique=True,
            nullable=False,
            comment="Canonical domain (e.g., nytimes.com)",
        ),
        sa.Column(
            "name",
            sa.String(255),
            comment="Human-readable source name",
        ),
        sa.Column(
            "homepage_url",
            sa.Text(),
            comment="Source homepage URL",
        ),
        # Source classification (NOT a score penalty - ADR-0028)
        sa.Column(
            "source_type",
            sa.String(20),
            nullable=False,
            server_default="news",
            comment="Type: news, satire, conspiracy, fake_news, pro_science, state_media, advocacy",
        ),
        # Factual reporting - the ONLY input to credibility_score
        sa.Column(
            "factual_reporting",
            sa.String(20),
            comment="Factual accuracy: very_high, high, mostly_factual, mixed, low, very_low",
        ),
        # Political bias - metadata only, NOT used in scoring (ADR-0028)
        sa.Column(
            "bias",
            sa.String(20),
            comment="Political bias: left, left_center, center, right_center, right (metadata only)",
        ),
        # Computed credibility score (0.0-1.0, based on factual_reporting only)
        sa.Column(
            "credibility_score",
            sa.Numeric(3, 2),
            comment="Computed score 0.00-1.00 based on factual_reporting only",
        ),
        # Synthesis eligibility (satire/fake excluded by default)
        sa.Column(
            "is_eligible_for_synthesis",
            sa.Boolean(),
            server_default="1",
            nullable=False,
            comment="Whether source can be included in story synthesis",
        ),
        # Provenance & versioning (ADR-0028)
        sa.Column(
            "provider",
            sa.String(50),
            nullable=False,
            server_default="mbfc_community",
            comment="Data provider: mbfc_community, mbfc_api, newsguard, manual",
        ),
        sa.Column(
            "provider_url",
            sa.Text(),
            comment="URL to provider's page for this source (e.g., MBFC review)",
        ),
        sa.Column(
            "dataset_version",
            sa.String(100),
            comment="Provider dataset version or commit SHA",
        ),
        sa.Column(
            "raw_payload",
            sa.Text(),
            comment="Original JSON payload from provider for troubleshooting",
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_updated",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Create indexes for common queries
    op.create_index(
        "idx_source_credibility_domain",
        "source_credibility",
        ["domain"],
    )
    op.create_index(
        "idx_source_credibility_type",
        "source_credibility",
        ["source_type"],
    )
    op.create_index(
        "idx_source_credibility_score",
        "source_credibility",
        ["credibility_score"],
    )
    op.create_index(
        "idx_source_credibility_provider",
        "source_credibility",
        ["provider"],
    )
    op.create_index(
        "idx_source_credibility_eligible",
        "source_credibility",
        ["is_eligible_for_synthesis"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_source_credibility_eligible", table_name="source_credibility")
    op.drop_index("idx_source_credibility_provider", table_name="source_credibility")
    op.drop_index("idx_source_credibility_score", table_name="source_credibility")
    op.drop_index("idx_source_credibility_type", table_name="source_credibility")
    op.drop_index("idx_source_credibility_domain", table_name="source_credibility")

    # Drop table
    op.drop_table("source_credibility")
