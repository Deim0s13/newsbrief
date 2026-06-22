"""Add confidence_score column to stories (#220).

Confidence score (0.0-1.0) reflects the reliability of the story synthesis,
combining source credibility, article breadth, recency, and synthesis quality.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018_confidence_score"
down_revision: Union[str, Sequence[str], None] = "017_embedding_vector_768"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stories", sa.Column("confidence_score", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("stories", "confidence_score")
