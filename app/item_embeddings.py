"""
Persist article embeddings after summarization (#252).

Shared helpers for #278 (pipeline enrichment): move the call site only.
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
    except Exception as e:
        logger.warning(
            "Embedding failed for item %s (article still saved): %s",
            item_id,
            e,
            exc_info=True,
        )
