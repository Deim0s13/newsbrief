"""Health and readiness endpoints."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from .. import scheduler
from ..deps import session_scope
from ..llm import OLLAMA_BASE_URL, get_llm_service, is_llm_available
from ..settings import get_settings_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    """
    Health check endpoint for container orchestration.

    Returns status of core dependencies:
    - database: SQLite/PostgreSQL connectivity
    - llm: Ollama LLM availability (optional, doesn't fail health check)
    - scheduler: Background job scheduler status
    """
    health_status: Dict[str, Any] = {
        "status": "healthy",
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
            "url": OLLAMA_BASE_URL,
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
    Ollama LLM service health probe.
    Returns 503 if Ollama is not available.
    """
    try:
        llm_service = get_llm_service()
        available = llm_service.is_available()

        if not available:
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "unavailable",
                    "url": OLLAMA_BASE_URL,
                    "message": "Ollama service is not responding",
                },
            )

        try:
            models_response = llm_service.client.list()
            if isinstance(models_response, dict) and "models" in models_response:
                models = [
                    {
                        "name": m.get("name", "unknown"),
                        "size": m.get("size", 0),
                        "modified_at": m.get("modified_at", ""),
                    }
                    for m in models_response.get("models", [])
                ]
            else:
                models = []
        except Exception:
            models = []

        return {
            "status": "healthy",
            "url": OLLAMA_BASE_URL,
            "default_model": get_settings_service().get_active_model(),
            "models_available": len(models),
            "models": models[:10],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ollama health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "url": OLLAMA_BASE_URL,
                "error": str(e),
            },
        )
