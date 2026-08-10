"""Integration tests for app.light_rag (#259, ADR-0026)."""

from __future__ import annotations

import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.light_rag import (
    SynthesisAnchor,
    compute_cluster_embedding,
    format_anchor_prompt_block,
    get_light_rag_settings,
    is_light_rag_enabled,
    select_synthesis_anchors,
)
from app.orm_models import Item, Story
from tests.pg_testutil import pg_session_truncate_story_graph


def _vec(seed: float, dims: int = 768) -> list[float]:
    return [seed + 0.0001 * i for i in range(dims)]


def _seed_feed(session) -> None:
    session.execute(
        text(
            "INSERT INTO feeds (id, url, name, disabled, health_score) "
            "VALUES (1, 'http://example.com/feed', 'Test Feed', 0, 100.0)"
        )
    )


def test_is_light_rag_enabled_env_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSBRIEF_LIGHT_RAG_ENABLED", "false")
    assert is_light_rag_enabled() is False


def test_is_light_rag_enabled_default_on() -> None:
    assert is_light_rag_enabled() is True


def test_get_light_rag_settings_defaults() -> None:
    settings = get_light_rag_settings()
    assert settings["threshold"] == 0.78
    assert settings["max_anchors"] == 3
    assert settings["window_days"] == 30


def test_format_anchor_prompt_block_empty() -> None:
    assert format_anchor_prompt_block([]) == ""


def test_format_anchor_prompt_block_with_anchors() -> None:
    anchors = [
        SynthesisAnchor(
            story_id=1,
            title="Prior coverage",
            key_point="Something happened",
            similarity=0.85,
            date=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    block = format_anchor_prompt_block(anchors)
    assert "## Historical Context" in block
    assert "Prior coverage" in block
    assert "2026-01-01" in block


class TestComputeClusterEmbedding:
    def test_averages_embedded_articles(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            session.add_all(
                [
                    Item(
                        id=1,
                        feed_id=1,
                        title="A",
                        url="http://x/1",
                        url_hash="h1",
                        embedding=[1.0] * 768,
                    ),
                    Item(
                        id=2,
                        feed_id=1,
                        title="B",
                        url="http://x/2",
                        url_hash="h2",
                        embedding=[3.0] * 768,
                    ),
                ]
            )
            session.commit()

            avg = compute_cluster_embedding(session, [1, 2])
            assert avg is not None
            assert abs(avg[0] - 2.0) < 1e-9
        finally:
            session.close()

    def test_none_when_no_embeddings(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            session.add(
                Item(id=1, feed_id=1, title="A", url="http://x/1", url_hash="h1")
            )
            session.commit()
            assert compute_cluster_embedding(session, [1]) is None
        finally:
            session.close()

    def test_empty_article_ids_returns_none(self):
        session = pg_session_truncate_story_graph()
        try:
            assert compute_cluster_embedding(session, []) is None
        finally:
            session.close()


class TestSelectSynthesisAnchors:
    def test_returns_anchor_above_threshold(self):
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
                        key_points_json=json.dumps(["Key fact one"]),
                        embedding=_vec(1.0001),
                        generated_at=now - timedelta(days=5),
                    ),
                ]
            )
            session.commit()

            anchors = select_synthesis_anchors(session, [1])
            assert len(anchors) == 1
            assert anchors[0].story_id == 1
            assert anchors[0].key_point == "Key fact one"
            assert anchors[0].similarity > 0.5
        finally:
            session.close()

    def test_no_anchors_below_threshold(self):
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

            anchors = select_synthesis_anchors(session, [1])
            assert anchors == []
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
            assert select_synthesis_anchors(session, [1]) == []
        finally:
            session.close()

    def test_disabled_via_env_returns_empty(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NEWSBRIEF_LIGHT_RAG_ENABLED", "false")
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

            assert select_synthesis_anchors(session, [1]) == []
        finally:
            session.close()
