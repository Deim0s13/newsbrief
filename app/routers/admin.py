"""Admin dashboard pages and APIs: credibility, quality, extraction, LLM stats."""

from __future__ import annotations

import logging
import os
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from ..credibility import canonicalize_domain
from ..credibility_import import import_mbfc_sources
from ..deps import session_scope, templates
from ..operator_audit import list_recent_operator_actions, record_operator_action
from ..orm_models import SourceCredibility
from ..settings import get_settings_service
from ..topics import get_available_topics, get_reclassification_stats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["admin"])


class PipelineRunBody(BaseModel):
    """Request body for manual pipeline execution (#274)."""

    from_stage: str = Field(
        default="full",
        description="full (ingest then stories), ingest, or story_generation",
    )


class PipelineReplayBody(BaseModel):
    """Targeted pipeline replay (#274 phase 2)."""

    target_type: Literal["item", "story"]
    target_id: int = Field(..., ge=1)
    from_stage: Literal["enrich", "story_generation"]
    model: Optional[str] = Field(
        default=None,
        description="LLM model (defaults to active profile from settings)",
    )


# -----------------------------------------------------------------------------
# Pipeline runner (ADR-0029 / #274)
# -----------------------------------------------------------------------------


@router.post("/api/admin/pipeline/run")
def admin_pipeline_run(request: Request, body: Optional[PipelineRunBody] = None):
    """Run pipeline stages manually (operator action)."""
    from .. import scheduler as scheduler_mod
    from ..pipeline_runner import run_pipeline

    payload = body or PipelineRunBody()
    fs = (payload.from_stage or "full").strip().lower()
    if fs == "full":
        mapped = None
    elif fs in ("ingest", "story_generation"):
        mapped = fs
    else:
        raise HTTPException(
            status_code=400,
            detail="from_stage must be one of: full, ingest, story_generation",
        )
    try:
        result = run_pipeline(
            trigger="manual",
            from_stage=mapped,
            time_window_hours=scheduler_mod.STORY_TIME_WINDOW_HOURS,
            min_articles_per_story=scheduler_mod.STORY_MIN_ARTICLES,
            model=get_settings_service().get_active_model(),
            max_workers=3,
        )
        record_operator_action(
            request=request,
            action_type="pipeline_run",
            details={
                "from_stage": fs,
                "success": result.get("success"),
                "run_group_id": result.get("run_group_id"),
            },
        )
        return result
    except ValueError as e:
        record_operator_action(
            request=request,
            action_type="pipeline_run",
            details={"from_stage": fs, "success": False, "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        record_operator_action(
            request=request,
            action_type="pipeline_run",
            details={"from_stage": fs, "success": False, "error": str(e)},
        )
        logger.error("Manual pipeline run failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/admin/pipeline/replay")
def admin_pipeline_replay(request: Request, body: PipelineReplayBody):
    """Re-run one stage for a single item (enrich) or story (regenerate synthesis)."""
    from .. import scheduler as scheduler_mod
    from ..pipeline_runner import run_targeted_replay

    model = body.model or get_settings_service().get_active_model()
    try:
        result = run_targeted_replay(
            trigger="manual",
            target_type=body.target_type,
            target_id=body.target_id,
            from_stage=body.from_stage,
            model=model,
        )
        record_operator_action(
            request=request,
            action_type="pipeline_replay",
            details={
                "target_type": body.target_type,
                "target_id": body.target_id,
                "from_stage": body.from_stage,
                "model": model,
                "success": result.get("success"),
                "run_group_id": result.get("run_group_id"),
            },
        )
        return result
    except ValueError as e:
        record_operator_action(
            request=request,
            action_type="pipeline_replay",
            details={
                "target_type": body.target_type,
                "target_id": body.target_id,
                "from_stage": body.from_stage,
                "success": False,
                "error": str(e),
            },
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        record_operator_action(
            request=request,
            action_type="pipeline_replay",
            details={
                "target_type": body.target_type,
                "target_id": body.target_id,
                "from_stage": body.from_stage,
                "success": False,
                "error": str(e),
            },
        )
        logger.error("Pipeline replay failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/admin/pipeline/audit")
def admin_pipeline_audit(
    limit: int = Query(50, ge=1, le=200, description="Max audit rows"),
):
    """Recent operator actions (pipeline admin API, #277)."""
    return {"actions": list_recent_operator_actions(limit=limit)}


@router.get("/api/admin/pipeline/stages")
def admin_pipeline_stages():
    """Article/story counts by ``processing_state`` (#276)."""
    from ..pipeline_monitoring import get_processing_stage_snapshot

    return get_processing_stage_snapshot()


@router.get("/api/admin/pipeline/run-metrics")
def admin_pipeline_run_metrics(
    window_hours: float = Query(
        24.0,
        ge=0.25,
        le=720.0,
        description="Rolling window for runs whose started_at is within this many hours",
    ),
):
    """Aggregates from ``pipeline_stage_runs`` by stage (#276)."""
    from ..pipeline_monitoring import get_pipeline_run_metrics

    return get_pipeline_run_metrics(window_hours=window_hours)


@router.get("/api/admin/pipeline/stuck")
def admin_pipeline_stuck(
    max_age_seconds: Optional[int] = Query(
        None,
        ge=60,
        le=86400 * 14,
        description="Override PIPELINE_STUCK_AFTER_SECONDS (default 3600); min 60",
    ),
    limit: int = Query(50, ge=1, le=200, description="Max stuck rows to return"),
):
    """In-flight stage runs older than the stuck threshold (#276)."""
    from ..pipeline_monitoring import list_stuck_pipeline_runs

    return list_stuck_pipeline_runs(max_age_seconds=max_age_seconds, limit=limit)


@router.get("/api/admin/pipeline/failed-entities")
def admin_pipeline_failed_entities(
    limit_items: int = Query(50, ge=1, le=200),
    limit_stories: int = Query(50, ge=1, le=200),
):
    """Items and stories with ``processing_state = failed`` (#293)."""
    from ..failed_entities import list_failed_entities

    return list_failed_entities(limit_items=limit_items, limit_stories=limit_stories)


@router.post("/api/admin/pipeline/failed-items/{item_id}/discard")
def admin_discard_failed_item(request: Request, item_id: int):
    from ..failed_entities import discard_failed_item

    try:
        result = discard_failed_item(item_id)
        record_operator_action(
            request=request,
            action_type="pipeline_failed_item_discard",
            details=result,
        )
        return result
    except ValueError as e:
        record_operator_action(
            request=request,
            action_type="pipeline_failed_item_discard",
            details={"item_id": item_id, "success": False, "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/admin/pipeline/failed-stories/{story_id}/discard")
def admin_discard_failed_story(request: Request, story_id: int):
    from ..failed_entities import discard_failed_story

    try:
        result = discard_failed_story(story_id)
        record_operator_action(
            request=request,
            action_type="pipeline_failed_story_discard",
            details=result,
        )
        return result
    except ValueError as e:
        record_operator_action(
            request=request,
            action_type="pipeline_failed_story_discard",
            details={"story_id": story_id, "success": False, "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/admin/pipeline/failed-items/{item_id}/retry")
def admin_retry_failed_item(
    request: Request,
    item_id: int,
    model: Optional[str] = Query(
        None,
        description="LLM model (defaults to active profile from settings)",
    ),
):
    from .. import scheduler as scheduler_mod
    from ..failed_entities import retry_failed_item

    m = model or get_settings_service().get_active_model()
    try:
        result = retry_failed_item(item_id, model=m)
        record_operator_action(
            request=request,
            action_type="pipeline_failed_item_retry",
            details=result,
        )
        return result
    except ValueError as e:
        record_operator_action(
            request=request,
            action_type="pipeline_failed_item_retry",
            details={"item_id": item_id, "success": False, "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        record_operator_action(
            request=request,
            action_type="pipeline_failed_item_retry",
            details={"item_id": item_id, "success": False, "error": str(e)},
        )
        logger.error("Failed item retry failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/admin/pipeline/failed-stories/{story_id}/retry")
def admin_retry_failed_story(
    request: Request,
    story_id: int,
    model: Optional[str] = Query(
        None,
        description="LLM model (defaults to active profile from settings)",
    ),
):
    from .. import scheduler as scheduler_mod
    from ..failed_entities import retry_failed_story

    m = model or get_settings_service().get_active_model()
    try:
        result = retry_failed_story(story_id, model=m)
        record_operator_action(
            request=request,
            action_type="pipeline_failed_story_retry",
            details=result,
        )
        return result
    except ValueError as e:
        record_operator_action(
            request=request,
            action_type="pipeline_failed_story_retry",
            details={"story_id": story_id, "success": False, "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        record_operator_action(
            request=request,
            action_type="pipeline_failed_story_retry",
            details={"story_id": story_id, "success": False, "error": str(e)},
        )
        logger.error("Failed story retry failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/admin/pipeline/runs")
def admin_pipeline_runs(
    limit: int = Query(50, ge=1, le=200, description="Max rows to return"),
    outcome: str = Query(
        "all",
        description="Filter: all | failed | dead_letter (failed, not discarded) | succeeded",
    ),
):
    """Recent pipeline stage executions (metadata; #275 dead-letter filters)."""
    from ..pipeline_runner import list_recent_stage_runs

    try:
        return {"runs": list_recent_stage_runs(limit=limit, outcome=outcome)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/admin/pipeline/runs/{run_id}/discard")
def admin_pipeline_discard_run(request: Request, run_id: int):
    """Dismiss a failed run from the dead-letter queue (#275)."""
    from ..pipeline_runner import discard_pipeline_stage_run

    try:
        result = discard_pipeline_stage_run(run_id)
        record_operator_action(
            request=request,
            action_type="pipeline_discard_run",
            details={"run_id": run_id, **result},
        )
        return result
    except ValueError as e:
        record_operator_action(
            request=request,
            action_type="pipeline_discard_run",
            details={"run_id": run_id, "success": False, "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        record_operator_action(
            request=request,
            action_type="pipeline_discard_run",
            details={"run_id": run_id, "success": False, "error": str(e)},
        )
        logger.error("Pipeline discard failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/admin/pipeline/runs/{run_id}/retry")
def admin_pipeline_retry_run(request: Request, run_id: int):
    """Re-run the same stage as a new pipeline run (#275)."""
    from ..pipeline_runner import retry_pipeline_stage_run

    try:
        result = retry_pipeline_stage_run(run_id)
        record_operator_action(
            request=request,
            action_type="pipeline_retry_run",
            details={
                "original_run_id": run_id,
                "success": result.get("success"),
                "new_run_group_id": result.get("new_run_group_id"),
            },
        )
        return result
    except ValueError as e:
        record_operator_action(
            request=request,
            action_type="pipeline_retry_run",
            details={"original_run_id": run_id, "success": False, "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        record_operator_action(
            request=request,
            action_type="pipeline_retry_run",
            details={"original_run_id": run_id, "success": False, "error": str(e)},
        )
        logger.error("Pipeline retry failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


# -----------------------------------------------------------------------------
# Source Credibility API
# -----------------------------------------------------------------------------


@router.post("/api/credibility/refresh")
def refresh_credibility_data():
    """Trigger a refresh of source credibility data from MBFC."""
    try:
        stats = import_mbfc_sources()
        return {
            "success": True,
            "message": "Credibility data refreshed",
            **stats.to_dict(),
        }
    except Exception as e:
        logger.error(f"Credibility refresh failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Refresh failed: {e}")


@router.get("/api/credibility/stats")
def get_credibility_stats():
    """Get statistics about source credibility data."""
    with session_scope() as db:
        total = db.query(SourceCredibility).count()
        by_type = {}
        type_counts = (
            db.query(SourceCredibility.source_type, text("COUNT(*)"))
            .group_by(SourceCredibility.source_type)
            .all()
        )
        for source_type, count in type_counts:
            by_type[source_type or "unknown"] = count
        by_factual = {}
        factual_counts = (
            db.query(SourceCredibility.factual_reporting, text("COUNT(*)"))
            .group_by(SourceCredibility.factual_reporting)
            .all()
        )
        for factual, count in factual_counts:
            by_factual[factual or "unknown"] = count
        eligible = (
            db.query(SourceCredibility)
            .filter(SourceCredibility.is_eligible_for_synthesis == True)
            .count()
        )
        return {
            "total_sources": total,
            "by_source_type": by_type,
            "by_factual_reporting": by_factual,
            "eligible_for_synthesis": eligible,
            "ineligible_for_synthesis": total - eligible,
        }


@router.get("/api/credibility/lookup")
def lookup_credibility(
    domains: str = Query(..., description="Comma-separated domains"),
):
    """Look up credibility data for one or more domains."""
    domain_list = [d.strip() for d in domains.split(",") if d.strip()]
    if not domain_list:
        return {}
    canonical_map = {}
    for d in domain_list:
        canonical = canonicalize_domain(d)
        if canonical:
            canonical_map[canonical] = d
    if not canonical_map:
        return {}
    with session_scope() as db:
        results = (
            db.query(SourceCredibility)
            .filter(SourceCredibility.domain.in_(canonical_map.keys()))
            .all()
        )
        response = {}
        for record in results:
            response[record.domain] = {
                "domain": record.domain,
                "name": record.name,
                "source_type": record.source_type,
                "factual_reporting": record.factual_reporting,
                "bias": record.bias,
                "credibility_score": record.credibility_score,
                "is_eligible_for_synthesis": record.is_eligible_for_synthesis,
                "provider_url": record.provider_url,
            }
        return response


# -----------------------------------------------------------------------------
# Admin dashboard pages (HTML)
# -----------------------------------------------------------------------------


@router.get("/admin/credibility", response_class=HTMLResponse)
def credibility_dashboard_page(request: Request):
    """Source credibility data dashboard."""
    return templates.TemplateResponse(
        request,
        "credibility_dashboard.html",
        {
            "current_page": "admin",
            "environment": os.environ.get("ENVIRONMENT", "development"),
        },
    )


@router.get("/admin/extraction", response_class=HTMLResponse)
def extraction_dashboard_page(request: Request):
    """Extraction quality monitoring dashboard."""
    return templates.TemplateResponse(
        request,
        "extraction_dashboard.html",
        {
            "current_page": "admin",
            "environment": os.environ.get("ENVIRONMENT", "development"),
        },
    )


@router.get("/admin/quality", response_class=HTMLResponse)
def quality_dashboard_page(request: Request):
    """LLM output quality monitoring dashboard."""
    return templates.TemplateResponse(
        request,
        "quality_dashboard.html",
        {
            "current_page": "admin",
            "environment": os.environ.get("ENVIRONMENT", "development"),
        },
    )


@router.get("/admin/topics", response_class=HTMLResponse)
def topics_management_page(request: Request):
    """Topic management dashboard for article reclassification."""
    stats = get_reclassification_stats()
    topics = get_available_topics()
    return templates.TemplateResponse(
        request,
        "topics_management.html",
        {
            "current_page": "admin",
            "environment": os.environ.get("ENVIRONMENT", "development"),
            "stats": stats,
            "topics": topics,
        },
    )


@router.get("/admin/models", response_class=HTMLResponse)
def models_management_page(request: Request):
    """Model configuration dashboard for LLM profile management."""
    settings = get_settings_service()
    profiles = settings.get_available_profiles()
    active_profile_id = settings.get_active_profile()
    active_profile = settings.get_profile_info(active_profile_id)
    models = settings.get_available_models()
    return templates.TemplateResponse(
        request,
        "models_management.html",
        {
            "current_page": "admin",
            "environment": os.environ.get("ENVIRONMENT", "development"),
            "profiles": profiles,
            "active_profile": active_profile,
            "models": models,
        },
    )


@router.get("/admin/pipeline", response_class=HTMLResponse)
def pipeline_operator_page(request: Request):
    """Pipeline operator: runs, replay, dead-letter, audit (#277)."""
    return templates.TemplateResponse(
        request,
        "pipeline_operator.html",
        {
            "current_page": "admin",
            "environment": os.environ.get("ENVIRONMENT", "development"),
        },
    )


# -----------------------------------------------------------------------------
# Extraction stats API
# -----------------------------------------------------------------------------


@router.get("/api/extraction/stats")
def get_extraction_stats():
    """Get content extraction statistics and metrics."""
    try:
        with session_scope() as s:
            total_query = text("SELECT COUNT(*) FROM items")
            total_articles = s.execute(total_query).scalar() or 0
            method_query = text(
                """
                SELECT
                    COALESCE(extraction_method, 'legacy') as method,
                    COUNT(*) as count
                FROM items
                GROUP BY COALESCE(extraction_method, 'legacy')
                ORDER BY count DESC
                """
            )
            method_rows = s.execute(method_query).fetchall()
            method_distribution = {row[0]: row[1] for row in method_rows}
            failed_count = method_distribution.get("failed", 0)
            success_count = total_articles - failed_count
            success_rate = success_count / total_articles if total_articles > 0 else 0
            avg_length_query = text(
                "SELECT AVG(LENGTH(content)) FROM items WHERE content IS NOT NULL AND content != ''"
            )
            avg_content_length = s.execute(avg_length_query).scalar() or 0
            avg_time_query = text(
                "SELECT AVG(extraction_time_ms) FROM items WHERE extraction_time_ms IS NOT NULL"
            )
            avg_extraction_time = s.execute(avg_time_query).scalar()
            failure_domains_query = text(
                """
                WITH domain_stats AS (
                    SELECT
                        SUBSTRING(url FROM '://([^/]+)') as domain,
                        COUNT(*) as total_count,
                        COUNT(CASE WHEN extraction_method = 'failed'
                                   OR (content IS NULL AND extraction_method IS NULL)
                              THEN 1 END) as failure_count
                    FROM items
                    GROUP BY SUBSTRING(url FROM '://([^/]+)')
                )
                SELECT domain, failure_count,
                       CASE WHEN total_count > 0 THEN failure_count * 100.0 / total_count ELSE 0 END as failure_rate
                FROM domain_stats
                WHERE failure_count > 0
                ORDER BY failure_count DESC
                LIMIT 10
                """
            )
            failure_domain_rows = s.execute(failure_domains_query).fetchall()
            failures_by_domain = [
                {
                    "domain": row[0] or "unknown",
                    "count": row[1],
                    "rate": round(row[2], 1) if row[2] else 0,
                }
                for row in failure_domain_rows
            ]
            failure_reasons_query = text(
                """
                SELECT COALESCE(extraction_error, 'unknown') as reason, COUNT(*) as count
                FROM items
                WHERE extraction_method = 'failed' OR extraction_error IS NOT NULL
                GROUP BY COALESCE(extraction_error, 'unknown')
                ORDER BY count DESC
                LIMIT 10
                """
            )
            failure_reason_rows = s.execute(failure_reasons_query).fetchall()
            failures_by_reason = {row[0]: row[1] for row in failure_reason_rows}
            time_series_query = text(
                """
                SELECT
                    DATE(COALESCE(extracted_at, created_at)) as date,
                    COUNT(*) as total,
                    COUNT(CASE WHEN extraction_method != 'failed' AND extraction_method IS NOT NULL THEN 1 END) as success,
                    COUNT(CASE WHEN extraction_method = 'failed' THEN 1 END) as failed
                FROM items
                WHERE COALESCE(extracted_at, created_at) >= CURRENT_DATE - INTERVAL '7 days'
                GROUP BY DATE(COALESCE(extracted_at, created_at))
                ORDER BY date DESC
                """
            )
            time_series_rows = s.execute(time_series_query).fetchall()
            recent_extractions = [
                {
                    "date": str(row[0]),
                    "total": row[1],
                    "success": row[2],
                    "failed": row[3],
                }
                for row in time_series_rows
            ]
            quality_query = text(
                """
                SELECT
                    CASE
                        WHEN extraction_quality >= 0.9 THEN 'excellent'
                        WHEN extraction_quality >= 0.7 THEN 'good'
                        WHEN extraction_quality >= 0.5 THEN 'fair'
                        WHEN extraction_quality >= 0.3 THEN 'poor'
                        WHEN extraction_quality IS NOT NULL THEN 'very_poor'
                        ELSE 'unknown'
                    END as quality_tier,
                    COUNT(*) as count
                FROM items
                GROUP BY quality_tier
                ORDER BY count DESC
                """
            )
            quality_rows = s.execute(quality_query).fetchall()
            quality_distribution = {row[0]: row[1] for row in quality_rows}
            return {
                "total_articles": total_articles,
                "extraction_stats": {
                    "success_rate": round(success_rate, 3),
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "method_distribution": method_distribution,
                    "avg_content_length": (
                        int(avg_content_length) if avg_content_length else 0
                    ),
                    "avg_extraction_time_ms": (
                        int(avg_extraction_time) if avg_extraction_time else None
                    ),
                    "quality_distribution": quality_distribution,
                },
                "failures_by_domain": failures_by_domain,
                "failures_by_reason": failures_by_reason,
                "recent_extractions": recent_extractions,
            }
    except Exception as e:
        logger.error(f"Failed to get extraction stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve extraction statistics: {str(e)}",
        )


# -----------------------------------------------------------------------------
# LLM and quality metrics APIs (dashboard data)
# -----------------------------------------------------------------------------


@router.get("/api/llm/stats")
def get_llm_quality_stats(
    hours: int = Query(24, description="Hours of history to include"),
):
    """Get LLM output quality statistics (success rates, strategy distribution)."""
    from ..llm_output import get_output_logger
    from ..quality_metrics import (
        get_quality_distribution,
        get_quality_summary,
        get_strategy_distribution,
    )

    try:
        with session_scope() as s:
            days = max(1, hours // 24)
            return {
                "success_rates": get_output_logger().get_success_rate(hours),
                "failure_summary": get_output_logger().get_failure_summary(hours),
                "strategy_distribution": get_strategy_distribution(s, days),
                "quality_distribution": get_quality_distribution(s, days),
                "by_operation": get_quality_summary(s, days),
            }
    except Exception as e:
        logger.error(f"Failed to get LLM stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve LLM statistics: {str(e)}",
        )


@router.get("/api/quality/summary")
def get_quality_summary_endpoint(
    days: int = Query(7, description="Days of history to include"),
):
    """Get overall quality summary across all LLM operations."""
    from ..quality_metrics import (
        get_component_averages,
        get_quality_distribution,
        get_quality_summary,
        get_quality_trends,
        get_recent_low_quality_stories,
    )

    try:
        with session_scope() as s:
            return {
                "period_days": days,
                "by_operation": get_quality_summary(s, days),
                "synthesis": {
                    "quality_distribution": get_quality_distribution(s, days),
                    "component_averages": get_component_averages(s, days),
                    "trends": get_quality_trends(s, days, "synthesis"),
                },
                "recent_low_quality": get_recent_low_quality_stories(s, threshold=0.5),
            }
    except Exception as e:
        logger.error(f"Failed to get quality summary: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve quality summary: {str(e)}",
        )


@router.get("/api/quality/trends")
def get_quality_trends_endpoint(
    days: int = Query(7, description="Days of history to include"),
    operation: str = Query("synthesis", description="Operation type to filter"),
):
    """Get quality score trends over time."""
    from ..quality_metrics import get_quality_trends

    try:
        with session_scope() as s:
            return {
                "operation": operation,
                "period_days": days,
                "trends": get_quality_trends(s, days, operation),
            }
    except Exception as e:
        logger.error(f"Failed to get quality trends: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve quality trends: {str(e)}",
        )
