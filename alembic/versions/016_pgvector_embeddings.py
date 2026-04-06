"""pgvector extension and embedding columns (#250, ADR-0026).

Adds vector(1536) embeddings and metadata on items and stories, with IVFFlat
indexes for cosine similarity. Requires PostgreSQL with pgvector (e.g.
pgvector/pgvector image).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "016_pgvector_embeddings"
down_revision: Union[str, Sequence[str], None] = "015_entity_processing_failure_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# OpenAI-compatible dimension; embedding service (#251) must emit this width.
EMBED_DIM = 1536

# IVFFlat lists: tune with sqrt(row_count) as data grows; 100 is a common default.
IVFFLAT_LISTS = 100


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    op.add_column(
        "items",
        sa.Column("embedding", Vector(EMBED_DIM), nullable=True),
    )
    op.add_column("items", sa.Column("embedding_model", sa.String(100), nullable=True))
    op.add_column("items", sa.Column("embedding_version", sa.String(50), nullable=True))
    op.add_column(
        "items", sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.add_column(
        "stories",
        sa.Column("embedding", Vector(EMBED_DIM), nullable=True),
    )
    op.add_column(
        "stories", sa.Column("embedding_model", sa.String(100), nullable=True)
    )
    op.add_column(
        "stories", sa.Column("embedding_version", sa.String(50), nullable=True)
    )
    op.add_column(
        "stories", sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True)
    )

    # lists is a fixed migration constant (not user input).
    op.execute(
        sa.text(
            f"""
            CREATE INDEX idx_items_embedding ON items
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = {IVFFLAT_LISTS})
            WHERE embedding IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX idx_stories_embedding ON stories
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = {IVFFLAT_LISTS})
            WHERE embedding IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_items_embedding"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_stories_embedding"))

    op.drop_column("stories", "embedded_at")
    op.drop_column("stories", "embedding_version")
    op.drop_column("stories", "embedding_model")
    op.drop_column("stories", "embedding")

    op.drop_column("items", "embedded_at")
    op.drop_column("items", "embedding_version")
    op.drop_column("items", "embedding_model")
    op.drop_column("items", "embedding")

    op.execute(sa.text("DROP EXTENSION IF EXISTS vector"))
