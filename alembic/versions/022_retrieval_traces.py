"""Add retrieval_traces table for semantic retrieval observability (#256, ADR-0026).

Logs completed similarity searches (similar articles, related stories,
semantic search) for debugging, evaluation, and quality monitoring.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022_retrieval_traces"
down_revision: Union[str, Sequence[str], None] = "021_historical_story_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "retrieval_traces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("query_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=20), nullable=True),
        sa.Column(
            "retrieved_ids_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "similarity_scores_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("filters_applied_json", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_retrieval_traces_type", "retrieval_traces", ["query_type"], unique=False
    )
    op.create_index(
        "idx_retrieval_traces_created",
        "retrieval_traces",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_retrieval_traces_created", table_name="retrieval_traces")
    op.drop_index("idx_retrieval_traces_type", table_name="retrieval_traces")
    op.drop_table("retrieval_traces")
