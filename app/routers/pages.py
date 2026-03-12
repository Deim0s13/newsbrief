"""HTML page routes: stories landing, articles, story/article detail, feeds-manage, search."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from ..deps import session_scope, templates
from ..models import StructuredSummary, extract_first_sentences
from ..stories import get_story_by_id

router = APIRouter(prefix="", tags=["pages"])


@router.get("/", response_class=HTMLResponse)
def home_page(request: Request):
    """Main web interface page - Stories landing page."""
    return templates.TemplateResponse(
        "stories.html", {"request": request, "current_page": "stories"}
    )


@router.get("/articles", response_class=HTMLResponse)
def articles_page(request: Request):
    """Articles listing page (legacy view)."""
    return templates.TemplateResponse(
        "index.html", {"request": request, "current_page": "articles"}
    )


@router.get("/story/{story_id}", response_class=HTMLResponse)
def story_detail_page(request: Request, story_id: int):
    """Individual story detail page."""
    with session_scope() as s:
        story = get_story_by_id(session=s, story_id=story_id)

        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

    return templates.TemplateResponse(
        "story_detail.html",
        {"request": request, "story": story, "current_page": "stories"},
    )


@router.get("/article/{item_id}", response_class=HTMLResponse)
def article_detail_page(request: Request, item_id: int):
    """Individual article detail page."""
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

    article = dict(result._mapping)

    if article["structured_summary_json"]:
        try:
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

    article["fallback_summary"] = None
    article["is_fallback_summary"] = False

    if not article["structured_summary"] and not article["ai_summary"]:
        if article["content"]:
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


@router.get("/feeds-manage", response_class=HTMLResponse)
def feeds_management_page(request: Request):
    """Feed management interface page."""
    return templates.TemplateResponse(
        "feed_management.html", {"request": request, "current_page": "feed-management"}
    )


@router.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = ""):
    """Search results page."""
    articles = []
    search_query = q.strip()

    if search_query:
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
                    ORDER BY COALESCE(published, created_at) DESC, ranking_score DESC
                    LIMIT 50
                """
                ),
                {"query": f"%{search_query}%"},
            ).fetchall()

            for row in results:
                article_dict = dict(row._mapping)

                if article_dict["structured_summary_json"]:
                    try:
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
