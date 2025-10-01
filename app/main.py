from __future__ import annotations

import logging
from datetime import datetime
from typing import List

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
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
    fetch_and_store,
    import_opml,
)
from .llm import DEFAULT_MODEL, OLLAMA_BASE_URL, get_llm_service, is_llm_available
from .models import (
    FeedIn,
    ItemOut,
    LLMStatusOut,
    StructuredSummary,
    SummaryRequest,
    SummaryResponse,
    SummaryResultOut,
    extract_first_sentences,
)
from .ranking import (
    calculate_ranking_score,
    classify_article_topic,
    get_available_topics,
    get_topic_display_name,
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


# Web Interface Routes
@app.get("/", response_class=HTMLResponse)
def home_page(request: Request):
    """Main web interface page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/article/{item_id}", response_class=HTMLResponse)
def article_detail_page(request: Request, item_id: int):
    """Individual article detail page."""
    # Get article details
    with session_scope() as s:
        result = s.execute(
            text("""
                SELECT id, title, url, published, author, summary, content, content_hash,
                       ai_summary, ai_model, ai_generated_at,
                       structured_summary_json, structured_summary_model, 
                       structured_summary_content_hash, structured_summary_generated_at,
                       ranking_score, topic, topic_confidence, source_weight,
                       created_at
                FROM items 
                WHERE id = :item_id
            """),
            {"item_id": item_id}
        ).fetchone()
    
    if not result:
        raise HTTPException(status_code=404, detail="Article not found")
    
    # Convert to dict for template
    article = dict(result._mapping)
    
    # Parse structured summary if available
    if article["structured_summary_json"]:
        try:
            from .models import StructuredSummary
            import json
            structured_data = json.loads(article["structured_summary_json"])
            article["structured_summary"] = StructuredSummary(
                bullets=structured_data.get("bullets", []),
                why_it_matters=structured_data.get("why_it_matters", ""),
                tags=structured_data.get("tags", []),
                content_hash=article["structured_summary_content_hash"] or "",
                model=article["structured_summary_model"] or "",
                generated_at=article["structured_summary_generated_at"] or article["created_at"],
                is_chunked=structured_data.get("is_chunked", False),
                chunk_count=structured_data.get("chunk_count"),
                total_tokens=structured_data.get("total_tokens"),
                processing_method=structured_data.get("processing_method", "direct")
            )
        except (json.JSONDecodeError, ValueError):
            article["structured_summary"] = None
    else:
        article["structured_summary"] = None
    
    # Handle fallback summary (generate on-the-fly since not stored in DB)
    article["fallback_summary"] = None
    article["is_fallback_summary"] = False
    
    if not article["structured_summary"] and not article["ai_summary"]:
        if article["content"]:
            from .models import extract_first_sentences
            try:
                article["fallback_summary"] = extract_first_sentences(article["content"])
                article["is_fallback_summary"] = True
            except Exception:
                article["fallback_summary"] = article.get("summary", "No summary available")
                article["is_fallback_summary"] = True
        else:
            article["fallback_summary"] = article.get("summary", "No summary available")
            article["is_fallback_summary"] = True
    
    return templates.TemplateResponse("article_detail.html", {
        "request": request, 
        "article": article
    })


@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = ""):
    """Search results page."""
    articles = []
    search_query = q.strip()
    
    if search_query:
        # Perform basic search on title and summary
        with session_scope() as s:
            results = s.execute(
                text("""
                    SELECT id, title, url, published, author, summary, 
                           ai_summary, ai_model, ai_generated_at,
                           structured_summary_json, structured_summary_model,
                           structured_summary_content_hash, structured_summary_generated_at,
                           ranking_score, topic, topic_confidence, source_weight,
                           created_at
                    FROM items 
                    WHERE title LIKE :query OR summary LIKE :query OR ai_summary LIKE :query
                    ORDER BY ranking_score DESC, COALESCE(published, created_at) DESC
                    LIMIT 50
                """),
                {"query": f"%{search_query}%"}
            ).fetchall()
            
            # Convert to list of dicts for template
            for row in results:
                article_dict = dict(row._mapping)
                
                # Parse structured summary if available
                if article_dict["structured_summary_json"]:
                    try:
                        import json
                        from .models import StructuredSummary
                        structured_data = json.loads(article_dict["structured_summary_json"])
                        article_dict["structured_summary"] = {
                            "bullets": structured_data.get("bullets", []),
                            "why_it_matters": structured_data.get("why_it_matters", ""),
                            "tags": structured_data.get("tags", []),
                        }
                    except (json.JSONDecodeError, ValueError):
                        article_dict["structured_summary"] = None
                else:
                    article_dict["structured_summary"] = None
                
                articles.append(article_dict)
    
    return templates.TemplateResponse("search_results.html", {
        "request": request,
        "articles": articles,
        "search_query": search_query,
        "result_count": len(articles)
    })


@app.post("/feeds")
def add_feed_endpoint(feed: FeedIn):
    fid = add_feed(str(feed.url))
    return {"ok": True, "feed_id": fid}


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


@app.get("/items", response_model=List[ItemOut])
def list_items(limit: int = Query(50, le=200)):
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
        ORDER BY ranking_score DESC, COALESCE(published, created_at) DESC
        LIMIT :lim
        """
            ),
            {"lim": limit},
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

        return ItemOut(
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
            # New ranking fields (v0.4.0)
            ranking_score=float(row[14]) if row[14] is not None else 0.0,
            topic=row[15],
            topic_confidence=float(row[16]) if row[16] is not None else 0.0,
            source_weight=float(row[17]) if row[17] is not None else 1.0,
        )


# New ranking and topic endpoints (v0.4.0)


@app.get("/topics")
def get_topics():
    """Get available article topics."""
    return {
        "topics": get_available_topics(),
        "description": "Available topic categories for article classification",
    }


@app.get("/items/topic/{topic_key}")
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
        ORDER BY ranking_score DESC, COALESCE(published, created_at) DESC
        LIMIT :lim
        """
            ),
            {"topic_key": topic_key, "lim": limit},
        ).all()

        items = []
        for r in rows:
            # Parse structured summary if available (same logic as list_items)
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

            # Generate fallback summary if needed (same logic as list_items)
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


@app.post("/ranking/recalculate")
def recalculate_rankings():
    """Recalculate ranking scores and topic classifications for all articles."""
    updated_count = 0

    with session_scope() as s:
        # Get all items that need ranking updates
        rows = s.execute(
            text(
                """
        SELECT id, title, published, summary, content, source_weight, topic
        FROM items 
        ORDER BY id
        """
            )
        ).all()

        for row in rows:
            (
                item_id,
                title,
                published,
                summary,
                content,
                current_source_weight,
                current_topic,
            ) = row

            # Classify topic if not already classified
            topic_result = None
            if not current_topic and title:
                topic_result = classify_article_topic(
                    title=title or "",
                    content=content or summary or "",
                    use_llm_fallback=False,  # Use keywords only for bulk operations
                )

            # Calculate ranking score
            ranking_result = calculate_ranking_score(
                published=published,
                source_weight=current_source_weight or 1.0,
                title=title or "",
                content=content or summary or "",
                topic=topic_result.topic if topic_result else current_topic,
            )

            # Update database
            update_data = {"ranking_score": ranking_result.score, "item_id": item_id}

            if topic_result:
                update_data.update(
                    {
                        "topic": topic_result.topic,
                        "topic_confidence": topic_result.confidence,
                    }
                )

                s.execute(
                    text(
                        """
                UPDATE items 
                SET ranking_score = :ranking_score,
                    topic = :topic,
                    topic_confidence = :topic_confidence
                WHERE id = :item_id
                """
                    ),
                    update_data,
                )
            else:
                s.execute(
                    text(
                        """
                UPDATE items 
                SET ranking_score = :ranking_score
                WHERE id = :item_id
                """
                    ),
                    update_data,
                )

            updated_count += 1

        s.commit()

    return {
        "success": True,
        "updated_items": updated_count,
        "message": f"Recalculated rankings for {updated_count} articles",
    }
