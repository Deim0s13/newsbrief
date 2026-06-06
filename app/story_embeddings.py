"""
Persist story embeddings after synthesis (#253).

Uses the same master switch as article embeddings (#252).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy.orm import Session

from .embedding_service import create_embedding_service_from_settings
from .item_embeddings import is_embedding_generation_enabled
from .orm_models import Story

logger = logging.getLogger(__name__)


def build_story_embed_text(
    title: Optional[str], synthesis: Optional[str]
) -> Optional[str]:
    """Plain text for embedding: title + synthesis (issue #253)."""
    t = (title or "").strip()
    s = (synthesis or "").strip()
    if not t and not s:
        return None
    if not t:
        return s
    if not s:
        return t
    return f"{t}\n\n{s}"


def persist_story_embedding(
    story: Story,
    embedding: list[float],
    *,
    embedding_model: str,
    embedding_version: str,
) -> None:
    story.embedding = embedding  # type: ignore[assignment]
    story.embedding_model = (embedding_model or "")[:100]  # type: ignore[assignment]
    story.embedding_version = (embedding_version or "")[:50]  # type: ignore[assignment]
    story.embedded_at = datetime.now(UTC)  # type: ignore[assignment]


def maybe_embed_story_after_synthesis(session: Session, story: Story) -> None:
    """
    After synthesis is written on ``story`` (flushed so ``story.id`` is set),
    compute and store embedding. Failures are logged only.
    """
    if not is_embedding_generation_enabled():
        return
    if story.id is None:
        logger.debug("Skipping embed for story without id")
        return
    embed_text = build_story_embed_text(
        story.title,  # type: ignore[arg-type]
        story.synthesis,  # type: ignore[arg-type]
    )
    if not embed_text:
        logger.debug("Skipping embed for story %s: no text", story.id)
        return
    try:

        async def _embed() -> tuple[list[float], dict]:
            svc = create_embedding_service_from_settings()
            vec = await svc.embed_text(embed_text)
            return vec, svc.get_model_info()

        vector, info = asyncio.run(_embed())
        persist_story_embedding(
            story,
            vector,
            embedding_model=str(info.get("model", "")),
            embedding_version=str(info.get("version", "")),
        )
    except Exception as e:
        logger.warning(
            "Embedding failed for story %s (story row still saved): %s",
            story.id,
            e,
            exc_info=True,
        )
