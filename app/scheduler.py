"""
Background scheduler for automated story generation.

Uses APScheduler to run story generation on a configurable schedule.
Default: Daily at 6 AM.
"""

import logging
import os
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db import session_scope
from app.stories import generate_stories_simple

logger = logging.getLogger(__name__)

# Configuration from environment variables
STORY_GENERATION_SCHEDULE = os.getenv(
    "STORY_GENERATION_SCHEDULE", "0 6 * * *"
)  # Default: 6 AM daily (cron format)
STORY_GENERATION_TIMEZONE = os.getenv(
    "STORY_GENERATION_TIMEZONE", "Pacific/Auckland"
)  # Default: New Zealand time (handles NZST/NZDT)
STORY_ARCHIVE_DAYS = int(
    os.getenv("STORY_ARCHIVE_DAYS", "7")
)  # Archive stories older than 7 days
STORY_TIME_WINDOW_HOURS = int(
    os.getenv("STORY_TIME_WINDOW_HOURS", "24")
)  # Generate from last 24 hours
STORY_MIN_ARTICLES = int(
    os.getenv("STORY_MIN_ARTICLES", "2")
)  # Minimum articles per story
STORY_MODEL = os.getenv("STORY_MODEL", "llama3.1:8b")  # LLM model for synthesis

# Global scheduler instance
scheduler: BackgroundScheduler = None  # type: ignore


def archive_old_stories() -> int:
    """
    Archive stories older than configured days.

    Marks stories as 'archived' instead of deleting them.
    This keeps historical data while hiding old stories from main views.

    Returns:
        Number of stories archived
    """
    try:
        from sqlalchemy import text

        cutoff_date = datetime.now(UTC) - timedelta(days=STORY_ARCHIVE_DAYS)

        with session_scope() as session:
            result = session.execute(
                text(
                    """
                    UPDATE stories 
                    SET status = 'archived', last_updated = :now
                    WHERE status = 'active' 
                    AND generated_at < :cutoff
                    """
                ),
                {
                    "cutoff": cutoff_date.isoformat(),
                    "now": datetime.now(UTC).isoformat(),
                },
            )
            session.commit()
            count = result.rowcount or 0

            if count > 0:
                logger.info(
                    f"Archived {count} stories older than {STORY_ARCHIVE_DAYS} days"
                )
            else:
                logger.debug(f"No stories to archive (cutoff: {cutoff_date})")

            return count

    except Exception as e:
        logger.error(f"Failed to archive old stories: {e}", exc_info=True)
        return 0


def scheduled_story_generation():
    """
    Generate stories on schedule.

    This function is called by APScheduler according to the configured cron schedule.
    It archives old stories, then generates new stories from recent articles.
    """
    logger.info("Starting scheduled story generation")
    start_time = datetime.now(UTC)

    try:
        # Step 1: Archive old stories
        archived_count = archive_old_stories()

        # Step 2: Generate new stories
        with session_scope() as session:
            story_ids = generate_stories_simple(
                session=session,
                time_window_hours=STORY_TIME_WINDOW_HOURS,
                min_articles_per_story=STORY_MIN_ARTICLES,
                similarity_threshold=0.25,  # Lowered from 0.3 for v0.6.1 entity-based clustering
                model=STORY_MODEL,
                max_workers=3,  # Parallel LLM synthesis
            )

            elapsed = (datetime.now(UTC) - start_time).total_seconds()

            logger.info(
                f"Scheduled story generation complete: "
                f"{len(story_ids)} stories generated, "
                f"{archived_count} archived, "
                f"took {elapsed:.1f}s"
            )

            return {
                "success": True,
                "stories_generated": len(story_ids),
                "stories_archived": archived_count,
                "elapsed_seconds": elapsed,
            }

    except Exception as e:
        elapsed = (datetime.now(UTC) - start_time).total_seconds()
        logger.error(
            f"Scheduled story generation failed after {elapsed:.1f}s: {e}",
            exc_info=True,
        )
        return {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed,
        }


def start_scheduler():
    """
    Start the background scheduler.

    Initializes APScheduler and schedules story generation according to
    the configured cron schedule.

    Should be called once during application startup.
    """
    global scheduler

    if scheduler is not None and scheduler.running:
        logger.warning("Scheduler already running")
        return

    scheduler = BackgroundScheduler(timezone=STORY_GENERATION_TIMEZONE)

    # Add scheduled story generation job
    try:
        trigger = CronTrigger.from_crontab(
            STORY_GENERATION_SCHEDULE, timezone=STORY_GENERATION_TIMEZONE
        )
        scheduler.add_job(
            scheduled_story_generation,
            trigger=trigger,
            id="story_generation",
            name="Scheduled Story Generation",
            replace_existing=True,
            max_instances=1,  # Only one instance running at a time
        )

        scheduler.start()

        logger.info(
            f"Scheduler started - Story generation scheduled: {STORY_GENERATION_SCHEDULE} {STORY_GENERATION_TIMEZONE}"
        )
        logger.info(
            f"Configuration: "
            f"time_window={STORY_TIME_WINDOW_HOURS}h, "
            f"archive_after={STORY_ARCHIVE_DAYS}d, "
            f"model={STORY_MODEL}, "
            f"timezone={STORY_GENERATION_TIMEZONE}"
        )

    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}", exc_info=True)
        raise


def stop_scheduler():
    """
    Stop the background scheduler.

    Should be called during application shutdown to cleanly stop background tasks.
    """
    global scheduler

    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")
    else:
        logger.debug("Scheduler not running")


def get_scheduler_status() -> dict:
    """
    Get current scheduler status.

    Returns:
        Dict with scheduler status information
    """
    global scheduler

    if scheduler is None or not scheduler.running:
        return {
            "running": False,
            "next_run": None,
        }

    jobs = scheduler.get_jobs()
    story_job = next((j for j in jobs if j.id == "story_generation"), None)

    return {
        "running": True,
        "schedule": STORY_GENERATION_SCHEDULE,
        "timezone": STORY_GENERATION_TIMEZONE,
        "next_run": story_job.next_run_time.isoformat() if story_job else None,
        "configuration": {
            "time_window_hours": STORY_TIME_WINDOW_HOURS,
            "archive_days": STORY_ARCHIVE_DAYS,
            "min_articles": STORY_MIN_ARTICLES,
            "model": STORY_MODEL,
        },
    }
