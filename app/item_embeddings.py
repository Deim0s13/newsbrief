"""
Persist article embeddings after summarization (#252), made a first-class,
observable part of article processing rather than a side effect that can
silently be skipped (#278).

Covers: embedding on every fresh summarize (existing), embedding on a
cache-hit summary if the item still has no vector (closes a gap where
never-embedded items stay that way until a manual backfill), advancing
``ArticleProcessingState.EMBEDDED`` on success, and recording the last
failure message on ``items.embedding_error`` for operator visibility.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from .embedding_service import create_embedding_service_from_settings
from .models import StructuredSummary
from .orm_models import Item
from .processing_states import ArticleProcessingState, apply_article_processing_state
from .settings import get_settings_service

if TYPE_CHECKING:
    from .llm import SummaryResult

logger = logging.getLogger(__name__)


def is_embedding_generation_enabled() -> bool:
    """Master switch: env overrides JSON; default on."""
    raw = os.getenv("NEWSBRIEF_EMBEDDING_ENABLED", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    try:
        emb = get_settings_service().get_model_config().get("embedding", {})
        if emb.get("enabled") is False:
            return False
    except Exception as e:
        logger.debug("embedding.enabled read failed: %s", e)
    return True


def build_item_embed_text(
    title: Optional[str],
    *,
    structured_summary: Optional[StructuredSummary] = None,
    ai_summary: Optional[str] = None,
    feed_summary: Optional[str] = None,
) -> Optional[str]:
    """
    Plain text for Ollama embedding: title + summary-like body (not raw article HTML/body).
    Prefer structured summary, then AI plain summary, then RSS ``items.summary``.
    """
    t = (title or "").strip()
    body: Optional[str] = None
    if structured_summary is not None:
        bullets = "\n".join(f"- {b}" for b in structured_summary.bullets)
        body = f"{bullets}\n\n{structured_summary.why_it_matters}"
    elif ai_summary and str(ai_summary).strip():
        body = str(ai_summary).strip()
    elif feed_summary and str(feed_summary).strip():
        body = str(feed_summary).strip()
    if not body:
        return None
    if not t:
        return body
    return f"{t}\n\n{body}"


def persist_item_embedding(
    session: Session,
    item_id: int,
    embedding: list[float],
    *,
    embedding_model: str,
    embedding_version: str,
) -> None:
    item = session.get(Item, item_id)
    if item is None:
        return
    # SQLAlchemy Column descriptors are runtime-compatible with values; stubs disagree.
    item.embedding = embedding  # type: ignore[assignment]
    item.embedding_model = (embedding_model or "")[:100]  # type: ignore[assignment]
    item.embedding_version = (embedding_version or "")[:50]  # type: ignore[assignment]
    item.embedded_at = datetime.now(UTC)  # type: ignore[assignment]
    item.embedding_error = None  # type: ignore[assignment]


def record_item_embedding_failure(
    session: Session,
    item_id: int,
    message: str,
) -> None:
    """Best-effort: record the last embedding failure for operator visibility (#278)."""
    try:
        item = session.get(Item, item_id)
        if item is None:
            return
        item.embedding_error = (message or "unknown error")[:2000]  # type: ignore[assignment]
    except Exception as e:
        logger.debug("Failed to record embedding_error for item %s: %s", item_id, e)


def _after_embed_success(session: Session, item_id: int, *, context: str) -> None:
    """Shared post-embed hooks: state transition + semantic dedupe check (#257)."""
    apply_article_processing_state(
        session,
        item_id,
        ArticleProcessingState.EMBEDDED,
        context=context,
    )
    try:
        from .semantic_dedup import maybe_flag_semantic_duplicate

        maybe_flag_semantic_duplicate(session, item_id)
    except Exception as e:
        logger.debug("Semantic dedupe hook skipped for item %s: %s", item_id, e)


def maybe_embed_item_after_summary(
    session: Session,
    item_id: int,
    title: Optional[str],
    result: "SummaryResult",
    *,
    use_structured: bool,
    feed_summary: Optional[str] = None,
) -> None:
    """
    After a fresh (non-cache) summarization, compute and store embedding. Failures are logged only.
    """
    if not is_embedding_generation_enabled():
        return
    if not result.success:
        return
    if result.cache_hit:
        return

    embed_text: Optional[str] = None
    if result.structured_summary is not None:
        embed_text = build_item_embed_text(
            title, structured_summary=result.structured_summary
        )
    elif result.summary and str(result.summary).strip():
        if use_structured:
            try:
                ss = StructuredSummary.from_json_string(
                    result.summary,
                    result.content_hash or "",
                    result.model,
                    datetime.now(UTC),
                )
                embed_text = build_item_embed_text(title, structured_summary=ss)
            except Exception:
                embed_text = build_item_embed_text(title, ai_summary=result.summary)
        else:
            embed_text = build_item_embed_text(title, ai_summary=result.summary)
    if not embed_text:
        embed_text = build_item_embed_text(title, feed_summary=feed_summary)
    if not embed_text:
        logger.debug("Skipping embed for item %s: no text", item_id)
        return

    try:

        async def _embed() -> tuple[list[float], dict]:
            svc = create_embedding_service_from_settings()
            vec = await svc.embed_text(embed_text)
            return vec, svc.get_model_info()

        vector, info = asyncio.run(_embed())
        persist_item_embedding(
            session,
            item_id,
            vector,
            embedding_model=str(info.get("model", "")),
            embedding_version=str(info.get("version", "")),
        )
        _after_embed_success(session, item_id, context="maybe_embed_item_after_summary")
    except Exception as e:
        logger.warning(
            "Embedding failed for item %s (article still saved): %s",
            item_id,
            e,
            exc_info=True,
        )
        record_item_embedding_failure(session, item_id, str(e))


def maybe_embed_item_if_missing(
    session: Session,
    item_id: int,
    title: Optional[str],
    *,
    structured_summary: Optional[StructuredSummary] = None,
    ai_summary: Optional[str] = None,
    feed_summary: Optional[str] = None,
) -> None:
    """
    Embed an item from already-available (cached) summary text if it has no
    embedding yet (#278).

    Closes a gap where a cache-hit ``/summarize`` response never calls
    :func:`maybe_embed_item_after_summary` at all, so an item summarized
    before embeddings existed (or while disabled) could stay unembedded
    forever without a manual backfill. Cheap no-op once embedded.
    """
    if not is_embedding_generation_enabled():
        return
    try:
        item = session.get(Item, item_id)
        if item is None or item.embedding is not None:
            return
    except Exception as e:
        logger.debug("maybe_embed_item_if_missing lookup failed for %s: %s", item_id, e)
        return

    embed_text = build_item_embed_text(
        title,
        structured_summary=structured_summary,
        ai_summary=ai_summary,
        feed_summary=feed_summary,
    )
    if not embed_text:
        return

    try:

        async def _embed() -> tuple[list[float], dict]:
            svc = create_embedding_service_from_settings()
            vec = await svc.embed_text(embed_text)
            return vec, svc.get_model_info()

        vector, info = asyncio.run(_embed())
        persist_item_embedding(
            session,
            item_id,
            vector,
            embedding_model=str(info.get("model", "")),
            embedding_version=str(info.get("version", "")),
        )
        _after_embed_success(session, item_id, context="maybe_embed_item_if_missing")
    except Exception as e:
        logger.warning(
            "Cache-hit backfill embedding failed for item %s: %s",
            item_id,
            e,
            exc_info=True,
        )
        record_item_embedding_failure(session, item_id, str(e))
