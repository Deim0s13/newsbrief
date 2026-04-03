"""Tests for ADR-0030 processing state transitions."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.processing_states import (
    ArticleProcessingState,
    StoryProcessingState,
    apply_story_processing_state,
    article_state_after_ingest,
    article_transition_allowed,
    coerce_article_state,
    coerce_story_state,
    discard_article_failure,
    discard_story_failure,
    mark_article_failed,
    mark_story_failed,
    story_transition_allowed,
)


class TestArticleTransitions:
    def test_idempotent(self) -> None:
        assert article_transition_allowed(
            ArticleProcessingState.FETCHED, ArticleProcessingState.FETCHED
        )

    def test_forward_step(self) -> None:
        assert article_transition_allowed(
            ArticleProcessingState.FETCHED, ArticleProcessingState.EXTRACTED
        )

    def test_forward_skip(self) -> None:
        assert article_transition_allowed(
            ArticleProcessingState.FETCHED, ArticleProcessingState.ENRICHED
        )

    def test_to_failed_from_any(self) -> None:
        assert article_transition_allowed(
            ArticleProcessingState.EXTRACTED, ArticleProcessingState.FAILED
        )

    def test_backward_disallowed(self) -> None:
        assert not article_transition_allowed(
            ArticleProcessingState.ENRICHED, ArticleProcessingState.FETCHED
        )

    def test_failed_retry(self) -> None:
        assert article_transition_allowed(
            ArticleProcessingState.FAILED, ArticleProcessingState.EXTRACTED
        )
        assert not article_transition_allowed(
            ArticleProcessingState.FAILED, ArticleProcessingState.CLUSTERED
        )


class TestStoryTransitions:
    def test_idempotent(self) -> None:
        assert story_transition_allowed(
            StoryProcessingState.SYNTHESIZING, StoryProcessingState.SYNTHESIZING
        )

    def test_forward_and_skip_optional_stages(self) -> None:
        assert story_transition_allowed(
            StoryProcessingState.CANDIDATE, StoryProcessingState.SYNTHESIZING
        )
        assert story_transition_allowed(
            StoryProcessingState.SYNTHESIZING, StoryProcessingState.PUBLISHED
        )

    def test_published_to_archived(self) -> None:
        assert story_transition_allowed(
            StoryProcessingState.PUBLISHED, StoryProcessingState.ARCHIVED
        )

    def test_archived_idempotent(self) -> None:
        assert story_transition_allowed(
            StoryProcessingState.ARCHIVED, StoryProcessingState.ARCHIVED
        )

    def test_candidate_to_archived_invalid(self) -> None:
        assert not story_transition_allowed(
            StoryProcessingState.CANDIDATE, StoryProcessingState.ARCHIVED
        )

    def test_to_failed(self) -> None:
        assert story_transition_allowed(
            StoryProcessingState.SYNTHESIZING, StoryProcessingState.FAILED
        )

    def test_failed_retry(self) -> None:
        assert story_transition_allowed(
            StoryProcessingState.FAILED, StoryProcessingState.SYNTHESIZING
        )


class TestArticleStateAfterIngest:
    def test_failed(self) -> None:
        assert (
            article_state_after_ingest("failed", None, None)
            == ArticleProcessingState.FAILED
        )

    def test_blocked(self) -> None:
        assert (
            article_state_after_ingest("blocked", None, None)
            == ArticleProcessingState.FETCHED
        )

    def test_extracted_with_body(self) -> None:
        now = datetime.now(UTC)
        assert (
            article_state_after_ingest("readability", now, "paragraph")
            == ArticleProcessingState.EXTRACTED
        )

    def test_none_method_is_fetched(self) -> None:
        assert (
            article_state_after_ingest("none", None, None)
            == ArticleProcessingState.FETCHED
        )

    def test_whitespace_body_not_extracted(self) -> None:
        now = datetime.now(UTC)
        assert (
            article_state_after_ingest("readability", now, "  \n  ")
            == ArticleProcessingState.FETCHED
        )


class TestCoerce:
    def test_coerce_article(self) -> None:
        assert coerce_article_state("fetched") == ArticleProcessingState.FETCHED
        assert coerce_article_state(None) is None
        assert coerce_article_state("nope") is None

    def test_coerce_story(self) -> None:
        assert coerce_story_state("published") == StoryProcessingState.PUBLISHED
        assert coerce_story_state("") is None


class TestEntityFailureHelpers:
    """#293 M1: mark_failed / discard with mocked SQL session."""

    def test_mark_article_failed_runs_update(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            MagicMock(first=MagicMock(return_value=("enriched",))),
            MagicMock(),
        ]
        assert mark_article_failed(
            session,
            42,
            "boom",
            failure_stage="story_generation",
            run_group_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        )
        assert session.execute.call_count == 2

    def test_discard_article_failure_requires_failed(self) -> None:
        session = MagicMock()
        session.execute.return_value = MagicMock(
            first=MagicMock(return_value=("enriched",))
        )
        assert not discard_article_failure(session, 1)

    def test_discard_story_failure_success(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            MagicMock(first=MagicMock(return_value=("failed",))),
            MagicMock(),
        ]
        assert discard_story_failure(session, 99)
        assert session.execute.call_count == 2

    def test_apply_story_processing_state_clears_failure_when_leaving_failed(
        self,
    ) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            MagicMock(first=MagicMock(return_value=("failed",))),
            MagicMock(),
        ]
        assert apply_story_processing_state(session, 7, StoryProcessingState.CANDIDATE)
        second_sql = session.execute.call_args_list[1][0][0].text
        assert "processing_error = NULL" in second_sql
