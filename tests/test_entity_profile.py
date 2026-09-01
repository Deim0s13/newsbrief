"""Integration tests for app.entity_profile (#201, ADR-0023, v0.9.0)."""

from __future__ import annotations

import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.entity_profile import get_entity_profile, search_entities
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


def _make_article(session, article_id: int, title: str = None) -> None:
    session.execute(
        text(
            """
            INSERT INTO items (id, feed_id, title, url, url_hash, published)
            VALUES (:id, 1, :title, :url, :hash, NOW())
            """
        ),
        {
            "id": article_id,
            "title": title or f"Article {article_id}",
            "url": f"http://x/{article_id}",
            "hash": f"h{article_id}",
        },
    )


def _make_entity(
    session,
    entity_id: int,
    name: str,
    entity_type: str = "company",
    aliases: list | None = None,
    mention_count: int = 0,
) -> None:
    session.execute(
        text(
            "INSERT INTO entities (id, canonical_name, entity_type, aliases, mention_count) "
            "VALUES (:id, :name, :etype, :aliases, :mc)"
        ),
        {
            "id": entity_id,
            "name": name,
            "etype": entity_type,
            "aliases": __import__("json").dumps(aliases or []),
            "mc": mention_count,
        },
    )


def _make_mention(
    session,
    entity_id: int,
    article_id: int,
    story_id: int | None = None,
    prominence: float = 0.8,
    mentioned_at: datetime | None = None,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO entity_mentions
                (entity_id, article_id, story_id, prominence_score, mentioned_at)
            VALUES (:eid, :aid, :sid, :prom, COALESCE(:mentioned_at, NOW()))
            """
        ),
        {
            "eid": entity_id,
            "aid": article_id,
            "sid": story_id,
            "prom": prominence,
            "mentioned_at": mentioned_at,
        },
    )


class TestGetEntityProfile:
    def test_unknown_entity_returns_none(self):
        session = pg_session_truncate_entity_graph()
        try:
            assert get_entity_profile(session, 999) is None
        finally:
            session.close()

    def test_basic_profile_fields(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            _make_entity(
                session, 1, "OpenAI", "company", aliases=["Open AI"], mention_count=3
            )
            session.commit()

            profile = get_entity_profile(session, 1)
            assert profile is not None
            assert profile.canonical_name == "OpenAI"
            assert profile.entity_type == "company"
            assert profile.aliases == ["Open AI"]
            assert profile.mention_count == 3
        finally:
            session.close()

    def test_timeline_ordered_most_recent_first(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            now = datetime.now(UTC)
            story_id = _make_story(session, "A Story", now)
            session.commit()

            _make_article(session, 1, "Old Article")
            _make_article(session, 2, "New Article")
            _make_entity(session, 1, "OpenAI")
            session.commit()

            _make_mention(session, 1, 1, story_id, mentioned_at=now - timedelta(days=5))
            _make_mention(session, 1, 2, story_id, mentioned_at=now)
            session.commit()

            profile = get_entity_profile(session, 1)
            assert [t.article_title for t in profile.timeline] == [
                "New Article",
                "Old Article",
            ]
            assert profile.timeline[0].story_id == story_id
        finally:
            session.close()

    def test_co_mentioned_entities_ranked_by_count(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            for i in range(1, 4):
                _make_article(session, i)
            _make_entity(session, 1, "OpenAI")
            _make_entity(session, 2, "Sam Altman")
            _make_entity(session, 3, "Microsoft")
            session.commit()

            # OpenAI + Sam Altman co-occur twice; OpenAI + Microsoft once.
            _make_mention(session, 1, 1)
            _make_mention(session, 2, 1)
            _make_mention(session, 1, 2)
            _make_mention(session, 2, 2)
            _make_mention(session, 1, 3)
            _make_mention(session, 3, 3)
            session.commit()

            profile = get_entity_profile(session, 1)
            names_in_order = [c.canonical_name for c in profile.co_mentioned]
            assert names_in_order == ["Sam Altman", "Microsoft"]
            assert profile.co_mentioned[0].co_mention_count == 2
            assert profile.co_mentioned[1].co_mention_count == 1
        finally:
            session.close()


class TestSearchEntities:
    def test_matches_canonical_name_case_insensitive(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            _make_entity(session, 1, "OpenAI", mention_count=5)
            _make_entity(session, 2, "Microsoft", mention_count=2)
            session.commit()

            results = search_entities(session, "openai")
            assert len(results) == 1
            assert results[0].canonical_name == "OpenAI"
        finally:
            session.close()

    def test_matches_alias(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            _make_entity(session, 1, "OpenAI", aliases=["GPT maker"], mention_count=5)
            session.commit()

            results = search_entities(session, "GPT maker")
            assert len(results) == 1
            assert results[0].id == 1
        finally:
            session.close()

    def test_empty_query_returns_top_mentioned(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            _make_entity(session, 1, "Low", mention_count=1)
            _make_entity(session, 2, "High", mention_count=10)
            session.commit()

            results = search_entities(session, "")
            assert [r.canonical_name for r in results] == ["High", "Low"]
        finally:
            session.close()

    def test_entity_type_filter(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            _make_entity(session, 1, "OpenAI", entity_type="company")
            _make_entity(session, 2, "Sam Altman", entity_type="person")
            session.commit()

            results = search_entities(session, "", entity_type="person")
            assert [r.canonical_name for r in results] == ["Sam Altman"]
        finally:
            session.close()

    def test_no_match_returns_empty(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            _make_entity(session, 1, "OpenAI")
            session.commit()

            assert search_entities(session, "nonexistent-entity-xyz") == []
        finally:
            session.close()
