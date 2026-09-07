"""Add items.perspective_json column (#203, ADR-0023, v0.9.1).

Phase 1 of the Multi-Perspective Synthesis milestone: perspective/viewpoint
classification (political leaning, stakeholder, regional scope, tone) for
each article, extracted in the same LLM call as entity extraction (see
``app/entities.py extract_entities()`` / ``ArticlePerspective``) rather than
a separate round-trip.

Deliberately a single nullable column, not a new table -- most articles
have no identifiable perspective at all, and this is a 1:1 per-article
classification cached alongside (but kept separate from) ``entities_json``,
reusing the existing ``entities_model``/``entities_extracted_at`` columns
for cache-validity tracking since both are produced by the same call.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "030_perspective_detection"
down_revision: Union[str, Sequence[str], None] = "029_entity_intelligence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("items", sa.Column("perspective_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("items", "perspective_json")
