"""Add stories consensus/divergence columns (#204, ADR-0023, v0.9.1).

Phase 2 of the Multi-Perspective Synthesis milestone: consensus points
(facts multiple sources agree on) and divergence points (topics where
sources disagree/emphasize differently), extracted in the same synthesis
LLM call as the rest of the story (see ``app/llm_output.py
SynthesisOutput`` / ``app/stories.py _run_synthesis_pass()``) rather than
a separate round-trip.

Null/empty-list is the common case -- most clusters in a personal feed
simply agree or complement each other rather than diverge -- not a
failure signal. Currently only populated by the direct synthesis strategy
(<=8 articles per cluster); map-reduce/hierarchical clusters leave these
columns null (see #204 scoping note in app/stories.py).
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "031_consensus_divergence"
down_revision: Union[str, Sequence[str], None] = "030_perspective_detection"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stories", sa.Column("consensus_points_json", sa.Text(), nullable=True)
    )
    op.add_column(
        "stories", sa.Column("divergence_points_json", sa.Text(), nullable=True)
    )
    op.add_column(
        "stories",
        sa.Column("source_agreement_score", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stories", "source_agreement_score")
    op.drop_column("stories", "divergence_points_json")
    op.drop_column("stories", "consensus_points_json")
