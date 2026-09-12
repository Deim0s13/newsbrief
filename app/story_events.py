"""
Story Evolution & Timeline: event detection and lifecycle status (v0.9.2,
#206/#207, ADR-0023).

Two event types are created automatically, with no new LLM round-trip:

- ``broke``: created once, when a story is first generated (rule-based,
  purely descriptive -- no LLM needed for "this is new").
- ``update`` / ``development``: created whenever
  ``update_story_with_new_articles()`` (ADR-0004 versioning) creates a new
  version of an existing story. Classification is rule-based (new-article
  ratio + dormancy-then-reactivation), not LLM-classified -- see the
  "Known gaps" note below for why.

``story_status`` (breaking/developing/established) is a simple,
deterministic function of story age and update recency -- not narrative
judgment. It's set at write-time (when a broke/update event is created)
and can go stale for stories that simply stop getting new articles
without ever triggering another write; ``refresh_stale_story_statuses()``
sweeps for that case and is intended to be called opportunistically (e.g.
once per scheduled story-generation run).

Known gaps (deliberately out of scope for this pass, see ADR-0023 v0.9.2
addendum): ``correction`` and ``resolved`` event types are not
auto-detected. Reliably detecting "this new information contradicts
earlier reporting" needs a real old-synthesis-vs-new-synthesis comparison
(LLM or otherwise) and risks false positives if done cheaply; "resolved"
needs a definition of "concluded" this codebase doesn't have signal for
yet. Both remain valid values in the ``event_type``/``story_status``
columns for future/manual use, just not written by this module today.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.orm import Session

from .orm_models import Story, StoryEvent

logger = logging.getLogger(__name__)

# Thresholds for the rule-based event_type/significance/story_status logic
# below. Deliberately simple (no LLM) -- see module docstring.
DEVELOPMENT_NEW_ARTICLE_RATIO = 0.4  # >= this fraction of merged set is new
DEVELOPMENT_DORMANCY_HOURS = 6  # reactivating after this long counts as a "development"
BREAKING_WINDOW_HOURS = 6  # age since first_reported_at to still count as "breaking"
DEVELOPING_STALE_HOURS = 48  # no update in this long -> "established"


def create_broke_event(
    session: Session, story: Story, article_ids: Sequence[int]
) -> StoryEvent:
    """
    Record the initial 'broke' event for a brand-new story and initialize
    its lifecycle columns. Call after ``session.flush()`` has assigned
    ``story.id``, before the caller commits.
    """
    now = story.generated_at or datetime.now(UTC)
    source_count = _distinct_source_count(session, article_ids)
    description = (
        f"First reported with {len(article_ids)} article"
        f"{'s' if len(article_ids) != 1 else ''}"
        f" from {source_count} source{'s' if source_count != 1 else ''}"
    )

    event = StoryEvent(
        story_id=story.id,
        event_type="broke",
        event_title=story.title,
        event_description=description,
        source_articles_json=json.dumps(list(article_ids)),
        significance_score=_clamp(0.4 + 0.05 * len(article_ids)),
        occurred_at=now,
    )
    session.add(event)

    story.first_reported_at = now  # type: ignore[assignment]
    story.last_major_update = now  # type: ignore[assignment]
    story.update_count = 0  # type: ignore[assignment]
    story.story_status = "breaking"  # type: ignore[assignment]

    return event


def create_update_event(
    session: Session,
    new_story: Story,
    old_story: Story,
    new_article_ids: Sequence[int],
    total_article_count: int,
) -> StoryEvent:
    """
    Record an 'update'/'development' event when ``update_story_with_new_articles()``
    creates a new version. Call after the new story is flushed (so
    ``new_story.id`` is set) and before the caller commits.

    Carries forward ``first_reported_at``/``update_count`` from
    ``old_story`` onto ``new_story`` (a fresh version row otherwise has no
    memory of its own lineage's lifecycle history).
    """
    now = datetime.now(UTC)
    new_ratio = (
        len(new_article_ids) / total_article_count if total_article_count else 0.0
    )

    dormant = False
    if old_story.last_major_update:
        last_update = _ensure_aware(old_story.last_major_update)  # type: ignore[arg-type]
        dormant = (now - last_update) >= timedelta(hours=DEVELOPMENT_DORMANCY_HOURS)

    is_development = new_ratio >= DEVELOPMENT_NEW_ARTICLE_RATIO or dormant
    event_type = "development" if is_development else "update"

    source_count = _distinct_source_count(session, new_article_ids)
    description = (
        f"{len(new_article_ids)} new article"
        f"{'s' if len(new_article_ids) != 1 else ''}"
        f" from {source_count} source{'s' if source_count != 1 else ''} added"
    )
    if dormant and not is_development:
        # Shouldn't happen given the `or` above, kept for clarity if
        # thresholds are tuned independently later.
        description += " after a period of inactivity"

    significance = _clamp(0.3 + 0.4 * new_ratio + (0.2 if dormant else 0.0))

    event = StoryEvent(
        story_id=new_story.id,
        event_type=event_type,
        event_title=new_story.title,
        event_description=description,
        source_articles_json=json.dumps(list(new_article_ids)),
        significance_score=significance,
        occurred_at=now,
    )
    session.add(event)

    new_update_count: int = (old_story.update_count or 0) + 1  # type: ignore[assignment]
    new_story.first_reported_at = old_story.first_reported_at or now  # type: ignore[assignment]
    new_story.last_major_update = now  # type: ignore[assignment]
    new_story.update_count = new_update_count  # type: ignore[assignment]
    new_story.story_status = _derive_story_status(  # type: ignore[assignment]
        first_reported_at=new_story.first_reported_at,  # type: ignore[arg-type]
        last_major_update=now,
        update_count=new_update_count,
        now=now,
    )

    return event


def refresh_stale_story_statuses(session: Session) -> int:
    """
    Bulk-transition stories whose ``story_status`` has gone stale purely
    from time passing (no new event to trigger a write) -- e.g. a
    'breaking' story older than ``BREAKING_WINDOW_HOURS`` with no
    update yet, or a 'developing' story quiet for
    ``DEVELOPING_STALE_HOURS``. Intended to be called opportunistically
    (e.g. once per scheduled story-generation run), not on a tight loop.

    Returns the number of rows updated. Commits internally (small,
    self-contained maintenance operation, mirroring
    ``cleanup_archived_stories()``'s style elsewhere in this module).
    """
    now = datetime.now(UTC)
    breaking_cutoff = now - timedelta(hours=BREAKING_WINDOW_HOURS)
    stale_cutoff = now - timedelta(hours=DEVELOPING_STALE_HOURS)

    result = session.execute(
        text(
            """
            UPDATE stories
            SET story_status = CASE
                WHEN COALESCE(last_major_update, first_reported_at) < :stale_cutoff
                    THEN 'established'
                WHEN first_reported_at < :breaking_cutoff
                    THEN 'developing'
                ELSE story_status
            END
            WHERE status = 'active'
              AND story_status IN ('breaking', 'developing')
              AND (
                    (story_status = 'breaking' AND first_reported_at < :breaking_cutoff)
                 OR (COALESCE(last_major_update, first_reported_at) < :stale_cutoff)
              )
            """
        ),
        {"breaking_cutoff": breaking_cutoff, "stale_cutoff": stale_cutoff},
    )
    updated = result.rowcount or 0  # type: ignore[attr-defined]
    session.commit()
    if updated:
        logger.info("refresh_stale_story_statuses: transitioned %d stories", updated)
    return updated


def get_story_events(session: Session, story_id: int) -> List[Dict[str, Any]]:
    """Chronological event list for a story's detail page/API (oldest first)."""
    events = (
        session.query(StoryEvent)
        .filter(StoryEvent.story_id == story_id)
        .order_by(StoryEvent.occurred_at.asc())
        .all()
    )
    out = []
    for e in events:
        try:
            source_articles = json.loads(str(e.source_articles_json or "[]"))
        except (json.JSONDecodeError, TypeError):
            source_articles = []
        out.append(
            {
                "id": e.id,
                "event_type": e.event_type,
                "event_title": e.event_title,
                "event_description": e.event_description,
                "source_articles": source_articles,
                "significance_score": e.significance_score,
                "occurred_at": e.occurred_at,
            }
        )
    return out


def _derive_story_status(
    *,
    first_reported_at: Optional[datetime],
    last_major_update: Optional[datetime],
    update_count: int,
    now: Optional[datetime] = None,
) -> str:
    now = now or datetime.now(UTC)
    if not first_reported_at:
        return "breaking"
    first_reported_at = _ensure_aware(first_reported_at)
    reference = (
        _ensure_aware(last_major_update) if last_major_update else first_reported_at
    )

    if (now - reference) >= timedelta(hours=DEVELOPING_STALE_HOURS):
        return "established"
    if update_count > 0 or (now - first_reported_at) >= timedelta(
        hours=BREAKING_WINDOW_HOURS
    ):
        return "developing"
    return "breaking"


def _distinct_source_count(session: Session, article_ids: Sequence[int]) -> int:
    if not article_ids:
        return 0
    try:
        row = session.execute(
            text(
                """
                SELECT COUNT(DISTINCT i.feed_id)
                FROM items i
                WHERE i.id = ANY(:ids)
                """
            ),
            {"ids": list(article_ids)},
        ).scalar()
        return int(row or 0)
    except Exception:
        # Best-effort only -- never block event creation over this.
        return 0


def _ensure_aware(dt: datetime) -> datetime:
    """Normalize naive datetimes (assume UTC) so timedelta math is safe."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))
