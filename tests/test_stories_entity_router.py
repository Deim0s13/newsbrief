"""Router-level tests for entity-based story connections/filtering (#202, v0.9.0)."""

from __future__ import annotations

import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import text
from starlette.testclient import TestClient

from app.routers.stories import router
from tests.pg_testutil import (
    create_test_story,
    link_test_articles_to_story,
    pg_session_truncate_entity_graph,
    seed_default_feed,
)

LONG_TITLE = "A Sufficiently Long Story Title For Validation"
LONG_SYNTHESIS = (
    "This is a synthesis body long enough to satisfy the StoryOut model's "
    "minimum-length validator for testing purposes."
)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def two_connected_stories():
    """Two stories sharing entity id=1 (OpenAI) and id=2 (GPT-5)."""
    session = pg_session_truncate_entity_graph()
    seed_default_feed(session)
    now = datetime.now(UTC)

    story_a = create_test_story(
        session,
        title=LONG_TITLE + " A",
        synthesis=LONG_SYNTHESIS,
        key_points=["p1", "p2", "p3"],
        why_it_matters="matters",
        topics=["tech"],
        entities=[],
        importance_score=0.5,
        freshness_score=0.5,
        model="test-model",
        time_window_start=now - timedelta(hours=1),
        time_window_end=now,
        first_seen=now,
    )
    story_b = create_test_story(
        session,
        title=LONG_TITLE + " B",
        synthesis=LONG_SYNTHESIS,
        key_points=["p1", "p2", "p3"],
        why_it_matters="matters",
        topics=["tech"],
        entities=[],
        importance_score=0.5,
        freshness_score=0.5,
        model="test-model",
        time_window_start=now - timedelta(hours=1),
        time_window_end=now,
        first_seen=now,
    )
    session.commit()

    session.execute(
        text(
            "INSERT INTO items (id, feed_id, title, url, url_hash, published) "
            "VALUES (1, 1, 'a', 'http://x/1', 'h1', NOW()), "
            "(2, 1, 'b', 'http://x/2', 'h2', NOW())"
        )
    )
    session.execute(
        text(
            "INSERT INTO entities (id, canonical_name, entity_type) "
            "VALUES (1, 'OpenAI', 'company'), (2, 'GPT-5', 'product')"
        )
    )
    session.commit()

    link_test_articles_to_story(session, story_a, [1], primary_article_id=1)
    link_test_articles_to_story(session, story_b, [2], primary_article_id=2)

    session.execute(
        text(
            "INSERT INTO entity_mentions (entity_id, article_id, story_id, prominence_score) "
            "VALUES (1, 1, :a, 0.9), (2, 1, :a, 0.8), (1, 2, :b, 0.9), (2, 2, :b, 0.8)"
        ),
        {"a": story_a, "b": story_b},
    )
    session.commit()

    yield session, story_a, story_b

    session.close()


class TestEntityConnectionsEndpoint:
    def test_returns_connected_story(self, client, two_connected_stories):
        _, story_a, story_b = two_connected_stories

        resp = client.get(f"/stories/{story_a}/entity-connections")
        assert resp.status_code == 200
        body = resp.json()
        assert body["query_id"] == story_a
        assert len(body["results"]) == 1
        result = body["results"][0]
        assert result["story_id"] == story_b
        assert result["shared_entity_count"] == 2
        assert result["strength"] == "strong"
        names = {e["canonical_name"] for e in result["shared_entities"]}
        assert names == {"OpenAI", "GPT-5"}

    def test_unknown_story_404s(self, client, two_connected_stories):
        resp = client.get("/stories/999999/entity-connections")
        assert resp.status_code == 404

    def test_min_shared_entities_param(self, client, two_connected_stories):
        _, story_a, _ = two_connected_stories
        resp = client.get(
            f"/stories/{story_a}/entity-connections",
            params={"min_shared_entities": 3},
        )
        assert resp.status_code == 200
        assert resp.json()["results"] == []


class TestStoriesEntityFilter:
    def test_filters_stories_by_entity(self, client, two_connected_stories):
        _, story_a, story_b = two_connected_stories

        resp = client.get("/stories", params={"entity": 1})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert {s["id"] for s in body["stories"]} == {story_a, story_b}
        assert body["entity_filter"] == {
            "id": 1,
            "canonical_name": "OpenAI",
            "entity_type": "company",
        }

    def test_unknown_entity_404s(self, client, two_connected_stories):
        resp = client.get("/stories", params={"entity": 999999})
        assert resp.status_code == 404

    def test_no_entity_filter_omits_field(self, client, two_connected_stories):
        resp = client.get("/stories")
        assert resp.status_code == 200
        assert resp.json()["entity_filter"] is None
