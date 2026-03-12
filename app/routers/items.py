"""Article (items) list, detail, by topic, LLM status, and summarize endpoints."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from ..deps import session_scope
from ..llm import OLLAMA_BASE_URL, get_llm_service, is_llm_available
from ..models import (
    ItemOut,
    LLMStatusOut,
    StructuredSummary,
    SummaryRequest,
    SummaryResponse,
    SummaryResultOut,
    extract_first_sentences,
)
from ..ranking import get_topic_display_name
from ..settings import get_settings_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["items"])


def _parse_structured(
    r, idx_json=10, idx_model=11, idx_chash=12, idx_ts=13, idx_content_hash=5
):
    """Parse structured summary from row indices."""
    if not (r[idx_json] and r[idx_model]):
        return None
    try:
        return StructuredSummary.from_json_string(
            r[idx_json],
            r[idx_chash] or r[idx_content_hash] or "",
            r[idx_model],
            (
                datetime.fromisoformat(r[idx_ts])
                if r[idx_ts]
                else datetime.now(timezone.utc)
            ),
        )
    except Exception as e:
        logger.warning(f"Failed to parse structured summary for item {r[0]}: {e}")
        return None


def _fallback_summary(row, content_idx=6, summary_idx=4, title_idx=1):
    """Build fallback summary from content/summary/title. Returns (summary or None, is_fallback)."""
    if not row[content_idx]:
        return None, False
    try:
        fallback = extract_first_sentences(row[content_idx], sentence_count=2)
        if not fallback.strip():
            fallback = (
                row[summary_idx] or row[title_idx] or "Content preview unavailable"
            )
        return fallback, True
    except Exception as e:
        logger.warning(f"Failed to extract fallback summary: {e}")
        return (
            row[summary_idx] or row[title_idx] or "Content preview unavailable",
            True,
        )


@router.get("/items", response_model=List[ItemOut])
def list_items(
    limit: int = Query(50, le=200),
    story_id: Optional[int] = Query(None, description="Filter by story ID"),
    topic: Optional[str] = Query(None, description="Filter by topic"),
    feed_id: Optional[int] = Query(None, description="Filter by feed ID"),
    published_after: Optional[datetime] = Query(
        None, description="Filter articles published after this date (ISO format)"
    ),
    published_before: Optional[datetime] = Query(
        None, description="Filter articles published before this date (ISO format)"
    ),
    has_story: Optional[bool] = Query(
        None, description="Filter by story association (true/false)"
    ),
):
    with session_scope() as s:
        if story_id is not None:
            story_exists = s.execute(
                text("SELECT id FROM stories WHERE id = :sid"),
                {"sid": story_id},
            ).first()
            if not story_exists:
                raise HTTPException(
                    status_code=404, detail=f"Story with ID {story_id} not found"
                )

        select_clause = """
        SELECT DISTINCT i.id, i.title, i.url, i.published, i.summary, i.content_hash, i.content,
               i.ai_summary, i.ai_model, i.ai_generated_at,
               i.structured_summary_json, i.structured_summary_model,
               i.structured_summary_content_hash, i.structured_summary_generated_at,
               i.ranking_score, i.topic, i.topic_confidence, i.source_weight,
               i.created_at, i.feed_id, COALESCE(i.published, i.created_at) AS sort_date
        FROM items i
        """
        joins: list[str] = []
        where_clauses: list[str] = []
        params: dict[str, Any] = {"lim": limit}

        if story_id is not None:
            joins.append("JOIN story_articles sa ON i.id = sa.article_id")
            where_clauses.append("sa.story_id = :story_id")
            params["story_id"] = story_id
        if topic is not None:
            where_clauses.append("i.topic = :topic")
            params["topic"] = topic
        if feed_id is not None:
            where_clauses.append("i.feed_id = :feed_id")
            params["feed_id"] = feed_id
        if published_after is not None:
            where_clauses.append("i.published >= :published_after")
            params["published_after"] = published_after.isoformat()
        if published_before is not None:
            where_clauses.append("i.published <= :published_before")
            params["published_before"] = published_before.isoformat()
        if has_story is not None:
            if has_story:
                where_clauses.append(
                    "EXISTS (SELECT 1 FROM story_articles sa2 WHERE sa2.article_id = i.id)"
                )
            else:
                where_clauses.append(
                    "NOT EXISTS (SELECT 1 FROM story_articles sa2 WHERE sa2.article_id = i.id)"
                )

        query = select_clause
        if joins:
            query += " " + " ".join(joins)
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        query += (
            " ORDER BY COALESCE(i.published, i.created_at) DESC, i.ranking_score DESC"
        )
        query += " LIMIT :lim"
        rows = s.execute(text(query), params).all()

        items = []
        for r in rows:
            structured_summary = _parse_structured(r, idx_content_hash=5)
            fallback_summary = None
            is_fallback = False
            has_ai_summary = structured_summary is not None or r[7] is not None
            if not has_ai_summary and r[6]:
                fallback_summary, is_fallback = _fallback_summary(r)
            items.append(
                ItemOut(
                    id=r[0],
                    title=r[1],
                    url=r[2],
                    published=r[3],
                    summary=r[4],
                    feed_id=r[19],
                    ai_summary=r[7],
                    ai_model=r[8],
                    ai_generated_at=r[9],
                    structured_summary=structured_summary,
                    fallback_summary=fallback_summary,
                    is_fallback_summary=is_fallback,
                    ranking_score=float(r[14]) if r[14] is not None else 0.0,
                    topic=r[15],
                    topic_confidence=float(r[16]) if r[16] is not None else 0.0,
                    source_weight=float(r[17]) if r[17] is not None else 1.0,
                )
            )
        return items


@router.get("/llm/status", response_model=LLMStatusOut)
def llm_status():
    """Get LLM service status and available models."""
    try:
        service = get_llm_service()
        available = service.is_available()
        models = []
        error = None
        if available:
            try:
                model_list = service.client.list()
                if isinstance(model_list, dict) and "models" in model_list:
                    models = [
                        m.get("name", m.get("model", ""))
                        for m in model_list["models"]
                        if m
                    ]
                else:
                    models = []
            except Exception as e:
                error = f"Could not list models: {e}"
        else:
            error = "LLM service not available"
        return LLMStatusOut(
            available=available,
            base_url=OLLAMA_BASE_URL,
            current_model=get_settings_service().get_active_model(),
            models_available=models,
            error=error,
        )
    except Exception as e:
        return LLMStatusOut(
            available=False,
            base_url=OLLAMA_BASE_URL,
            current_model=get_settings_service().get_active_model(),
            models_available=[],
            error=str(e),
        )


@router.post("/summarize", response_model=SummaryResponse)
def generate_summaries(request: SummaryRequest):
    """Generate AI summaries for specified items."""
    if not is_llm_available():
        raise HTTPException(status_code=503, detail="LLM service is not available")
    service = get_llm_service()
    results = []
    summaries_generated = 0
    errors = 0

    with session_scope() as s:
        for item_id in request.item_ids:
            try:
                row = s.execute(
                    text(
                        """
                    SELECT id, title, content, content_hash,
                           ai_summary, ai_model, ai_generated_at,
                           structured_summary_json, structured_summary_model,
                           structured_summary_content_hash, structured_summary_generated_at
                    FROM items
                    WHERE id = :item_id
                """
                    ),
                    {"item_id": item_id},
                ).first()

                if not row:
                    results.append(
                        SummaryResultOut(
                            item_id=item_id,
                            success=False,
                            error="Item not found",
                            cache_hit=False,
                        )
                    )
                    errors += 1
                    continue

                title, content, content_hash = row[1] or "", row[2] or "", row[3]
                structured_json, structured_model = row[7], row[8]
                active_model = get_settings_service().get_active_model()

                if (
                    request.use_structured
                    and structured_json
                    and not request.force_regenerate
                    and structured_model == (request.model or active_model)
                ):
                    try:
                        structured_summary = StructuredSummary.from_json_string(
                            structured_json,
                            content_hash or "",
                            structured_model,
                            (
                                datetime.fromisoformat(row[10])
                                if row[10]
                                else datetime.now(timezone.utc)
                            ),
                        )
                        results.append(
                            SummaryResultOut(
                                item_id=item_id,
                                success=True,
                                summary=structured_json,
                                model=structured_model,
                                structured_summary=structured_summary,
                                content_hash=content_hash,
                                cache_hit=True,
                            )
                        )
                        continue
                    except Exception as e:
                        logger.warning(
                            f"Failed to parse existing structured summary for item {item_id}: {e}"
                        )
                elif (
                    not request.use_structured
                    and row[4]
                    and not request.force_regenerate
                ):
                    results.append(
                        SummaryResultOut(
                            item_id=item_id,
                            success=True,
                            summary=row[4],
                            model=row[5] or "existing",
                            cache_hit=True,
                        )
                    )
                    continue

                result = service.summarize_article(
                    title=title,
                    content=content,
                    model=request.model,
                    use_structured=request.use_structured,
                )

                if result.success:
                    if not content_hash and result.content_hash:
                        s.execute(
                            text(
                                "UPDATE items SET content_hash = :content_hash WHERE id = :item_id"
                            ),
                            {"content_hash": result.content_hash, "item_id": item_id},
                        )
                    if request.use_structured and result.structured_summary:
                        s.execute(
                            text(
                                """
                            UPDATE items
                            SET structured_summary_json = :json_data,
                                structured_summary_model = :model,
                                structured_summary_content_hash = :content_hash,
                                structured_summary_generated_at = :generated_at
                            WHERE id = :item_id
                        """
                            ),
                            {
                                "json_data": result.structured_summary.to_json_string(),
                                "model": result.model,
                                "content_hash": result.content_hash,
                                "generated_at": result.structured_summary.generated_at.isoformat(),
                                "item_id": item_id,
                            },
                        )
                    else:
                        s.execute(
                            text(
                                """
                            UPDATE items
                            SET ai_summary = :summary, ai_model = :model, ai_generated_at = :generated_at
                            WHERE id = :item_id
                        """
                            ),
                            {
                                "summary": result.summary,
                                "model": result.model,
                                "generated_at": datetime.now(timezone.utc).isoformat(),
                                "item_id": item_id,
                            },
                        )
                    summaries_generated += 1
                else:
                    errors += 1

                results.append(
                    SummaryResultOut(
                        item_id=item_id,
                        success=result.success,
                        summary=result.summary if result.success else None,
                        model=result.model,
                        error=result.error,
                        tokens_used=result.tokens_used,
                        generation_time=result.generation_time,
                        structured_summary=result.structured_summary,
                        content_hash=result.content_hash,
                        cache_hit=result.cache_hit,
                    )
                )
            except Exception as e:
                logger.error(f"Error processing item {item_id}: {e}")
                results.append(
                    SummaryResultOut(
                        item_id=item_id, success=False, error=str(e), cache_hit=False
                    )
                )
                errors += 1

    return SummaryResponse(
        success=errors == 0,
        summaries_generated=summaries_generated,
        errors=errors,
        results=results,
    )


@router.get("/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int):
    """Get a specific item with all details including AI summary."""
    with session_scope() as s:
        row = s.execute(
            text(
                """
            SELECT id, title, url, published, summary, content_hash, content,
                   ai_summary, ai_model, ai_generated_at,
                   structured_summary_json, structured_summary_model,
                   structured_summary_content_hash, structured_summary_generated_at,
                   ranking_score, topic, topic_confidence, source_weight
            FROM items
            WHERE id = :item_id
        """
            ),
            {"item_id": item_id},
        ).first()

        if not row:
            raise HTTPException(status_code=404, detail="Item not found")

        structured_summary = _parse_structured(row, idx_content_hash=5)
        fallback_summary = None
        is_fallback = False
        has_ai_summary = structured_summary is not None or row[7] is not None
        if not has_ai_summary and row[6]:
            fallback_summary, is_fallback = _fallback_summary(row)

        return ItemOut(
            id=row[0],
            title=row[1],
            url=row[2],
            published=row[3],
            summary=row[4],
            feed_id=None,
            ai_summary=row[7],
            ai_model=row[8],
            ai_generated_at=row[9],
            structured_summary=structured_summary,
            fallback_summary=fallback_summary,
            is_fallback_summary=is_fallback,
            ranking_score=float(row[14]) if row[14] is not None else 0.0,
            topic=row[15],
            topic_confidence=float(row[16]) if row[16] is not None else 0.0,
            source_weight=float(row[17]) if row[17] is not None else 1.0,
        )


@router.get("/items/topic/{topic_key}")
def get_items_by_topic(topic_key: str, limit: int = Query(50, le=200)):
    """Get articles filtered by topic, ordered by ranking score."""
    with session_scope() as s:
        rows = s.execute(
            text(
                """
        SELECT id, title, url, published, summary, content_hash, content,
               ai_summary, ai_model, ai_generated_at,
               structured_summary_json, structured_summary_model,
               structured_summary_content_hash, structured_summary_generated_at,
               ranking_score, topic, topic_confidence, source_weight
        FROM items
        WHERE topic = :topic_key
        ORDER BY COALESCE(published, created_at) DESC, ranking_score DESC
        LIMIT :lim
        """
            ),
            {"topic_key": topic_key, "lim": limit},
        ).all()

        items = []
        for r in rows:
            structured_summary = _parse_structured(r, idx_content_hash=5)
            fallback_summary = None
            is_fallback = False
            has_ai_summary = structured_summary is not None or r[7] is not None
            if not has_ai_summary and r[6]:
                fallback_summary, is_fallback = _fallback_summary(r)
            items.append(
                ItemOut(
                    id=r[0],
                    title=r[1],
                    url=r[2],
                    published=r[3],
                    summary=r[4],
                    feed_id=None,
                    ai_summary=r[7],
                    ai_model=r[8],
                    ai_generated_at=r[9],
                    structured_summary=structured_summary,
                    fallback_summary=fallback_summary,
                    is_fallback_summary=is_fallback,
                    ranking_score=float(r[14]) if r[14] is not None else 0.0,
                    topic=r[15],
                    topic_confidence=float(r[16]) if r[16] is not None else 0.0,
                    source_weight=float(r[17]) if r[17] is not None else 1.0,
                )
            )
        return {
            "topic": topic_key,
            "display_name": get_topic_display_name(topic_key),
            "count": len(items),
            "items": items,
        }
