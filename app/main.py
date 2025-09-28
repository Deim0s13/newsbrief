from __future__ import annotations
from fastapi import FastAPI, Query, HTTPException
from typing import List
from datetime import datetime
from sqlalchemy import text
import logging
from .db import init_db, session_scope
from .models import FeedIn, ItemOut, SummaryRequest, SummaryResponse, SummaryResultOut, LLMStatusOut, StructuredSummary
from .feeds import add_feed, import_opml, fetch_and_store, RefreshStats, MAX_ITEMS_PER_REFRESH, MAX_ITEMS_PER_FEED, MAX_REFRESH_TIME_SECONDS
from .llm import get_llm_service, is_llm_available, OLLAMA_BASE_URL, DEFAULT_MODEL

logger = logging.getLogger(__name__)

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
        SELECT id, title, url, published, summary, content_hash,
               ai_summary, ai_model, ai_generated_at,
               structured_summary_json, structured_summary_model, 
               structured_summary_content_hash, structured_summary_generated_at
        FROM items
        ORDER BY COALESCE(published, created_at) DESC
        LIMIT :lim
        """), {"lim": limit}).all()
        
        items = []
        for r in rows:
            # Parse structured summary if available
            structured_summary = None
            if r[9] and r[10]:  # structured_summary_json and model
                try:
                    structured_summary = StructuredSummary.from_json_string(
                        r[9], 
                        r[11] or r[5] or "",  # structured content_hash, fallback to main content_hash
                        r[10],
                        datetime.fromisoformat(r[12]) if r[12] else datetime.now()
                    )
                except Exception as e:
                    logger.warning(f"Failed to parse structured summary for item {r[0]}: {e}")
            
            items.append(ItemOut(
                id=r[0], 
                title=r[1], 
                url=r[2], 
                published=r[3], 
                summary=r[4],
                ai_summary=r[6],
                ai_model=r[7],
                ai_generated_at=r[8],
                structured_summary=structured_summary
            ))
        
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
                # Get item details including structured summary fields
                row = s.execute(text("""
                    SELECT id, title, content, content_hash, 
                           ai_summary, ai_model, ai_generated_at,
                           structured_summary_json, structured_summary_model, 
                           structured_summary_content_hash, structured_summary_generated_at
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
                
                # Extract fields
                title, content, content_hash = row[1] or "", row[2] or "", row[3]
                structured_json = row[7]  # structured_summary_json
                structured_model = row[8]  # structured_summary_model
                
                # Check for existing structured summary (if not force regenerate)
                if (request.use_structured and structured_json and 
                    not request.force_regenerate and 
                    structured_model == (request.model or DEFAULT_MODEL)):
                    
                    # Return existing structured summary
                    try:
                        structured_summary = StructuredSummary.from_json_string(
                            structured_json, content_hash or "", structured_model, 
                            datetime.fromisoformat(row[10]) if row[10] else datetime.now()
                        )
                        results.append(SummaryResultOut(
                            item_id=item_id,
                            success=True,
                            summary=structured_json,  # Legacy field
                            model=structured_model,
                            structured_summary=structured_summary,
                            content_hash=content_hash,
                            cache_hit=True
                        ))
                        continue
                    except Exception as e:
                        logger.warning(f"Failed to parse existing structured summary for item {item_id}: {e}")
                
                # Check for existing legacy summary (backward compatibility)
                elif (not request.use_structured and row[4] and 
                      not request.force_regenerate):  # ai_summary exists
                    results.append(SummaryResultOut(
                        item_id=item_id,
                        success=True,
                        summary=row[4],
                        model=row[5] or "existing",
                        cache_hit=True
                    ))
                    continue
                
                # Generate new summary
                result = service.summarize_article(
                    title=title,
                    content=content,
                    model=request.model,
                    use_structured=request.use_structured
                )
                
                if result.success:
                    # Store in database - update content_hash if missing
                    if not content_hash and result.content_hash:
                        s.execute(text("""
                            UPDATE items SET content_hash = :content_hash WHERE id = :item_id
                        """), {"content_hash": result.content_hash, "item_id": item_id})
                    
                    if request.use_structured and result.structured_summary:
                        # Store structured summary
                        s.execute(text("""
                            UPDATE items 
                            SET structured_summary_json = :json_data,
                                structured_summary_model = :model,
                                structured_summary_content_hash = :content_hash,
                                structured_summary_generated_at = :generated_at
                            WHERE id = :item_id
                        """), {
                            "json_data": result.structured_summary.to_json_string(),
                            "model": result.model,
                            "content_hash": result.content_hash,
                            "generated_at": result.structured_summary.generated_at.isoformat(),
                            "item_id": item_id
                        })
                    else:
                        # Store legacy summary
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
                    generation_time=result.generation_time,
                    structured_summary=result.structured_summary,
                    content_hash=result.content_hash,
                    cache_hit=result.cache_hit
                ))
                
            except Exception as e:
                logger.error(f"Error processing item {item_id}: {e}")
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
            SELECT id, title, url, published, summary, content_hash,
                   ai_summary, ai_model, ai_generated_at,
                   structured_summary_json, structured_summary_model, 
                   structured_summary_content_hash, structured_summary_generated_at
            FROM items 
            WHERE id = :item_id
        """), {"item_id": item_id}).first()
        
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")
        
        # Parse structured summary if available
        structured_summary = None
        if row[9] and row[10]:  # structured_summary_json and model
            try:
                structured_summary = StructuredSummary.from_json_string(
                    row[9], 
                    row[11] or row[5] or "",  # Use structured content_hash, fallback to main content_hash
                    row[10],
                    datetime.fromisoformat(row[12]) if row[12] else datetime.now()
                )
            except Exception as e:
                logger.warning(f"Failed to parse structured summary for item {item_id}: {e}")
        
        return ItemOut(
            id=row[0],
            title=row[1],
            url=row[2],
            published=row[3],
            summary=row[4],
            ai_summary=row[6],
            ai_model=row[7],
            ai_generated_at=row[8],
            structured_summary=structured_summary
        )