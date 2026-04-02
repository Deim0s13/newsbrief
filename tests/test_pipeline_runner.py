"""Tests for pipeline runner (#274)."""

from unittest.mock import patch

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
