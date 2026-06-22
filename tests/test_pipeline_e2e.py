"""
E2E tests for pipeline state transitions and recovery (#289).

Covers:
- Article state machine: full happy path (fetched → clustered)
- Article state machine: failure and retry/recovery
- Ingest idempotency: same url_hash → no duplicate row
- Dead-letter queue: failed articles and stories appear via list_failed_entities
- Dead-letter discard: clears failure and re-enters retry state
- Confidence gate: low score → story withheld (status='held')
- Confidence gate: mid score → story published with confidence_warning
- Confidence gate: high score → story published without warning

Uses real PostgreSQL (DATABASE_URL required). No mocks for DB layer.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from app.failed_entities import list_failed_entities
from app.processing_states import (
    ArticleProcessingState,
    StoryProcessingState,
    apply_article_processing_state,
    coerce_article_state,
    coerce_story_state,
    discard_article_failure,
    discard_story_failure,
    mark_article_failed,
    mark_story_failed,
)
from app.publish_gate import (
    GateDecision,
    evaluate_confidence,
    gate_result_to_story_fields,
)
from app.stories import Story, create_story, get_stories, link_articles_to_story
from tests.pg_testutil import pg_session_truncate_story_graph


@pytest.fixture(autouse=True)
def disable_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests offline — no Ollama calls."""
    monkeypatch.setenv("NEWSBRIEF_EMBEDDING_ENABLED", "0")


def _setup_db_with_articles(n: int = 5) -> object:
    """Truncate tables, seed one feed and n articles; return open session."""
    session = pg_session_truncate_story_graph()
    session.execute(
        text(
            "INSERT INTO feeds (id, url, name, disabled, health_score) "
            "VALUES (1, 'http://e2e.test/feed', 'E2E Feed', 0, 100.0)"
        )
    )
    for i in range(1, n + 1):
        session.execute(
            text(
                """
                INSERT INTO items (
                    id, feed_id, title, url, url_hash, summary,
                    topic, published, processing_state
                ) VALUES (
                    :id, 1, :title, :url, :url_hash, :summary,
                    'tech', :published, 'fetched'
                )
                """
            ),
            {
                "id": i,
                "title": f"E2E Article {i}",
                "url": f"http://e2e.test/article/{i}",
                "url_hash": f"e2e_hash_{i:04d}",
                "summary": f"Summary for E2E article {i}",
                "published": datetime.now(UTC) - timedelta(hours=i),
            },
        )
    session.commit()
    return session


def _get_processing_state(session, item_id: int) -> str | None:
    row = session.execute(
        text("SELECT processing_state FROM items WHERE id = :id"), {"id": item_id}
    ).first()
    return row[0] if row else None


def _get_story_row(session, story_id: int) -> dict | None:
    row = session.execute(
        text(
            "SELECT status, processing_state, confidence_warning, failure_stage "
            "FROM stories WHERE id = :id"
        ),
        {"id": story_id},
    ).first()
    if not row:
        return None
    return {
        "status": row[0],
        "processing_state": row[1],
        "confidence_warning": row[2],
        "failure_stage": row[3],
    }


# ---------------------------------------------------------------------------
# Article state machine — happy path
# ---------------------------------------------------------------------------


class TestArticleStateMachineHappyPath:
    """Article transitions from fetched → extracted → enriched → clustered."""

    def test_full_forward_path(self) -> None:
        session = _setup_db_with_articles()
        try:
            item_id = 1
            transitions = [
                ArticleProcessingState.EXTRACTED,
                ArticleProcessingState.ENRICHED,
                ArticleProcessingState.EMBEDDED,
                ArticleProcessingState.CLUSTERED,
            ]
            for state in transitions:
                result = apply_article_processing_state(
                    session, item_id, state, context="e2e_test"
                )
                assert result, f"Transition to {state.value} should succeed"
                assert _get_processing_state(session, item_id) == state.value

        finally:
            session.close()

    def test_skip_intermediate_stages(self) -> None:
        """fetched → enriched (skipping extracted) is allowed."""
        session = _setup_db_with_articles()
        try:
            result = apply_article_processing_state(
                session, 2, ArticleProcessingState.ENRICHED, context="e2e_skip"
            )
            assert result
            assert _get_processing_state(session, 2) == "enriched"
        finally:
            session.close()

    def test_idempotent_transition(self) -> None:
        """Applying the same state twice is a no-op, not an error."""
        session = _setup_db_with_articles()
        try:
            apply_article_processing_state(session, 3, ArticleProcessingState.EXTRACTED)
            result = apply_article_processing_state(
                session, 3, ArticleProcessingState.EXTRACTED
            )
            assert result
            assert _get_processing_state(session, 3) == "extracted"
        finally:
            session.close()

    def test_backward_transition_blocked(self) -> None:
        """Moving backward along the pipeline is rejected."""
        session = _setup_db_with_articles()
        try:
            apply_article_processing_state(session, 4, ArticleProcessingState.ENRICHED)
            result = apply_article_processing_state(
                session, 4, ArticleProcessingState.FETCHED
            )
            assert not result
            # State should not have changed
            assert _get_processing_state(session, 4) == "enriched"
        finally:
            session.close()


# ---------------------------------------------------------------------------
# Article failure and recovery
# ---------------------------------------------------------------------------


class TestArticleFailureAndRecovery:
    """Mark article failed; discard and re-enter pipeline."""

    def test_mark_failed_sets_state(self) -> None:
        session = _setup_db_with_articles()
        try:
            apply_article_processing_state(session, 1, ArticleProcessingState.ENRICHED)
            mark_article_failed(session, 1, "test failure", failure_stage="summarize")
            assert _get_processing_state(session, 1) == "failed"

            # Error fields should be populated
            row = session.execute(
                text(
                    "SELECT processing_error, failure_stage " "FROM items WHERE id = 1"
                )
            ).first()
            assert row[0] == "test failure"
            assert row[1] == "summarize"
        finally:
            session.close()

    def test_discard_clears_failure_and_re_enters(self) -> None:
        session = _setup_db_with_articles()
        try:
            mark_article_failed(session, 1, "transient error")

            result = discard_article_failure(
                session, 1, to_state=ArticleProcessingState.ENRICHED
            )
            assert result

            state = _get_processing_state(session, 1)
            assert state == "enriched", f"Expected enriched, got {state}"

            # Error fields should be cleared
            row = session.execute(
                text(
                    "SELECT processing_error, failure_stage, processing_failed_at "
                    "FROM items WHERE id = 1"
                )
            ).first()
            assert row[0] is None
            assert row[1] is None
            assert row[2] is None
        finally:
            session.close()

    def test_discard_from_non_failed_is_noop(self) -> None:
        """discard_article_failure on a non-failed item returns False."""
        session = _setup_db_with_articles()
        try:
            apply_article_processing_state(session, 2, ArticleProcessingState.ENRICHED)
            result = discard_article_failure(
                session, 2, to_state=ArticleProcessingState.ENRICHED
            )
            assert not result
            assert _get_processing_state(session, 2) == "enriched"
        finally:
            session.close()

    def test_forward_transition_after_recovery(self) -> None:
        """Article can continue forward after failure is discarded."""
        session = _setup_db_with_articles()
        try:
            mark_article_failed(session, 3, "recoverable error")
            discard_article_failure(
                session, 3, to_state=ArticleProcessingState.ENRICHED
            )
            result = apply_article_processing_state(
                session, 3, ArticleProcessingState.CLUSTERED
            )
            assert result
            assert _get_processing_state(session, 3) == "clustered"
        finally:
            session.close()


# ---------------------------------------------------------------------------
# Ingest idempotency
# ---------------------------------------------------------------------------


class TestIngestIdempotency:
    """Same url_hash must not create a duplicate row (ADR-0031)."""

    def test_duplicate_url_hash_is_rejected(self) -> None:
        session = _setup_db_with_articles(n=1)
        try:
            # First insert already done by _setup_db_with_articles (url_hash='e2e_hash_0001')
            initial_count = session.execute(
                text("SELECT COUNT(*) FROM items WHERE url_hash = 'e2e_hash_0001'")
            ).scalar()
            assert initial_count == 1

            # Attempt duplicate via ON CONFLICT DO NOTHING (mirrors feeds.py ingest)
            session.execute(
                text(
                    """
                    INSERT INTO items (
                        feed_id, title, url, url_hash, summary, published, processing_state
                    )
                    VALUES (1, 'Duplicate', 'http://e2e.test/dup', 'e2e_hash_0001',
                            'Dup summary', NOW(), 'fetched')
                    ON CONFLICT (url_hash) DO NOTHING
                    """
                )
            )
            session.commit()

            final_count = session.execute(
                text("SELECT COUNT(*) FROM items WHERE url_hash = 'e2e_hash_0001'")
            ).scalar()
            assert (
                final_count == 1
            ), f"Expected 1 row after duplicate insert, got {final_count}"
        finally:
            session.close()

    def test_different_url_hash_creates_new_row(self) -> None:
        session = _setup_db_with_articles(n=1)
        try:
            # Use explicit id=999 to avoid conflicting with the serial sequence
            # (sequence resets to 1 on TRUNCATE but explicit inserts don't advance it)
            session.execute(
                text(
                    """
                    INSERT INTO items (
                        id, feed_id, title, url, url_hash, summary, published, processing_state
                    )
                    VALUES (999, 1, 'New Article', 'http://e2e.test/new', 'e2e_hash_new_unique',
                            'New summary', NOW(), 'fetched')
                    ON CONFLICT (url_hash) DO NOTHING
                    """
                )
            )
            session.commit()
            count = session.execute(text("SELECT COUNT(*) FROM items")).scalar()
            assert count == 2
        finally:
            session.close()


# ---------------------------------------------------------------------------
# Dead-letter queue integration
# ---------------------------------------------------------------------------


class TestDeadLetterQueue:
    """Failed articles and stories appear in the admin dead-letter listing."""

    def test_failed_article_appears_in_dead_letter(self) -> None:
        session = _setup_db_with_articles()
        try:
            mark_article_failed(
                session,
                1,
                "synthesize timeout",
                failure_stage="story_generation",
            )
            session.commit()
        finally:
            session.close()

        result = list_failed_entities(limit_items=50, limit_stories=0)
        ids = [r["id"] for r in result["items"]]
        assert 1 in ids, f"Item 1 should be in dead-letter, got: {ids}"
        matching = next(r for r in result["items"] if r["id"] == 1)
        assert matching["failure_stage"] == "story_generation"

    def test_failed_story_appears_in_dead_letter(self) -> None:
        session = _setup_db_with_articles()
        try:
            story_id = create_story(
                session=session,
                title="Failing Story",
                synthesis="X" * 100,
                key_points=["A", "B", "C"],
                why_it_matters="Test",
                topics=["tech"],
                entities=["Test"],
                importance_score=0.5,
                freshness_score=0.5,
                model="test",
                time_window_start=datetime.now(UTC),
                time_window_end=datetime.now(UTC),
            )
            mark_story_failed(
                session,
                story_id,
                "synthesis error",
                failure_stage="story_generation",
            )
            session.commit()
        finally:
            session.close()

        result = list_failed_entities(limit_items=0, limit_stories=50)
        ids = [r["id"] for r in result["stories"]]
        assert story_id in ids, f"Story {story_id} should be in dead-letter"

    def test_discard_removes_article_from_dead_letter(self) -> None:
        session = _setup_db_with_articles()
        try:
            mark_article_failed(session, 2, "transient error")
            session.commit()
        finally:
            session.close()

        # Verify it's in the queue
        before = list_failed_entities(limit_items=50, limit_stories=0)
        assert any(r["id"] == 2 for r in before["items"])

        # Discard
        session2 = (
            _setup_db_with_articles.__wrapped__
            if hasattr(_setup_db_with_articles, "__wrapped__")
            else None
        )
        from app.db import SessionLocal

        session2 = SessionLocal()
        try:
            discard_article_failure(
                session2, 2, to_state=ArticleProcessingState.ENRICHED
            )
            session2.commit()
        finally:
            session2.close()

        after = list_failed_entities(limit_items=50, limit_stories=0)
        assert not any(
            r["id"] == 2 for r in after["items"]
        ), "Item 2 should be absent from dead-letter after discard"

    def test_confidence_gate_held_story_appears_in_dead_letter(self) -> None:
        """Held stories (confidence_gate failure_stage) show in dead-letter queue."""
        session = _setup_db_with_articles()
        try:
            story_id = create_story(
                session=session,
                title="Low Confidence Story",
                synthesis="Y" * 100,
                key_points=["A", "B", "C"],
                why_it_matters="Test",
                topics=["tech"],
                entities=["Test"],
                importance_score=0.5,
                freshness_score=0.5,
                model="test",
                time_window_start=datetime.now(UTC),
                time_window_end=datetime.now(UTC),
            )
            # Simulate what the publish gate does for HOLD decision
            session.execute(
                text(
                    """
                    UPDATE stories SET
                        status = 'held',
                        processing_state = 'failed',
                        failure_stage = 'confidence_gate',
                        confidence_score = 0.1
                    WHERE id = :id
                    """
                ),
                {"id": story_id},
            )
            session.commit()
        finally:
            session.close()

        result = list_failed_entities(limit_items=0, limit_stories=50)
        matching = [
            r for r in result["stories"] if r.get("failure_stage") == "confidence_gate"
        ]
        assert len(matching) >= 1, "Held story should appear in dead-letter queue"


# ---------------------------------------------------------------------------
# Confidence gate
# ---------------------------------------------------------------------------


class TestConfidenceGate:
    """Publish gate routes stories by confidence score."""

    def test_evaluate_hold_below_threshold(self) -> None:
        assert evaluate_confidence(0.1) == GateDecision.HOLD
        assert evaluate_confidence(0.39) == GateDecision.HOLD

    def test_evaluate_warn_between_thresholds(self) -> None:
        assert evaluate_confidence(0.4) == GateDecision.WARN
        assert evaluate_confidence(0.64) == GateDecision.WARN

    def test_evaluate_publish_above_warn_threshold(self) -> None:
        assert evaluate_confidence(0.65) == GateDecision.PUBLISH
        assert evaluate_confidence(1.0) == GateDecision.PUBLISH

    def test_evaluate_none_score_passes(self) -> None:
        """Missing confidence score must not block publishing."""
        assert evaluate_confidence(None) == GateDecision.PUBLISH

    def test_held_story_not_in_get_stories(self) -> None:
        """A story with status='held' must not appear in the public stories list."""
        session = _setup_db_with_articles()
        try:
            story_id = create_story(
                session=session,
                title="Held Story Should Not Appear",
                synthesis="Z" * 100,
                key_points=["A", "B", "C"],
                why_it_matters="Test",
                topics=["tech"],
                entities=["Test"],
                importance_score=0.5,
                freshness_score=0.5,
                model="test",
                time_window_start=datetime.now(UTC),
                time_window_end=datetime.now(UTC),
            )
            gate_fields = gate_result_to_story_fields(GateDecision.HOLD)
            session.execute(
                text(
                    """
                    UPDATE stories SET
                        status = :status,
                        processing_state = :ps,
                        confidence_score = 0.1,
                        failure_stage = :fs
                    WHERE id = :id
                    """
                ),
                {
                    "status": gate_fields["status"],
                    "ps": gate_fields["processing_state"],
                    "fs": gate_fields["failure_stage"],
                    "id": story_id,
                },
            )
            session.commit()

            stories = get_stories(session, status="active")
        finally:
            session.close()

        ids = [s.id for s in stories]
        assert (
            story_id not in ids
        ), f"Held story {story_id} must not appear in active stories list"

    def test_warned_story_appears_with_flag(self) -> None:
        """A warned story publishes with confidence_warning=True."""
        session = _setup_db_with_articles()
        try:
            story_id = create_story(
                session=session,
                title="Warned Story With Badge",
                synthesis="W" * 100,
                key_points=["A", "B", "C"],
                why_it_matters="Test",
                topics=["tech"],
                entities=["Test"],
                importance_score=0.5,
                freshness_score=0.5,
                model="test",
                time_window_start=datetime.now(UTC),
                time_window_end=datetime.now(UTC),
            )
            gate_fields = gate_result_to_story_fields(GateDecision.WARN)
            session.execute(
                text(
                    """
                    UPDATE stories SET
                        status = :status,
                        processing_state = :ps,
                        confidence_warning = TRUE,
                        confidence_score = 0.5
                    WHERE id = :id
                    """
                ),
                {
                    "status": gate_fields["status"],
                    "ps": gate_fields["processing_state"],
                    "id": story_id,
                },
            )
            session.commit()

            row = _get_story_row(session, story_id)
        finally:
            session.close()

        assert row is not None
        assert row["status"] == "active"
        assert row["confidence_warning"] is True

    def test_published_story_has_no_warning(self) -> None:
        """A high-confidence story publishes without the warning flag."""
        session = _setup_db_with_articles()
        try:
            story_id = create_story(
                session=session,
                title="High Confidence Story",
                synthesis="V" * 100,
                key_points=["A", "B", "C"],
                why_it_matters="Test",
                topics=["tech"],
                entities=["Test"],
                importance_score=0.9,
                freshness_score=0.9,
                model="test",
                time_window_start=datetime.now(UTC),
                time_window_end=datetime.now(UTC),
            )
            gate_fields = gate_result_to_story_fields(GateDecision.PUBLISH)
            session.execute(
                text(
                    """
                    UPDATE stories SET
                        status = :status,
                        processing_state = :ps,
                        confidence_warning = FALSE,
                        confidence_score = 0.85
                    WHERE id = :id
                    """
                ),
                {
                    "status": gate_fields["status"],
                    "ps": gate_fields["processing_state"],
                    "id": story_id,
                },
            )
            session.commit()

            row = _get_story_row(session, story_id)
        finally:
            session.close()

        assert row is not None
        assert row["status"] == "active"
        assert not row["confidence_warning"]

    def test_gate_fields_for_all_decisions(self) -> None:
        """gate_result_to_story_fields returns correct values for each decision."""
        hold = gate_result_to_story_fields(GateDecision.HOLD)
        assert hold["status"] == "held"
        assert hold["processing_state"] == StoryProcessingState.FAILED.value
        assert hold["failure_stage"] == "confidence_gate"
        assert not hold["confidence_warning"]

        warn = gate_result_to_story_fields(GateDecision.WARN)
        assert warn["status"] == "active"
        assert warn["processing_state"] == StoryProcessingState.PUBLISHED.value
        assert warn["confidence_warning"] is True
        assert warn["failure_stage"] is None

        publish = gate_result_to_story_fields(GateDecision.PUBLISH)
        assert publish["status"] == "active"
        assert publish["processing_state"] == StoryProcessingState.PUBLISHED.value
        assert not publish["confidence_warning"]
        assert publish["failure_stage"] is None
