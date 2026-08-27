"""Integration tests for app.retrieval.RetrievalService (#255, ADR-0026)."""

from __future__ import annotations

import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.orm_models import Item, Story
from app.retrieval import RetrievalService
from tests.pg_testutil import _seed_feed, _vec, pg_session_truncate_story_graph


class TestFindSimilarArticles:
    def test_returns_closest_first_above_threshold(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            session.add_all(
                [
                    Item(
                        id=1,
                        feed_id=1,
                        title="Source",
                        url="http://x/1",
                        url_hash="h1",
                        embedding=_vec(1.0),
                    ),
                    Item(
                        id=2,
                        feed_id=1,
                        title="Close match",
                        url="http://x/2",
                        url_hash="h2",
                        embedding=_vec(1.0001),
                    ),
                    Item(
                        id=3,
                        feed_id=1,
                        title="Unrelated",
                        url="http://x/3",
                        url_hash="h3",
                        embedding=_vec(-1.0),
                    ),
                    Item(
                        id=4,
                        feed_id=1,
                        title="No vector",
                        url="http://x/4",
                        url_hash="h4",
                    ),
                ]
            )
            session.commit()

            results = RetrievalService(session).find_similar_articles(
                1, top_k=5, min_similarity=0.5
            )

            assert [r.id for r in results] == [2]
            assert results[0].similarity > 0.99
        finally:
            session.close()

    def test_missing_article_returns_empty(self):
        session = pg_session_truncate_story_graph()
        try:
            assert RetrievalService(session).find_similar_articles(999) == []
        finally:
            session.close()

    def test_article_without_embedding_returns_empty(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            session.add(
                Item(
                    id=1, feed_id=1, title="No vector", url="http://x/1", url_hash="h1"
                )
            )
            session.commit()
            assert RetrievalService(session).find_similar_articles(1) == []
        finally:
            session.close()

    def test_date_range_filters_results(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            now = datetime.now(UTC)
            session.add_all(
                [
                    Item(
                        id=1,
                        feed_id=1,
                        title="Source",
                        url="http://x/1",
                        url_hash="h1",
                        embedding=_vec(1.0),
                        published=now,
                    ),
                    Item(
                        id=2,
                        feed_id=1,
                        title="Old close match",
                        url="http://x/2",
                        url_hash="h2",
                        embedding=_vec(1.0001),
                        published=now - timedelta(days=30),
                    ),
                ]
            )
            session.commit()

            results = RetrievalService(session).find_similar_articles(
                1,
                min_similarity=0.5,
                date_range=(now - timedelta(days=7), now),
            )
            assert results == []
        finally:
            session.close()

    def test_query_type_override_is_traced(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            session.add_all(
                [
                    Item(
                        id=1,
                        feed_id=1,
                        title="Source",
                        url="http://x/1",
                        url_hash="h1",
                        embedding=_vec(1.0),
                    ),
                    Item(
                        id=2,
                        feed_id=1,
                        title="Close match",
                        url="http://x/2",
                        url_hash="h2",
                        embedding=_vec(1.0001),
                    ),
                ]
            )
            session.commit()

            RetrievalService(session).find_similar_articles(
                1, min_similarity=0.5, query_type="semantic_dedupe"
            )
            row = session.execute(
                text("SELECT query_type FROM retrieval_traces ORDER BY id DESC LIMIT 1")
            ).first()
            assert row[0] == "semantic_dedupe"
        finally:
            session.close()

    def test_top_k_limits_results(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            session.add(
                Item(
                    id=1,
                    feed_id=1,
                    title="Source",
                    url="http://x/1",
                    url_hash="h1",
                    embedding=_vec(1.0),
                )
            )
            for i in range(2, 6):
                session.add(
                    Item(
                        id=i,
                        feed_id=1,
                        title=f"Near {i}",
                        url=f"http://x/{i}",
                        url_hash=f"h{i}",
                        embedding=_vec(1.0 + 0.0001 * i),
                    )
                )
            session.commit()

            results = RetrievalService(session).find_similar_articles(
                1, top_k=2, min_similarity=0.5
            )
            assert len(results) == 2
        finally:
            session.close()


class TestFindRelatedStories:
    def test_related_stories_excludes_self_and_respects_threshold(self):
        session = pg_session_truncate_story_graph()
        try:
            session.add_all(
                [
                    Story(
                        id=1, title="Story A", synthesis="x" * 60, embedding=_vec(1.0)
                    ),
                    Story(
                        id=2,
                        title="Story B",
                        synthesis="x" * 60,
                        embedding=_vec(1.0001),
                    ),
                    Story(
                        id=3, title="Story C", synthesis="x" * 60, embedding=_vec(-1.0)
                    ),
                ]
            )
            session.commit()

            results = RetrievalService(session).find_related_stories(
                1, min_similarity=0.5
            )
            assert [r.id for r in results] == [2]
        finally:
            session.close()

    def test_missing_story_returns_empty(self):
        session = pg_session_truncate_story_graph()
        try:
            assert RetrievalService(session).find_related_stories(999) == []
        finally:
            session.close()

    def test_date_range_filters_results(self):
        session = pg_session_truncate_story_graph()
        try:
            now = datetime.now(UTC)
            session.add_all(
                [
                    Story(
                        id=1,
                        title="Story A",
                        synthesis="x" * 60,
                        embedding=_vec(1.0),
                        generated_at=now,
                    ),
                    Story(
                        id=2,
                        title="Old related story",
                        synthesis="x" * 60,
                        embedding=_vec(1.0001),
                        generated_at=now - timedelta(days=60),
                    ),
                ]
            )
            session.commit()

            results = RetrievalService(session).find_related_stories(
                1,
                min_similarity=0.5,
                date_range=(now - timedelta(days=30), now),
            )
            assert results == []
        finally:
            session.close()


class TestFindByText:
    def test_embeds_query_and_searches_items(self, monkeypatch: pytest.MonkeyPatch):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            session.add(
                Item(
                    id=1,
                    feed_id=1,
                    title="Match",
                    url="http://x/1",
                    url_hash="h1",
                    embedding=_vec(1.0),
                )
            )
            session.commit()

            monkeypatch.setattr(
                RetrievalService,
                "_embed_query_text",
                staticmethod(lambda text: _vec(1.0001)),
            )

            results = RetrievalService(session).find_by_text(
                "some query", top_k=5, min_similarity=0.5
            )
            assert [r.id for r in results] == [1]
        finally:
            session.close()

    def test_blank_query_returns_empty(self):
        session = pg_session_truncate_story_graph()
        try:
            assert RetrievalService(session).find_by_text("   ") == []
        finally:
            session.close()
