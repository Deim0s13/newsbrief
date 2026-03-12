"""Config and admin-style API routes: topics, model profiles, ranking, scheduler."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from ..deps import session_scope, templates
from ..llm import reload_llm_service
from ..ranking import calculate_ranking_score, classify_article_topic
from ..scheduler import get_scheduler_status
from ..settings import get_settings_service
from ..topics import get_available_topics

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["config"])


# -----------------------------------------------------------------------------
# Topics (HTML + API)
# -----------------------------------------------------------------------------


@router.get("/topics", response_class=HTMLResponse)
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


@router.get("/api/topics")
def get_topics_api():
    """Get available article topics (API endpoint)."""
    return {
        "topics": get_available_topics(),
        "description": "Available topic categories for article classification",
    }


@router.get("/api/topics/stats")
def get_topics_stats_api():
    """
    Get statistics about articles needing topic reclassification.

    Returns counts for:
    - Articles with 'general' topic (unclassified)
    - Articles with low confidence (< 0.5)
    - Last reclassification run info
    - Active job ID if running
    """
    from ..topics import get_reclassification_stats

    return get_reclassification_stats()


@router.post("/api/topics/reclassify")
async def reclassify_topics_api(
    background_tasks: BackgroundTasks,
    batch_size: int = Query(
        100, description="Number of articles to process", ge=10, le=1000
    ),
    use_llm: bool = Query(
        True, description="Use LLM for classification (more accurate)"
    ),
):
    """
    Start async topic reclassification for articles with 'general' topic or low confidence.

    This endpoint starts a background job and returns immediately with a job ID.
    Use GET /api/topics/reclassify/status/{job_id} to poll for progress.
    Use DELETE /api/topics/reclassify/{job_id} to cancel.

    Args:
        batch_size: Number of articles to process (default: 100, max: 1000)
        use_llm: Whether to use LLM classification (default: True)

    Returns:
        Dict with job_id for status polling
    """
    from ..topics import (
        create_reclassify_job,
        get_reclassification_stats,
        run_reclassify_job_async,
    )

    # Check if there's already an active job
    stats = get_reclassification_stats()
    if stats.get("active_job_id"):
        raise HTTPException(
            status_code=409,
            detail=f"Reclassification job {stats['active_job_id']} is already running",
        )

    # Create job record
    job_id = create_reclassify_job(batch_size=batch_size, use_llm=use_llm)

    # Start background task
    background_tasks.add_task(run_reclassify_job_async, job_id)

    return {
        "job_id": job_id,
        "status": "started",
        "message": "Reclassification job started. Poll /api/topics/reclassify/status/{job_id} for progress.",
        "batch_size": batch_size,
        "use_llm": use_llm,
    }


@router.get("/api/topics/reclassify/status/{job_id}")
def get_reclassify_status_api(job_id: int):
    """
    Get the status of a reclassification job.

    Returns progress information including:
    - Current status (pending, running, completed, cancelled, failed)
    - Progress percentage
    - Articles processed/changed/errors
    - Elapsed time
    """
    from ..topics import get_reclassify_job

    job = get_reclassify_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return job


@router.delete("/api/topics/reclassify/{job_id}")
def cancel_reclassify_api(job_id: int):
    """
    Cancel a running reclassification job.

    Only pending or running jobs can be cancelled.
    """
    from ..topics import cancel_reclassify_job, get_reclassify_job

    job = get_reclassify_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job["status"] not in ("pending", "running"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status '{job['status']}'",
        )

    success = cancel_reclassify_job(job_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to cancel job")

    return {
        "job_id": job_id,
        "status": "cancelled",
        "message": "Job cancellation initiated",
    }


# -----------------------------------------------------------------------------
# Model Profile Endpoints (Issue #100)
# -----------------------------------------------------------------------------


@router.get("/api/models/profiles")
def get_model_profiles():
    """
    Get all available model profiles.

    Returns list of profiles with their configuration and expected performance.
    """
    try:
        settings = get_settings_service()
        profiles = settings.get_available_profiles()
        active_profile = settings.get_active_profile()

        return {
            "profiles": [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "model": p.model,
                    "expected_speed": p.expected_speed,
                    "expected_time_per_story": p.expected_time_per_story,
                    "quality_level": p.quality_level,
                    "use_cases": p.use_cases,
                    "is_active": p.id == active_profile,
                }
                for p in profiles
            ],
            "active_profile": active_profile,
        }
    except Exception as e:
        logger.error(f"Failed to get model profiles: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/models/profiles/active")
def get_active_profile():
    """
    Get the currently active model profile.

    Returns the active profile ID and its full configuration.
    """
    try:
        settings = get_settings_service()
        profile_id = settings.get_active_profile()
        profile = settings.get_profile_info(profile_id)
        model = settings.get_active_model()

        if not profile:
            return {
                "profile_id": profile_id,
                "model": model,
                "error": "Profile not found in configuration",
            }

        return {
            "profile_id": profile_id,
            "name": profile.name,
            "description": profile.description,
            "model": model,
            "expected_speed": profile.expected_speed,
            "expected_time_per_story": profile.expected_time_per_story,
            "quality_level": profile.quality_level,
            "use_cases": profile.use_cases,
        }
    except Exception as e:
        logger.error(f"Failed to get active profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/models/profiles/active")
def set_active_profile(
    profile_id: str = Query(..., description="Profile ID to activate")
):
    """
    Set the active model profile.

    Changes the model used for all LLM operations.
    Valid profile IDs: fast, balanced, quality

    Note: The model will be pulled automatically if not already available.
    """
    try:
        settings = get_settings_service()

        # Validate profile exists
        profile = settings.get_profile_info(profile_id)
        if not profile:
            available = [p.id for p in settings.get_available_profiles()]
            raise HTTPException(
                status_code=400,
                detail=f"Invalid profile ID: {profile_id}. Available: {available}",
            )

        # Set the active profile
        success = settings.set_active_profile(profile_id)
        if not success:
            raise HTTPException(
                status_code=500, detail="Failed to save profile setting"
            )

        # Reload LLM service to pick up new model
        reload_llm_service()

        return {
            "status": "success",
            "profile_id": profile_id,
            "name": profile.name,
            "model": profile.model,
            "message": f"Active profile changed to '{profile.name}'. Model: {profile.model}",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set active profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/models")
def get_available_models():
    """
    Get all configured models with their specifications.

    Returns list of models with context window, memory requirements, etc.
    """
    try:
        settings = get_settings_service()
        models = settings.get_available_models()
        active_model = settings.get_active_model()

        return {
            "models": [
                {
                    "name": m.name,
                    "description": m.description,
                    "family": m.family,
                    "parameters": m.parameters,
                    "context_window": m.context_window,
                    "vram_required_gb": m.vram_required_gb,
                    "is_active": m.name == active_model,
                }
                for m in models
            ],
            "active_model": active_model,
        }
    except Exception as e:
        logger.error(f"Failed to get models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------------
# Ranking and scheduler
# -----------------------------------------------------------------------------


def _recalculate_rankings():
    """Recalculate ranking scores and topic classifications for all articles."""
    updated_count = 0

    with session_scope() as s:
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

            topic_result = None
            if not current_topic and title:
                topic_result = classify_article_topic(
                    title=title or "",
                    content=content or summary or "",
                    use_llm_fallback=False,
                )

            ranking_result = calculate_ranking_score(
                published=published,
                source_weight=current_source_weight or 1.0,
                title=title or "",
                content=content or summary or "",
                topic=topic_result.topic if topic_result else current_topic,
            )

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


@router.post("/ranking/recalculate")
def recalculate_rankings_api():
    """Recalculate ranking scores and topic classifications for all articles."""
    return _recalculate_rankings()


@router.get("/scheduler/status")
def scheduler_status_api():
    """Get current scheduler status (jobs, next run times, configuration)."""
    return get_scheduler_status()
