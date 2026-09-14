"""Tests for app.data_trends (#213 reduced scope, ADR-0023, v0.9.3)."""

from __future__ import annotations

import os

import pytest

from app.data_trends import find_data_changes, find_data_conflicts


def _point(id_, article_id, data_type, value, context, unit=None):
    return {
        "id": id_,
        "article_id": article_id,
        "data_type": data_type,
        "value": value,
        "unit": unit,
        "context": context,
        "confidence_score": 0.8,
        "created_at": None,
    }


class TestFindDataConflicts:
    def test_no_points_no_conflicts(self):
        assert find_data_conflicts([]) == []

    def test_single_point_no_conflict(self):
        points = [_point(1, 10, "statistic", "3.4%", "unemployment rate fell")]
        assert find_data_conflicts(points) == []

    def test_same_value_is_not_a_conflict(self):
        """Two articles reporting the SAME figure is corroboration, not a
        conflict."""
        points = [
            _point(1, 10, "statistic", "3.4%", "unemployment rate fell to 3.4%"),
            _point(2, 20, "statistic", "3.4%", "unemployment rate at 3.4%"),
        ]
        assert find_data_conflicts(points) == []

    def test_same_article_different_value_is_not_a_conflict(self):
        """A conflict needs two DIFFERENT articles -- one article citing two
        related-but-distinct figures isn't a source disagreement."""
        points = [
            _point(1, 10, "statistic", "3.4%", "unemployment rate fell"),
            _point(2, 10, "statistic", "4.1%", "unemployment rate context"),
        ]
        assert find_data_conflicts(points) == []

    def test_different_articles_same_subject_different_value_is_conflict(self):
        points = [
            _point(1, 10, "statistic", "3.4%", "the unemployment rate fell sharply"),
            _point(2, 20, "statistic", "4.1%", "the unemployment rate rose sharply"),
        ]
        conflicts = find_data_conflicts(points)
        assert len(conflicts) == 1
        assert conflicts[0]["data_type"] == "statistic"
        values = {v["value"] for v in conflicts[0]["reported_values"]}
        assert values == {"3.4%", "4.1%"}

    def test_unrelated_subjects_not_flagged(self):
        points = [
            _point(1, 10, "statistic", "3.4%", "unemployment rate in the economy"),
            _point(2, 20, "statistic", "70%", "electric vehicle sales growth"),
        ]
        assert find_data_conflicts(points) == []

    def test_quote_and_claim_types_never_flagged(self):
        points = [
            _point(1, 10, "quote", "It was great", "speaker context words shared"),
            _point(2, 20, "quote", "It was terrible", "speaker context words shared"),
        ]
        assert find_data_conflicts(points) == []

    def test_missing_context_never_flagged(self):
        points = [
            _point(1, 10, "statistic", "3.4%", None),
            _point(2, 20, "statistic", "4.1%", None),
        ]
        assert find_data_conflicts(points) == []

    def test_each_point_used_at_most_once(self):
        """A point already placed in a conflict group isn't reused in a
        second group."""
        points = [
            _point(1, 10, "statistic", "3.4%", "unemployment rate fell sharply"),
            _point(2, 20, "statistic", "4.1%", "unemployment rate rose sharply"),
            _point(3, 30, "statistic", "5.0%", "unemployment rate climbed sharply"),
        ]
        conflicts = find_data_conflicts(points)
        assert len(conflicts) == 1
        assert len(conflicts[0]["reported_values"]) == 3


class TestFindDataChanges:
    def test_no_continuation_returns_empty(self):
        assert find_data_changes(object(), 1, None) == []  # type: ignore[arg-type]


# --- DB integration test (needs get_extracted_data_for_story) ---------------

if not os.environ.get("DATABASE_URL"):
    pytest.skip(
        "PostgreSQL required for DB integration test below (set DATABASE_URL)",
        allow_module_level=True,
    )

from datetime import UTC, datetime  # noqa: E402

from app.data_extraction import store_extracted_data  # noqa: E402
from app.llm_output import ExtractedDataItem  # noqa: E402
from app.orm_models import Feed, Item  # noqa: E402
from tests.pg_testutil import (  # noqa: E402
    create_test_story,
    link_test_articles_to_story,
    pg_session_truncate_story_graph,
)


def _seed_feed(session, feed_id: int = 1) -> None:
    session.add(Feed(id=feed_id, url=f"http://example.com/feed{feed_id}", name="F"))
    session.commit()


def _seed_item(session, item_id: int, feed_id: int) -> None:
    session.add(
        Item(
            id=item_id,
            feed_id=feed_id,
            title=f"Article {item_id}",
            url=f"http://example.com/a{item_id}",
            # Namespaced (not the bare "hash1"/"hash2" convention some
            # other test files use) -- this class's last test doesn't
            # delete its rows the way test_data_extraction.py's cascade
            # test does, so a plain "hash2" leftover here previously
            # collided with test_entities.py's hardcoded "hash2" literal
            # later in the same suite run.
            url_hash=f"trends-hash-{item_id}",
        )
    )
    session.commit()


def _cleanup_and_close(session) -> None:
    """Leave a clean items/stories table behind -- see _seed_item docstring."""
    from sqlalchemy import text as _text

    session.execute(
        _text("TRUNCATE story_articles, stories, items, feeds RESTART IDENTITY CASCADE")
    )
    session.commit()
    session.close()


class TestFindDataChangesAcrossContinuation:
    def test_matches_same_subject_different_value(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            _seed_item(session, 1, 1)
            _seed_item(session, 2, 1)

            now = datetime.now(UTC)
            prev_story_id = create_test_story(
                session,
                title="Previous",
                synthesis="x" * 60,
                key_points=[],
                why_it_matters="",
                topics=[],
                entities=[],
                importance_score=0.5,
                freshness_score=0.5,
                model="m",
                time_window_start=now,
                time_window_end=now,
            )
            link_test_articles_to_story(
                session, prev_story_id, [1], primary_article_id=1
            )
            store_extracted_data(
                session,
                1,
                [
                    ExtractedDataItem(
                        data_type="statistic",
                        value="3.1%",
                        context="the unemployment rate held steady",
                        confidence=0.8,
                    )
                ],
            )

            current_story_id = create_test_story(
                session,
                title="Current",
                synthesis="y" * 60,
                key_points=[],
                why_it_matters="",
                topics=[],
                entities=[],
                importance_score=0.5,
                freshness_score=0.5,
                model="m",
                time_window_start=now,
                time_window_end=now,
            )
            link_test_articles_to_story(
                session, current_story_id, [2], primary_article_id=2
            )
            store_extracted_data(
                session,
                2,
                [
                    ExtractedDataItem(
                        data_type="statistic",
                        value="3.4%",
                        context="the unemployment rate rose",
                        confidence=0.8,
                    )
                ],
            )

            changes = find_data_changes(session, current_story_id, prev_story_id)
            assert len(changes) == 1
            assert changes[0]["previous_value"] == "3.1%"
            assert changes[0]["current_value"] == "3.4%"
        finally:
            _cleanup_and_close(session)

    def test_no_change_when_value_unchanged(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            _seed_item(session, 1, 1)
            _seed_item(session, 2, 1)
            now = datetime.now(UTC)

            prev_story_id = create_test_story(
                session,
                title="Previous",
                synthesis="x" * 60,
                key_points=[],
                why_it_matters="",
                topics=[],
                entities=[],
                importance_score=0.5,
                freshness_score=0.5,
                model="m",
                time_window_start=now,
                time_window_end=now,
            )
            link_test_articles_to_story(
                session, prev_story_id, [1], primary_article_id=1
            )
            store_extracted_data(
                session,
                1,
                [
                    ExtractedDataItem(
                        data_type="statistic",
                        value="3.4%",
                        context="the unemployment rate held steady",
                        confidence=0.8,
                    )
                ],
            )

            current_story_id = create_test_story(
                session,
                title="Current",
                synthesis="y" * 60,
                key_points=[],
                why_it_matters="",
                topics=[],
                entities=[],
                importance_score=0.5,
                freshness_score=0.5,
                model="m",
                time_window_start=now,
                time_window_end=now,
            )
            link_test_articles_to_story(
                session, current_story_id, [2], primary_article_id=2
            )
            store_extracted_data(
                session,
                2,
                [
                    ExtractedDataItem(
                        data_type="statistic",
                        value="3.4%",
                        context="the unemployment rate remains steady",
                        confidence=0.8,
                    )
                ],
            )

            assert find_data_changes(session, current_story_id, prev_story_id) == []
        finally:
            _cleanup_and_close(session)
