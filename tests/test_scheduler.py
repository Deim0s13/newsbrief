"""
Tests for the scheduler module.

Tests cover:
- Story archiving
- Feed refresh state management
- Scheduler lifecycle
- Status reporting
"""

import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import patch, MagicMock


class TestArchiveOldStories:
    """Tests for archive_old_stories function."""

    @patch("app.scheduler.session_scope")
    def test_archive_old_stories_success(self, mock_session_scope):
        """Test archiving old stories."""
        from app.scheduler import archive_old_stories

        # Mock session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        mock_session.execute.return_value = mock_result
        mock_session_scope.return_value.__enter__.return_value = mock_session

        result = archive_old_stories()

        assert result == 3
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch("app.scheduler.session_scope")
    def test_archive_old_stories_none_to_archive(self, mock_session_scope):
        """Test when no stories need archiving."""
        from app.scheduler import archive_old_stories

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result
        mock_session_scope.return_value.__enter__.return_value = mock_session

        result = archive_old_stories()

        assert result == 0

    @patch("app.scheduler.session_scope")
    def test_archive_old_stories_exception(self, mock_session_scope):
        """Test exception handling during archiving."""
        from app.scheduler import archive_old_stories

        mock_session_scope.side_effect = Exception("Database error")

        result = archive_old_stories()

        assert result == 0  # Returns 0 on error


class TestFeedRefreshState:
    """Tests for feed refresh state management."""

    def test_is_feed_refresh_in_progress_default(self):
        """Test default state is not in progress."""
        from app.scheduler import is_feed_refresh_in_progress, set_feed_refresh_in_progress

        # Reset to known state
        set_feed_refresh_in_progress(False)

        assert is_feed_refresh_in_progress() is False

    def test_set_feed_refresh_in_progress(self):
        """Test setting feed refresh state."""
        from app.scheduler import is_feed_refresh_in_progress, set_feed_refresh_in_progress

        set_feed_refresh_in_progress(True)
        assert is_feed_refresh_in_progress() is True

        set_feed_refresh_in_progress(False)
        assert is_feed_refresh_in_progress() is False


class TestScheduledFeedRefresh:
    """Tests for scheduled_feed_refresh function."""

    @patch("app.scheduler._feed_refresh_lock")
    def test_scheduled_feed_refresh_skips_when_locked(self, mock_lock):
        """Test that scheduled refresh skips if manual refresh is in progress."""
        from app.scheduler import scheduled_feed_refresh

        mock_lock.acquire.return_value = False  # Lock not acquired

        result = scheduled_feed_refresh()

        assert result["success"] is True
        assert result["skipped"] is True
        assert "Manual refresh in progress" in result["reason"]

    @patch("app.feeds.fetch_and_store")
    @patch("app.scheduler._feed_refresh_lock")
    def test_scheduled_feed_refresh_success(self, mock_lock, mock_fetch):
        """Test successful scheduled feed refresh."""
        from app.scheduler import scheduled_feed_refresh

        mock_lock.acquire.return_value = True

        # Mock RefreshStats
        mock_stats = MagicMock()
        mock_stats.total_items = 50
        mock_stats.total_feeds_processed = 10
        mock_stats.feeds_skipped_disabled = 2
        mock_stats.feeds_cached_304 = 3
        mock_stats.feeds_error = 1
        mock_fetch.return_value = mock_stats

        result = scheduled_feed_refresh()

        assert result["success"] is True
        assert result["skipped"] is False
        assert result["articles_ingested"] == 50
        assert "elapsed_seconds" in result
        mock_lock.release.assert_called_once()

    @patch("app.feeds.fetch_and_store")
    @patch("app.scheduler._feed_refresh_lock")
    def test_scheduled_feed_refresh_exception(self, mock_lock, mock_fetch):
        """Test exception handling in scheduled feed refresh."""
        from app.scheduler import scheduled_feed_refresh

        mock_lock.acquire.return_value = True
        mock_fetch.side_effect = Exception("Network error")

        result = scheduled_feed_refresh()

        assert result["success"] is False
        assert "Network error" in result["error"]
        mock_lock.release.assert_called_once()  # Lock should still be released


class TestScheduledStoryGeneration:
    """Tests for scheduled_story_generation function."""

    @patch("app.scheduler.generate_stories_simple")
    @patch("app.scheduler.archive_old_stories")
    @patch("app.scheduler.session_scope")
    def test_scheduled_story_generation_success(
        self, mock_session_scope, mock_archive, mock_generate
    ):
        """Test successful scheduled story generation."""
        from app.scheduler import scheduled_story_generation

        mock_archive.return_value = 5  # Archived 5 stories
        mock_generate.return_value = {"story_ids": [1, 2, 3], "articles_found": 10}
        mock_session_scope.return_value.__enter__.return_value = MagicMock()

        result = scheduled_story_generation()

        assert result["success"] is True
        mock_archive.assert_called_once()
        mock_generate.assert_called_once()

    @patch("app.scheduler.archive_old_stories")
    @patch("app.scheduler.session_scope")
    def test_scheduled_story_generation_exception(self, mock_session_scope, mock_archive):
        """Test exception handling in scheduled story generation."""
        from app.scheduler import scheduled_story_generation

        mock_archive.side_effect = Exception("Database error")

        result = scheduled_story_generation()

        assert result["success"] is False
        assert "Database error" in result["error"]


class TestSchedulerLifecycle:
    """Tests for scheduler start/stop functions."""

    @patch("app.scheduler.BackgroundScheduler")
    def test_start_scheduler_success(self, mock_scheduler_class):
        """Test starting the scheduler."""
        from app import scheduler as scheduler_module
        from app.scheduler import start_scheduler

        # Reset global scheduler
        scheduler_module.scheduler = None

        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_scheduler_class.return_value = mock_scheduler

        start_scheduler()

        mock_scheduler.add_job.assert_called()  # Jobs added
        mock_scheduler.start.assert_called_once()

    @patch("app.scheduler.BackgroundScheduler")
    def test_start_scheduler_already_running(self, mock_scheduler_class):
        """Test starting scheduler when already running."""
        from app import scheduler as scheduler_module
        from app.scheduler import start_scheduler

        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        scheduler_module.scheduler = mock_scheduler

        start_scheduler()

        # Should not create new scheduler or call start again
        mock_scheduler_class.assert_not_called()

    def test_stop_scheduler_when_running(self):
        """Test stopping a running scheduler."""
        from app import scheduler as scheduler_module
        from app.scheduler import stop_scheduler

        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        scheduler_module.scheduler = mock_scheduler

        stop_scheduler()

        mock_scheduler.shutdown.assert_called_once_with(wait=True)

    def test_stop_scheduler_when_not_running(self):
        """Test stopping scheduler when not running."""
        from app import scheduler as scheduler_module
        from app.scheduler import stop_scheduler

        scheduler_module.scheduler = None

        # Should not raise
        stop_scheduler()


class TestGetSchedulerStatus:
    """Tests for get_scheduler_status function."""

    def test_get_status_when_not_running(self):
        """Test status when scheduler is not running."""
        from app import scheduler as scheduler_module
        from app.scheduler import get_scheduler_status

        scheduler_module.scheduler = None

        status = get_scheduler_status()

        assert status["running"] is False
        assert status["feed_refresh"] is None
        assert status["story_generation"] is None

    def test_get_status_when_running(self):
        """Test status when scheduler is running."""
        from app import scheduler as scheduler_module
        from app.scheduler import get_scheduler_status

        # Create mock scheduler with jobs
        mock_scheduler = MagicMock()
        mock_scheduler.running = True

        mock_story_job = MagicMock()
        mock_story_job.id = "story_generation"
        mock_story_job.next_run_time = datetime.now(UTC) + timedelta(hours=6)

        mock_feed_job = MagicMock()
        mock_feed_job.id = "feed_refresh"
        mock_feed_job.next_run_time = datetime.now(UTC) + timedelta(hours=5)

        mock_scheduler.get_jobs.return_value = [mock_story_job, mock_feed_job]
        scheduler_module.scheduler = mock_scheduler

        status = get_scheduler_status()

        assert status["running"] is True
        assert status["story_generation"] is not None
        assert status["feed_refresh"] is not None
        assert "next_run" in status["story_generation"]
        assert "schedule" in status["story_generation"]

    def test_get_status_when_running_no_feed_job(self):
        """Test status when scheduler is running but feed refresh is disabled."""
        from app import scheduler as scheduler_module
        from app.scheduler import get_scheduler_status

        mock_scheduler = MagicMock()
        mock_scheduler.running = True

        mock_story_job = MagicMock()
        mock_story_job.id = "story_generation"
        mock_story_job.next_run_time = datetime.now(UTC) + timedelta(hours=6)

        # No feed job
        mock_scheduler.get_jobs.return_value = [mock_story_job]
        scheduler_module.scheduler = mock_scheduler

        status = get_scheduler_status()

        assert status["running"] is True
        assert status["feed_refresh"]["next_run"] is None


class TestConfigurationEnvironmentVariables:
    """Tests for configuration from environment variables."""

    def test_default_configuration_values(self):
        """Test that default configuration values are set."""
        from app.scheduler import (
            FEED_REFRESH_ENABLED,
            FEED_REFRESH_SCHEDULE,
            STORY_GENERATION_SCHEDULE,
            STORY_ARCHIVE_DAYS,
            STORY_TIME_WINDOW_HOURS,
            STORY_MIN_ARTICLES,
            STORY_MODEL,
        )

        # These are the defaults from the module
        assert FEED_REFRESH_ENABLED is True
        assert FEED_REFRESH_SCHEDULE == "30 5 * * *"
        assert STORY_GENERATION_SCHEDULE == "0 6 * * *"
        assert STORY_ARCHIVE_DAYS == 7
        assert STORY_TIME_WINDOW_HOURS == 24
        assert STORY_MIN_ARTICLES == 2
        assert STORY_MODEL == "llama3.1:8b"

