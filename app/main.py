from __future__ import annotations
from fastapi import FastAPI, Query
from typing import List
from .db import init_db, session_scope
from .models import FeedIn, ItemOut
from .feeds import add_feed, import_opml, fetch_and_store, RefreshStats, MAX_ITEMS_PER_REFRESH, MAX_ITEMS_PER_FEED, MAX_REFRESH_TIME_SECONDS

app = FastAPI(title="NewsBrief")

@app.on_event("startup")
def _startup() -> None:
    init_db()
    # seed from OPML if present (one-time harmless)
    import_opml("data/feeds.opml")

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
                "robots_blocked": stats.robots_txt_blocked_articles
            },
            "feeds": {
                "processed": stats.total_feeds_processed,
                "skipped_disabled": stats.feeds_skipped_disabled,
                "skipped_robots": stats.feeds_skipped_robots,
                "cached_304": stats.feeds_cached_304,
                "errors": stats.feeds_error
            },
            "performance": {
                "refresh_time_seconds": round(stats.refresh_time_seconds, 2),
                "hit_global_limit": stats.hit_global_limit,
                "hit_time_limit": stats.hit_time_limit
            },
            "config": {
                "max_items_per_refresh": MAX_ITEMS_PER_REFRESH,
                "max_items_per_feed": MAX_ITEMS_PER_FEED,
                "max_refresh_time_seconds": MAX_REFRESH_TIME_SECONDS
            }
        }
    }

@app.get("/items", response_model=List[ItemOut])
def list_items(limit: int = Query(50, le=200)):
    with session_scope() as s:
        rows = s.execute("""
        SELECT id, title, url, published, summary
        FROM items
        ORDER BY COALESCE(published, created_at) DESC
        LIMIT :lim
        """, {"lim": limit}).all()
        return [ItemOut(id=r[0], title=r[1], url=r[2], published=r[3], summary=r[4]) for r in rows]