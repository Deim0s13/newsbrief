"""
Entity profile pages: single-entity detail view + basic search (#201,
ADR-0023, v0.9.0).

Reads only from the normalized ``entities`` / ``entity_mentions`` tables
(populated by ``app/entity_normalization.py``) -- no LLM calls, no changes to
the existing per-article extraction or clustering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

DEFAULT_TIMELINE_LIMIT = 25
DEFAULT_CO_MENTIONED_LIMIT = 10
DEFAULT_SEARCH_LIMIT = 25
MAX_SEARCH_LIMIT = 100


@dataclass
class MentionTimelineItem:
    """One mention of the entity, chronological (most recent first)."""

    article_id: int
    article_title: str
    published: Optional[datetime]
    story_id: Optional[int]
    story_title: Optional[str]
    mentioned_at: datetime
    prominence_score: Optional[float]


@dataclass
class CoMentionedEntity:
    """Another entity that co-occurs with this one (shared article or story)."""

    id: int
    canonical_name: str
    entity_type: str
    co_mention_count: int


@dataclass
class EntityProfile:
    id: int
    canonical_name: str
    entity_type: str
    aliases: List[str]
    description: Optional[str]
    first_seen: datetime
    last_seen: datetime
    mention_count: int
    timeline: List[MentionTimelineItem] = field(default_factory=list)
    co_mentioned: List[CoMentionedEntity] = field(default_factory=list)


@dataclass
class EntitySearchResult:
    id: int
    canonical_name: str
    entity_type: str
    mention_count: int
    last_seen: datetime


def get_entity_profile(
    session: Session,
    entity_id: int,
    *,
    timeline_limit: int = DEFAULT_TIMELINE_LIMIT,
    co_mentioned_limit: int = DEFAULT_CO_MENTIONED_LIMIT,
) -> Optional[EntityProfile]:
    """Full profile for one entity, or ``None`` if the id doesn't exist."""
    row = session.execute(
        text(
            "SELECT id, canonical_name, entity_type, aliases, description, "
            "first_seen, last_seen, mention_count FROM entities WHERE id = :eid"
        ),
        {"eid": entity_id},
    ).first()
    if row is None:
        return None

    timeline = _get_mention_timeline(session, entity_id, limit=timeline_limit)
    co_mentioned = _get_co_mentioned_entities(
        session, entity_id, limit=co_mentioned_limit
    )

    return EntityProfile(
        id=row[0],
        canonical_name=row[1],
        entity_type=row[2],
        aliases=list(row[3] or []),
        description=row[4],
        first_seen=row[5],
        last_seen=row[6],
        mention_count=row[7],
        timeline=timeline,
        co_mentioned=co_mentioned,
    )


def _get_mention_timeline(
    session: Session, entity_id: int, *, limit: int
) -> List[MentionTimelineItem]:
    rows = session.execute(
        text(
            """
            SELECT
                em.article_id, i.title, i.published,
                em.story_id, s.title,
                em.mentioned_at, em.prominence_score
            FROM entity_mentions em
            JOIN items i ON i.id = em.article_id
            LEFT JOIN stories s ON s.id = em.story_id
            WHERE em.entity_id = :eid
            ORDER BY em.mentioned_at DESC
            LIMIT :limit
            """
        ),
        {"eid": entity_id, "limit": limit},
    ).fetchall()

    return [
        MentionTimelineItem(
            article_id=r[0],
            article_title=r[1] or "",
            published=r[2],
            story_id=r[3],
            story_title=r[4],
            mentioned_at=r[5],
            prominence_score=r[6],
        )
        for r in rows
    ]


def _get_co_mentioned_entities(
    session: Session, entity_id: int, *, limit: int
) -> List[CoMentionedEntity]:
    """
    Other entities appearing in the same articles as this one, ranked by how
    often they co-occur. Simple count-based join over ``article_id`` (per the
    plan's own scope note) -- not weighted by prominence or story overlap.
    """
    rows = session.execute(
        text(
            """
            SELECT e.id, e.canonical_name, e.entity_type, COUNT(*) AS co_count
            FROM entity_mentions em1
            JOIN entity_mentions em2
                ON em2.article_id = em1.article_id AND em2.entity_id != em1.entity_id
            JOIN entities e ON e.id = em2.entity_id
            WHERE em1.entity_id = :eid
            GROUP BY e.id, e.canonical_name, e.entity_type
            ORDER BY co_count DESC, e.canonical_name ASC
            LIMIT :limit
            """
        ),
        {"eid": entity_id, "limit": limit},
    ).fetchall()

    return [
        CoMentionedEntity(
            id=r[0],
            canonical_name=r[1],
            entity_type=r[2],
            co_mention_count=int(r[3]),
        )
        for r in rows
    ]


def search_entities(
    session: Session,
    query: str,
    *,
    limit: int = DEFAULT_SEARCH_LIMIT,
    entity_type: Optional[str] = None,
) -> List[EntitySearchResult]:
    """
    Case-insensitive substring search over ``canonical_name`` and the
    ``aliases`` JSONB array. Empty/whitespace-only ``query`` returns the most
    mentioned entities instead of an empty result (useful as a default
    "browse" listing on the search page).
    """
    limit = max(1, min(limit, MAX_SEARCH_LIMIT))
    query = query.strip()

    params: dict = {"limit": limit}
    where_parts: List[str] = []

    if query:
        where_parts.append(
            "(canonical_name ILIKE :pattern OR "
            "EXISTS (SELECT 1 FROM jsonb_array_elements_text(aliases) AS a "
            "WHERE a ILIKE :pattern))"
        )
        params["pattern"] = f"%{query}%"

    if entity_type:
        where_parts.append("entity_type = :entity_type")
        params["entity_type"] = entity_type

    sql = (
        "SELECT id, canonical_name, entity_type, mention_count, last_seen FROM entities"
    )
    if where_parts:
        sql += " WHERE " + " AND ".join(where_parts)
    sql += " ORDER BY mention_count DESC, canonical_name ASC LIMIT :limit"

    rows = session.execute(text(sql), params).fetchall()

    return [
        EntitySearchResult(
            id=r[0],
            canonical_name=r[1],
            entity_type=r[2],
            mention_count=r[3],
            last_seen=r[4],
        )
        for r in rows
    ]
