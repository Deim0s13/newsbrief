"""
Entity-based story connections (#202, ADR-0023, v0.9.0).

Complements the embedding-based ``/stories/{id}/related``
(``app/retrieval.py``, ADR-0026) with a different signal: two stories
connected because they mention the same real-world entities, not because
their synthesized text is semantically similar. Both are useful and
independent -- this module doesn't replace or feed into retrieval.py, and
reads only from the ``entities``/``entity_mentions`` tables populated by
``app/entity_normalization.py``.

Algorithm (per #202's own issue notes):
- Stories sharing 2+ entities are considered "strongly" related; those
  sharing exactly 1 are still surfaced (weaker) but ranked lower.
- Weighted by entity role/prominence (``entity_mentions.prominence_score``,
  already blends confidence x role -- see entity_normalization.py) and by
  temporal proximity (candidates closer in time to the source story rank
  higher, all else equal, via exponential decay).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5
MAX_TOP_K = 50
DEFAULT_MIN_SHARED_ENTITIES = 1
# Stories sharing this many entities or more are flagged "strong" (#202).
STRONG_CONNECTION_THRESHOLD = 2
# Temporal decay half-life in days: two candidates with equal entity overlap
# are ranked by recency relative to the source story.
TEMPORAL_DECAY_HALF_LIFE_DAYS = 14.0


@dataclass
class SharedEntity:
    id: int
    canonical_name: str
    entity_type: str


@dataclass
class EntityConnection:
    story_id: int
    title: str
    generated_at: Optional[datetime]
    shared_entity_count: int
    score: float
    strength: str  # "strong" (2+ shared entities) or "weak" (1)
    shared_entities: List[SharedEntity] = field(default_factory=list)


def find_entity_connected_stories(
    session: Session,
    story_id: int,
    *,
    top_k: int = DEFAULT_TOP_K,
    min_shared_entities: int = DEFAULT_MIN_SHARED_ENTITIES,
) -> List[EntityConnection]:
    """
    Other stories sharing entities with ``story_id``, ranked by shared entity
    count first, then a role/prominence + temporal-proximity score.

    Empty if the story has no normalized entity mentions yet (e.g. it
    predates #199, or backfill hasn't reached it yet) -- this is a read-only
    query over whatever's already in entity_mentions, not a fallback to the
    legacy entities_json blob.
    """
    top_k = max(1, min(top_k, MAX_TOP_K))
    min_shared_entities = max(1, min_shared_entities)

    source_row = session.execute(
        text("SELECT generated_at FROM stories WHERE id = :sid"),
        {"sid": story_id},
    ).first()
    if source_row is None:
        return []
    source_generated_at: Optional[datetime] = source_row[0]

    rows = session.execute(
        text(
            """
            WITH source_entities AS (
                SELECT DISTINCT entity_id, COALESCE(prominence_score, 0.5) AS prominence
                FROM entity_mentions
                WHERE story_id = :sid
            ),
            candidates AS (
                SELECT
                    em.story_id AS candidate_story_id,
                    em.entity_id,
                    COALESCE(em.prominence_score, 0.5) + se.prominence AS pair_weight
                FROM entity_mentions em
                JOIN source_entities se ON se.entity_id = em.entity_id
                WHERE em.story_id IS NOT NULL AND em.story_id != :sid
            )
            SELECT
                c.candidate_story_id,
                COUNT(DISTINCT c.entity_id) AS shared_count,
                SUM(c.pair_weight) AS weight_sum,
                s.title,
                s.generated_at
            FROM candidates c
            JOIN stories s ON s.id = c.candidate_story_id
            GROUP BY c.candidate_story_id, s.title, s.generated_at
            HAVING COUNT(DISTINCT c.entity_id) >= :min_shared
            ORDER BY shared_count DESC, weight_sum DESC
            LIMIT :limit
            """
        ),
        {"sid": story_id, "min_shared": min_shared_entities, "limit": top_k},
    ).fetchall()

    if not rows:
        return []

    candidate_ids = [int(r[0]) for r in rows]
    shared_by_story = _shared_entities_by_story(session, story_id, candidate_ids)

    connections: List[EntityConnection] = []
    for candidate_id, shared_count, weight_sum, title, generated_at in rows:
        temporal_factor = _temporal_proximity_factor(source_generated_at, generated_at)
        score = round(float(weight_sum) * temporal_factor, 4)
        connections.append(
            EntityConnection(
                story_id=int(candidate_id),
                title=title or "",
                generated_at=generated_at,
                shared_entity_count=int(shared_count),
                score=score,
                strength=(
                    "strong" if shared_count >= STRONG_CONNECTION_THRESHOLD else "weak"
                ),
                shared_entities=shared_by_story.get(int(candidate_id), []),
            )
        )

    # Re-sort in Python too: the SQL ORDER BY already does this, but scoring
    # by the temporal-adjusted score (not the raw weight_sum) can reorder
    # same-shared-count candidates.
    connections.sort(key=lambda c: (-c.shared_entity_count, -c.score))
    return connections


def _temporal_proximity_factor(
    source: Optional[datetime], candidate: Optional[datetime]
) -> float:
    """Exponential decay by day-distance; a missing timestamp is neutral (1.0)."""
    if source is None or candidate is None:
        return 1.0
    days = abs((source - candidate).total_seconds()) / 86400.0
    return 0.5 ** (days / TEMPORAL_DECAY_HALF_LIFE_DAYS)


def _shared_entities_by_story(
    session: Session, story_id: int, candidate_story_ids: List[int]
) -> Dict[int, List[SharedEntity]]:
    """Which specific entities each candidate shares with ``story_id`` (for UI chips)."""
    if not candidate_story_ids:
        return {}
    rows = session.execute(
        text(
            """
            SELECT DISTINCT em.story_id, e.id, e.canonical_name, e.entity_type
            FROM entity_mentions em
            JOIN entities e ON e.id = em.entity_id
            WHERE em.story_id IN :candidate_ids
            AND em.entity_id IN (
                SELECT DISTINCT entity_id FROM entity_mentions WHERE story_id = :sid
            )
            """
        ).bindparams(bindparam("candidate_ids", expanding=True)),
        {"candidate_ids": candidate_story_ids, "sid": story_id},
    ).fetchall()
    out: Dict[int, List[SharedEntity]] = {}
    for candidate_story_id, entity_id, canonical_name, entity_type in rows:
        out.setdefault(int(candidate_story_id), []).append(
            SharedEntity(
                id=int(entity_id),
                canonical_name=canonical_name,
                entity_type=entity_type,
            )
        )
    return out
