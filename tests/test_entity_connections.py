"""Integration tests for app.entity_connections (#202, ADR-0023, v0.9.0)."""

from __future__ import annotations

import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.entity_connections import find_entity_connected_stories
from tests.pg_testutil import (
    create_test_story,
    pg_session_truncate_entity_graph,
    seed_default_feed,
)


def _make_story(session, title: str, generated_at: datetime) -> int:
    return create_test_story(
        session,
        title=title,
        synthesis="synthesis text",
        key_points=["point"],
        why_it_matters="matters",
        topics=["tech"],
        entities=[],
        importance_score=0.5,
        freshness_score=0.5,
        model="test-model",
        time_window_start=generated_at - timedelta(hours=1),
        time_window_end=generated_at,
        first_seen=generated_at,
    )


def _make_article(session, article_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO items (id, feed_id, title, url, url_hash, published)
            VALUES (:id, 1, :title, :url, :hash, NOW())
            """
        ),
        {
            "id": article_id,
            "title": f"Article {article_id}",
            "url": f"http://x/{article_id}",
            "hash": f"h{article_id}",
        },
    )


def _make_entity(
    session, entity_id: int, name: str, entity_type: str = "company"
) -> None:
    session.execute(
        text(
            "INSERT INTO entities (id, canonical_name, entity_type) "
            "VALUES (:id, :name, :etype)"
        ),
        {"id": entity_id, "name": name, "etype": entity_type},
    )


def _make_mention(
    session,
    entity_id: int,
    article_id: int,
    story_id: int,
    prominence: float = 0.8,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO entity_mentions (entity_id, article_id, story_id, prominence_score)
            VALUES (:eid, :aid, :sid, :prom)
            """
        ),
        {"eid": entity_id, "aid": article_id, "sid": story_id, "prom": prominence},
    )


class TestFindEntityConnectedStories:
    def test_ranks_by_shared_count_then_score(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            now = datetime.now(UTC)

            source_id = _make_story(session, "Source Story", now)
            strong_id = _make_story(session, "Strong Match (2 shared)", now)
            weak_id = _make_story(session, "Weak Match (1 shared)", now)
            strongest_id = _make_story(
                session,
                "Strongest Match (3 shared, far in time)",
                now - timedelta(days=60),
            )
            session.commit()

            for i in range(1, 9):
                _make_article(session, i)
            _make_entity(session, 1, "CompanyA")
            _make_entity(session, 2, "CompanyB")
            _make_entity(session, 3, "CompanyC")
            session.commit()

            # Source story mentions A, B, C.
            _make_mention(session, 1, 1, source_id)
            _make_mention(session, 2, 2, source_id)
            _make_mention(session, 3, 3, source_id)
            # Strong match shares A, B.
            _make_mention(session, 1, 4, strong_id)
            _make_mention(session, 2, 5, strong_id)
            # Weak match shares only A.
            _make_mention(session, 1, 6, weak_id)
            # Strongest match shares A, B, C but is temporally distant.
            _make_mention(session, 1, 7, strongest_id)
            _make_mention(session, 2, 8, strongest_id)
            _make_mention(session, 3, 8, strongest_id)
            session.commit()

            results = find_entity_connected_stories(session, source_id, top_k=10)

            ids_in_order = [r.story_id for r in results]
            assert ids_in_order == [strongest_id, strong_id, weak_id]

            strongest = next(r for r in results if r.story_id == strongest_id)
            strong = next(r for r in results if r.story_id == strong_id)
            weak = next(r for r in results if r.story_id == weak_id)

            assert strongest.shared_entity_count == 3
            assert strongest.strength == "strong"
            assert strong.shared_entity_count == 2
            assert strong.strength == "strong"
            assert weak.shared_entity_count == 1
            assert weak.strength == "weak"

            weak_names = {e.canonical_name for e in weak.shared_entities}
            assert weak_names == {"CompanyA"}
        finally:
            session.close()

    def test_min_shared_entities_filters_weak_matches(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            now = datetime.now(UTC)
            source_id = _make_story(session, "Source", now)
            weak_id = _make_story(session, "Weak", now)
            session.commit()

            for i in range(1, 3):
                _make_article(session, i)
            _make_entity(session, 1, "SoloCo")
            session.commit()

            _make_mention(session, 1, 1, source_id)
            _make_mention(session, 1, 2, weak_id)
            session.commit()

            results = find_entity_connected_stories(
                session, source_id, min_shared_entities=2
            )
            assert results == []

            results_default = find_entity_connected_stories(session, source_id)
            assert len(results_default) == 1
        finally:
            session.close()

    def test_no_mentions_returns_empty(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            story_id = _make_story(session, "Lonely Story", datetime.now(UTC))
            session.commit()

            assert find_entity_connected_stories(session, story_id) == []
        finally:
            session.close()

    def test_unknown_story_returns_empty(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            session.commit()
            assert find_entity_connected_stories(session, 999) == []
        finally:
            session.close()
