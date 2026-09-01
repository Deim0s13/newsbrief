"""Normalize per-article LLM entity extraction into the relational entity graph.

Consumes the existing ``ExtractedEntities`` output from ``app/entities.py``
(unchanged) and upserts it into the ``entities`` / ``entity_mentions`` tables
introduced for #199 (ADR-0023, v0.9.0). This module does not call the LLM --
it is a pure normalization/dedup step over already-extracted data, run
either go-forward (wired into ``extract_and_cache_entities``) or retroactively
(``python -m app.cli entity-backfill``).

Dedup strategy (exact-match only, per ADR-0023's own MVP mitigation -- no
fuzzy/LLM-based disambiguation in this pass): lowercase, strip a small set of
common corporate suffixes, and match within the same ``entity_type``. This
collapses e.g. "Apple Inc." and "Apple" into one entity, but will not merge
genuinely different spellings/aliases (e.g. "OpenAI" vs "Open AI").

Idempotent by design: re-normalizing the same article (e.g. during a
backfill re-run, or because clustering re-reads a cached extraction across
multiple story-generation passes) is a no-op for mentions already recorded --
safe to call on every ``extract_and_cache_entities`` invocation regardless of
cache hit/miss.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Dict, Iterable, Optional, Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from .entities import EntityWithMetadata, ExtractedEntities

logger = logging.getLogger(__name__)

# Maps ExtractedEntities category -> entities.entity_type value.
CATEGORY_TO_ENTITY_TYPE: Dict[str, str] = {
    "companies": "company",
    "products": "product",
    "people": "person",
    "technologies": "technology",
    "locations": "location",
}

# Role -> prominence multiplier, matching the weighting already used by
# get_entity_overlap() in app/entities.py for clustering similarity.
_ROLE_MULTIPLIER: Dict[str, float] = {
    "primary_subject": 1.5,
    "quoted": 1.2,
    "mentioned": 1.0,
}

_SUFFIX_RE = re.compile(
    r"[,]?\s+(inc|incorporated|corp|corporation|ltd|limited|llc|co|company|group|plc)\.?$",
    re.IGNORECASE,
)
_WS_RE = re.compile(r"\s+")


def canonicalize_entity_name(raw_name: str) -> str:
    """
    Canonicalize an entity name for exact-match dedup.

    "Apple Inc." / "Apple Inc" / "apple inc." all canonicalize to "Apple".
    Case of the *first* occurrence seen is preserved (lookups match
    case-insensitively via the DB's ``lower(canonical_name)`` unique index).
    """
    name = _WS_RE.sub(" ", raw_name).strip()
    name = _SUFFIX_RE.sub("", name)
    return name.strip().strip(".,").strip()


def _upsert_entity(session: Session, canonical_name: str, entity_type: str) -> int:
    """Find-or-create an Entity row by (lower(canonical_name), entity_type)."""
    row = session.execute(
        text(
            """
            INSERT INTO entities (canonical_name, entity_type)
            VALUES (:name, :etype)
            ON CONFLICT (lower(canonical_name), entity_type)
            DO UPDATE SET updated_at = now()
            RETURNING id
            """
        ),
        {"name": canonical_name, "etype": entity_type},
    ).first()
    assert row is not None
    return int(row[0])


def _record_mention(
    session: Session,
    entity_id: int,
    article_id: int,
    story_id: Optional[int],
    mention_context: Optional[str],
    prominence_score: Optional[float],
) -> bool:
    """
    Insert an EntityMention if one doesn't already exist for this
    (entity_id, article_id) pair; otherwise backfill story_id if it was
    previously NULL. Returns True if a new mention row was created.
    """
    existing = session.execute(
        text(
            "SELECT id, story_id FROM entity_mentions "
            "WHERE entity_id = :eid AND article_id = :aid"
        ),
        {"eid": entity_id, "aid": article_id},
    ).first()
    if existing:
        if story_id is not None and existing[1] is None:
            session.execute(
                text("UPDATE entity_mentions SET story_id = :sid WHERE id = :id"),
                {"sid": story_id, "id": existing[0]},
            )
        return False

    try:
        session.execute(
            text(
                """
                INSERT INTO entity_mentions
                    (entity_id, article_id, story_id, mention_context, prominence_score)
                VALUES (:eid, :aid, :sid, :context, :prominence)
                """
            ),
            {
                "eid": entity_id,
                "aid": article_id,
                "sid": story_id,
                "context": mention_context,
                "prominence": prominence_score,
            },
        )
    except IntegrityError:
        # Lost a race to another concurrent writer for the same
        # (entity_id, article_id) pair -- already recorded, nothing to do.
        session.rollback()
        return False

    session.execute(
        text(
            "UPDATE entities SET mention_count = mention_count + 1, "
            "last_seen = now() WHERE id = :id"
        ),
        {"id": entity_id},
    )
    return True


def normalize_and_store_entities(
    session: Session,
    article_id: int,
    entities: "ExtractedEntities",
    story_id: Optional[int] = None,
) -> int:
    """
    Normalize one article's extracted entities into entities/entity_mentions.

    Args:
        session: SQLAlchemy session (caller commits; this does not commit).
        article_id: The article the entities were extracted from.
        entities: Already-extracted entities (from entities.py; LLM call, if
            any, has already happened by the time this is called).
        story_id: Story the article has been clustered into, if known yet
            (usually not, at extraction time -- linked later via
            ``link_entity_mentions_to_story``).

    Returns:
        Number of *new* mention rows created (0 if everything was already
        recorded, e.g. a repeat pass over a cached extraction).
    """
    new_mentions = 0
    for category, entity_type in CATEGORY_TO_ENTITY_TYPE.items():
        raw_entities: Sequence = getattr(entities, category, [])
        for raw_entity in raw_entities:
            meta: "EntityWithMetadata" = entities._normalize_entity(raw_entity)
            name = (meta.name or "").strip()
            if not name:
                continue
            canonical = canonicalize_entity_name(name)
            if not canonical:
                continue

            try:
                entity_id = _upsert_entity(session, canonical, entity_type)
                role_mult = _ROLE_MULTIPLIER.get(meta.role, 1.0)
                prominence = round(min(meta.confidence * role_mult, 1.0), 4)
                if _record_mention(
                    session,
                    entity_id,
                    article_id,
                    story_id,
                    meta.disambiguation,
                    prominence,
                ):
                    new_mentions += 1
            except Exception:
                logger.warning(
                    "Entity normalization failed for article=%s entity=%r "
                    "(type=%s); skipping this entity",
                    article_id,
                    name,
                    entity_type,
                    exc_info=True,
                )
                session.rollback()

    return new_mentions


def link_entity_mentions_to_story(
    session: Session, story_id: int, article_ids: Iterable[int]
) -> int:
    """
    Backfill ``story_id`` onto existing entity_mentions rows for a set of
    articles once they've been clustered into a story.

    Called right after a Story row + its StoryArticle links are created
    (``_persist_synthesized_story`` / ``update_story_with_new_articles`` in
    app/stories.py). Safe to call even if some/all articles have no
    normalized mentions yet (e.g. extraction failed for that article) --
    those are simply skipped.
    """
    ids = list(article_ids)
    if not ids:
        return 0
    result = session.execute(
        text(
            """
            UPDATE entity_mentions
            SET story_id = :story_id
            WHERE article_id IN :article_ids
            """
        ).bindparams(bindparam("article_ids", expanding=True)),
        {"story_id": story_id, "article_ids": ids},
    )
    return result.rowcount or 0  # type: ignore[attr-defined]
