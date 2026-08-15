"""Health and readiness endpoints."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from .. import scheduler
from ..deps import get_git_revision, get_version, session_scope
from ..llm import OLLAMA_BASE_URL, get_llm_service, is_llm_available
from ..settings import get_settings_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    """
    Health check endpoint for container orchestration.

    Returns status of core dependencies:
    - database: PostgreSQL connectivity
    - llm: Ollama LLM availability (optional, doesn't fail health check)
    - scheduler: Background job scheduler status
    """
    rev = get_git_revision()
    health_status: Dict[str, Any] = {
        "status": "healthy",
        "version": get_version(),
        "git_revision": rev,
        "git_revision_short": rev[:7] if len(rev) >= 7 else rev,
        "timestamp": datetime.utcnow().isoformat(),
        "components": {},
    }

    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
        health_status["components"]["database"] = {"status": "healthy"}
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    try:
        llm_available = is_llm_available()
        health_status["components"]["llm"] = {
            "status": "healthy" if llm_available else "unavailable",
            "url": get_llm_service().backend.base_url,
        }
    except Exception as e:
        health_status["components"]["llm"] = {
            "status": "unavailable",
            "error": str(e),
        }

    try:
        scheduler_running = scheduler.is_scheduler_running()
        health_status["components"]["scheduler"] = {
            "status": "healthy" if scheduler_running else "stopped",
        }
    except Exception as e:
        health_status["components"]["scheduler"] = {
            "status": "unknown",
            "error": str(e),
        }

    if health_status["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=health_status)

    return health_status


@router.get("/healthz")
def healthz() -> dict:
    """Kubernetes-style liveness probe. Only checks if the application is running."""
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> dict:
    """Kubernetes-style readiness probe. Verifies database connectivity."""
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "database": "disconnected", "error": str(e)},
        )


@router.get("/ollamaz")
def ollamaz() -> dict:
    """
    LLM backend health probe (Ollama, or oMLX on macOS -- #336/#337).
    Returns 503 if the resolved backend is not available.
    """
    base_url = OLLAMA_BASE_URL
    try:
        llm_service = get_llm_service()
        backend_type = get_settings_service().get_backend_type()
        base_url = llm_service.backend.base_url
        available = llm_service.is_available()

        if not available:
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "unavailable",
                    "url": base_url,
                    "backend": backend_type,
                    "message": "LLM backend is not responding",
                },
            )

        try:
            models = llm_service.backend.list_models()
        except Exception:
            models = []

        resolution = get_settings_service().get_model_resolution_info()

        return {
            "status": "healthy",
            "url": base_url,
            "backend": backend_type,
            "default_model": resolution.model,
            "effective_model": resolution.model,
            "detected_platform": resolution.platform,
            "resolution_source": resolution.source,
            "models_available": len(models),
            "models": models[:10],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"LLM backend health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "url": base_url,
                "error": str(e),
            },
        )
