"""Cross-cutting semantic search endpoint (#255, ADR-0026)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from ..deps import session_scope
from ..models import SemanticSearchOut, SimilarityResultOut
from ..retrieval import (
    DEFAULT_MIN_SIMILARITY,
    DEFAULT_TOP_K,
    MAX_TOP_K,
    ContentType,
    RetrievalService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["search"])


@router.get("/search/semantic", response_model=SemanticSearchOut)
def semantic_search(
    q: str = Query(..., min_length=1, description="Free-text query"),
    content_type: ContentType = Query(
        "article", description="Search articles or stories"
    ),
    top_k: int = Query(DEFAULT_TOP_K, ge=1, le=MAX_TOP_K, description="Max results"),
    min_similarity: float = Query(
        DEFAULT_MIN_SIMILARITY, ge=0.0, le=1.0, description="Minimum cosine similarity"
    ),
):
    """Embed ``q`` via Ollama and return the closest articles/stories by cosine similarity."""
    try:
        with session_scope() as s:
            results = RetrievalService(s).find_by_text(
                q, content_type=content_type, top_k=top_k, min_similarity=min_similarity
            )
            return SemanticSearchOut(
                query=q,
                content_type=content_type,
                results=[SimilarityResultOut(**r.__dict__) for r in results],
            )
    except Exception as e:
        logger.error("Semantic search failed for query %r: %s", q, e, exc_info=True)
        raise HTTPException(status_code=503, detail=f"Semantic search failed: {e}")
