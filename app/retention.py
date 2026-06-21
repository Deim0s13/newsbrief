"""Article and data retention policies (issues #178, #118)."""

import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Retention periods (days) — configurable via environment variables.
ARTICLE_RETENTION_DAYS = int(os.getenv("NEWSBRIEF_ARTICLE_RETENTION_DAYS", "30"))
LLM_OUTPUT_RETENTION_DAYS = int(os.getenv("NEWSBRIEF_LLM_OUTPUT_RETENTION_DAYS", "60"))
STORY_RETENTION_DAYS = int(os.getenv("NEWSBRIEF_STORY_RETENTION_DAYS", "90"))
PIPELINE_LOG_RETENTION_DAYS = int(
    os.getenv("NEWSBRIEF_PIPELINE_LOG_RETENTION_DAYS", "30")
)

# Cron schedule for the retention job (default: 3 AM daily)
RETENTION_SCHEDULE = os.getenv("NEWSBRIEF_RETENTION_SCHEDULE", "0 3 * * *")
RETENTION_ENABLED = os.getenv("NEWSBRIEF_RETENTION_ENABLED", "true").lower() == "true"


def get_retention_counts(session: Session) -> dict:
    """Return counts of rows eligible for purge under each retention policy."""
    article_cutoff = datetime.now(UTC) - timedelta(days=ARTICLE_RETENTION_DAYS)
    story_cutoff = datetime.now(UTC) - timedelta(days=STORY_RETENTION_DAYS)
    log_cutoff = datetime.now(UTC) - timedelta(days=PIPELINE_LOG_RETENTION_DAYS)

    total_articles = session.execute(text("SELECT COUNT(*) FROM items")).scalar() or 0

    eligible_articles = (
        session.execute(
            text(
                """
            SELECT COUNT(*) FROM items
            WHERE created_at < :cutoff
              AND id NOT IN (SELECT article_id FROM story_articles)
            """
            ),
            {"cutoff": article_cutoff},
        ).scalar()
        or 0
    )

    total_stories = session.execute(text("SELECT COUNT(*) FROM stories")).scalar() or 0

    eligible_stories = (
        session.execute(
            text(
                """
            SELECT COUNT(*) FROM stories
            WHERE status = 'archived' AND generated_at < :cutoff
            """
            ),
            {"cutoff": story_cutoff},
        ).scalar()
        or 0
    )

    total_logs = (
        session.execute(text("SELECT COUNT(*) FROM pipeline_stage_runs")).scalar() or 0
    )

    eligible_logs = (
        session.execute(
            text("SELECT COUNT(*) FROM pipeline_stage_runs WHERE started_at < :cutoff"),
            {"cutoff": log_cutoff},
        ).scalar()
        or 0
    )

    return {
        "articles": {
            "total": total_articles,
            "eligible_for_purge": eligible_articles,
            "retention_days": ARTICLE_RETENTION_DAYS,
            "cutoff_date": article_cutoff.date().isoformat(),
            "note": "Articles with no story link older than retention window",
        },
        "stories": {
            "total": total_stories,
            "eligible_for_purge": eligible_stories,
            "retention_days": STORY_RETENTION_DAYS,
            "cutoff_date": story_cutoff.date().isoformat(),
            "note": "Archived stories only",
        },
        "pipeline_logs": {
            "total": total_logs,
            "eligible_for_purge": eligible_logs,
            "retention_days": PIPELINE_LOG_RETENTION_DAYS,
            "cutoff_date": log_cutoff.date().isoformat(),
            "note": "pipeline_stage_runs rows",
        },
    }


def _purge_articles(
    session: Session,
    retention_days: Optional[int] = None,
    dry_run: bool = False,
) -> dict:
    days = retention_days if retention_days is not None else ARTICLE_RETENTION_DAYS
    cutoff = datetime.now(UTC) - timedelta(days=days)

    eligible = (
        session.execute(
            text(
                """
            SELECT COUNT(*) FROM items
            WHERE created_at < :cutoff
              AND id NOT IN (SELECT article_id FROM story_articles)
            """
            ),
            {"cutoff": cutoff},
        ).scalar()
        or 0
    )

    if not dry_run and eligible > 0:
        session.execute(
            text(
                """
                DELETE FROM items
                WHERE created_at < :cutoff
                  AND id NOT IN (SELECT article_id FROM story_articles)
                """
            ),
            {"cutoff": cutoff},
        )
        logger.info("Purged %d articles older than %d days", eligible, days)

    return {"eligible": eligible, "deleted": eligible if not dry_run else 0}


def _purge_pipeline_logs(
    session: Session,
    retention_days: Optional[int] = None,
    dry_run: bool = False,
) -> dict:
    days = retention_days if retention_days is not None else PIPELINE_LOG_RETENTION_DAYS
    cutoff = datetime.now(UTC) - timedelta(days=days)

    eligible = (
        session.execute(
            text("SELECT COUNT(*) FROM pipeline_stage_runs WHERE started_at < :cutoff"),
            {"cutoff": cutoff},
        ).scalar()
        or 0
    )

    if not dry_run and eligible > 0:
        session.execute(
            text("DELETE FROM pipeline_stage_runs WHERE started_at < :cutoff"),
            {"cutoff": cutoff},
        )
        logger.info("Purged %d pipeline log rows older than %d days", eligible, days)

    return {"eligible": eligible, "deleted": eligible if not dry_run else 0}


def run_retention(session: Session, dry_run: bool = False) -> dict:
    """Run all configured retention policies in a single transaction."""
    start = datetime.now(UTC)

    article_result = _purge_articles(session, dry_run=dry_run)
    log_result = _purge_pipeline_logs(session, dry_run=dry_run)

    if not dry_run:
        session.commit()

    elapsed = (datetime.now(UTC) - start).total_seconds()
    total_deleted = article_result["deleted"] + log_result["deleted"]
    total_eligible = article_result["eligible"] + log_result["eligible"]

    return {
        "dry_run": dry_run,
        "elapsed_seconds": round(elapsed, 3),
        "total_eligible": total_eligible,
        "total_deleted": total_deleted,
        "articles": article_result,
        "pipeline_logs": log_result,
    }
