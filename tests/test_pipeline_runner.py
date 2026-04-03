"""Tests for pipeline runner (#274, #275)."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.pipeline_runner import run_pipeline, run_targeted_replay


class TestRunPipelineBranching:
    @patch("app.pipeline_runner.execute_story_generation_stage")
    @patch("app.pipeline_runner.execute_ingest_stage")
    def test_full_runs_both(self, mock_ingest, mock_story):
        """from_stage None runs ingest then story_generation."""
        from app.pipeline_runner import StageResult

        mock_ingest.return_value = StageResult(
            "ingest", True, {"articles_ingested": 1}, None
        )
        mock_story.return_value = StageResult(
            "story_generation", True, {"stories_created": 0}, None
        )

        out = run_pipeline(trigger="manual", from_stage=None)
        assert out["success"] is True
        assert len(out["stages"]) == 2
        mock_ingest.assert_called_once()
        mock_story.assert_called_once()

    @patch("app.pipeline_runner.execute_story_generation_stage")
    @patch("app.pipeline_runner.execute_ingest_stage")
    def test_ingest_only_skips_story(self, mock_ingest, mock_story):
        from app.pipeline_runner import StageResult

        mock_ingest.return_value = StageResult(
            "ingest", True, {"articles_ingested": 0}, None
        )

        out = run_pipeline(trigger="manual", from_stage="ingest")
        assert out["success"] is True
        assert len(out["stages"]) == 1
        mock_story.assert_not_called()

    @patch("app.pipeline_runner.execute_story_generation_stage")
    @patch("app.pipeline_runner.execute_ingest_stage")
    def test_story_only_skips_ingest(self, mock_ingest, mock_story):
        from app.pipeline_runner import StageResult

        mock_story.return_value = StageResult(
            "story_generation", True, {"stories_created": 0}, None
        )

        out = run_pipeline(trigger="manual", from_stage="story_generation")
        assert out["success"] is True
        assert len(out["stages"]) == 1
        mock_ingest.assert_not_called()

    @patch("app.pipeline_runner.execute_story_generation_stage")
    @patch("app.pipeline_runner.execute_ingest_stage")
    def test_ingest_failure_stops_before_story(self, mock_ingest, mock_story):
        from app.pipeline_runner import StageResult

        mock_ingest.return_value = StageResult("ingest", False, {}, error="boom")

        out = run_pipeline(trigger="manual", from_stage=None)
        assert out["success"] is False
        assert len(out["stages"]) == 1
        mock_story.assert_not_called()


class TestRunTargetedReplay:
    def test_item_wrong_stage_raises(self) -> None:
        with pytest.raises(ValueError, match="item requires"):
            run_targeted_replay(
                target_type="item",
                target_id=1,
                from_stage="story_generation",
                model="llama3.1:8b",
            )

    def test_story_wrong_stage_raises(self) -> None:
        with pytest.raises(ValueError, match="story requires"):
            run_targeted_replay(
                target_type="story",
                target_id=1,
                from_stage="enrich",
                model="llama3.1:8b",
            )

    @patch("app.pipeline_runner.execute_enrich_item_stage")
    def test_item_enrich_delegates(self, mock_enrich) -> None:
        from app.pipeline_runner import StageResult

        mock_enrich.return_value = StageResult("enrich", True, {"item_id": 1}, None)
        out = run_targeted_replay(
            target_type="item",
            target_id=1,
            from_stage="enrich",
            model="llama3.1:8b",
        )
        assert out["success"] is True
        assert len(out["stages"]) == 1
        mock_enrich.assert_called_once()

    @patch("app.pipeline_runner.execute_story_targeted_regeneration_stage")
    def test_story_regen_delegates(self, mock_st) -> None:
        from app.pipeline_runner import StageResult

        mock_st.return_value = StageResult(
            "story_generation",
            True,
            {"new_story_id": 2, "previous_story_id": 1},
            None,
        )
        out = run_targeted_replay(
            target_type="story",
            target_id=5,
            from_stage="story_generation",
            model="llama3.1:8b",
        )
        assert out["success"] is True
        mock_st.assert_called_once()


class TestPipelineRetryHelpers:
    def test_backoff_sequence(self) -> None:
        from app.pipeline_runner import pipeline_retry_backoff_seconds

        assert pipeline_retry_backoff_seconds(3, 2.0, 60.0) == [2.0, 4.0, 8.0]
        assert pipeline_retry_backoff_seconds(2, 2.0, 3.0) == [2.0, 3.0]

    def test_list_recent_bad_outcome(self) -> None:
        from app.pipeline_runner import list_recent_stage_runs

        with pytest.raises(ValueError, match="outcome must be"):
            list_recent_stage_runs(outcome="not-a-filter")


class TestIngestRetries:
    @patch("app.pipeline_runner.session_scope")
    @patch("app.pipeline_runner._stage_retry_settings", return_value=(2, 1.0, 60.0))
    @patch("app.feeds.fetch_and_store")
    @patch("app.pipeline_runner._sleep_before_retry")
    @patch("app.pipeline_runner._insert_stage_start", return_value=1)
    @patch("app.pipeline_runner._finalize_stage_row")
    def test_retries_then_success(
        self,
        mock_finalize,
        mock_insert,
        mock_sleep,
        mock_fetch,
        mock_settings,
        mock_scope,
    ) -> None:
        from app.pipeline_runner import execute_ingest_stage

        ok = SimpleNamespace(
            total_items=0,
            total_feeds_processed=1,
            feeds_error=0,
            feeds_cached_304=0,
        )
        mock_fetch.side_effect = [RuntimeError("fail1"), RuntimeError("fail2"), ok]
        mock_scope.side_effect = lambda: nullcontext(MagicMock())

        execute_ingest_stage(trigger="manual", run_group_id="test-group")

        assert mock_fetch.call_count == 3
        assert mock_sleep.call_count == 2
        mock_finalize.assert_called_once()
        assert mock_finalize.call_args.kwargs["attempts"] == 3
        assert mock_finalize.call_args.kwargs["success"] is True
