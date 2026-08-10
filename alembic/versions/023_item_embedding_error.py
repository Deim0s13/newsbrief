"""Add items.embedding_error for embedding failure observability (#278, ADR-0026).

Mirrors the existing ``processing_error`` pattern: set on a failed embed
attempt, cleared on the next successful embed. Enables an operator-visible
count of items whose embedding generation is failing, distinct from items
that simply haven't been embedded yet.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "023_item_embedding_error"
down_revision: Union[str, Sequence[str], None] = "022_retrieval_traces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("items", sa.Column("embedding_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("items", "embedding_error")
