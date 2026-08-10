"""Integration tests for app.historical_linking (#258, ADR-0026)."""

from __future__ import annotations

import json
import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from datetime import UTC, datetime, timedelta

from app.historical_linking import maybe_link_historical_context
from app.orm_models import Story
from tests.pg_testutil import pg_session_truncate_story_graph


def _vec(seed: float, dims: int = 768) -> list[float]:
    """Deterministic vector; small seed deltas => near-1.0 cosine similarity."""
    return [seed + 0.0001 * i for i in range(dims)]


class TestMaybeLinkHistoricalContext:
    def test_links_closest_match_above_threshold(self):
        session = pg_session_truncate_story_graph()
        try:
            now = datetime.now(UTC)
            old_story = Story(
                id=1,
                title="Old related story",
                synthesis="x" * 60,
                embedding=_vec(1.0),
                generated_at=now - timedelta(days=5),
            )
            new_story = Story(
                id=2,
                title="New story",
                synthesis="x" * 60,
                embedding=_vec(1.0001),
                generated_at=now,
            )
            session.add_all([old_story, new_story])
            session.commit()

            maybe_link_historical_context(session, new_story, threshold=0.5)
            session.commit()

            refreshed = session.get(Story, 2)
            assert refreshed.continues_story_id == 1
            assert refreshed.continues_similarity > 0.99
            links = json.loads(refreshed.historical_links_json)
            assert links[0]["story_id"] == 1
        finally:
            session.close()

    def test_no_match_below_threshold_leaves_fields_unset(self):
        session = pg_session_truncate_story_graph()
        try:
            now = datetime.now(UTC)
            session.add_all(
                [
                    Story(
                        id=1,
                        title="Unrelated old story",
                        synthesis="x" * 60,
                        embedding=_vec(-1.0),
                        generated_at=now - timedelta(days=5),
                    ),
                    Story(
                        id=2,
                        title="New story",
                        synthesis="x" * 60,
                        embedding=_vec(1.0),
                        generated_at=now,
                    ),
                ]
            )
            session.commit()
            new_story = session.get(Story, 2)

            maybe_link_historical_context(session, new_story, threshold=0.75)
            session.commit()

            refreshed = session.get(Story, 2)
            assert refreshed.continues_story_id is None
            assert refreshed.continues_similarity is None
            assert json.loads(refreshed.historical_links_json) == []
        finally:
            session.close()

    def test_excludes_stories_outside_window(self):
        session = pg_session_truncate_story_graph()
        try:
            now = datetime.now(UTC)
            session.add_all(
                [
                    Story(
                        id=1,
                        title="Too old",
                        synthesis="x" * 60,
                        embedding=_vec(1.0),
                        generated_at=now - timedelta(days=60),
                    ),
                    Story(
                        id=2,
                        title="New story",
                        synthesis="x" * 60,
                        embedding=_vec(1.0001),
                        generated_at=now,
                    ),
                ]
            )
            session.commit()
            new_story = session.get(Story, 2)

            maybe_link_historical_context(
                session, new_story, threshold=0.5, window_days=30
            )
            session.commit()

            refreshed = session.get(Story, 2)
            assert refreshed.continues_story_id is None
        finally:
            session.close()

    def test_story_without_embedding_is_noop(self):
        session = pg_session_truncate_story_graph()
        try:
            story = Story(id=1, title="No vector", synthesis="x" * 60)
            session.add(story)
            session.commit()

            maybe_link_historical_context(session, story)
            session.commit()

            refreshed = session.get(Story, 1)
            assert refreshed.continues_story_id is None
            assert refreshed.historical_links_json is None
        finally:
            session.close()

    def test_disabled_via_env_is_noop(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("NEWSBRIEF_HISTORICAL_LINKING_ENABLED", "false")
        session = pg_session_truncate_story_graph()
        try:
            now = datetime.now(UTC)
            session.add_all(
                [
                    Story(
                        id=1,
                        title="Old related story",
                        synthesis="x" * 60,
                        embedding=_vec(1.0),
                        generated_at=now - timedelta(days=5),
                    ),
                    Story(
                        id=2,
                        title="New story",
                        synthesis="x" * 60,
                        embedding=_vec(1.0001),
                        generated_at=now,
                    ),
                ]
            )
            session.commit()
            new_story = session.get(Story, 2)

            maybe_link_historical_context(session, new_story, threshold=0.5)
            session.commit()

            refreshed = session.get(Story, 2)
            assert refreshed.continues_story_id is None
            assert refreshed.historical_links_json is None
        finally:
            session.close()
