"""Integration tests for app.semantic_dedup (#257, ADR-0026)."""

from __future__ import annotations

import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.orm_models import Item
from app.semantic_dedup import (
    get_semantic_dedupe_settings,
    is_semantic_dedupe_enabled,
    maybe_flag_semantic_duplicate,
)
from tests.pg_testutil import pg_session_truncate_story_graph


def _vec(seed: float, dims: int = 768) -> list[float]:
    """Deterministic vector; small seed deltas => near-1.0 cosine similarity."""
    return [seed + 0.0001 * i for i in range(dims)]


def _seed_feed(session) -> None:
    session.execute(
        text(
            "INSERT INTO feeds (id, url, name, disabled, health_score) "
            "VALUES (1, 'http://example.com/feed', 'Test Feed', 0, 100.0)"
        )
    )


def test_is_semantic_dedupe_enabled_env_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSBRIEF_SEMANTIC_DEDUPE_ENABLED", "false")
    assert is_semantic_dedupe_enabled() is False


def test_is_semantic_dedupe_enabled_default_on() -> None:
    assert is_semantic_dedupe_enabled() is True


def test_get_semantic_dedupe_settings_defaults() -> None:
    settings = get_semantic_dedupe_settings()
    assert settings["threshold"] == 0.92
    assert settings["window_days"] == 7
    assert settings["action"] == "flag"


class TestMaybeFlagSemanticDuplicate:
    def test_flags_high_similarity_recent_item(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            now = datetime.now(UTC)
            session.add_all(
                [
                    Item(
                        id=1,
                        feed_id=1,
                        title="Original report",
                        url="http://x/1",
                        url_hash="h1",
                        embedding=_vec(1.0),
                        published=now - timedelta(days=1),
                    ),
                    Item(
                        id=2,
                        feed_id=1,
                        title="Same story, different wording",
                        url="http://x/2",
                        url_hash="h2",
                        embedding=_vec(1.0001),
                        published=now,
                    ),
                ]
            )
            session.commit()

            maybe_flag_semantic_duplicate(session, 2)
            session.commit()

            refreshed = session.get(Item, 2)
            assert refreshed.duplicate_of_id == 1
            assert refreshed.duplicate_similarity > 0.99
            assert refreshed.duplicate_detection_method == "semantic"
        finally:
            session.close()

    def test_no_match_below_threshold_leaves_fields_unset(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            now = datetime.now(UTC)
            session.add_all(
                [
                    Item(
                        id=1,
                        feed_id=1,
                        title="Unrelated",
                        url="http://x/1",
                        url_hash="h1",
                        embedding=_vec(-1.0),
                        published=now - timedelta(days=1),
                    ),
                    Item(
                        id=2,
                        feed_id=1,
                        title="New article",
                        url="http://x/2",
                        url_hash="h2",
                        embedding=_vec(1.0),
                        published=now,
                    ),
                ]
            )
            session.commit()

            maybe_flag_semantic_duplicate(session, 2)
            session.commit()

            refreshed = session.get(Item, 2)
            assert refreshed.duplicate_of_id is None
            assert refreshed.duplicate_similarity is None
        finally:
            session.close()

    def test_excludes_items_outside_window(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            now = datetime.now(UTC)
            session.add_all(
                [
                    Item(
                        id=1,
                        feed_id=1,
                        title="Too old to count as recent duplicate",
                        url="http://x/1",
                        url_hash="h1",
                        embedding=_vec(1.0),
                        published=now - timedelta(days=30),
                    ),
                    Item(
                        id=2,
                        feed_id=1,
                        title="New article",
                        url="http://x/2",
                        url_hash="h2",
                        embedding=_vec(1.0001),
                        published=now,
                    ),
                ]
            )
            session.commit()

            maybe_flag_semantic_duplicate(session, 2)
            session.commit()

            refreshed = session.get(Item, 2)
            assert refreshed.duplicate_of_id is None
        finally:
            session.close()

    def test_item_without_embedding_is_noop(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            session.add(
                Item(
                    id=1,
                    feed_id=1,
                    title="No vector",
                    url="http://x/1",
                    url_hash="h1",
                )
            )
            session.commit()

            maybe_flag_semantic_duplicate(session, 1)
            session.commit()

            refreshed = session.get(Item, 1)
            assert refreshed.duplicate_of_id is None
        finally:
            session.close()

    def test_disabled_via_env_is_noop(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NEWSBRIEF_SEMANTIC_DEDUPE_ENABLED", "false")
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            now = datetime.now(UTC)
            session.add_all(
                [
                    Item(
                        id=1,
                        feed_id=1,
                        title="Original report",
                        url="http://x/1",
                        url_hash="h1",
                        embedding=_vec(1.0),
                        published=now - timedelta(days=1),
                    ),
                    Item(
                        id=2,
                        feed_id=1,
                        title="Same story, different wording",
                        url="http://x/2",
                        url_hash="h2",
                        embedding=_vec(1.0001),
                        published=now,
                    ),
                ]
            )
            session.commit()

            maybe_flag_semantic_duplicate(session, 2)
            session.commit()

            refreshed = session.get(Item, 2)
            assert refreshed.duplicate_of_id is None
        finally:
            session.close()
