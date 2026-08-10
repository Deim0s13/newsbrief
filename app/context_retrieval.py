"""
Bounded retrieval hook between clustering and synthesis (#279, ADR-0026).

Unlike ``app/light_rag.py`` (#259), which only selects a handful of
high-confidence anchors for the "direct" synthesis path's prompt, this hook
runs for *every* cluster regardless of synthesis strategy (direct,
map-reduce, hierarchical). Its output is bounded and inspectable (traced via
``app/retrieval_tracing.py``) and is treated as supporting context, not
canonical source facts — callers should not present it as verified fact
about the current cluster. ``app/stories.py`` formalizes it into the
per-story ``context_anchors`` payload (#281).
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from .light_rag import compute_cluster_embedding
from .retrieval import RetrievalService, SimilarityResult

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.65
DEFAULT_TOP_K = 5
DEFAULT_WINDOW_DAYS = 30
TRACE_QUERY_TYPE = "cluster_pre_synthesis"


def is_retrieval_hook_enabled() -> bool:
    """Master switch: env overrides JSON; default on."""
    raw = os.getenv("NEWSBRIEF_RETRIEVAL_HOOK_ENABLED", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    try:
        from .settings import get_settings_service

        cfg = get_settings_service().get_model_config().get("retrieval_hook", {})
        if cfg.get("enabled") is False:
            return False
    except Exception as e:
        logger.debug("retrieval_hook.enabled read failed: %s", e)
    return True


def get_retrieval_hook_settings() -> Dict[str, Any]:
    """``threshold`` / ``top_k`` / ``window_days`` from ``model_config.json``."""
    threshold, top_k, window_days = (
        DEFAULT_THRESHOLD,
        DEFAULT_TOP_K,
        DEFAULT_WINDOW_DAYS,
    )
    try:
        from .settings import get_settings_service

        cfg = get_settings_service().get_model_config().get("retrieval_hook", {})
        threshold = float(cfg.get("threshold", threshold))
        top_k = int(cfg.get("top_k", top_k))
        window_days = int(cfg.get("window_days", window_days))
    except Exception as e:
        logger.debug("retrieval_hook settings read failed: %s", e)
    return {"threshold": threshold, "top_k": top_k, "window_days": window_days}


def to_background_anchors(
    retrieved_context: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Convert the raw ``_retrieved_context`` entries stashed on a synthesis
    result into the structured ``context_anchors`` shape (#281): every
    pre-synthesis retrieval hit starts out tagged ``kind="background"``;
    ``app/historical_linking.py`` later promotes the continuation match (if
    any) to ``kind="current"`` once post-synthesis linking has run.
    """
    anchors = []
    for entry in retrieved_context:
        similarity = entry.get("similarity") or 0.0
        anchors.append(
            {
                "story_id": entry.get("story_id"),
                "title": entry.get("title"),
                "similarity": similarity,
                "published_at": entry.get("published_at"),
                "kind": "background",
                "rationale": (
                    f"Related prior coverage identified before synthesis "
                    f"(similarity {similarity:.0%})"
                ),
            }
        )
    return anchors


def retrieve_cluster_context(
    session: Session, article_ids: List[int]
) -> List[SimilarityResult]:
    """
    Bounded set of previously-published stories related to a cluster, looked
    up *before* synthesis runs (#279). Best-effort: returns ``[]`` on any
    failure, when disabled, or when the cluster has no embedded articles yet.
    """
    if not is_retrieval_hook_enabled():
        return []
    if not article_ids:
        return []
    try:
        embedding = compute_cluster_embedding(session, article_ids)
        if embedding is None:
            return []

        settings = get_retrieval_hook_settings()
        window_end = datetime.now(UTC)
        window_start = window_end - timedelta(days=settings["window_days"])

        return RetrievalService(session).find_related_stories_by_embedding(
            embedding,
            top_k=settings["top_k"],
            min_similarity=settings["threshold"],
            date_range=(window_start, window_end),
            query_type=TRACE_QUERY_TYPE,
        )
    except Exception as e:
        logger.warning(
            "Cluster pre-synthesis retrieval failed (continuing without context): %s",
            e,
            exc_info=True,
        )
        return []
