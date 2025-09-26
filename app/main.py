from __future__ import annotations
from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional
from .db import init_db, session_scope
from .models import FeedIn, ItemOut
from .feeds import add_feed, import_opml, fetch_and_store

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
    n = fetch_and_store()
    return {"ingested": n}

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