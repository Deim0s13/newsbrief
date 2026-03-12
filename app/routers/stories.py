"""Story list, detail, generate, and cache endpoints."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import text

from ..deps import limiter, session_scope
from ..models import (
    ItemOut,
    StoriesListOut,
    StoryGenerationRequest,
    StoryGenerationResponse,
    StoryOut,
    StructuredSummary,
)
from ..stories import generate_stories_simple, get_stories, get_story_by_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["stories"])


@limiter.limit("10/minute")
@router.post("/stories/generate", response_model=StoryGenerationResponse)
def generate_stories_endpoint(
    request: Request, body: StoryGenerationRequest = None  # type: ignore[assignment]
):
    """
    Generate stories from recent articles using hybrid clustering and LLM synthesis.
    """
    try:
        if body is None:
            body = StoryGenerationRequest()  # type: ignore[call-arg]

        with session_scope() as s:
            result = generate_stories_simple(
                session=s,
                time_window_hours=body.time_window_hours,
                min_articles_per_story=body.min_articles_per_story,
                similarity_threshold=body.similarity_threshold,
                model=body.model,
                max_workers=3,
            )

            story_ids = result["story_ids"]
            articles_found = result["articles_found"]
            clusters_created = result["clusters_created"]
            duplicates_skipped = result["duplicates_skipped"]

            message = None
            if len(story_ids) == 0:
                if articles_found == 0:
                    message = f"No articles found in the last {body.time_window_hours} hours. Try fetching feeds or increasing the time window."
                elif duplicates_skipped > 0:
                    message = f"All {duplicates_skipped} story clusters were duplicates of existing stories. Your stories are up to date! Try increasing the time window or fetch new articles."
                elif clusters_created == 0:
                    message = f"Found {articles_found} articles but they didn't cluster into stories. Try adjusting the similarity threshold or minimum articles per story."
                else:
                    message = f"Found {articles_found} articles in {clusters_created} clusters, but story generation failed. Check logs for details."

            return StoryGenerationResponse(
                success=True,
                story_ids=story_ids,
                stories_generated=len(story_ids),
                time_window_hours=body.time_window_hours,
                model=body.model,
                articles_found=articles_found,
                clusters_created=clusters_created,
                duplicates_skipped=duplicates_skipped,
                message=message,
            )
    except Exception as e:
        logger.error(f"Story generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Story generation failed: {str(e)}"
        )


@router.get("/stories", response_model=StoriesListOut)
def list_stories_endpoint(
    limit: int = Query(10, le=50, description="Maximum number of stories to return"),
    offset: int = Query(
        0, ge=0, description="Number of stories to skip for pagination"
    ),
    status: str = Query(
        "active", description="Filter by status: active, archived, or all"
    ),
    order_by: str = Query(
        "importance", description="Sort field: importance, freshness, or generated_at"
    ),
    topic: str = Query(
        None, description="Filter by topic (e.g., 'ai-ml', 'security', 'politics')"
    ),
    apply_interests: bool = Query(
        True,
        description="Apply interest-based ranking (blends importance with topic preferences)",
    ),
):
    """List stories with filtering, sorting, and pagination."""
    try:
        if status not in ["active", "archived", "all"]:
            raise HTTPException(
                status_code=400, detail="status must be 'active', 'archived', or 'all'"
            )
        if order_by not in ["importance", "freshness", "generated_at"]:
            raise HTTPException(
                status_code=400,
                detail="order_by must be 'importance', 'freshness', or 'generated_at'",
            )

        with session_scope() as s:
            status_filter = None if status == "all" else status
            stories = get_stories(
                session=s,
                limit=limit,
                offset=offset,
                status=status_filter,
                order_by=order_by,
                topic=topic,
                apply_interests=apply_interests,
            )

            count_params: dict = {}
            count_parts: list[str] = []
            if status_filter:
                count_parts.append("status = :status_filter")
                count_params["status_filter"] = status_filter
            if topic:
                count_parts.append("topics_json LIKE :topic_pattern")
                count_params["topic_pattern"] = f'%"{topic}"%'
            count_sql = "SELECT COUNT(*) FROM stories"
            if count_parts:
                count_sql += " WHERE " + " AND ".join(count_parts)
            total = s.execute(text(count_sql), count_params).scalar() or 0

            return StoriesListOut(
                stories=stories,
                total=total,
                limit=limit,
                offset=offset,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list stories: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve stories: {str(e)}"
        )


@router.get("/stories/stats")
def get_story_stats():
    """Get story generation statistics and metadata."""
    try:
        with session_scope() as s:
            stats_query = text(
                """
                SELECT
                    COUNT(*) as total_stories,
                    COUNT(CASE WHEN status = 'active' THEN 1 END) as active_stories,
                    COUNT(CASE WHEN status = 'archived' THEN 1 END) as archived_stories,
                    MAX(generated_at) as last_generated_at,
                    AVG(article_count) as avg_articles_per_story,
                    SUM(article_count) as total_articles_in_stories
                FROM stories
            """
            )
            stats_row = s.execute(stats_query).fetchone()

            topic_query = text(
                """
                SELECT topics_json, COUNT(*) as count
                FROM stories
                WHERE status = 'active' AND topics_json IS NOT NULL
                GROUP BY topics_json
                LIMIT 10
            """
            )
            topic_rows = s.execute(topic_query).fetchall()

            topic_counts: dict = {}
            for row in topic_rows:
                try:
                    topics = json.loads(row[0])
                    for topic in topics:
                        topic_counts[topic] = topic_counts.get(topic, 0) + row[1]
                except (json.JSONDecodeError, TypeError):
                    continue

            return {
                "total_stories": stats_row[0] or 0,
                "active_stories": stats_row[1] or 0,
                "archived_stories": stats_row[2] or 0,
                "last_generated_at": stats_row[3],
                "avg_articles_per_story": (
                    round(stats_row[4], 2) if stats_row[4] else 0.0
                ),
                "total_articles_in_stories": stats_row[5] or 0,
                "top_topics": dict(
                    sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                ),
            }
    except Exception as e:
        logger.error(f"Failed to get story stats: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve statistics: {str(e)}"
        )


@router.get("/stories/cache/stats")
def get_synthesis_cache_stats():
    """Get synthesis cache statistics."""
    from ..synthesis_cache import get_cache_stats

    try:
        with session_scope() as s:
            stats = get_cache_stats(s)
            return stats
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve cache statistics: {str(e)}"
        )


@router.post("/stories/cache/clear")
def clear_synthesis_cache(
    expired_only: bool = Query(
        True, description="Only clear expired/invalidated entries"
    )
):
    """Clear the synthesis cache."""
    from ..synthesis_cache import SynthesisCache, cleanup_expired_cache

    try:
        with session_scope() as s:
            if expired_only:
                deleted_count = cleanup_expired_cache(s)
            else:
                deleted_count = s.query(SynthesisCache).delete()
                logger.info(
                    f"Cleared entire synthesis cache: {deleted_count} entries deleted"
                )
            return {
                "cleared": deleted_count,
                "mode": "expired_only" if expired_only else "full_clear",
            }
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.get("/stories/{story_id}", response_model=StoryOut)
def get_story_endpoint(story_id: int):
    """Get a single story with full details and supporting articles."""
    try:
        with session_scope() as s:
            story = get_story_by_id(session=s, story_id=story_id)
            if not story:
                raise HTTPException(
                    status_code=404, detail=f"Story with ID {story_id} not found"
                )
            return story  # type: ignore[return-value]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get story {story_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve story: {str(e)}"
        )


@router.get("/stories/{story_id}/articles", response_model=List[ItemOut])
def get_story_articles(story_id: int):
    """Get all articles associated with a specific story."""
    with session_scope() as s:
        story_exists = s.execute(
            text("SELECT id FROM stories WHERE id = :sid"),
            {"sid": story_id},
        ).first()
        if not story_exists:
            raise HTTPException(
                status_code=404, detail=f"Story with ID {story_id} not found"
            )

        rows = s.execute(
            text(
                """
                SELECT i.id, i.title, i.url, i.published, i.summary, i.content_hash, i.content,
                       i.ai_summary, i.ai_model, i.ai_generated_at,
                       i.structured_summary_json, i.structured_summary_model,
                       i.structured_summary_content_hash, i.structured_summary_generated_at,
                       i.ranking_score, i.topic, i.topic_confidence, i.source_weight
                FROM items i
                JOIN story_articles sa ON i.id = sa.article_id
                WHERE sa.story_id = :story_id
                ORDER BY sa.is_primary DESC, sa.relevance_score DESC, i.published DESC
                """
            ),
            {"story_id": story_id},
        ).all()

        items = []
        for r in rows:
            structured_summary = None
            if r[10] and r[11]:
                try:
                    structured_summary = StructuredSummary.from_json_string(
                        r[10],
                        r[12] or r[5] or "",
                        r[11],
                        (
                            datetime.fromisoformat(r[13])
                            if r[13]
                            else datetime.now(timezone.utc)
                        ),
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to parse structured summary for item {r[0]}: {e}"
                    )
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
                    fallback_summary=None,
                    is_fallback_summary=False,
                    ranking_score=float(r[14]) if r[14] is not None else 0.0,
                    topic=r[15],
                    topic_confidence=float(r[16]) if r[16] is not None else 0.0,
                    source_weight=float(r[17]) if r[17] is not None else 1.0,
                )
            )
        return items
