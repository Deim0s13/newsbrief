from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, List, Optional

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from . import scheduler
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
    migrate_sanitize_existing_summaries,
    recalculate_rankings_and_topics,
    update_feed_health_scores,
    update_feed_names,
)
from .llm import DEFAULT_MODEL, OLLAMA_BASE_URL, get_llm_service, is_llm_available
from .logging_config import configure_logging
from .models import (
    FeedIn,
    FeedOut,
    FeedStats,
    FeedUpdate,
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
from .ranking import (
    calculate_ranking_score,
    classify_article_topic,
    get_available_topics,
    get_topic_display_name,
)
from .stories import generate_stories_simple, get_stories, get_story_by_id
from .topics import migrate_article_topics_v062

# Configure structured logging (must be after imports, before app initialization)
configure_logging()

logger = logging.getLogger(__name__)

app = FastAPI(title="NewsBrief")

# Template and static file setup
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Add environment variable to all templates (shows DEV banner in development)
templates.env.globals["environment"] = os.environ.get("ENVIRONMENT", "development")


# Read version from pyproject.toml (single source of truth)
def get_version() -> str:
    """Read version from pyproject.toml."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # Python < 3.11 fallback

    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            return data.get("project", {}).get("version", "dev")
    except Exception:
        return "dev"


APP_VERSION = get_version()
templates.env.globals["app_version"] = APP_VERSION


@app.on_event("startup")
def _startup() -> None:
    init_db()
    # seed from OPML if present (one-time harmless)
    import_opml("data/feeds.opml")
    # Migrate existing summaries to sanitized HTML (idempotent)
    try:
        migrate_sanitize_existing_summaries()
    except Exception as e:
        logger.warning(f"Summary sanitization migration failed: {e}")
    # Migrate article topics to unified system (one-time, v0.6.2)
    try:
        migrate_article_topics_v062()
    except Exception as e:
        logger.warning(f"Topic migration v0.6.2 failed: {e}")
    # Start background scheduler for automated story generation
    try:
        scheduler.start_scheduler()
        logger.info("Background scheduler started successfully")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}", exc_info=True)


@app.on_event("shutdown")
def _shutdown() -> None:
    """Shutdown event - stop background scheduler."""
    try:
        scheduler.stop_scheduler()
        logger.info("Background scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}", exc_info=True)


# Health Check Endpoint
@app.get("/health")
def health_check() -> dict:
    """
    Health check endpoint for container orchestration.

    Returns status of core dependencies:
    - database: SQLite/PostgreSQL connectivity
    - llm: Ollama LLM availability (optional, doesn't fail health check)
    - scheduler: Background job scheduler status

    Returns:
        dict: Health status with component details
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {},
    }

    # Check database connectivity
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
        health_status["components"]["database"] = {"status": "healthy"}
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    # Check LLM availability (non-critical)
    try:
        llm_available = is_llm_available()
        health_status["components"]["llm"] = {
            "status": "healthy" if llm_available else "unavailable",
            "url": OLLAMA_BASE_URL,
        }
    except Exception as e:
        health_status["components"]["llm"] = {
            "status": "unavailable",
            "error": str(e),
        }

    # Check scheduler status
    try:
        scheduler_running = scheduler.is_scheduler_running()
        health_status["components"]["scheduler"] = {
            "status": "healthy" if scheduler_running else "stopped",
        }
    except Exception as e:
        health_status["components"]["scheduler"] = {
            "status": "unknown",
            "error": str(e),
        }

    # Return 503 if unhealthy for container orchestration
    if health_status["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=health_status)

    return health_status


@app.get("/healthz")
def healthz() -> dict:
    """
    Kubernetes-style liveness probe endpoint.

    Returns minimal status for container orchestration.
    Only checks if the application is running.
    """
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> dict:
    """
    Kubernetes-style readiness probe endpoint.

    Checks if the application is ready to accept traffic.
    Verifies database connectivity.
    """
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "database": "disconnected", "error": str(e)},
        )


@app.get("/ollamaz")
def ollamaz() -> dict:
    """
    Ollama LLM service health probe endpoint.

    Returns detailed status of the Ollama LLM service including:
    - Service availability
    - Available models
    - Configuration

    Returns 503 if Ollama is not available.
    """
    try:
        llm_service = get_llm_service()
        available = llm_service.is_available()

        if not available:
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "unavailable",
                    "url": OLLAMA_BASE_URL,
                    "message": "Ollama service is not responding",
                },
            )

        # Get available models
        try:
            models_response = llm_service.client.list()
            if isinstance(models_response, dict) and "models" in models_response:
                models = [
                    {
                        "name": m.get("name", "unknown"),
                        "size": m.get("size", 0),
                        "modified_at": m.get("modified_at", ""),
                    }
                    for m in models_response.get("models", [])
                ]
            else:
                models = []
        except Exception:
            models = []

        return {
            "status": "healthy",
            "url": OLLAMA_BASE_URL,
            "default_model": DEFAULT_MODEL,
            "models_available": len(models),
            "models": models[:10],  # Limit to first 10
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ollama health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "url": OLLAMA_BASE_URL,
                "error": str(e),
            },
        )


# Web Interface Routes
@app.get("/", response_class=HTMLResponse)
def home_page(request: Request):
    """Main web interface page - Stories landing page."""
    return templates.TemplateResponse(
        "stories.html", {"request": request, "current_page": "stories"}
    )


@app.get("/articles", response_class=HTMLResponse)
def articles_page(request: Request):
    """Articles listing page (legacy view)."""
    return templates.TemplateResponse(
        "index.html", {"request": request, "current_page": "articles"}
    )


@app.get("/story/{story_id}", response_class=HTMLResponse)
def story_detail_page(request: Request, story_id: int):
    """Individual story detail page."""
    # Get story details with supporting articles
    with session_scope() as s:
        story = get_story_by_id(session=s, story_id=story_id)

        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

    return templates.TemplateResponse(
        "story_detail.html",
        {"request": request, "story": story, "current_page": "stories"},
    )


@app.get("/article/{item_id}", response_class=HTMLResponse)
def article_detail_page(request: Request, item_id: int):
    """Individual article detail page."""
    # Get article details
    with session_scope() as s:
        result = s.execute(
            text(
                """
                SELECT id, title, url, published, author, summary, content, content_hash,
                       ai_summary, ai_model, ai_generated_at,
                       structured_summary_json, structured_summary_model,
                       structured_summary_content_hash, structured_summary_generated_at,
                       ranking_score, topic, topic_confidence, source_weight,
                       created_at
                FROM items
                WHERE id = :item_id
            """
            ),
            {"item_id": item_id},
        ).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Article not found")

    # Convert to dict for template
    article = dict(result._mapping)

    # Parse structured summary if available
    if article["structured_summary_json"]:
        try:
            import json

            from .models import StructuredSummary

            structured_data = json.loads(article["structured_summary_json"])
            article["structured_summary"] = StructuredSummary(
                bullets=structured_data.get("bullets", []),
                why_it_matters=structured_data.get("why_it_matters", ""),
                tags=structured_data.get("tags", []),
                content_hash=article["structured_summary_content_hash"] or "",
                model=article["structured_summary_model"] or "",
                generated_at=article["structured_summary_generated_at"]
                or article["created_at"],
                is_chunked=structured_data.get("is_chunked", False),
                chunk_count=structured_data.get("chunk_count"),
                total_tokens=structured_data.get("total_tokens"),
                processing_method=structured_data.get("processing_method", "direct"),
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
                article["fallback_summary"] = extract_first_sentences(
                    article["content"]
                )
                article["is_fallback_summary"] = True
            except Exception:
                article["fallback_summary"] = article.get(
                    "summary", "No summary available"
                )
                article["is_fallback_summary"] = True
        else:
            article["fallback_summary"] = article.get("summary", "No summary available")
            article["is_fallback_summary"] = True

    return templates.TemplateResponse(
        "article_detail.html",
        {"request": request, "article": article, "current_page": "articles"},
    )


@app.get("/feeds-manage", response_class=HTMLResponse)
def feeds_management_page(request: Request):
    """Feed management interface page."""
    return templates.TemplateResponse(
        "feed_management.html", {"request": request, "current_page": "feed-management"}
    )


@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = ""):
    """Search results page."""
    articles = []
    search_query = q.strip()

    if search_query:
        # Perform basic search on title and summary
        with session_scope() as s:
            results = s.execute(
                text(
                    """
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
                """
                ),
                {"query": f"%{search_query}%"},
            ).fetchall()

            # Convert to list of dicts for template
            for row in results:
                article_dict = dict(row._mapping)

                # Parse structured summary if available
                if article_dict["structured_summary_json"]:
                    try:
                        import json

                        from .models import StructuredSummary

                        structured_data = json.loads(
                            article_dict["structured_summary_json"]
                        )
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

    return templates.TemplateResponse(
        "search_results.html",
        {
            "request": request,
            "articles": articles,
            "search_query": search_query,
            "result_count": len(articles),
            "current_page": "articles",
        },
    )


@app.get("/feeds", response_model=List[FeedOut])
def list_feeds():
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
                ORDER BY f.priority DESC, f.created_at DESC
            """
            )
        ).fetchall()

        for row in results:
            feed_data = dict(row._mapping)
            # Convert database booleans
            feed_data["disabled"] = bool(feed_data["disabled"])
            feed_data["robots_allowed"] = bool(feed_data["robots_allowed"])
            feeds.append(FeedOut(**feed_data))

    return feeds


# --- Specific feed routes (must come before /feeds/{feed_id}) ---


@app.get("/feeds/categories")
def get_feed_categories():
    """Get all available feed categories with statistics."""
    with session_scope() as s:
        results = s.execute(
            text(
                """
                SELECT category,
                       COUNT(*) as feed_count,
                       SUM(CASE WHEN disabled = 0 THEN 1 ELSE 0 END) as active_count,
                       AVG(health_score) as avg_health,
                       SUM((SELECT COUNT(*) FROM items WHERE feed_id = feeds.id)) as total_articles
                FROM feeds
                WHERE category IS NOT NULL AND category != ''
                GROUP BY category
                ORDER BY feed_count DESC, category
            """
            )
        ).fetchall()

        categories = []
        for row in results:
            categories.append(
                {
                    "name": row[0],
                    "feed_count": row[1],
                    "active_count": row[2],
                    "avg_health": round(row[3] or 100, 1),
                    "total_articles": row[4] or 0,
                }
            )

        # Add predefined categories that might not exist yet
        existing_names = {cat["name"] for cat in categories}
        predefined = [
            "News",
            "Technology",
            "Business",
            "Science",
            "Sports",
            "Entertainment",
            "Health",
            "Politics",
            "Opinion",
            "Personal",
        ]

        for pred_cat in predefined:
            if pred_cat not in existing_names:
                categories.append(
                    {
                        "name": pred_cat,
                        "feed_count": 0,
                        "active_count": 0,
                        "avg_health": 100.0,
                        "total_articles": 0,
                        "is_predefined": True,
                    }
                )

        return {"categories": categories}


@app.get("/feeds/export/opml")
def export_feeds_opml():
    """Export all feeds as OPML file."""
    from fastapi.responses import Response

    opml_content = export_opml()

    return Response(
        content=opml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename=newsbrief_feeds_{datetime.now().strftime('%Y%m%d_%H%M%S')}.opml"
        },
    )


@app.post("/feeds/import/opml")
def import_feeds_opml(file: bytes = None):
    """Import feeds from OPML file upload or raw content."""

    if not file:
        raise HTTPException(status_code=400, detail="No file content provided")

    try:
        # Decode file content
        opml_content = file.decode("utf-8")

        # Process OPML import
        result = import_opml_content(opml_content)

        return {
            "success": True,
            "message": f"Import completed: {result['feeds_added']} added, {result['feeds_updated']} updated, {result['feeds_skipped']} skipped",
            "details": result,
        }

    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid file encoding. Please upload a valid OPML file.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@app.post("/feeds/import/opml/upload")
async def import_feeds_opml_upload(file: UploadFile = File(...)):
    """Import feeds from OPML file upload (multipart form)."""

    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    # Check file type
    if not file.filename.endswith(".opml") and file.content_type not in [
        "application/xml",
        "text/xml",
    ]:
        raise HTTPException(status_code=400, detail="File must be an OPML file (.opml)")

    try:
        # Read file content
        file_content = await file.read()
        opml_content = file_content.decode("utf-8")

        # Process OPML import
        result = import_opml_content(opml_content)

        return {
            "success": True,
            "filename": file.filename,
            "message": f"Import completed: {result['feeds_added']} added, {result['feeds_updated']} updated, {result['feeds_skipped']} skipped",
            "details": result,
        }

    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid file encoding. Please upload a valid UTF-8 encoded OPML file.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@app.post("/feeds/categories/bulk-assign")
def bulk_assign_category(feed_ids: List[int], category: str):
    """Assign a category to multiple feeds at once."""
    if not feed_ids:
        raise HTTPException(status_code=400, detail="No feed IDs provided")

    # Validate category name
    if not category or len(category.strip()) == 0:
        category = None
    else:
        category = category.strip()

    with session_scope() as s:
        # Verify all feed IDs exist
        existing_feeds = s.execute(
            text("SELECT id FROM feeds WHERE id IN :feed_ids"),
            {"feed_ids": tuple(feed_ids)},
        ).fetchall()

        existing_ids = {row[0] for row in existing_feeds}
        invalid_ids = [fid for fid in feed_ids if fid not in existing_ids]

        if invalid_ids:
            raise HTTPException(
                status_code=404, detail=f"Feed IDs not found: {invalid_ids}"
            )

        # Update categories
        s.execute(
            text(
                """
                UPDATE feeds
                SET category = :category, updated_at = CURRENT_TIMESTAMP
                WHERE id IN :feed_ids
            """
            ),
            {"category": category, "feed_ids": tuple(feed_ids)},
        )

        return {
            "success": True,
            "message": f"Updated {len(feed_ids)} feeds",
            "category": category,
            "updated_feed_ids": feed_ids,
        }


@app.post("/feeds/categories/bulk-priority")
def bulk_assign_priority(feed_ids: List[int], priority: int):
    """Assign priority to multiple feeds at once."""
    if not feed_ids:
        raise HTTPException(status_code=400, detail="No feed IDs provided")

    if priority < 1 or priority > 5:
        raise HTTPException(status_code=400, detail="Priority must be between 1 and 5")

    with session_scope() as s:
        # Verify all feed IDs exist
        existing_feeds = s.execute(
            text("SELECT id FROM feeds WHERE id IN :feed_ids"),
            {"feed_ids": tuple(feed_ids)},
        ).fetchall()

        existing_ids = {row[0] for row in existing_feeds}
        invalid_ids = [fid for fid in feed_ids if fid not in existing_ids]

        if invalid_ids:
            raise HTTPException(
                status_code=404, detail=f"Feed IDs not found: {invalid_ids}"
            )

        # Update priorities
        s.execute(
            text(
                """
                UPDATE feeds
                SET priority = :priority, updated_at = CURRENT_TIMESTAMP
                WHERE id IN :feed_ids
            """
            ),
            {"priority": priority, "feed_ids": tuple(feed_ids)},
        )

        return {
            "success": True,
            "message": f"Updated priority for {len(feed_ids)} feeds",
            "priority": priority,
            "updated_feed_ids": feed_ids,
        }


# --- End specific feed routes ---


@app.get("/feeds/{feed_id}", response_model=FeedOut)
def get_feed(feed_id: int):
    """Get detailed information about a specific feed."""
    with session_scope() as s:
        result = s.execute(
            text(
                """
                SELECT f.*,
                       COUNT(i.id) as total_articles,
                       MAX(i.created_at) as last_article_at
                FROM feeds f
                LEFT JOIN items i ON f.id = i.feed_id
                WHERE f.id = :feed_id
                GROUP BY f.id
            """
            ),
            {"feed_id": feed_id},
        ).fetchone()

        if not result:
            raise HTTPException(status_code=404, detail="Feed not found")

        feed_data = dict(result._mapping)
        feed_data["disabled"] = bool(feed_data["disabled"])
        feed_data["robots_allowed"] = bool(feed_data["robots_allowed"])
        return FeedOut(**feed_data)


@app.post("/feeds", response_model=FeedOut)
def add_feed_endpoint(feed: FeedIn):
    """Add a new RSS/Atom feed."""
    # Use the existing add_feed function but with enhanced data
    fid = add_feed(str(feed.url))

    # Update the feed with additional metadata if provided
    if any(
        [feed.name, feed.description, feed.category, feed.priority != 1, feed.disabled]
    ):
        with session_scope() as s:
            s.execute(
                text(
                    """
                    UPDATE feeds
                    SET name = :name, description = :description, category = :category,
                        priority = :priority, disabled = :disabled, updated_at = CURRENT_TIMESTAMP
                    WHERE id = :feed_id
                """
                ),
                {
                    "name": feed.name,
                    "description": feed.description,
                    "category": feed.category,
                    "priority": feed.priority,
                    "disabled": int(feed.disabled),
                    "feed_id": fid,
                },
            )

    # Return the created feed
    return get_feed(fid)


@app.put("/feeds/{feed_id}", response_model=FeedOut)
def update_feed(feed_id: int, feed_update: FeedUpdate):
    """Update an existing feed."""
    with session_scope() as s:
        # Check if feed exists
        existing = s.execute(
            text("SELECT id FROM feeds WHERE id = :feed_id"), {"feed_id": feed_id}
        ).fetchone()

        if not existing:
            raise HTTPException(status_code=404, detail="Feed not found")

        # Build update query dynamically
        update_fields: list[str] = []
        params: dict[str, Any] = {"feed_id": feed_id}

        if feed_update.name is not None:
            update_fields.append("name = :name")
            params["name"] = feed_update.name

        if feed_update.description is not None:
            update_fields.append("description = :description")
            params["description"] = feed_update.description

        if feed_update.category is not None:
            update_fields.append("category = :category")
            params["category"] = feed_update.category

        if feed_update.priority is not None:
            update_fields.append("priority = :priority")
            params["priority"] = feed_update.priority

        if feed_update.disabled is not None:
            update_fields.append("disabled = :disabled")
            params["disabled"] = int(feed_update.disabled)

        if update_fields:
            update_fields.append("updated_at = CURRENT_TIMESTAMP")
            sql = f"UPDATE feeds SET {', '.join(update_fields)} WHERE id = :feed_id"
            s.execute(text(sql), params)

    return get_feed(feed_id)


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


@app.get("/feeds/{feed_id}/stats", response_model=FeedStats)
def get_feed_stats(feed_id: int):
    """Get detailed statistics for a specific feed."""
    with session_scope() as s:
        # Check if feed exists
        feed_check = s.execute(
            text("SELECT id FROM feeds WHERE id = :feed_id"), {"feed_id": feed_id}
        ).fetchone()

        if not feed_check:
            raise HTTPException(status_code=404, detail="Feed not found")

        # Get article counts by time period
        stats_result = s.execute(
            text(
                """
                SELECT
                    COUNT(*) as total_articles,
                    COUNT(CASE WHEN created_at >= datetime('now', '-1 day') THEN 1 END) as articles_last_24h,
                    COUNT(CASE WHEN created_at >= datetime('now', '-7 days') THEN 1 END) as articles_last_7d,
                    COUNT(CASE WHEN created_at >= datetime('now', '-30 days') THEN 1 END) as articles_last_30d,
                    MAX(created_at) as last_fetch_at
                FROM items
                WHERE feed_id = :feed_id
            """
            ),
            {"feed_id": feed_id},
        ).fetchone()

        # Get feed info for error tracking and response times
        feed_info = s.execute(
            text(
                """SELECT last_error, fetch_count, success_count, avg_response_time_ms
                   FROM feeds WHERE id = :feed_id"""
            ),
            {"feed_id": feed_id},
        ).fetchone()

        stats_data = dict(stats_result._mapping)
        feed_data = dict(feed_info._mapping)

        # Calculate derived statistics
        total_articles = stats_data["total_articles"]
        fetch_count = feed_data["fetch_count"] or 0
        success_count = feed_data["success_count"] or 0
        avg_response_time_ms = feed_data["avg_response_time_ms"] or 0.0

        success_rate = (success_count / fetch_count * 100) if fetch_count > 0 else 0.0
        avg_articles_per_day = (
            total_articles / 30.0 if total_articles > 0 else 0.0
        )  # Simple 30-day average

        return FeedStats(
            feed_id=feed_id,
            total_articles=total_articles,
            articles_last_24h=stats_data["articles_last_24h"],
            articles_last_7d=stats_data["articles_last_7d"],
            articles_last_30d=stats_data["articles_last_30d"],
            avg_articles_per_day=round(avg_articles_per_day, 2),
            last_fetch_at=stats_data["last_fetch_at"],
            last_error=feed_data["last_error"],
            success_rate=round(success_rate, 1),
            avg_response_time_ms=round(avg_response_time_ms, 1),
        )


@app.post("/refresh")
def refresh_endpoint():
    # Set in-progress flag to prevent scheduled refresh overlap
    from app.scheduler import set_feed_refresh_in_progress

    set_feed_refresh_in_progress(True)
    try:
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
    finally:
        set_feed_refresh_in_progress(False)


@app.get("/items", response_model=List[ItemOut])
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
        # Validate story_id if provided
        if story_id is not None:
            story_exists = s.execute(
                text("SELECT id FROM stories WHERE id = :sid"),
                {"sid": story_id},
            ).first()
            if not story_exists:
                raise HTTPException(
                    status_code=404, detail=f"Story with ID {story_id} not found"
                )

        # Build dynamic query
        # Note: PostgreSQL with SELECT DISTINCT requires ORDER BY expressions to be in SELECT
        # So we add COALESCE(published, created_at) as sort_date for ordering
        select_clause = """
        SELECT DISTINCT i.id, i.title, i.url, i.published, i.summary, i.content_hash, i.content,
               i.ai_summary, i.ai_model, i.ai_generated_at,
               i.structured_summary_json, i.structured_summary_model,
               i.structured_summary_content_hash, i.structured_summary_generated_at,
               i.ranking_score, i.topic, i.topic_confidence, i.source_weight,
               i.created_at, COALESCE(i.published, i.created_at) AS sort_date
        FROM items i
        """

        joins: list[str] = []
        where_clauses: list[str] = []
        params: dict[str, Any] = {"lim": limit}

        # story_id filter - join with story_articles
        if story_id is not None:
            joins.append("JOIN story_articles sa ON i.id = sa.article_id")
            where_clauses.append("sa.story_id = :story_id")
            params["story_id"] = story_id

        # topic filter
        if topic is not None:
            where_clauses.append("i.topic = :topic")
            params["topic"] = topic

        # feed_id filter
        if feed_id is not None:
            where_clauses.append("i.feed_id = :feed_id")
            params["feed_id"] = feed_id

        # published_after filter
        if published_after is not None:
            where_clauses.append("i.published >= :published_after")
            params["published_after"] = published_after.isoformat()

        # published_before filter
        if published_before is not None:
            where_clauses.append("i.published <= :published_before")
            params["published_before"] = published_before.isoformat()

        # has_story filter
        if has_story is not None:
            if has_story:
                where_clauses.append(
                    "EXISTS (SELECT 1 FROM story_articles sa2 WHERE sa2.article_id = i.id)"
                )
            else:
                where_clauses.append(
                    "NOT EXISTS (SELECT 1 FROM story_articles sa2 WHERE sa2.article_id = i.id)"
                )

        # Build final query
        query = select_clause
        if joins:
            query += " " + " ".join(joins)
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        query += " ORDER BY i.ranking_score DESC, sort_date DESC"
        query += " LIMIT :lim"

        rows = s.execute(text(query), params).all()

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
                    feed_id=None,  # Not included in query, default to None
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
            feed_id=None,  # Not included in query
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


@app.get("/topics", response_class=HTMLResponse)
def topics_page(request: Request):
    """Topics overview page."""
    topics = get_available_topics()

    # Get article counts per topic
    topic_stats = []
    with session_scope() as s:
        for topic in topics:
            count_result = s.execute(
                text("SELECT COUNT(*) as count FROM items WHERE topic = :topic"),
                {"topic": topic["key"]},
            ).fetchone()

            topic_stats.append(
                {
                    "key": topic["key"],
                    "name": topic["name"],
                    "article_count": count_result[0] if count_result else 0,
                }
            )

    return templates.TemplateResponse(
        "topics.html",
        {"request": request, "topics": topic_stats, "current_page": "topics"},
    )


@app.get("/api/topics")
def get_topics_api():
    """Get available article topics (API endpoint)."""
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
                    feed_id=None,  # Not included in query
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
    4. Generates multi-document synthesis via LLM (in parallel)
    5. Stores stories with links to source articles (batched commits)

    Optimizations:
    - Parallel LLM synthesis (3 concurrent workers)
    - Cached article data
    - Batched database commits
    - Duplicate detection

    Returns:
        Story generation results including story IDs and statistics
    """
    try:
        # Use default request if none provided
        if request is None:
            # All fields have defaults via Pydantic Field()
            request = StoryGenerationRequest()  # type: ignore[call-arg]

        with session_scope() as s:
            result = generate_stories_simple(
                session=s,
                time_window_hours=request.time_window_hours,
                min_articles_per_story=request.min_articles_per_story,
                similarity_threshold=request.similarity_threshold,
                model=request.model,
                max_workers=3,  # Parallel LLM calls
            )

            # v0.6.1: Generate helpful message based on results
            story_ids = result["story_ids"]
            articles_found = result["articles_found"]
            clusters_created = result["clusters_created"]
            duplicates_skipped = result["duplicates_skipped"]

            message = None
            if len(story_ids) == 0:
                if articles_found == 0:
                    message = f"No articles found in the last {request.time_window_hours} hours. Try fetching feeds or increasing the time window."
                elif duplicates_skipped > 0:
                    message = f"All {duplicates_skipped} story clusters were duplicates of existing stories. Your stories are up to date! Try increasing the time window or fetch new articles."
                elif clusters_created == 0:
                    message = f"Found {articles_found} articles but they didn't cluster into stories. Try adjusting the similarity threshold or minimum articles per story."
                else:
                    message = f"Found {articles_found} articles in {clusters_created} clusters, but story generation failed. Check logs for details."

            # Success even if 0 stories (might be all duplicates)
            return StoryGenerationResponse(
                success=True,
                story_ids=story_ids,
                stories_generated=len(story_ids),
                time_window_hours=request.time_window_hours,
                model=request.model,
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
    topic: str = Query(
        None, description="Filter by topic (e.g., 'ai-ml', 'security', 'politics')"
    ),
    apply_interests: bool = Query(
        True,
        description="Apply interest-based ranking (blends importance with topic preferences)",
    ),
):
    """
    List stories with filtering, sorting, and pagination.

    Stories are the main aggregated news briefs synthesized from multiple articles.
    By default, returns the top 10 most important active stories, weighted by interest preferences.

    Query Parameters:
        limit: Maximum stories to return (default: 10, max: 50)
        offset: Pagination offset (default: 0)
        status: Filter by status - 'active', 'archived', or 'all' (default: active)
        order_by: Sort field - 'importance', 'freshness', or 'generated_at' (default: importance)
        topic: Filter by topic (optional)
        apply_interests: Apply interest-based ranking (default: true)

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
                topic=topic,
                apply_interests=apply_interests,
            )

            # Get total count for pagination
            conditions = []
            if status_filter:
                conditions.append(f"status = '{status_filter}'")
            if topic:
                conditions.append(f"topics_json LIKE '%\"{topic}\"%'")

            count_query = "SELECT COUNT(*) FROM stories"
            if conditions:
                count_query += " WHERE " + " AND ".join(conditions)

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


@app.get("/stories/cache/stats")
def get_synthesis_cache_stats():
    """
    Get synthesis cache statistics.

    Returns information about the LLM synthesis cache including:
    - Cache configuration (enabled, TTL)
    - Entry counts (total, valid, expired, invalidated)
    - Performance metrics (average generation time, token usage)

    Returns:
        Cache statistics and configuration
    """
    from .synthesis_cache import get_cache_stats

    try:
        with session_scope() as s:
            stats = get_cache_stats(s)
            return stats
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve cache statistics: {str(e)}"
        )


@app.post("/stories/cache/clear")
def clear_synthesis_cache(
    expired_only: bool = Query(
        True, description="Only clear expired/invalidated entries"
    )
):
    """
    Clear the synthesis cache.

    By default, only removes expired and invalidated entries (safe cleanup).
    Set expired_only=false to clear all cache entries (forces regeneration).

    Args:
        expired_only: If True, only clear expired/invalidated entries. If False, clear everything.

    Returns:
        Number of entries cleared
    """
    from .synthesis_cache import SynthesisCache, cleanup_expired_cache

    try:
        with session_scope() as s:
            if expired_only:
                # Safe cleanup - only expired/invalidated
                deleted_count = cleanup_expired_cache(s)
            else:
                # Full clear - delete all entries
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


@app.get("/scheduler/status")
def get_scheduler_status():
    """
    Get background scheduler status.

    Returns information about scheduled background tasks:
    - Feed refresh status (enabled, schedule, next run, in progress)
    - Story generation status (schedule, next run, configuration)

    Returns:
        Scheduler status and configuration for all scheduled jobs
    """
    try:
        status = scheduler.get_scheduler_status()
        return status
    except Exception as e:
        logger.error(f"Failed to get scheduler status: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve scheduler status: {str(e)}"
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


@app.get("/stories/{story_id}/articles", response_model=List[ItemOut])
def get_story_articles(story_id: int):
    """
    Get all articles associated with a specific story.

    Convenience endpoint that returns all articles linked to a story,
    ordered by relevance score (primary articles first).

    Args:
        story_id: The ID of the story

    Returns:
        List of articles in the story

    Raises:
        404: Story not found
    """
    with session_scope() as s:
        # Verify story exists
        story_exists = s.execute(
            text("SELECT id FROM stories WHERE id = :sid"),
            {"sid": story_id},
        ).first()
        if not story_exists:
            raise HTTPException(
                status_code=404, detail=f"Story with ID {story_id} not found"
            )

        # Get articles for this story, ordered by relevance
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

            items.append(
                ItemOut(
                    id=r[0],
                    title=r[1],
                    url=r[2],
                    published=r[3],
                    summary=r[4],
                    feed_id=None,  # Not included in query
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
