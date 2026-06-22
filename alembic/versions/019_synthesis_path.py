"""Add synthesis_path column to stories (#282).

Records whether the cluster was routed through the standard or deep
synthesis processing path, based on topic diversity and article count.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019_synthesis_path"
down_revision: Union[str, Sequence[str], None] = "018_confidence_score"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stories", sa.Column("synthesis_path", sa.String(20), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("stories", "synthesis_path")
