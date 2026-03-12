"""Feed CRUD, import/export, and refresh endpoints."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import Response
from sqlalchemy import text

from ..deps import limiter, session_scope
from ..feeds import (
    MAX_ITEMS_PER_FEED,
    MAX_ITEMS_PER_REFRESH,
    MAX_REFRESH_TIME_SECONDS,
    RefreshStats,
    add_feed,
    create_import_record,
    export_opml,
    fail_import,
    fetch_and_store,
    get_failed_imports,
    get_import_history,
    get_import_status,
    get_latest_import_summary,
    import_opml_content,
    update_failed_import_status,
    validate_feed_url,
)
from ..models import FeedIn, FeedOut, FeedStats, FeedUpdate

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="", tags=["feeds"]
)  # no prefix so paths stay /feeds, /refresh


# --- Specific feed routes (must come before /feeds/{feed_id}) ---


@router.get("/feeds", response_model=List[FeedOut])
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
            feed_data["disabled"] = bool(feed_data["disabled"])
            feed_data["robots_allowed"] = bool(feed_data["robots_allowed"])
            feeds.append(FeedOut(**feed_data))

    return feeds


@router.get("/feeds/categories")
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


@router.get("/feeds/export/opml")
def export_feeds_opml():
    """Export all feeds as OPML file."""
    opml_content = export_opml()
    return Response(
        content=opml_content,
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename=newsbrief_feeds_{datetime.now().strftime('%Y%m%d_%H%M%S')}.opml"
        },
    )


@router.post("/feeds/import/opml")
def import_feeds_opml(
    file: bytes = None,
    validate: bool = Query(True, description="Validate feed URLs before importing"),
):
    """Import feeds from OPML file upload or raw content."""
    if not file:
        raise HTTPException(status_code=400, detail="No file content provided")

    try:
        opml_content = file.decode("utf-8")
        result = import_opml_content(opml_content, validate=validate)
        failed_msg = (
            f", {result['feeds_failed']} failed" if result["feeds_failed"] > 0 else ""
        )
        return {
            "success": True,
            "message": f"Import completed: {result['feeds_added']} added, {result['feeds_updated']} updated, {result['feeds_skipped']} skipped{failed_msg}",
            "details": result,
        }
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid file encoding. Please upload a valid OPML file.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


def _process_opml_import_background(
    opml_content: str, validate: bool, filename: str, import_id: int
) -> None:
    """Background task to process OPML import without blocking the main thread."""
    try:
        logger.info(
            f"Background OPML import starting: {filename} (import_id={import_id})"
        )
        result = import_opml_content(
            opml_content, validate=validate, filename=filename, import_id=import_id
        )
        logger.info(
            f"Background OPML import completed: {filename} - "
            f"{result['feeds_added']} added, {result['feeds_updated']} updated, "
            f"{result['feeds_skipped']} skipped, {result['feeds_failed']} failed"
        )
    except Exception as e:
        logger.error(f"Background OPML import failed: {filename} - {str(e)}")
        fail_import(import_id, str(e))


@router.post("/feeds/import/opml/upload")
async def import_feeds_opml_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    validate: bool = Query(
        False, description="Validate feed URLs before importing (slower)"
    ),
    async_import: bool = Query(True, description="Process import asynchronously"),
):
    """Import feeds from OPML file upload (multipart form)."""
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")

    if not file.filename.endswith(".opml") and file.content_type not in [
        "application/xml",
        "text/xml",
    ]:
        raise HTTPException(status_code=400, detail="File must be an OPML file (.opml)")

    try:
        file_content = await file.read()
        opml_content = file_content.decode("utf-8")
        logger.info(
            f"OPML upload received: {file.filename}, size={len(file_content)} bytes"
        )

        if async_import:
            import_id = create_import_record(
                filename=file.filename,
                total_feeds=0,
                validation_enabled=validate,
            )
            background_tasks.add_task(
                _process_opml_import_background,
                opml_content,
                validate,
                file.filename,
                import_id,
            )
            return {
                "success": True,
                "filename": file.filename,
                "message": "Import started in background. Check /feeds/import/history for status.",
                "async": True,
                "import_id": import_id,
                "details": {"status": "processing", "validation_enabled": validate},
            }
        else:
            result = import_opml_content(
                opml_content, validate=validate, filename=file.filename
            )
            failed_msg = (
                f", {result['feeds_failed']} failed"
                if result["feeds_failed"] > 0
                else ""
            )
            return {
                "success": True,
                "filename": file.filename,
                "message": f"Import completed: {result['feeds_added']} added, {result['feeds_updated']} updated, {result['feeds_skipped']} skipped{failed_msg}",
                "async": False,
                "details": result,
            }
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid file encoding. Please upload a valid UTF-8 encoded OPML file.",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.get("/feeds/import/history")
def get_import_history_endpoint(
    days: int = Query(30, description="Number of days of history to retrieve")
):
    """Get import history for the last N days."""
    return get_import_history(days=days)


@router.get("/feeds/import/status/{import_id}")
def get_import_status_endpoint(import_id: int):
    """Get the current status of an import by ID."""
    result = get_import_status(import_id)
    if not result:
        raise HTTPException(status_code=404, detail="Import not found")
    return result


@router.get("/feeds/import/failed")
def get_failed_imports_endpoint(
    status: Optional[str] = Query(
        "pending",
        description="Filter by status: pending, resolved, dismissed, or None for all",
    )
):
    """Get failed feed imports."""
    return get_failed_imports(status=status if status != "all" else None)


@router.get("/feeds/import/latest")
def get_latest_import_endpoint():
    """Get summary of the most recent import."""
    result = get_latest_import_summary()
    if not result:
        return {"has_import": False}
    return {"has_import": True, **result}


@router.post("/feeds/import/failed/{failed_id}/dismiss")
def dismiss_failed_import(failed_id: int):
    """Dismiss a failed import."""
    success = update_failed_import_status(failed_id, "dismissed")
    if not success:
        raise HTTPException(status_code=404, detail="Failed import not found")
    return {"success": True, "status": "dismissed"}


@router.post("/feeds/import/failed/{failed_id}/retry")
def retry_failed_import(
    failed_id: int,
    validate: bool = Query(True, description="Validate the feed URL before adding"),
):
    """Retry adding a failed feed."""
    failed_imports = get_failed_imports(status=None)
    failed_import = next((f for f in failed_imports if f["id"] == failed_id), None)
    if not failed_import:
        raise HTTPException(status_code=404, detail="Failed import not found")

    feed_url = failed_import["feed_url"]
    feed_name = failed_import["feed_name"]

    if validate:
        validation = validate_feed_url(feed_url)
        if not validation.is_valid:
            return {
                "success": False,
                "error": validation.error,
                "message": f"Feed still invalid: {validation.error}",
            }

    try:
        feed_id = add_feed(feed_url)
        if feed_name:
            with session_scope() as s:
                s.execute(
                    text("UPDATE feeds SET name = :name WHERE id = :id"),
                    {"name": feed_name, "id": feed_id},
                )
        update_failed_import_status(failed_id, "resolved")
        return {
            "success": True,
            "feed_id": feed_id,
            "message": "Feed added successfully",
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": f"Failed to add feed: {str(e)}",
        }


@router.post("/feeds/categories/bulk-assign")
def bulk_assign_category(feed_ids: List[int], category: str):
    """Assign a category to multiple feeds at once."""
    if not feed_ids:
        raise HTTPException(status_code=400, detail="No feed IDs provided")
    category = category.strip() if category and category.strip() else None

    with session_scope() as s:
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


@router.post("/feeds/categories/bulk-priority")
def bulk_assign_priority(feed_ids: List[int], priority: int):
    """Assign priority to multiple feeds at once."""
    if not feed_ids:
        raise HTTPException(status_code=400, detail="No feed IDs provided")
    if priority < 1 or priority > 5:
        raise HTTPException(status_code=400, detail="Priority must be between 1 and 5")

    with session_scope() as s:
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


# --- Feed by ID (after more specific routes) ---


@router.get("/feeds/{feed_id}", response_model=FeedOut)
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


@router.post("/feeds", response_model=FeedOut)
def add_feed_endpoint(
    feed: FeedIn,
    validate: bool = Query(True, description="Validate feed URL before adding"),
):
    """Add a new RSS/Atom feed."""
    if validate:
        validation = validate_feed_url(str(feed.url))
        if not validation.is_valid:
            raise HTTPException(
                status_code=400, detail=f"Feed validation failed: {validation.error}"
            )
        if not feed.name and validation.feed_title:
            feed.name = validation.feed_title

    fid = add_feed(str(feed.url))
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
    return get_feed(fid)


@router.put("/feeds/{feed_id}", response_model=FeedOut)
def update_feed(feed_id: int, feed_update: FeedUpdate):
    """Update an existing feed."""
    with session_scope() as s:
        existing = s.execute(
            text("SELECT id FROM feeds WHERE id = :feed_id"), {"feed_id": feed_id}
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Feed not found")

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


@router.delete("/feeds/{feed_id}")
def delete_feed(feed_id: int):
    """Delete a feed and all its articles."""
    with session_scope() as s:
        existing = s.execute(
            text("SELECT id FROM feeds WHERE id = :feed_id"), {"feed_id": feed_id}
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Feed not found")
        articles_deleted = s.execute(
            text("DELETE FROM items WHERE feed_id = :feed_id"), {"feed_id": feed_id}
        ).rowcount
        s.execute(text("DELETE FROM feeds WHERE id = :feed_id"), {"feed_id": feed_id})
    return {"ok": True, "articles_deleted": articles_deleted}


@router.get("/feeds/{feed_id}/stats", response_model=FeedStats)
def get_feed_stats(feed_id: int):
    """Get detailed statistics for a specific feed."""
    with session_scope() as s:
        feed_check = s.execute(
            text("SELECT id FROM feeds WHERE id = :feed_id"), {"feed_id": feed_id}
        ).fetchone()
        if not feed_check:
            raise HTTPException(status_code=404, detail="Feed not found")

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

        feed_info = s.execute(
            text(
                """SELECT last_error, fetch_count, success_count, avg_response_time_ms
                   FROM feeds WHERE id = :feed_id"""
            ),
            {"feed_id": feed_id},
        ).fetchone()

        stats_data = dict(stats_result._mapping)
        feed_data = dict(feed_info._mapping)
        total_articles = stats_data["total_articles"]
        fetch_count = feed_data["fetch_count"] or 0
        success_count = feed_data["success_count"] or 0
        avg_response_time_ms = feed_data["avg_response_time_ms"] or 0.0
        success_rate = (success_count / fetch_count * 100) if fetch_count > 0 else 0.0
        avg_articles_per_day = total_articles / 30.0 if total_articles > 0 else 0.0

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


@limiter.limit("10/minute")
@router.post("/refresh")
def refresh_endpoint(request: Request):
    """Trigger feed refresh. Rate limited."""
    from ..scheduler import set_feed_refresh_in_progress

    set_feed_refresh_in_progress(True)
    try:
        stats: RefreshStats = fetch_and_store()
        return {
            "ingested": stats.total_items,
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
