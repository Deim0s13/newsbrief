"""HTML page routes: stories landing, articles, story/article detail, feeds-manage, search."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import bindparam, text

from ..deps import session_scope, templates
from ..entity_connections import find_entity_connected_stories
from ..entity_profile import get_entity_profile, search_entities
from ..models import StructuredSummary, extract_first_sentences
from ..retrieval import RetrievalService
from ..stories import get_story_by_id

router = APIRouter(prefix="", tags=["pages"])


@router.get("/", response_class=HTMLResponse)
def home_page(request: Request):
    """Main web interface page - Stories landing page."""
    return templates.TemplateResponse(
        request,
        "stories.html",
        {"current_page": "stories"},
    )


@router.get("/articles", response_class=HTMLResponse)
def articles_page(request: Request):
    """Articles listing page (legacy view)."""
    return templates.TemplateResponse(
        request,
        "index.html",
        {"current_page": "articles"},
    )


@router.get("/story/{story_id}", response_class=HTMLResponse)
def story_detail_page(request: Request, story_id: int):
    """Individual story detail page."""
    with session_scope() as s:
        story = get_story_by_id(session=s, story_id=story_id)

        if not story:
            raise HTTPException(status_code=404, detail="Story not found")

        # Related stories panel (#260)
        related_stories = RetrievalService(s).find_related_stories(story_id, top_k=5)

        # Entity-based story connections (#202) -- a different signal from
        # the embedding-based related_stories above: connected because the
        # stories share normalized entities, not semantic similarity.
        entity_connections = find_entity_connected_stories(s, story_id, top_k=5)

        # Best-effort name -> entity id lookup so the "Key Entities" chips
        # below can link to /entities/<id> (#201). story.entities is a flat
        # list of free-form names from the synthesis LLM call -- not the
        # same source as the normalized entity graph -- so this is a
        # case-insensitive match, not a guaranteed one; unmatched names stay
        # plain (non-clickable) text in the template.
        entity_name_to_id: dict = {}
        if story.entities:
            rows = s.execute(
                text(
                    "SELECT id, canonical_name FROM entities "
                    "WHERE lower(canonical_name) IN :names"
                ).bindparams(bindparam("names", expanding=True)),
                {"names": [e.lower() for e in story.entities]},
            ).fetchall()
            entity_name_to_id = {r[1].lower(): r[0] for r in rows}

        # "Continues from..." banner (#261): only set when historical linking
        # (#258) found a match above threshold at generation time.
        continues_from = None
        if story.continues_story_id:
            continues_from = get_story_by_id(
                session=s, story_id=story.continues_story_id
            )

    return templates.TemplateResponse(
        request,
        "story_detail.html",
        {
            "story": story,
            "related_stories": related_stories,
            "entity_connections": entity_connections,
            "entity_name_to_id": entity_name_to_id,
            "continues_from": continues_from,
            "current_page": "stories",
        },
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
        request,
        "article_detail.html",
        {"article": article, "current_page": "articles"},
    )


@router.get("/feeds-manage", response_class=HTMLResponse)
def feeds_management_page(request: Request):
    """Feed management interface page."""
    return templates.TemplateResponse(
        request,
        "feed_management.html",
        {"current_page": "feed-management"},
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
        request,
        "search_results.html",
        {
            "articles": articles,
            "search_query": search_query,
            "result_count": len(articles),
            "current_page": "articles",
        },
    )


@router.get("/entities", response_class=HTMLResponse)
def entities_search_page(
    request: Request,
    q: str = "",
    type: str = "",
):
    """
    Entity search/browse page (#201). With no ``q``, shows the most-mentioned
    entities as a default "browse" listing rather than an empty page.
    """
    with session_scope() as s:
        results = search_entities(s, q, entity_type=type or None)

    return templates.TemplateResponse(
        request,
        "entities_search.html",
        {
            "results": results,
            "search_query": q,
            "selected_type": type,
            "current_page": "entities",
        },
    )


@router.get("/entities/{entity_id}", response_class=HTMLResponse)
def entity_profile_page(request: Request, entity_id: int):
    """Individual entity profile page (#201): header, mention timeline, co-mentioned entities."""
    with session_scope() as s:
        profile = get_entity_profile(s, entity_id)

    if not profile:
        raise HTTPException(status_code=404, detail="Entity not found")

    return templates.TemplateResponse(
        request,
        "entity_profile.html",
        {
            "entity": profile,
            "current_page": "entities",
        },
    )
