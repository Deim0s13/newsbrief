"""Add stories.context_anchors_json for structured context anchors (#279, #281, ADR-0026).

Formalizes the pre-synthesis retrieval hook (#279) and the existing
post-synthesis historical linking (#258) into a single, UI-facing payload:
a list of ``{story_id, title, similarity, published_at, kind, rationale}``
entries where ``kind`` is ``"current"`` (direct continuation of this story's
coverage) or ``"background"`` (related-but-distinct prior context). Distinct
from ``historical_links_json`` (#258, raw links) and ``synthesis_anchors_json``
(#259, prompt-injected anchors only).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "026_context_anchors"
down_revision: Union[str, Sequence[str], None] = "025_synthesis_anchors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stories", sa.Column("context_anchors_json", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("stories", "context_anchors_json")
