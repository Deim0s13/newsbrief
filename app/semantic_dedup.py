"""
Post-hoc semantic duplicate detection (#257, ADR-0026).

Runs after an article has a fresh embedding (see ``app/item_embeddings.py``),
not before ingest: comparing an item's embedding against other recently
embedded items and flagging a high-confidence match for operator review.

This is deliberately post-hoc rather than a pre-save ingest-path check —
embeddings are only available once an item has been summarized (#278), so
blocking ingestion on a synchronous embed call would add Ollama latency/risk
to the RSS fetch hot path. The existing exact-match dedup (``url_hash`` /
``content_hash`` in ``app/feeds.py``) is unaffected and still runs at
insert time.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from .orm_models import Item
from .retrieval import RetrievalService
from .settings import get_settings_service

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.92
DEFAULT_WINDOW_DAYS = 7
DEFAULT_ACTION = "flag"
_CHECK_TOP_K = 3
TRACE_QUERY_TYPE = "semantic_dedupe"


def is_semantic_dedupe_enabled() -> bool:
    """Master switch: env overrides JSON; default on."""
    raw = os.getenv("NEWSBRIEF_SEMANTIC_DEDUPE_ENABLED", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    try:
        cfg = get_settings_service().get_model_config().get("semantic_dedupe", {})
        if cfg.get("enabled") is False:
            return False
    except Exception as e:
        logger.debug("semantic_dedupe.enabled read failed: %s", e)
    return True


def get_semantic_dedupe_settings() -> Dict[str, Any]:
    """``threshold`` / ``window_days`` / ``action`` from ``model_config.json``."""
    threshold, window_days, action = (
        DEFAULT_THRESHOLD,
        DEFAULT_WINDOW_DAYS,
        DEFAULT_ACTION,
    )
    try:
        cfg = get_settings_service().get_model_config().get("semantic_dedupe", {})
        threshold = float(cfg.get("threshold", threshold))
        window_days = int(cfg.get("window_days", window_days))
        action = str(cfg.get("action", action) or action)
    except Exception as e:
        logger.debug("semantic_dedupe settings read failed: %s", e)
    return {"threshold": threshold, "window_days": window_days, "action": action}


def maybe_flag_semantic_duplicate(session: Session, item_id: int) -> None:
    """
    After ``item_id`` has a fresh embedding, check for a high-confidence
    semantic duplicate among recently embedded items and flag it (#257).

    Best-effort: never raises, and never removes or skips saving the article
    itself (``action: 'flag'`` is the only behavior implemented — the item
    stays visible with duplicate metadata set for operator review).
    """
    if not is_semantic_dedupe_enabled():
        return
    try:
        item = session.get(Item, item_id)
        if item is None or item.embedding is None:
            return

        settings = get_semantic_dedupe_settings()
        window_end = datetime.now(UTC)
        window_start = window_end - timedelta(days=settings["window_days"])

        results = RetrievalService(session).find_similar_articles(
            item_id,
            top_k=_CHECK_TOP_K,
            min_similarity=settings["threshold"],
            date_range=(window_start, window_end),
            query_type=TRACE_QUERY_TYPE,
        )
        if not results:
            return

        top = results[0]
        item.duplicate_of_id = top.id  # type: ignore[assignment]
        item.duplicate_similarity = top.similarity  # type: ignore[assignment]
        item.duplicate_detection_method = "semantic"  # type: ignore[assignment]
        logger.info(
            "Item %s flagged as likely semantic duplicate of item %s "
            "(similarity=%.3f, action=%s)",
            item_id,
            top.id,
            top.similarity,
            settings["action"],
        )
    except Exception as e:
        logger.warning(
            "Semantic dedupe check failed for item %s (article still saved): %s",
            item_id,
            e,
            exc_info=True,
        )


def list_flagged_semantic_duplicates(
    session: Session, *, limit: int = 50
) -> List[Dict[str, Any]]:
    """Items flagged as likely semantic duplicates, most recent first (admin review, #257)."""
    rows = (
        session.query(Item)
        .filter(Item.duplicate_of_id.isnot(None))
        .order_by(Item.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "item_id": r.id,
            "title": r.title,
            "url": r.url,
            "duplicate_of_id": r.duplicate_of_id,
            "duplicate_similarity": r.duplicate_similarity,
            "duplicate_detection_method": r.duplicate_detection_method,
        }
        for r in rows
    ]
