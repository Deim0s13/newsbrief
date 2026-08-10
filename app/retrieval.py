"""
Semantic similarity retrieval over pgvector embeddings (#255, ADR-0026).

Read-only: queries the existing ``items.embedding`` / ``stories.embedding``
columns populated by ``item_embeddings.py`` / ``story_embeddings.py``. Does
not touch clustering, synthesis, or ingestion — this is the foundation the
rest of the v0.8.6 RAG milestone (#256-#262) builds on.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from .orm_models import Item, Story

logger = logging.getLogger(__name__)

DEFAULT_TOP_K = 5
DEFAULT_MIN_SIMILARITY = 0.7
MAX_TOP_K = 50

ContentType = Literal["article", "story"]


@dataclass
class SimilarityResult:
    """One retrieval hit: entity id/title plus cosine similarity (0.0-1.0)."""

    id: int
    title: str
    similarity: float
    published_at: Optional[datetime] = None
    url: Optional[str] = None


class RetrievalService:
    """pgvector cosine-similarity search across articles (items) and stories."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def find_similar_articles(
        self,
        article_id: int,
        *,
        top_k: int = DEFAULT_TOP_K,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        date_range: Optional[Tuple[datetime, datetime]] = None,
        query_type: str = "similar_articles",
    ) -> List[SimilarityResult]:
        """
        Articles semantically similar to ``article_id``. Empty if it has no embedding.

        ``date_range`` restricts candidates by ``published`` (falling back to
        ``created_at``); ``query_type`` lets callers (e.g. semantic dedupe,
        #257) tag the resulting :mod:`app.retrieval_tracing` row distinctly
        from a plain "similar articles" lookup.
        """
        source = self.session.get(Item, article_id)
        if source is None or source.embedding is None:
            return []
        started = time.monotonic()
        results = self._search_items(
            source.embedding,  # type: ignore[arg-type]
            exclude_id=article_id,
            top_k=top_k,
            min_similarity=min_similarity,
            date_range=date_range,
        )
        filters: Dict[str, Any] = {"top_k": top_k, "min_similarity": min_similarity}
        if date_range is not None:
            filters["date_range"] = [d.isoformat() for d in date_range]
        self._trace(
            query_type=query_type,
            source_id=article_id,
            source_type="article",
            results=results,
            filters_applied=filters,
            started=started,
        )
        return results

    def find_related_stories(
        self,
        story_id: int,
        *,
        top_k: int = DEFAULT_TOP_K,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        date_range: Optional[Tuple[datetime, datetime]] = None,
    ) -> List[SimilarityResult]:
        """Stories semantically related to ``story_id``. Empty if it has no embedding."""
        source = self.session.get(Story, story_id)
        if source is None or source.embedding is None:
            return []
        return self.find_related_stories_by_embedding(
            source.embedding,  # type: ignore[arg-type]
            exclude_id=story_id,
            top_k=top_k,
            min_similarity=min_similarity,
            date_range=date_range,
        )

    def find_related_stories_by_embedding(
        self,
        embedding: List[float],
        *,
        exclude_id: Optional[int] = None,
        top_k: int = DEFAULT_TOP_K,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
        date_range: Optional[Tuple[datetime, datetime]] = None,
        query_type: str = "related_stories",
    ) -> List[SimilarityResult]:
        """
        Stories semantically related to a raw embedding vector rather than an
        existing story row — used to look up anchors for a cluster that
        hasn't been synthesized into a story yet (#259, #279).
        """
        started = time.monotonic()
        results = self._search_stories(
            embedding,
            exclude_id=exclude_id,
            top_k=top_k,
            min_similarity=min_similarity,
            date_range=date_range,
        )
        filters: Dict[str, Any] = {"top_k": top_k, "min_similarity": min_similarity}
        if date_range is not None:
            filters["date_range"] = [d.isoformat() for d in date_range]
        self._trace(
            query_type=query_type,
            source_id=exclude_id,
            source_type="story",
            results=results,
            filters_applied=filters,
            started=started,
        )
        return results

    def find_by_text(
        self,
        query_text: str,
        *,
        content_type: ContentType = "article",
        top_k: int = DEFAULT_TOP_K,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
    ) -> List[SimilarityResult]:
        """Free-text semantic search: embeds ``query_text`` via Ollama, then searches."""
        query_text = (query_text or "").strip()
        if not query_text:
            return []
        embedding = self._embed_query_text(query_text)
        started = time.monotonic()
        if content_type == "story":
            results = self._search_stories(
                embedding, exclude_id=None, top_k=top_k, min_similarity=min_similarity
            )
        else:
            results = self._search_items(
                embedding, exclude_id=None, top_k=top_k, min_similarity=min_similarity
            )
        self._trace(
            query_type="semantic_search",
            source_id=None,
            source_type=content_type,
            results=results,
            filters_applied={
                "top_k": top_k,
                "min_similarity": min_similarity,
                "query_text": query_text[:200],
            },
            started=started,
        )
        return results

    def _trace(
        self,
        *,
        query_type: str,
        source_id: Optional[int],
        source_type: Optional[str],
        results: List[SimilarityResult],
        filters_applied: Dict[str, Any],
        started: float,
    ) -> None:
        """Best-effort trace insert (#256); never raises."""
        from .retrieval_tracing import record_retrieval_trace

        duration_ms = int((time.monotonic() - started) * 1000)
        record_retrieval_trace(
            self.session,
            query_type=query_type,
            source_id=source_id,
            source_type=source_type,
            retrieved_ids=[r.id for r in results],
            similarity_scores=[r.similarity for r in results],
            filters_applied=filters_applied,
            duration_ms=duration_ms,
        )

    @staticmethod
    def _embed_query_text(text: str) -> List[float]:
        from .embedding_service import create_embedding_service_from_settings

        async def _embed() -> List[float]:
            svc = create_embedding_service_from_settings()
            return await svc.embed_text(text)

        return asyncio.run(_embed())

    def _search_items(
        self,
        embedding: List[float],
        *,
        exclude_id: Optional[int],
        top_k: int,
        min_similarity: float,
        date_range: Optional[Tuple[datetime, datetime]] = None,
    ) -> List[SimilarityResult]:
        top_k = max(1, min(top_k, MAX_TOP_K))
        max_distance = 1.0 - min_similarity
        distance = Item.embedding.cosine_distance(embedding)
        published_at = func.coalesce(Item.published, Item.created_at)

        q = (
            self.session.query(
                Item.id,
                Item.title,
                Item.url,
                published_at.label("published_at"),
                distance.label("distance"),
            )
            .filter(Item.embedding.isnot(None))
            .filter(distance <= max_distance)
        )
        if exclude_id is not None:
            q = q.filter(Item.id != exclude_id)
        if date_range is not None:
            start, end = date_range
            q = q.filter(published_at >= start, published_at <= end)
        rows = q.order_by(distance).limit(top_k).all()

        return [
            SimilarityResult(
                id=r.id,
                title=r.title or "",
                similarity=round(1.0 - r.distance, 4),
                published_at=r.published_at,
                url=r.url,
            )
            for r in rows
        ]

    def _search_stories(
        self,
        embedding: List[float],
        *,
        exclude_id: Optional[int],
        top_k: int,
        min_similarity: float,
        date_range: Optional[Tuple[datetime, datetime]] = None,
    ) -> List[SimilarityResult]:
        top_k = max(1, min(top_k, MAX_TOP_K))
        max_distance = 1.0 - min_similarity
        distance = Story.embedding.cosine_distance(embedding)

        q = (
            self.session.query(
                Story.id, Story.title, Story.generated_at, distance.label("distance")
            )
            .filter(Story.embedding.isnot(None))
            .filter(distance <= max_distance)
        )
        if exclude_id is not None:
            q = q.filter(Story.id != exclude_id)
        if date_range is not None:
            start, end = date_range
            q = q.filter(Story.generated_at >= start, Story.generated_at <= end)
        rows = q.order_by(distance).limit(top_k).all()

        return [
            SimilarityResult(
                id=r.id,
                title=r.title or "",
                similarity=round(1.0 - r.distance, 4),
                published_at=r.generated_at,
            )
            for r in rows
        ]
