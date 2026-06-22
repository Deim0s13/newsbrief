"""Add confidence_warning column to stories (#287).

Marks stories where confidence_score falls below the warn threshold
but above the hold threshold — published but flagged with a warning badge.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020_confidence_warning"
down_revision: Union[str, Sequence[str], None] = "019_synthesis_path"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stories",
        sa.Column("confidence_warning", sa.Boolean(), nullable=True, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("stories", "confidence_warning")
