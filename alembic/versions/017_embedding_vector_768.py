"""Reduce embedding column width to 768 for Ollama embedders (#251).

nomic-embed-text / similar models emit 768 dimensions. Existing non-null
vectors (1536-dim) are cleared before alter — re-embed after upgrade.

IVFFlat indexes are recreated for cosine similarity.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017_embedding_vector_768"
down_revision: Union[str, Sequence[str], None] = "016_pgvector_embeddings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

IVFFLAT_LISTS = 100


def upgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_items_embedding"))
    op.execute(sa.text("DROP INDEX IF EXISTS idx_stories_embedding"))

    # Dimension change invalidates stored vectors; avoid ALTER failures on
    # incompatible lengths.
    op.execute(sa.text("UPDATE items SET embedding = NULL WHERE embedding IS NOT NULL"))
    op.execute(
        sa.text("UPDATE stories SET embedding = NULL WHERE embedding IS NOT NULL")
    )

    op.execute(sa.text("ALTER TABLE items ALTER COLUMN embedding TYPE vector(768)"))
    op.execute(sa.text("ALTER TABLE stories ALTER COLUMN embedding TYPE vector(768)"))

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

    op.execute(sa.text("UPDATE items SET embedding = NULL WHERE embedding IS NOT NULL"))
    op.execute(
        sa.text("UPDATE stories SET embedding = NULL WHERE embedding IS NOT NULL")
    )

    op.execute(sa.text("ALTER TABLE items ALTER COLUMN embedding TYPE vector(1536)"))
    op.execute(sa.text("ALTER TABLE stories ALTER COLUMN embedding TYPE vector(1536)"))

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
