from __future__ import annotations

import logging
from datetime import datetime
from typing import List

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from .db import init_db, session_scope
from .feeds import (
    MAX_ITEMS_PER_FEED,
    MAX_ITEMS_PER_REFRESH,
    MAX_REFRESH_TIME_SECONDS,
    RefreshStats,
    add_feed,
    export_opml,
    fetch_and_store,
    import_opml,
    import_opml_content,
    list_feeds,
    recalculate_rankings_and_topics,
    update_feed_health_scores,
    update_feed_names,
)
from .llm import DEFAULT_MODEL, OLLAMA_BASE_URL, get_llm_service, is_llm_available
from .models import (
    FeedIn,
    ItemOut,
    LLMStatusOut,
    StoriesListOut,
    StoryGenerationRequest,
    StoryGenerationResponse,
    StoryOut,
    StructuredSummary,
    SummaryRequest,
    SummaryResponse,
    SummaryResultOut,
    extract_first_sentences,
)
from .stories import (
    generate_stories_simple,
    get_stories,
    get_story_by_id,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="NewsBrief")

# Template and static file setup
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.on_event("startup")
def _startup() -> None:
    init_db()
    # seed from OPML if present (one-time harmless)
    import_opml("data/feeds.opml")


@app.get("/", response_class=HTMLResponse)
def home_page(request: Request):
    """Main web interface page."""
    return templates.TemplateResponse(
        "index.html", {"request": request, "current_page": "articles"}
    )


@app.get("/monitoring", response_class=HTMLResponse)
def monitoring_page(request: Request):
    """System monitoring dashboard page."""
    return templates.TemplateResponse(
        "monitoring.html", {"request": request, "current_page": "monitoring"}
    )


@app.get("/feeds-manage", response_class=HTMLResponse)
def feeds_management_page(request: Request):
    """Feed management interface page."""
    return templates.TemplateResponse(
        "feed_management.html", {"request": request, "current_page": "feed-management"}
    )


@app.get("/feeds")
def list_feeds_endpoint():
    """List all feeds with their statistics."""
    feeds = []
    with session_scope() as s:
        results = s.execute(
            text(
                """
                SELECT f.*, 
                       COUNT(i.id) as total_articles,
                       MAX(i.created_at) as last_article_at
                FROM feeds f
                LEFT JOIN items i ON f.id = i.feed_id
                GROUP BY f.id
                ORDER BY f.created_at DESC
            """
            )
        ).fetchall()

        for row in results:
            feed_data = dict(row._mapping)
            # Convert database booleans
            feed_data["disabled"] = bool(feed_data["disabled"])
            feed_data["robots_allowed"] = bool(feed_data["robots_allowed"])

            # Convert timestamps to ISO 8601 with UTC indicator for proper browser parsing
            for field in [
                "created_at",
                "updated_at",
                "last_fetch_at",
                "last_success_at",
                "last_article_at",
            ]:
                if field in feed_data and feed_data[field]:
                    # Add 'Z' to indicate UTC timezone
                    ts = str(feed_data[field])
                    if "T" not in ts:
                        ts = ts.replace(" ", "T")
                    if not ts.endswith("Z"):
                        ts = ts + "Z"
                    feed_data[field] = ts

            feeds.append(feed_data)

    return feeds


@app.post("/feeds")
def add_feed_endpoint(feed: FeedIn):
    fid = add_feed(str(feed.url))
    return {"ok": True, "feed_id": fid}


@app.put("/feeds/{feed_id}")
def update_feed(feed_id: int, feed_update: dict):
    """Update an existing feed."""
    with session_scope() as s:
        # Check if feed exists
        existing = s.execute(
            text("SELECT id FROM feeds WHERE id = :feed_id"), {"feed_id": feed_id}
        ).fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Feed not found")

        # Build update query dynamically
        update_fields = []
        params = {"feed_id": feed_id}

        if "url" in feed_update:
            update_fields.append("url = :url")
            params["url"] = feed_update["url"]

        if "disabled" in feed_update:
            update_fields.append("disabled = :disabled")
            params["disabled"] = int(feed_update["disabled"])

        if update_fields:
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            sql = f"UPDATE feeds SET {', '.join(update_fields)} WHERE id = :feed_id"
            s.execute(text(sql), params)

    return {"ok": True, "message": "Feed updated successfully"}


@app.delete("/feeds/{feed_id}")
def delete_feed(feed_id: int):
    """Delete a feed and all its articles."""
    with session_scope() as s:
        # Check if feed exists
        existing = s.execute(
            text("SELECT id FROM feeds WHERE id = :feed_id"), {"feed_id": feed_id}
        ).fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Feed not found")

        # Delete articles first (due to foreign key constraint)
        articles_deleted = s.execute(
            text("DELETE FROM items WHERE feed_id = :feed_id"), {"feed_id": feed_id}
        ).rowcount

        # Delete the feed
        s.execute(text("DELETE FROM feeds WHERE id = :feed_id"), {"feed_id": feed_id})

    return {"ok": True, "articles_deleted": articles_deleted}


@app.post("/feeds/import/opml/upload")
def import_opml_upload(file: UploadFile = File(...)):
    """Import feeds from uploaded OPML file."""
    try:
        content = file.file.read().decode("utf-8")
        result = import_opml_content(content)

        # Build informative message
        message_parts = []
        if result["added"] > 0:
            message_parts.append(f"{result['added']} feed(s) added")
        if result["skipped"] > 0:
            message_parts.append(f"{result['skipped']} already existed")
        if result["errors"] > 0:
            message_parts.append(f"{result['errors']} failed")

        if message_parts:
            message = "Import complete: " + ", ".join(message_parts)
        elif result["error_details"]:
            message = result["error_details"][0]  # Show first error detail
        else:
            message = "No feeds found in OPML file"

        return {"ok": True, "message": message, "stats": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to import OPML: {str(e)}")


@app.get("/feeds/export/opml")
def export_opml_endpoint():
    """Export all feeds as OPML file."""
    try:
        opml_content = export_opml()
        return Response(
            content=opml_content,
            media_type="application/xml",
            headers={
                "Content-Disposition": "attachment; filename=newsbrief_feeds.opml"
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export OPML: {str(e)}")


@app.post("/refresh")
def refresh_endpoint():
    stats = fetch_and_store()
    return {
        # Backward compatibility
        "ingested": stats.total_items,
        # Enhanced statistics
        "stats": {
            "items": {
                "total": stats.total_items,
                "per_feed": stats.items_per_feed,
                "robots_blocked": stats.robots_txt_blocked_articles,
            },
            "feeds": {
                "processed": stats.total_feeds_processed,
                "skipped_disabled": stats.feeds_skipped_disabled,
                "skipped_robots": stats.feeds_skipped_robots,
                "cached_304": stats.feeds_cached_304,
                "errors": stats.feeds_error,
            },
            "performance": {
                "refresh_time_seconds": round(stats.refresh_time_seconds, 2),
                "hit_global_limit": stats.hit_global_limit,
                "hit_time_limit": stats.hit_time_limit,
            },
            "config": {
                "max_items_per_refresh": MAX_ITEMS_PER_REFRESH,
                "max_items_per_feed": MAX_ITEMS_PER_FEED,
                "max_refresh_time_seconds": MAX_REFRESH_TIME_SECONDS,
            },
        },
    }


@app.post("/update-feed-names")
def update_feed_names_endpoint():
    """Update existing feeds with proper names from their RSS feeds."""
    try:
        stats = update_feed_names()
        return {
            "ok": True,
            "message": f"Updated {stats['feeds_updated']} feed names",
            "stats": stats,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update feed names: {str(e)}"
        )


@app.post("/recalculate-rankings")
def recalculate_rankings_endpoint():
    """Recalculate ranking scores and topic classifications for all articles."""
    try:
        stats = recalculate_rankings_and_topics()
        return {
            "ok": True,
            "message": f"Recalculated rankings and topics for {stats['articles_processed']} articles",
            "stats": stats,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to recalculate rankings: {str(e)}"
        )


@app.post("/update-feed-health")
def update_feed_health_endpoint():
    """Update health scores for all feeds based on their metrics."""
    try:
        stats = update_feed_health_scores()
        return {
            "ok": True,
            "message": f"Updated health scores for {stats['feeds_updated']} feeds",
            "stats": stats,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update health scores: {str(e)}"
        )


@app.get("/items", response_model=List[ItemOut])
def list_items(limit: int = Query(50, le=200), offset: int = Query(0, ge=0)):
    with session_scope() as s:
        rows = s.execute(
            text(
                """
        SELECT id, title, url, published, summary, content_hash, content,
               ai_summary, ai_model, ai_generated_at,
               structured_summary_json, structured_summary_model, 
               structured_summary_content_hash, structured_summary_generated_at,
               ranking_score, topic, topic_confidence, source_weight, feed_id
        FROM items
        ORDER BY ranking_score DESC, COALESCE(published, created_at) DESC
        LIMIT :lim OFFSET :off
        """
            ),
            {"lim": limit, "off": offset},
        ).all()

        items = []
        for r in rows:
            # Parse structured summary if available
            structured_summary = None
            if (
                r[10] and r[11]
            ):  # structured_summary_json and model (indices shifted due to content column)
                try:
                    structured_summary = StructuredSummary.from_json_string(
                        r[10],
                        r[12]
                        or r[5]
                        or "",  # structured content_hash, fallback to main content_hash
                        r[11],
                        datetime.fromisoformat(r[13]) if r[13] else datetime.now(),
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to parse structured summary for item {r[0]}: {e}"
                    )

            # Generate fallback summary if no AI summary available
            fallback_summary = None
            is_fallback = False

            # Check if we have any AI-generated summary
            has_ai_summary = (
                structured_summary is not None or r[7] is not None
            )  # ai_summary field

            if not has_ai_summary and r[6]:  # content is available
                # Generate fallback summary from first 2 sentences
                try:
                    fallback_summary = extract_first_sentences(r[6], sentence_count=2)
                    is_fallback = True

                    # If we still don't have a fallback, use title or original summary
                    if not fallback_summary.strip():
                        fallback_summary = r[4] or r[1] or "Content preview unavailable"
                except Exception as e:
                    logger.warning(
                        f"Failed to extract fallback summary for item {r[0]}: {e}"
                    )
                    fallback_summary = r[4] or r[1] or "Content preview unavailable"
                    is_fallback = True

            items.append(
                ItemOut(
                    id=r[0],
                    title=r[1],
                    url=r[2],
                    published=r[3],
                    summary=r[4],
                    feed_id=r[18],  # feed_id field
                    ai_summary=r[7],  # Updated index
                    ai_model=r[8],  # Updated index
                    ai_generated_at=r[9],  # Updated index
                    structured_summary=structured_summary,
                    fallback_summary=fallback_summary,
                    is_fallback_summary=is_fallback,
                    # New ranking fields (v0.4.0)
                    ranking_score=float(r[14]) if r[14] is not None else 0.0,
                    topic=r[15],
                    topic_confidence=float(r[16]) if r[16] is not None else 0.0,
                    source_weight=float(r[17]) if r[17] is not None else 1.0,
                )
            )

        return items


@app.get("/items/count")
def get_items_count():
    """Get total count of items for pagination."""
    with session_scope() as s:
        result = s.execute(text("SELECT COUNT(*) as count FROM items")).fetchone()
        return {"count": result[0]}


@app.get("/llm/status", response_model=LLMStatusOut)
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
            current_model=DEFAULT_MODEL,
            models_available=models,
            error=error,
        )
    except Exception as e:
        return LLMStatusOut(
            available=False,
            base_url=OLLAMA_BASE_URL,
            current_model=DEFAULT_MODEL,
            models_available=[],
            error=str(e),
        )


@app.post("/summarize", response_model=SummaryResponse)
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
                # Get item details including structured summary fields
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

                # Extract fields
                title, content, content_hash = row[1] or "", row[2] or "", row[3]
                structured_json = row[7]  # structured_summary_json
                structured_model = row[8]  # structured_summary_model

                # Check for existing structured summary (if not force regenerate)
                if (
                    request.use_structured
                    and structured_json
                    and not request.force_regenerate
                    and structured_model == (request.model or DEFAULT_MODEL)
                ):

                    # Return existing structured summary
                    try:
                        structured_summary = StructuredSummary.from_json_string(
                            structured_json,
                            content_hash or "",
                            structured_model,
                            (
                                datetime.fromisoformat(row[10])
                                if row[10]
                                else datetime.now()
                            ),
                        )
                        results.append(
                            SummaryResultOut(
                                item_id=item_id,
                                success=True,
                                summary=structured_json,  # Legacy field
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

                # Check for existing legacy summary (backward compatibility)
                elif (
                    not request.use_structured
                    and row[4]
                    and not request.force_regenerate
                ):  # ai_summary exists
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

                # Generate new summary
                result = service.summarize_article(
                    title=title,
                    content=content,
                    model=request.model,
                    use_structured=request.use_structured,
                )

                if result.success:
                    # Store in database - update content_hash if missing
                    if not content_hash and result.content_hash:
                        s.execute(
                            text(
                                """
                            UPDATE items SET content_hash = :content_hash WHERE id = :item_id
                        """
                            ),
                            {"content_hash": result.content_hash, "item_id": item_id},
                        )

                    if request.use_structured and result.structured_summary:
                        # Store structured summary
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
                        # Store legacy summary
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
                                "generated_at": datetime.now().isoformat(),
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


@app.get("/items/topic/{topic_key}")
def get_items_by_topic(topic_key: str, limit: int = Query(50, le=200)):
    """Get articles filtered by topic, ordered by ranking score."""
    with session_scope() as s:
        # Get total count for this topic
        count_result = s.execute(
            text("SELECT COUNT(*) FROM items WHERE topic = :topic_key"),
            {"topic_key": topic_key},
        ).fetchone()
        total_count = count_result[0]

        rows = s.execute(
            text(
                """
        SELECT id, title, url, published, summary, content_hash, content,
               ai_summary, ai_model, ai_generated_at,
               structured_summary_json, structured_summary_model, 
               structured_summary_content_hash, structured_summary_generated_at,
               ranking_score, topic, topic_confidence, source_weight, feed_id
        FROM items
        WHERE topic = :topic_key
        ORDER BY ranking_score DESC, COALESCE(published, created_at) DESC
        LIMIT :lim
        """
            ),
            {"topic_key": topic_key, "lim": limit},
        ).all()

        items = []
        for r in rows:
            # Parse structured summary if available
            structured_summary = None
            if r[10] and r[11]:
                try:
                    structured_summary = StructuredSummary.from_json_string(
                        r[10],
                        r[12] or r[5] or "",
                        r[11],
                        datetime.fromisoformat(r[13]) if r[13] else datetime.now(),
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to parse structured summary for item {r[0]}: {e}"
                    )

            # Generate fallback summary if needed
            fallback_summary = None
            is_fallback = False
            has_ai_summary = structured_summary is not None or r[7] is not None

            if not has_ai_summary and r[6]:
                try:
                    fallback_summary = extract_first_sentences(r[6], sentence_count=2)
                    is_fallback = True
                    if not fallback_summary.strip():
                        fallback_summary = r[4] or r[1] or "Content preview unavailable"
                except Exception as e:
                    logger.warning(
                        f"Failed to extract fallback summary for item {r[0]}: {e}"
                    )
                    fallback_summary = r[4] or r[1] or "Content preview unavailable"
                    is_fallback = True

            items.append(
                ItemOut(
                    id=r[0],
                    title=r[1],
                    url=r[2],
                    published=r[3],
                    summary=r[4],
                    feed_id=r[18],  # feed_id field
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
            "display_name": topic_key.replace("-", "/").title(),
            "count": total_count,
            "items": items,
        }


@app.get("/article/{item_id}", response_class=HTMLResponse)
def get_article_page(request: Request, item_id: int):
    """Get article detail page."""
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
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Article not found")

        # Parse structured summary if available
        structured_summary = None
        if row[10] and row[11]:  # structured_summary_json and model
            try:
                structured_summary = StructuredSummary.from_json_string(
                    row[10],
                    row[12]
                    or row[5]
                    or "",  # structured content_hash, fallback to main content_hash
                    row[11],
                    datetime.fromisoformat(row[13]) if row[13] else datetime.now(),
                )
            except Exception as e:
                logger.warning(
                    f"Failed to parse structured summary for item {item_id}: {e}"
                )

        # Generate fallback summary if no AI summary available
        fallback_summary = None
        is_fallback = False

        # Check if we have any AI-generated summary
        has_ai_summary = structured_summary is not None or row[7] is not None

        if not has_ai_summary and row[6]:  # content is available
            try:
                from .models import extract_first_sentences

                fallback_summary = extract_first_sentences(row[6], sentence_count=2)
                is_fallback = True

                if not fallback_summary.strip():
                    fallback_summary = row[4] or row[1] or "Content preview unavailable"
            except Exception as e:
                logger.warning(
                    f"Failed to extract fallback summary for item {item_id}: {e}"
                )
                fallback_summary = row[4] or row[1] or "Content preview unavailable"
                is_fallback = True

        article = ItemOut(  # type: ignore[call-arg]
            id=row[0],
            title=row[1],
            url=row[2],
            published=row[3],
            summary=row[4],
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

        # Get topic display info
        topic_display_name = "Unclassified"
        topic_badge_classes = (
            "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200"
        )

        if article.topic:
            topic_map = {
                "ai-ml": "AI/ML",
                "cloud-k8s": "Cloud/K8s",
                "security": "Security",
                "devtools": "DevTools",
                "chips-hardware": "Chips/Hardware",
            }
            topic_display_name = topic_map.get(article.topic, article.topic)

            badge_classes = {
                "ai-ml": "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
                "cloud-k8s": "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
                "security": "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
                "devtools": "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
                "chips-hardware": "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
            }
            topic_badge_classes = badge_classes.get(article.topic, topic_badge_classes)

        return templates.TemplateResponse(
            "article_detail.html",
            {
                "request": Request,
                "article": article,
                "topic_display_name": topic_display_name,
                "topic_badge_classes": topic_badge_classes,
            },
        )


@app.get("/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int):
    """Get a specific item with all details including AI summary."""
    with session_scope() as s:
        row = s.execute(
            text(
                """
            SELECT id, title, url, published, summary, content_hash, content,
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
            raise HTTPException(status_code=404, detail="Item not found")

        # Parse structured summary if available
        structured_summary = None
        if (
            row[10] and row[11]
        ):  # structured_summary_json and model (indices shifted due to content column)
            try:
                structured_summary = StructuredSummary.from_json_string(
                    row[10],
                    row[12]
                    or row[5]
                    or "",  # Use structured content_hash, fallback to main content_hash
                    row[11],
                    datetime.fromisoformat(row[13]) if row[13] else datetime.now(),
                )
            except Exception as e:
                logger.warning(
                    f"Failed to parse structured summary for item {item_id}: {e}"
                )

        # Generate fallback summary if no AI summary available
        fallback_summary = None
        is_fallback = False

        # Check if we have any AI-generated summary
        has_ai_summary = (
            structured_summary is not None or row[7] is not None
        )  # ai_summary field

        if not has_ai_summary and row[6]:  # content is available
            # Generate fallback summary from first 2 sentences
            try:
                fallback_summary = extract_first_sentences(row[6], sentence_count=2)
                is_fallback = True

                # If we still don't have a fallback, use title or original summary
                if not fallback_summary.strip():
                    fallback_summary = row[4] or row[1] or "Content preview unavailable"
            except Exception as e:
                logger.warning(
                    f"Failed to extract fallback summary for item {item_id}: {e}"
                )
                fallback_summary = row[4] or row[1] or "Content preview unavailable"
                is_fallback = True

        return ItemOut(  # type: ignore[call-arg]
            id=row[0],
            title=row[1],
            url=row[2],
            published=row[3],
            summary=row[4],
            ai_summary=row[7],  # Updated index
            ai_model=row[8],  # Updated index
            ai_generated_at=row[9],  # Updated index
            structured_summary=structured_summary,
            fallback_summary=fallback_summary,
            is_fallback_summary=is_fallback,
        )


# ============================================================================
# Story Endpoints (v0.5.0)
# ============================================================================


@app.post("/stories/generate", response_model=StoryGenerationResponse)
def generate_stories_endpoint(request: StoryGenerationRequest = None):  # type: ignore[assignment]
    """
    Generate stories from recent articles using hybrid clustering and LLM synthesis.

    This endpoint triggers the story generation pipeline which:
    1. Queries articles from the specified time window
    2. Groups articles by topic (coarse filter)
    3. Clusters by title keyword similarity (Jaccard index)
    4. Generates multi-document synthesis via LLM
    5. Stores stories with links to source articles

    Returns:
        Story generation results including story IDs and statistics
    """
    try:
        # Use default request if none provided
        if request is None:
            request = StoryGenerationRequest()

        with session_scope() as s:
            story_ids = generate_stories_simple(
                session=s,
                time_window_hours=request.time_window_hours,
                min_articles_per_story=request.min_articles_per_story,
                similarity_threshold=request.similarity_threshold,
                model=request.model,
            )

            return StoryGenerationResponse(
                success=True,
                story_ids=story_ids,
                stories_generated=len(story_ids),
                time_window_hours=request.time_window_hours,
                model=request.model,
            )
    except Exception as e:
        logger.error(f"Story generation failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Story generation failed: {str(e)}"
        )


@app.get("/stories", response_model=StoriesListOut)
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
):
    """
    List stories with filtering, sorting, and pagination.

    Stories are the main aggregated news briefs synthesized from multiple articles.
    By default, returns the top 10 most important active stories.

    Query Parameters:
        limit: Maximum stories to return (default: 10, max: 50)
        offset: Pagination offset (default: 0)
        status: Filter by status - 'active', 'archived', or 'all' (default: active)
        order_by: Sort field - 'importance', 'freshness', or 'generated_at' (default: importance)

    Returns:
        List of stories with metadata and supporting article summaries
    """
    try:
        # Validate status parameter
        if status not in ["active", "archived", "all"]:
            raise HTTPException(
                status_code=400, detail="status must be 'active', 'archived', or 'all'"
            )

        # Validate order_by parameter
        if order_by not in ["importance", "freshness", "generated_at"]:
            raise HTTPException(
                status_code=400,
                detail="order_by must be 'importance', 'freshness', or 'generated_at'",
            )

        with session_scope() as s:
            # Convert "all" to None for get_stories function
            status_filter = None if status == "all" else status

            stories = get_stories(
                session=s,
                limit=limit,
                offset=offset,
                status=status_filter,
                order_by=order_by,
            )

            # Get total count for pagination
            count_query = "SELECT COUNT(*) FROM stories"
            if status_filter:
                count_query += f" WHERE status = '{status_filter}'"

            total = s.execute(text(count_query)).scalar() or 0

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


@app.get("/stories/stats")
def get_story_stats():
    """
    Get story generation statistics and metadata.

    Provides an overview of the story system including:
    - Total number of stories (active and archived)
    - Most recent generation timestamp
    - Story count by topic
    - Average articles per story
    - Coverage statistics

    Returns:
        Story system statistics and metadata
    """
    try:
        with session_scope() as s:
            # Get basic counts
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

            # Get topic distribution
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

            # Parse topics (they're stored as JSON arrays)
            import json

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


@app.get("/stories/{story_id}", response_model=StoryOut)
def get_story_endpoint(story_id: int):
    """
    Get a single story with full details and supporting articles.

    Returns the complete story including:
    - Full synthesis narrative
    - All key points
    - "Why it matters" analysis
    - Topics and entities
    - List of supporting articles with summaries
    - Importance and freshness scores

    Args:
        story_id: The ID of the story to retrieve

    Returns:
        Complete story details with all supporting articles

    Raises:
        404: Story not found
    """
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
