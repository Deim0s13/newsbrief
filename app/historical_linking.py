"""
Link new stories to semantically related historical stories (#258, ADR-0026).

Runs after story embedding (story_embeddings.py) so RetrievalService can query
on the fresh vector. Best-effort: failures are logged only and never block
story creation.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from .orm_models import Story
from .retrieval import RetrievalService

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.75
DEFAULT_WINDOW_DAYS = 30
DEFAULT_MAX_LINKS = 3


def is_historical_linking_enabled() -> bool:
    """Master switch, mirroring the embedding-generation on/off pattern."""
    raw = os.getenv("NEWSBRIEF_HISTORICAL_LINKING_ENABLED", "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def maybe_link_historical_context(
    session: Session,
    story: Story,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    window_days: int = DEFAULT_WINDOW_DAYS,
    max_links: int = DEFAULT_MAX_LINKS,
) -> None:
    """
    After ``story`` has an embedding (flushed so ``story.id`` is set), find
    semantically related stories from the past ``window_days`` (excluding
    today's run) and persist them as historical links.

    Sets ``historical_links_json`` (top ``max_links`` matches) and, if the
    closest match is above ``threshold``, ``continues_story_id`` /
    ``continues_similarity`` for the "Continues from..." UI (#261).
    """
    if not is_historical_linking_enabled():
        return
    if story.id is None or story.embedding is None:
        return
    try:
        now = datetime.now(UTC)
        window_start = now - timedelta(days=window_days)
        window_end = now - timedelta(minutes=1)  # exclude stories from this run

        results = RetrievalService(session).find_related_stories(
            int(story.id),
            top_k=max_links,
            min_similarity=threshold,
            date_range=(window_start, window_end),
        )

        links: List[Dict[str, Any]] = [
            {
                "story_id": r.id,
                "similarity": r.similarity,
                "linked_at": now.isoformat(),
            }
            for r in results
        ]
        story.historical_links_json = json.dumps(links)  # type: ignore[assignment]

        if results:
            top = results[0]
            story.continues_story_id = top.id  # type: ignore[assignment]
            story.continues_similarity = top.similarity  # type: ignore[assignment]
            logger.info(
                "Story %s linked as continuation of story %s (similarity=%.3f)",
                story.id,
                top.id,
                top.similarity,
            )
    except Exception as e:
        logger.warning(
            "Historical linking failed for story %s (story row still saved): %s",
            story.id,
            e,
            exc_info=True,
        )
