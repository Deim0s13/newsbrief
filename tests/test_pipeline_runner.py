"""Tests for pipeline runner (#274, #275)."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.pipeline_runner import run_pipeline, run_targeted_replay


class TestRunPipelineBranching:
    @patch("app.pipeline_runner.execute_story_generation_stage")
    @patch("app.pipeline_runner.execute_summarize_stage")
    @patch("app.pipeline_runner.execute_ingest_stage")
    def test_full_runs_all_three(self, mock_ingest, mock_summarize, mock_story):
        """from_stage None runs ingest -> summarize -> story_generation (#328)."""
        from app.pipeline_runner import StageResult

        mock_ingest.return_value = StageResult(
            "ingest", True, {"articles_ingested": 1}, None
        )
        mock_summarize.return_value = StageResult(
            "summarize", True, {"summaries_generated": 1}, None
        )
        mock_story.return_value = StageResult(
            "story_generation", True, {"stories_created": 0}, None
        )

        out = run_pipeline(trigger="manual", from_stage=None)
        assert out["success"] is True
        assert len(out["stages"]) == 3
        assert [s["stage"] for s in out["stages"]] == [
            "ingest",
            "summarize",
            "story_generation",
        ]
        mock_ingest.assert_called_once()
        mock_summarize.assert_called_once()
        mock_story.assert_called_once()

    @patch("app.pipeline_runner.execute_story_generation_stage")
    @patch("app.pipeline_runner.execute_summarize_stage")
    @patch("app.pipeline_runner.execute_ingest_stage")
    def test_ingest_only_skips_summarize_and_story(
        self, mock_ingest, mock_summarize, mock_story
    ):
        from app.pipeline_runner import StageResult

        mock_ingest.return_value = StageResult(
            "ingest", True, {"articles_ingested": 0}, None
        )

        out = run_pipeline(trigger="manual", from_stage="ingest")
        assert out["success"] is True
        assert len(out["stages"]) == 1
        mock_summarize.assert_not_called()
        mock_story.assert_not_called()

    @patch("app.pipeline_runner.execute_story_generation_stage")
    @patch("app.pipeline_runner.execute_summarize_stage")
    @patch("app.pipeline_runner.execute_ingest_stage")
    def test_summarize_only_skips_ingest_and_story(
        self, mock_ingest, mock_summarize, mock_story
    ):
        from app.pipeline_runner import StageResult

        mock_summarize.return_value = StageResult(
            "summarize", True, {"summaries_generated": 5}, None
        )

        out = run_pipeline(trigger="manual", from_stage="summarize")
        assert out["success"] is True
        assert len(out["stages"]) == 1
        mock_ingest.assert_not_called()
        mock_story.assert_not_called()

    @patch("app.pipeline_runner.execute_story_generation_stage")
    @patch("app.pipeline_runner.execute_summarize_stage")
    @patch("app.pipeline_runner.execute_ingest_stage")
    def test_story_only_skips_ingest_and_summarize(
        self, mock_ingest, mock_summarize, mock_story
    ):
        from app.pipeline_runner import StageResult

        mock_story.return_value = StageResult(
            "story_generation", True, {"stories_created": 0}, None
        )

        out = run_pipeline(trigger="manual", from_stage="story_generation")
        assert out["success"] is True
        assert len(out["stages"]) == 1
        mock_ingest.assert_not_called()
        mock_summarize.assert_not_called()

    @patch("app.pipeline_runner.execute_story_generation_stage")
    @patch("app.pipeline_runner.execute_summarize_stage")
    @patch("app.pipeline_runner.execute_ingest_stage")
    def test_ingest_failure_stops_before_summarize(
        self, mock_ingest, mock_summarize, mock_story
    ):
        from app.pipeline_runner import StageResult

        mock_ingest.return_value = StageResult("ingest", False, {}, error="boom")

        out = run_pipeline(trigger="manual", from_stage=None)
        assert out["success"] is False
        assert len(out["stages"]) == 1
        mock_summarize.assert_not_called()
        mock_story.assert_not_called()

    @patch("app.pipeline_runner.execute_story_generation_stage")
    @patch("app.pipeline_runner.execute_summarize_stage")
    @patch("app.pipeline_runner.execute_ingest_stage")
    def test_summarize_failure_stops_before_story(
        self, mock_ingest, mock_summarize, mock_story
    ):
        from app.pipeline_runner import StageResult

        mock_ingest.return_value = StageResult(
            "ingest", True, {"articles_ingested": 1}, None
        )
        mock_summarize.return_value = StageResult(
            "summarize", False, {}, error="llm down"
        )

        out = run_pipeline(trigger="manual", from_stage=None)
        assert out["success"] is False
        assert len(out["stages"]) == 2
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

    @patch("app.pipeline_runner.execute_summarize_item_stage")
    def test_item_summarize_delegates(self, mock_summarize) -> None:
        """#328: targeted item replay also supports from_stage=summarize."""
        from app.pipeline_runner import StageResult

        mock_summarize.return_value = StageResult(
            "summarize", True, {"item_id": 1}, None
        )
        out = run_targeted_replay(
            target_type="item",
            target_id=1,
            from_stage="summarize",
            model="llama3.1:8b",
        )
        assert out["success"] is True
        assert len(out["stages"]) == 1
        mock_summarize.assert_called_once()

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


class TestExecuteSummarizeStage:
    """Tests for the bulk summarize+embed pipeline stage (#328)."""

    @patch("app.pipeline_runner.session_scope")
    @patch("app.llm.get_llm_service")
    @patch("app.pipeline_runner._insert_stage_start", return_value=1)
    @patch("app.pipeline_runner._finalize_stage_row")
    def test_no_articles_found(
        self, mock_finalize, mock_insert, mock_get_llm, mock_scope
    ) -> None:
        from app.pipeline_runner import execute_summarize_stage

        mock_session = MagicMock()
        mock_session.execute.return_value.all.return_value = []
        mock_scope.side_effect = lambda: nullcontext(mock_session)

        result = execute_summarize_stage(
            trigger="manual",
            run_group_id="g1",
            batch_size=10,
            model="m",
            max_workers=2,
        )

        assert result.success is True
        assert result.stats["articles_found"] == 0

    @patch("app.pipeline_runner.session_scope")
    @patch("app.processing_states.mark_article_failed")
    @patch("app.item_embeddings.maybe_embed_item_after_summary")
    @patch("app.llm.get_llm_service")
    @patch("app.pipeline_runner._insert_stage_start", return_value=1)
    @patch("app.pipeline_runner._finalize_stage_row")
    def test_success_and_failure_mixed(
        self,
        mock_finalize,
        mock_insert,
        mock_get_llm,
        mock_embed,
        mock_mark_failed,
        mock_scope,
    ) -> None:
        """One article summarizes successfully, one fails -- both counted, no crash."""
        from app.pipeline_runner import execute_summarize_stage

        mock_session = MagicMock()
        rows = [
            (1, "Title 1", "Content 1", "feed summary 1", None),
            (2, "Title 2", "Content 2", None, "hash2"),
        ]
        mock_session.execute.return_value.all.return_value = rows
        mock_scope.side_effect = lambda: nullcontext(mock_session)

        service = MagicMock()

        def summarize_article(*, title, content, model, use_structured):
            if title == "Title 1":
                return SimpleNamespace(
                    success=True,
                    summary="summary text",
                    model="m",
                    content_hash="h1",
                    structured_summary=None,
                    error=None,
                )
            return SimpleNamespace(
                success=False,
                summary=None,
                model="m",
                content_hash=None,
                structured_summary=None,
                error="LLM timeout",
            )

        service.summarize_article.side_effect = summarize_article
        mock_get_llm.return_value = service

        result = execute_summarize_stage(
            trigger="manual",
            run_group_id="g1",
            batch_size=10,
            model="m",
            max_workers=2,
        )

        assert result.success is True
        assert result.stats["articles_found"] == 2
        assert result.stats["summaries_generated"] == 1
        assert result.stats["errors"] == 1
        mock_embed.assert_called_once()
        mock_mark_failed.assert_called_once()
        assert mock_mark_failed.call_args.kwargs["failure_stage"] == "summarize"

    @patch("app.pipeline_runner.session_scope")
    @patch("app.processing_states.mark_article_failed")
    @patch("app.item_embeddings.maybe_embed_item_after_summary")
    @patch("app.llm.get_llm_service")
    @patch("app.pipeline_runner._insert_stage_start", return_value=1)
    @patch("app.pipeline_runner._finalize_stage_row")
    def test_worker_exception_counted_as_error(
        self,
        mock_finalize,
        mock_insert,
        mock_get_llm,
        mock_embed,
        mock_mark_failed,
        mock_scope,
    ) -> None:
        """An unhandled exception from summarize_article must not crash the batch."""
        from app.pipeline_runner import execute_summarize_stage

        mock_session = MagicMock()
        rows = [(1, "Title 1", "Content 1", None, None)]
        mock_session.execute.return_value.all.return_value = rows
        mock_scope.side_effect = lambda: nullcontext(mock_session)

        service = MagicMock()
        service.summarize_article.side_effect = RuntimeError("connection reset")
        mock_get_llm.return_value = service

        result = execute_summarize_stage(
            trigger="manual",
            run_group_id="g1",
            batch_size=10,
            model="m",
            max_workers=2,
        )

        assert result.success is True
        assert result.stats["errors"] == 1
        assert result.stats["summaries_generated"] == 0
        mock_embed.assert_not_called()
        mock_mark_failed.assert_called_once()

    @patch("app.pipeline_runner.session_scope")
    @patch("app.pipeline_runner._stage_retry_settings", return_value=(2, 1.0, 60.0))
    @patch("app.pipeline_runner._sleep_before_retry")
    @patch("app.pipeline_runner._insert_stage_start", return_value=1)
    @patch("app.pipeline_runner._finalize_stage_row")
    def test_stage_level_failure_retries_then_succeeds(
        self, mock_finalize, mock_insert, mock_sleep, mock_settings, mock_scope
    ) -> None:
        """A batch-level exception (e.g. DB down) triggers the stage retry/backoff."""
        from app.pipeline_runner import execute_summarize_stage

        mock_scope.side_effect = lambda: nullcontext(MagicMock())

        with patch(
            "app.pipeline_runner._run_summarize_batch",
            side_effect=[
                RuntimeError("db down"),
                RuntimeError("db still down"),
                {"articles_found": 0, "summaries_generated": 0, "errors": 0},
            ],
        ) as mock_batch:
            execute_summarize_stage(
                trigger="manual",
                run_group_id="g1",
                batch_size=10,
                model="m",
                max_workers=2,
            )

        assert mock_batch.call_count == 3
        assert mock_sleep.call_count == 2
        mock_finalize.assert_called_once()
        assert mock_finalize.call_args.kwargs["success"] is True
        assert mock_finalize.call_args.kwargs["attempts"] == 3


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
