"""Admin dashboard pages and APIs: credibility, quality, extraction, LLM stats."""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text

from ..credibility import canonicalize_domain
from ..credibility_import import import_mbfc_sources
from ..deps import session_scope, templates
from ..orm_models import SourceCredibility
from ..settings import get_settings_service
from ..topics import get_available_topics, get_reclassification_stats

logger = logging.getLogger(__name__)

router = APIRouter(prefix="", tags=["admin"])


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
        "credibility_dashboard.html",
        {
            "request": request,
            "current_page": "admin",
            "environment": os.environ.get("ENVIRONMENT", "development"),
        },
    )


@router.get("/admin/extraction", response_class=HTMLResponse)
def extraction_dashboard_page(request: Request):
    """Extraction quality monitoring dashboard."""
    return templates.TemplateResponse(
        "extraction_dashboard.html",
        {
            "request": request,
            "current_page": "admin",
            "environment": os.environ.get("ENVIRONMENT", "development"),
        },
    )


@router.get("/admin/quality", response_class=HTMLResponse)
def quality_dashboard_page(request: Request):
    """LLM output quality monitoring dashboard."""
    return templates.TemplateResponse(
        "quality_dashboard.html",
        {
            "request": request,
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
        "topics_management.html",
        {
            "request": request,
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
        "models_management.html",
        {
            "request": request,
            "current_page": "admin",
            "environment": os.environ.get("ENVIRONMENT", "development"),
            "profiles": profiles,
            "active_profile": active_profile,
            "models": models,
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
