"""Tests for ADR-0030 processing state transitions."""

from datetime import UTC, datetime

from app.processing_states import (
    ArticleProcessingState,
    StoryProcessingState,
    article_state_after_ingest,
    article_transition_allowed,
    coerce_article_state,
    coerce_story_state,
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
