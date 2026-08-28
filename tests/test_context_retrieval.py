"""Integration tests for app.context_retrieval (#279, ADR-0026)."""

from __future__ import annotations

import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from datetime import UTC, datetime, timedelta

from app.context_retrieval import (
    get_retrieval_hook_settings,
    is_retrieval_hook_enabled,
    retrieve_cluster_context,
    to_background_anchors,
)
from app.orm_models import Item, Story
from tests.pg_testutil import _seed_feed, _vec, pg_session_truncate_story_graph


def test_is_retrieval_hook_enabled_env_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSBRIEF_RETRIEVAL_HOOK_ENABLED", "false")
    assert is_retrieval_hook_enabled() is False


def test_is_retrieval_hook_enabled_default_on() -> None:
    assert is_retrieval_hook_enabled() is True


def test_get_retrieval_hook_settings_defaults() -> None:
    settings = get_retrieval_hook_settings()
    assert settings["threshold"] == 0.65
    assert settings["top_k"] == 5
    assert settings["window_days"] == 30


def test_to_background_anchors_shape() -> None:
    anchors = to_background_anchors(
        [
            {
                "story_id": 7,
                "title": "Prior story",
                "similarity": 0.8123,
                "published_at": "2026-01-01T00:00:00+00:00",
            }
        ]
    )
    assert anchors == [
        {
            "story_id": 7,
            "title": "Prior story",
            "similarity": 0.8123,
            "published_at": "2026-01-01T00:00:00+00:00",
            "kind": "background",
            "rationale": "Related prior coverage identified before synthesis "
            "(similarity 81%)",
        }
    ]


def test_to_background_anchors_empty() -> None:
    assert to_background_anchors([]) == []


class TestRetrieveClusterContext:
    def test_finds_related_story_above_threshold(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            now = datetime.now(UTC)
            session.add_all(
                [
                    Item(
                        id=1,
                        feed_id=1,
                        title="Cluster article",
                        url="http://x/1",
                        url_hash="h1",
                        embedding=_vec(1.0),
                    ),
                    Story(
                        id=1,
                        title="Earlier related story",
                        synthesis="x" * 60,
                        embedding=_vec(1.0001),
                        generated_at=now - timedelta(days=5),
                    ),
                ]
            )
            session.commit()

            results = retrieve_cluster_context(session, [1])
            assert len(results) == 1
            assert results[0].id == 1
            assert results[0].similarity > 0.5
        finally:
            session.close()

    def test_empty_when_no_matches(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            now = datetime.now(UTC)
            session.add_all(
                [
                    Item(
                        id=1,
                        feed_id=1,
                        title="Cluster article",
                        url="http://x/1",
                        url_hash="h1",
                        embedding=_vec(1.0),
                    ),
                    Story(
                        id=1,
                        title="Unrelated story",
                        synthesis="x" * 60,
                        embedding=_vec(-1.0),
                        generated_at=now - timedelta(days=5),
                    ),
                ]
            )
            session.commit()

            assert retrieve_cluster_context(session, [1]) == []
        finally:
            session.close()

    def test_empty_article_ids_returns_empty(self):
        session = pg_session_truncate_story_graph()
        try:
            assert retrieve_cluster_context(session, []) == []
        finally:
            session.close()

    def test_no_embedded_articles_returns_empty(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            session.add(
                Item(
                    id=1, feed_id=1, title="No vector", url="http://x/1", url_hash="h1"
                )
            )
            session.commit()
            assert retrieve_cluster_context(session, [1]) == []
        finally:
            session.close()

    def test_disabled_via_env_returns_empty(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NEWSBRIEF_RETRIEVAL_HOOK_ENABLED", "false")
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            now = datetime.now(UTC)
            session.add_all(
                [
                    Item(
                        id=1,
                        feed_id=1,
                        title="Cluster article",
                        url="http://x/1",
                        url_hash="h1",
                        embedding=_vec(1.0),
                    ),
                    Story(
                        id=1,
                        title="Earlier related story",
                        synthesis="x" * 60,
                        embedding=_vec(1.0001),
                        generated_at=now - timedelta(days=5),
                    ),
                ]
            )
            session.commit()

            assert retrieve_cluster_context(session, [1]) == []
        finally:
            session.close()

    def test_excludes_stories_outside_window(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            now = datetime.now(UTC)
            session.add_all(
                [
                    Item(
                        id=1,
                        feed_id=1,
                        title="Cluster article",
                        url="http://x/1",
                        url_hash="h1",
                        embedding=_vec(1.0),
                    ),
                    Story(
                        id=1,
                        title="Too old",
                        synthesis="x" * 60,
                        embedding=_vec(1.0001),
                        generated_at=now - timedelta(days=60),
                    ),
                ]
            )
            session.commit()

            assert retrieve_cluster_context(session, [1]) == []
        finally:
            session.close()
