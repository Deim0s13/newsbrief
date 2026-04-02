"""Tests for pipeline runner (#274)."""

from unittest.mock import patch

from app.pipeline_runner import run_pipeline


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
