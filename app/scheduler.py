"""
Background scheduler for automated feed refresh and story generation.

Uses APScheduler to run background tasks on configurable schedules.
Default schedules:
- Feed refresh: 5:30 AM daily
- Story generation: 6:00 AM daily
"""

import logging
import os
import threading
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db import session_scope
from app.stories import generate_stories_simple

logger = logging.getLogger(__name__)

# =============================================================================
# Configuration from environment variables
# =============================================================================

# Feed refresh configuration (v0.6.3)
FEED_REFRESH_ENABLED = os.getenv("FEED_REFRESH_ENABLED", "true").lower() == "true"
FEED_REFRESH_SCHEDULE = os.getenv(
    "FEED_REFRESH_SCHEDULE", "30 5 * * *"
)  # Default: 5:30 AM daily (30 min before story generation)

# Story generation configuration
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

# Topic reclassification configuration (v0.7.6)
TOPIC_RECLASSIFY_ENABLED = (
    os.getenv("TOPIC_RECLASSIFY_ENABLED", "true").lower() == "true"
)
TOPIC_RECLASSIFY_SCHEDULE = os.getenv(
    "TOPIC_RECLASSIFY_SCHEDULE", "0 4 * * *"
)  # Default: 4 AM daily (before feed refresh)
TOPIC_RECLASSIFY_USE_LLM = (
    os.getenv("TOPIC_RECLASSIFY_USE_LLM", "true").lower() == "true"
)
TOPIC_RECLASSIFY_BATCH_SIZE = int(
    os.getenv("TOPIC_RECLASSIFY_BATCH_SIZE", "100")
)  # Process 100 articles per run
TOPIC_RECLASSIFY_MODEL = os.getenv(
    "TOPIC_RECLASSIFY_MODEL", "llama3.1:8b"
)  # LLM model for classification

# Credibility data refresh configuration (v0.8.2 - Issue #271)
CREDIBILITY_REFRESH_ENABLED = (
    os.getenv("CREDIBILITY_REFRESH_ENABLED", "true").lower() == "true"
)
CREDIBILITY_REFRESH_SCHEDULE = os.getenv(
    "CREDIBILITY_REFRESH_SCHEDULE", "0 3 * * 0"
)  # Default: 3 AM every Sunday (weekly)

# =============================================================================
# Global state
# =============================================================================

# Global scheduler instance
scheduler: BackgroundScheduler = None  # type: ignore

# Lock to prevent overlapping feed refreshes (manual vs scheduled)
_feed_refresh_lock = threading.Lock()
_feed_refresh_in_progress = False


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


def is_feed_refresh_in_progress() -> bool:
    """Check if a feed refresh is currently in progress."""
    return _feed_refresh_in_progress


def set_feed_refresh_in_progress(in_progress: bool):
    """Set the feed refresh in-progress flag (for manual refresh coordination)."""
    global _feed_refresh_in_progress
    _feed_refresh_in_progress = in_progress


def scheduled_feed_refresh() -> dict:
    """
    Refresh all feeds on schedule.

    This function is called by APScheduler according to the configured cron schedule.
    It fetches new articles from all configured feeds.

    Skips if a manual refresh is already in progress.

    Returns:
        Dict with refresh statistics
    """
    global _feed_refresh_in_progress

    # Check if manual refresh is in progress
    if not _feed_refresh_lock.acquire(blocking=False):
        logger.info("Scheduled feed refresh skipped - manual refresh in progress")
        return {
            "success": True,
            "skipped": True,
            "reason": "Manual refresh in progress",
        }

    try:
        _feed_refresh_in_progress = True
        logger.info("Starting scheduled feed refresh")
        start_time = datetime.now(UTC)

        # Import here to avoid circular imports
        from app.feeds import fetch_and_store

        # Run the feed refresh (no session needed - function manages its own)
        result = fetch_and_store()

        elapsed = (datetime.now(UTC) - start_time).total_seconds()

        # Extract stats from RefreshStats dataclass
        ingested = result.total_items
        stats = {
            "feeds_processed": result.total_feeds_processed,
            "feeds_skipped_disabled": result.feeds_skipped_disabled,
            "feeds_cached_304": result.feeds_cached_304,
            "feeds_error": result.feeds_error,
        }

        logger.info(
            f"Scheduled feed refresh complete: "
            f"{ingested} articles ingested, "
            f"took {elapsed:.1f}s"
        )

        return {
            "success": True,
            "skipped": False,
            "articles_ingested": ingested,
            "elapsed_seconds": elapsed,
            "stats": stats,
        }

    except Exception as e:
        elapsed = (datetime.now(UTC) - start_time).total_seconds()
        logger.error(
            f"Scheduled feed refresh failed after {elapsed:.1f}s: {e}",
            exc_info=True,
        )
        return {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed,
        }

    finally:
        _feed_refresh_in_progress = False
        _feed_refresh_lock.release()


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


def scheduled_topic_reclassification() -> dict:
    """
    Reclassify articles with 'general' topic or low confidence.

    This function is called by APScheduler according to the configured cron schedule.
    It uses LLM-based classification for better accuracy than keyword-only.

    Returns:
        Dict with reclassification statistics
    """
    logger.info("Starting scheduled topic reclassification")
    start_time = datetime.now(UTC)

    try:
        from sqlalchemy import text

        from app.topics import classify_topic

        stats = {
            "articles_processed": 0,
            "topics_changed": 0,
            "errors": 0,
        }

        with session_scope() as session:
            # Find articles needing reclassification:
            # - topic = 'general' (catch-all)
            # - topic_confidence < 0.5 (low confidence)
            # Limit to batch size to avoid long-running jobs
            rows = session.execute(
                text(
                    """
                    SELECT id, title, summary, content, topic, topic_confidence
                    FROM items
                    WHERE topic = 'general' OR topic_confidence < 0.5 OR topic IS NULL
                    ORDER BY created_at DESC
                    LIMIT :batch_size
                    """
                ),
                {"batch_size": TOPIC_RECLASSIFY_BATCH_SIZE},
            ).all()

            if not rows:
                logger.info("No articles need reclassification")
                return {
                    "success": True,
                    "articles_processed": 0,
                    "topics_changed": 0,
                    "message": "No articles need reclassification",
                }

            logger.info(f"Found {len(rows)} articles to reclassify")

            for row in rows:
                try:
                    article_id = row[0]
                    title = row[1] or ""
                    summary = row[2] or ""
                    content = row[3] or ""
                    old_topic = row[4]
                    old_confidence = row[5] or 0.0

                    # Reclassify using LLM if enabled
                    result = classify_topic(
                        title=title,
                        summary=f"{content} {summary}".strip(),
                        use_llm=TOPIC_RECLASSIFY_USE_LLM,
                        model=(
                            TOPIC_RECLASSIFY_MODEL if TOPIC_RECLASSIFY_USE_LLM else None
                        ),
                    )

                    stats["articles_processed"] += 1

                    # Update if topic changed or confidence improved significantly
                    if (
                        result.topic != old_topic
                        or result.confidence > old_confidence + 0.2
                    ):
                        session.execute(
                            text(
                                """
                                UPDATE items
                                SET topic = :topic, topic_confidence = :confidence
                                WHERE id = :id
                                """
                            ),
                            {
                                "topic": result.topic,
                                "confidence": result.confidence,
                                "id": article_id,
                            },
                        )
                        stats["topics_changed"] += 1

                        logger.debug(
                            f"Reclassified article {article_id}: "
                            f"'{old_topic}' ({old_confidence:.2f}) -> "
                            f"'{result.topic}' ({result.confidence:.2f})"
                        )

                except Exception as e:
                    stats["errors"] += 1
                    logger.warning(f"Failed to reclassify article {row[0]}: {e}")
                    continue

            session.commit()

        elapsed = (datetime.now(UTC) - start_time).total_seconds()

        logger.info(
            f"Topic reclassification complete: "
            f"{stats['articles_processed']} processed, "
            f"{stats['topics_changed']} changed, "
            f"{stats['errors']} errors, "
            f"took {elapsed:.1f}s"
        )

        return {
            "success": True,
            **stats,
            "elapsed_seconds": elapsed,
            "use_llm": TOPIC_RECLASSIFY_USE_LLM,
            "model": TOPIC_RECLASSIFY_MODEL if TOPIC_RECLASSIFY_USE_LLM else None,
        }

    except Exception as e:
        elapsed = (datetime.now(UTC) - start_time).total_seconds()
        logger.error(
            f"Topic reclassification failed after {elapsed:.1f}s: {e}",
            exc_info=True,
        )
        return {
            "success": False,
            "error": str(e),
            "elapsed_seconds": elapsed,
        }


def scheduled_credibility_refresh() -> dict:
    """
    Scheduled job to refresh source credibility data from MBFC.

    Runs weekly to pick up any new sources or rating changes.

    Returns:
        Dict with refresh statistics
    """
    from app.credibility_import import import_mbfc_sources

    logger.info("Starting scheduled credibility data refresh")
    start_time = datetime.now(UTC)

    try:
        stats = import_mbfc_sources()
        elapsed = (datetime.now(UTC) - start_time).total_seconds()

        logger.info(
            f"Credibility refresh complete: "
            f"{stats.inserted} inserted, {stats.updated} updated, "
            f"{stats.skipped} skipped, took {elapsed:.1f}s"
        )

        return {
            "success": True,
            **stats.to_dict(),
            "elapsed_seconds": elapsed,
        }

    except Exception as e:
        elapsed = (datetime.now(UTC) - start_time).total_seconds()
        logger.error(
            f"Credibility refresh failed after {elapsed:.1f}s: {e}",
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

    Initializes APScheduler and schedules:
    - Credibility data refresh (if enabled)
    - Topic reclassification (if enabled)
    - Feed refresh (if enabled)
    - Story generation

    Should be called once during application startup.
    """
    global scheduler

    if scheduler is not None and scheduler.running:
        logger.warning("Scheduler already running")
        return

    scheduler = BackgroundScheduler(timezone=STORY_GENERATION_TIMEZONE)

    try:
        # Add scheduled topic reclassification job (v0.7.6)
        if TOPIC_RECLASSIFY_ENABLED:
            topic_trigger = CronTrigger.from_crontab(
                TOPIC_RECLASSIFY_SCHEDULE, timezone=STORY_GENERATION_TIMEZONE
            )
            scheduler.add_job(
                scheduled_topic_reclassification,
                trigger=topic_trigger,
                id="topic_reclassification",
                name="Scheduled Topic Reclassification",
                replace_existing=True,
                max_instances=1,
            )
            logger.info(
                f"Topic reclassification scheduled: {TOPIC_RECLASSIFY_SCHEDULE} {STORY_GENERATION_TIMEZONE}"
            )
        else:
            logger.info(
                "Topic reclassification disabled (TOPIC_RECLASSIFY_ENABLED=false)"
            )

        # Add scheduled credibility refresh job (v0.8.2 - Issue #271)
        if CREDIBILITY_REFRESH_ENABLED:
            credibility_trigger = CronTrigger.from_crontab(
                CREDIBILITY_REFRESH_SCHEDULE, timezone=STORY_GENERATION_TIMEZONE
            )
            scheduler.add_job(
                scheduled_credibility_refresh,
                trigger=credibility_trigger,
                id="credibility_refresh",
                name="Scheduled Credibility Data Refresh",
                replace_existing=True,
                max_instances=1,
            )
            logger.info(
                f"Credibility refresh scheduled: {CREDIBILITY_REFRESH_SCHEDULE} {STORY_GENERATION_TIMEZONE}"
            )
        else:
            logger.info(
                "Credibility refresh disabled (CREDIBILITY_REFRESH_ENABLED=false)"
            )

        # Add scheduled feed refresh job (v0.6.3)
        if FEED_REFRESH_ENABLED:
            feed_trigger = CronTrigger.from_crontab(
                FEED_REFRESH_SCHEDULE, timezone=STORY_GENERATION_TIMEZONE
            )
            scheduler.add_job(
                scheduled_feed_refresh,
                trigger=feed_trigger,
                id="feed_refresh",
                name="Scheduled Feed Refresh",
                replace_existing=True,
                max_instances=1,  # Only one instance running at a time
            )
            logger.info(
                f"Feed refresh scheduled: {FEED_REFRESH_SCHEDULE} {STORY_GENERATION_TIMEZONE}"
            )
        else:
            logger.info("Feed refresh disabled (FEED_REFRESH_ENABLED=false)")

        # Add scheduled story generation job
        story_trigger = CronTrigger.from_crontab(
            STORY_GENERATION_SCHEDULE, timezone=STORY_GENERATION_TIMEZONE
        )
        scheduler.add_job(
            scheduled_story_generation,
            trigger=story_trigger,
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


def is_scheduler_running() -> bool:
    """Check if the scheduler is currently running."""
    global scheduler
    return scheduler is not None and scheduler.running


def get_scheduler_status() -> dict:
    """
    Get current scheduler status.

    Returns:
        Dict with scheduler status information including topic reclassification,
        feed refresh, and story generation
    """
    global scheduler

    if scheduler is None or not scheduler.running:
        return {
            "running": False,
            "topic_reclassification": None,
            "feed_refresh": None,
            "story_generation": None,
        }

    jobs = scheduler.get_jobs()
    story_job = next((j for j in jobs if j.id == "story_generation"), None)
    feed_job = next((j for j in jobs if j.id == "feed_refresh"), None)
    topic_job = next((j for j in jobs if j.id == "topic_reclassification"), None)

    return {
        "running": True,
        "timezone": STORY_GENERATION_TIMEZONE,
        "topic_reclassification": {
            "enabled": TOPIC_RECLASSIFY_ENABLED,
            "schedule": TOPIC_RECLASSIFY_SCHEDULE if TOPIC_RECLASSIFY_ENABLED else None,
            "next_run": topic_job.next_run_time.isoformat() if topic_job else None,
            "configuration": {
                "use_llm": TOPIC_RECLASSIFY_USE_LLM,
                "batch_size": TOPIC_RECLASSIFY_BATCH_SIZE,
                "model": TOPIC_RECLASSIFY_MODEL,
            },
        },
        "feed_refresh": {
            "enabled": FEED_REFRESH_ENABLED,
            "schedule": FEED_REFRESH_SCHEDULE if FEED_REFRESH_ENABLED else None,
            "next_run": feed_job.next_run_time.isoformat() if feed_job else None,
            "in_progress": _feed_refresh_in_progress,
        },
        "story_generation": {
            "schedule": STORY_GENERATION_SCHEDULE,
            "next_run": story_job.next_run_time.isoformat() if story_job else None,
            "configuration": {
                "time_window_hours": STORY_TIME_WINDOW_HOURS,
                "archive_days": STORY_ARCHIVE_DAYS,
                "min_articles": STORY_MIN_ARTICLES,
                "model": STORY_MODEL,
            },
        },
    }
