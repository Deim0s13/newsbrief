from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, List, Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import scheduler
from .credibility_import import ensure_credibility_data
from .db import init_db
from .deps import get_version, register_limiter_on_app, templates
from .feeds import (
    import_opml,
    migrate_sanitize_existing_summaries,
    recalculate_rankings_and_topics,
    update_feed_health_scores,
)
from .logging_config import configure_logging
from .routers import admin, config, feeds, health, items, pages, stories
from .topics import migrate_article_topics_v062

# Configure structured logging (must be after imports, before app initialization)
configure_logging()

logger = logging.getLogger(__name__)

app = FastAPI(title="NewsBrief")

# Rate limiting (limiter lives in deps so routers can use it)
register_limiter_on_app(app)

# Static files and template globals (templates object lives in deps)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates.env.globals["environment"] = os.environ.get("ENVIRONMENT", "development")
templates.env.globals["app_version"] = get_version()

app.include_router(health.router)
app.include_router(feeds.router)
app.include_router(stories.router)
app.include_router(items.router)
app.include_router(admin.router)
app.include_router(config.router)
app.include_router(pages.router)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    # seed from OPML if present (one-time harmless)
    import_opml("data/feeds.opml")
    # Migrate existing summaries to sanitized HTML (idempotent)
    try:
        migrate_sanitize_existing_summaries()
    except Exception as e:
        logger.warning(f"Summary sanitization migration failed: {e}")
    # Migrate article topics to unified system (one-time, v0.6.2)
    try:
        migrate_article_topics_v062()
    except Exception as e:
        logger.warning(f"Topic migration v0.6.2 failed: {e}")
    # Ensure source credibility data exists (auto-import if empty)
    try:
        result = ensure_credibility_data()
        if result:
            logger.info(
                f"Credibility data imported: {result.inserted} sources "
                f"({result.duration_ms}ms)"
            )
    except Exception as e:
        logger.warning(f"Credibility data import failed: {e}")

    # Start background scheduler for automated story generation
    try:
        scheduler.start_scheduler()
        logger.info("Background scheduler started successfully")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}", exc_info=True)


@app.on_event("shutdown")
def _shutdown() -> None:
    """Shutdown event - stop background scheduler."""
    try:
        scheduler.stop_scheduler()
        logger.info("Background scheduler stopped")
    except Exception as e:
        logger.error(f"Error stopping scheduler: {e}", exc_info=True)


# Page routes (/, /articles, /story/..., /article/..., /feeds-manage, /search) moved to app.routers.pages

# Feed routes moved to app.routers.feeds


# Item routes moved to app.routers.items

# Config routes (topics, models, ranking, scheduler) moved to app.routers.config

# ============================================================================
# Story routes moved to app.routers.stories

# Admin routes moved to app.routers.admin
