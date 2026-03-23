"""
Canonical article and story processing states (ADR-0030, GitHub #273).

Pipeline position is separate from ``Story.status`` (``active`` / ``archived``).
Invalid transitions are logged; callers decide whether to enforce strictly.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional, Set, Tuple

logger = logging.getLogger(__name__)


class ArticleProcessingState(str, Enum):
    """Article-level pipeline state (``items.processing_state``)."""

    DISCOVERED = "discovered"
    FETCHED = "fetched"
    EXTRACTED = "extracted"
    ENRICHED = "enriched"
    EMBEDDED = "embedded"
    CLUSTERED = "clustered"
    FAILED = "failed"


class StoryProcessingState(str, Enum):
    """Story-level pipeline state (``stories.processing_state``)."""

    CANDIDATE = "candidate"
    SYNTHESIZING = "synthesizing"
    CONTEXT_ENRICHED = "context_enriched"
    QUALITY_CHECKED = "quality_checked"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    FAILED = "failed"


# Ordered main path (excluding terminal FAILED) for monotonic forward rules.
_ARTICLE_MAIN_PATH: Tuple[ArticleProcessingState, ...] = (
    ArticleProcessingState.DISCOVERED,
    ArticleProcessingState.FETCHED,
    ArticleProcessingState.EXTRACTED,
    ArticleProcessingState.ENRICHED,
    ArticleProcessingState.EMBEDDED,
    ArticleProcessingState.CLUSTERED,
)

_STORY_MAIN_PATH: Tuple[StoryProcessingState, ...] = (
    StoryProcessingState.CANDIDATE,
    StoryProcessingState.SYNTHESIZING,
    StoryProcessingState.CONTEXT_ENRICHED,
    StoryProcessingState.QUALITY_CHECKED,
    StoryProcessingState.PUBLISHED,
    StoryProcessingState.ARCHIVED,
)

# After FAILED, these are valid retry targets (subset of main path).
_ARTICLE_RETRY_TARGETS: Set[ArticleProcessingState] = {
    ArticleProcessingState.FETCHED,
    ArticleProcessingState.EXTRACTED,
    ArticleProcessingState.ENRICHED,
}

_STORY_RETRY_TARGETS: Set[StoryProcessingState] = {
    StoryProcessingState.CANDIDATE,
    StoryProcessingState.SYNTHESIZING,
}


def _index_in(
    state: ArticleProcessingState, path: Tuple[ArticleProcessingState, ...]
) -> Optional[int]:
    try:
        return path.index(state)
    except ValueError:
        return None


def article_transition_allowed(
    from_state: ArticleProcessingState, to_state: ArticleProcessingState
) -> bool:
    """
    Return True if ``to_state`` is allowed from ``from_state``.

    Rules:
    - Same state is allowed (idempotent no-op).
    - Any state may transition to ``FAILED``.
    - From ``FAILED``, only retry targets or ``FAILED`` again are allowed.
    - Otherwise, only forward moves along the main path (skipping intermediate
      stages is allowed, e.g. ``fetched`` -> ``enriched`` for combined ingest).
    """
    if from_state == to_state:
        return True
    if to_state == ArticleProcessingState.FAILED:
        return True
    if from_state == ArticleProcessingState.FAILED:
        return to_state in _ARTICLE_RETRY_TARGETS

    i_from = _index_in(from_state, _ARTICLE_MAIN_PATH)
    i_to = _index_in(to_state, _ARTICLE_MAIN_PATH)
    if i_from is None or i_to is None:
        return False
    return i_to >= i_from


def story_transition_allowed(
    from_state: StoryProcessingState, to_state: StoryProcessingState
) -> bool:
    """
    Return True if ``to_state`` is allowed from ``from_state``.

    Rules:
    - Same state is allowed.
    - Any state may transition to ``FAILED``.
    - From ``FAILED``, only retry targets (or ``FAILED``) are allowed.
    - ``ARCHIVED`` may be reached from ``PUBLISHED`` or ``ARCHIVED`` (idempotent).
    - Otherwise forward moves on the main path (skips allowed until published).
    """
    if from_state == to_state:
        return True
    if to_state == StoryProcessingState.FAILED:
        return True
    if from_state == StoryProcessingState.FAILED:
        return to_state in _STORY_RETRY_TARGETS

    if to_state == StoryProcessingState.ARCHIVED:
        return from_state in (
            StoryProcessingState.PUBLISHED,
            StoryProcessingState.ARCHIVED,
        )

    i_from = _index_in(from_state, _STORY_MAIN_PATH)
    i_to = _index_in(to_state, _STORY_MAIN_PATH)
    if i_from is None or i_to is None:
        return False
    # Do not use main-path ordering for PUBLISHED -> ARCHIVED (handled above).
    if from_state == StoryProcessingState.ARCHIVED:
        return to_state == StoryProcessingState.ARCHIVED
    return i_to >= i_from


def log_invalid_article_transition(
    from_state: ArticleProcessingState,
    to_state: ArticleProcessingState,
    *,
    item_id: Optional[int] = None,
    context: str = "",
) -> None:
    """Log a warning when an article transition would be invalid."""
    if article_transition_allowed(from_state, to_state):
        return
    extra = f" item_id={item_id}" if item_id is not None else ""
    ctx = f" {context}" if context else ""
    logger.warning(
        "Invalid article processing transition: %s -> %s%s%s",
        from_state.value,
        to_state.value,
        extra,
        ctx,
    )


def log_invalid_story_transition(
    from_state: StoryProcessingState,
    to_state: StoryProcessingState,
    *,
    story_id: Optional[int] = None,
    context: str = "",
) -> None:
    """Log a warning when a story transition would be invalid."""
    if story_transition_allowed(from_state, to_state):
        return
    extra = f" story_id={story_id}" if story_id is not None else ""
    ctx = f" {context}" if context else ""
    logger.warning(
        "Invalid story processing transition: %s -> %s%s%s",
        from_state.value,
        to_state.value,
        extra,
        ctx,
    )


def coerce_article_state(value: Optional[str]) -> Optional[ArticleProcessingState]:
    """Parse DB/API string to enum, or None if missing."""
    if value is None or value == "":
        return None
    try:
        return ArticleProcessingState(value)
    except ValueError:
        return None


def coerce_story_state(value: Optional[str]) -> Optional[StoryProcessingState]:
    """Parse DB/API string to enum, or None if missing."""
    if value is None or value == "":
        return None
    try:
        return StoryProcessingState(value)
    except ValueError:
        return None


__all__ = [
    "ArticleProcessingState",
    "StoryProcessingState",
    "article_transition_allowed",
    "story_transition_allowed",
    "log_invalid_article_transition",
    "log_invalid_story_transition",
    "coerce_article_state",
    "coerce_story_state",
]
