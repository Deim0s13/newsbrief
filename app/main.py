from __future__ import annotations
from fastapi import FastAPI, Query, HTTPException
from typing import List
from datetime import datetime
from sqlalchemy import text
from .db import init_db, session_scope
from .models import FeedIn, ItemOut, SummaryRequest, SummaryResponse, SummaryResultOut, LLMStatusOut
from .feeds import add_feed, import_opml, fetch_and_store, RefreshStats, MAX_ITEMS_PER_REFRESH, MAX_ITEMS_PER_FEED, MAX_REFRESH_TIME_SECONDS
from .llm import get_llm_service, is_llm_available, OLLAMA_BASE_URL, DEFAULT_MODEL

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
        rows = s.execute(text("""
        SELECT id, title, url, published, summary, ai_summary, ai_model, ai_generated_at
        FROM items
        ORDER BY COALESCE(published, created_at) DESC
        LIMIT :lim
        """), {"lim": limit}).all()
        return [ItemOut(
            id=r[0], 
            title=r[1], 
            url=r[2], 
            published=r[3], 
            summary=r[4],
            ai_summary=r[5],
            ai_model=r[6],
            ai_generated_at=r[7]
        ) for r in rows]

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
                if isinstance(model_list, dict) and 'models' in model_list:
                    models = [m.get('name', m.get('model', '')) for m in model_list['models'] if m]
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
            error=error
        )
    except Exception as e:
        return LLMStatusOut(
            available=False,
            base_url=OLLAMA_BASE_URL,
            current_model=DEFAULT_MODEL,
            models_available=[],
            error=str(e)
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
                # Get item details
                row = s.execute(text("""
                    SELECT id, title, content, ai_summary, ai_model
                    FROM items 
                    WHERE id = :item_id
                """), {"item_id": item_id}).first()
                
                if not row:
                    results.append(SummaryResultOut(
                        item_id=item_id,
                        success=False,
                        error="Item not found"
                    ))
                    errors += 1
                    continue
                
                # Check if summary already exists and force_regenerate is False
                if row[3] and not request.force_regenerate:  # ai_summary exists
                    results.append(SummaryResultOut(
                        item_id=item_id,
                        success=True,
                        summary=row[3],
                        model=row[4] or "existing"
                    ))
                    continue
                
                # Generate summary
                result = service.summarize_article(
                    title=row[1] or "",
                    content=row[2] or "",
                    model=request.model
                )
                
                if result.success:
                    # Store in database
                    s.execute(text("""
                        UPDATE items 
                        SET ai_summary = :summary, ai_model = :model, ai_generated_at = :generated_at
                        WHERE id = :item_id
                    """), {
                        "summary": result.summary,
                        "model": result.model,
                        "generated_at": datetime.now().isoformat(),
                        "item_id": item_id
                    })
                    summaries_generated += 1
                else:
                    errors += 1
                
                results.append(SummaryResultOut(
                    item_id=item_id,
                    success=result.success,
                    summary=result.summary if result.success else None,
                    model=result.model,
                    error=result.error,
                    tokens_used=result.tokens_used,
                    generation_time=result.generation_time
                ))
                
            except Exception as e:
                results.append(SummaryResultOut(
                    item_id=item_id,
                    success=False,
                    error=str(e)
                ))
                errors += 1
    
    return SummaryResponse(
        success=errors == 0,
        summaries_generated=summaries_generated,
        errors=errors,
        results=results
    )

@app.get("/items/{item_id}", response_model=ItemOut)
def get_item(item_id: int):
    """Get a specific item with all details including AI summary."""
    with session_scope() as s:
        row = s.execute(text("""
            SELECT id, title, url, published, summary, ai_summary, ai_model, ai_generated_at
            FROM items 
            WHERE id = :item_id
        """), {"item_id": item_id}).first()
        
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")
        
        return ItemOut(
            id=row[0],
            title=row[1],
            url=row[2],
            published=row[3],
            summary=row[4],
            ai_summary=row[5],
            ai_model=row[6],
            ai_generated_at=row[7]
        )