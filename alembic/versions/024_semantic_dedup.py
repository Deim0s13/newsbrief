"""Add semantic dedupe columns to items (#257, ADR-0026).

Post-hoc duplicate flagging: after an item is embedded, it may be flagged as
a likely duplicate of an earlier item published within the dedupe window.
Distinct from the existing exact-match ``url_hash``/``content_hash`` dedup
(app/feeds.py), which still runs at ingest time.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "024_semantic_dedup"
down_revision: Union[str, Sequence[str], None] = "023_item_embedding_error"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "items", sa.Column("duplicate_of_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "items", sa.Column("duplicate_similarity", sa.Float(), nullable=True)
    )
    op.add_column(
        "items",
        sa.Column("duplicate_detection_method", sa.String(length=20), nullable=True),
    )
    op.create_foreign_key(
        "fk_items_duplicate_of_id",
        "items",
        "items",
        ["duplicate_of_id"],
        ["id"],
    )
    op.create_index(
        "idx_items_duplicate_of_id", "items", ["duplicate_of_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_items_duplicate_of_id", table_name="items")
    op.drop_constraint("fk_items_duplicate_of_id", "items", type_="foreignkey")
    op.drop_column("items", "duplicate_detection_method")
    op.drop_column("items", "duplicate_similarity")
    op.drop_column("items", "duplicate_of_id")
