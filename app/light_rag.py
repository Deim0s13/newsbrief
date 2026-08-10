"""
Light RAG: inject high-confidence historical story anchors into synthesis
prompts for continuity (#259, ADR-0026).

Anchors are selected just before synthesis by embedding the cluster (mean of
its articles' existing embeddings — no extra Ollama call needed) and
searching for related, previously-published stories via the existing
pgvector retrieval, gated at a high similarity threshold and capped to a
handful of anchors to avoid prompt bloat.

Scoped to the "direct" synthesis path (roughly <= 8 articles, the common
case) for #259; the broader retrieval hook that also covers map-reduce and
hierarchical strategies is #279.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .orm_models import Item, Story
from .retrieval import RetrievalService

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.78
DEFAULT_MAX_ANCHORS = 3
DEFAULT_WINDOW_DAYS = 30
TRACE_QUERY_TYPE = "synthesis_anchors"


@dataclass
class SynthesisAnchor:
    """One historical story anchor considered for a synthesis prompt."""

    story_id: int
    title: str
    key_point: str
    similarity: float
    date: Optional[datetime] = None


def is_light_rag_enabled() -> bool:
    """Master switch: env overrides JSON; default on."""
    raw = os.getenv("NEWSBRIEF_LIGHT_RAG_ENABLED", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    try:
        from .settings import get_settings_service

        cfg = get_settings_service().get_model_config().get("light_rag", {})
        if cfg.get("enabled") is False:
            return False
    except Exception as e:
        logger.debug("light_rag.enabled read failed: %s", e)
    return True


def get_light_rag_settings() -> Dict[str, Any]:
    """``threshold`` / ``max_anchors`` / ``window_days`` from ``model_config.json``."""
    threshold, max_anchors, window_days = (
        DEFAULT_THRESHOLD,
        DEFAULT_MAX_ANCHORS,
        DEFAULT_WINDOW_DAYS,
    )
    try:
        from .settings import get_settings_service

        cfg = get_settings_service().get_model_config().get("light_rag", {})
        threshold = float(cfg.get("threshold", threshold))
        max_anchors = int(cfg.get("max_anchors", max_anchors))
        window_days = int(cfg.get("window_days", window_days))
    except Exception as e:
        logger.debug("light_rag settings read failed: %s", e)
    return {
        "threshold": threshold,
        "max_anchors": max_anchors,
        "window_days": window_days,
    }


def compute_cluster_embedding(
    session: Session, article_ids: List[int]
) -> Optional[List[float]]:
    """
    Mean of existing embeddings for ``article_ids``; ``None`` if none of the
    cluster's articles are embedded yet. Deliberately reuses embeddings
    already computed by ``app/item_embeddings.py`` rather than calling
    Ollama again here.
    """
    if not article_ids:
        return None
    rows = (
        session.query(Item.embedding)
        .filter(Item.id.in_(article_ids), Item.embedding.isnot(None))
        .all()
    )
    vectors = [list(r[0]) for r in rows if r[0] is not None]
    if not vectors:
        return None
    dims = len(vectors[0])
    sums = [0.0] * dims
    for v in vectors:
        for i in range(dims):
            sums[i] += v[i]
    n = len(vectors)
    return [s / n for s in sums]


def _lookup_key_point(session: Session, story_id: int) -> str:
    story = session.get(Story, story_id)
    if story is None:
        return ""
    try:
        key_points = (
            json.loads(str(story.key_points_json)) if story.key_points_json else []
        )
    except Exception:
        key_points = []
    if key_points:
        return str(key_points[0])[:160]
    return str(story.synthesis or "")[:160]


def select_synthesis_anchors(
    session: Session, article_ids: List[int]
) -> List[SynthesisAnchor]:
    """
    High-confidence historical story anchors for a cluster about to be
    synthesized (#259). Best-effort: returns ``[]`` on any failure, when
    disabled, or when the cluster has no embedded articles yet.
    """
    if not is_light_rag_enabled():
        return []
    try:
        embedding = compute_cluster_embedding(session, article_ids)
        if embedding is None:
            return []

        settings = get_light_rag_settings()
        window_end = datetime.now(UTC)
        window_start = window_end - timedelta(days=settings["window_days"])

        results = RetrievalService(session).find_related_stories_by_embedding(
            embedding,
            top_k=settings["max_anchors"],
            min_similarity=settings["threshold"],
            date_range=(window_start, window_end),
            query_type=TRACE_QUERY_TYPE,
        )
        if not results:
            return []

        return [
            SynthesisAnchor(
                story_id=r.id,
                title=r.title,
                key_point=_lookup_key_point(session, r.id),
                similarity=r.similarity,
                date=r.published_at,
            )
            for r in results[: settings["max_anchors"]]
        ]
    except Exception as e:
        logger.warning(
            "Synthesis anchor selection failed (continuing without anchors): %s",
            e,
            exc_info=True,
        )
        return []


def format_anchor_prompt_block(anchors: List[SynthesisAnchor]) -> str:
    """Render anchors as a prompt suffix; empty string when there are none."""
    if not anchors:
        return ""
    lines = [
        "\n\n## Historical Context",
        "Related previous coverage to consider for continuity:",
    ]
    for a in anchors:
        date_str = a.date.strftime("%Y-%m-%d") if a.date else "recent"
        lines.append(f'- "{a.title}" ({date_str}): {a.key_point}')
    lines.append(
        '\nIncorporate relevant continuity if appropriate (e.g. "this follows..." '
        'or "continuing coverage of..."); do not force a connection if these are '
        "not truly related to the current articles.\n"
    )
    return "\n".join(lines)
