"""Integration tests for app.retrieval_tracing (#256, ADR-0026)."""

from __future__ import annotations

import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from app.orm_models import Item, Story
from app.retrieval import RetrievalService
from app.retrieval_tracing import (
    get_retrieval_trace_stats,
    list_recent_retrieval_traces,
    record_retrieval_trace,
)
from tests.pg_testutil import _seed_feed, _vec, pg_session_truncate_retrieval_traces


class TestRecordAndListTraces:
    def test_record_and_list_round_trip(self):
        session = pg_session_truncate_retrieval_traces()
        try:
            record_retrieval_trace(
                session,
                query_type="similar_articles",
                source_id=1,
                source_type="article",
                retrieved_ids=[2, 3],
                similarity_scores=[0.95, 0.81],
                filters_applied={"top_k": 5, "min_similarity": 0.7},
                duration_ms=12,
            )
            session.commit()

            traces = list_recent_retrieval_traces(session, limit=10)
            assert len(traces) == 1
            trace = traces[0]
            assert trace["query_type"] == "similar_articles"
            assert trace["source_id"] == 1
            assert trace["retrieved_count"] == 2
            assert trace["avg_similarity"] == pytest.approx(0.88, abs=0.01)
            assert trace["duration_ms"] == 12
            assert trace["filters_applied"]["top_k"] == 5
        finally:
            session.close()

    def test_zero_results_trace(self):
        session = pg_session_truncate_retrieval_traces()
        try:
            record_retrieval_trace(
                session,
                query_type="semantic_search",
                source_id=None,
                source_type="article",
                retrieved_ids=[],
                similarity_scores=[],
                filters_applied=None,
                duration_ms=5,
            )
            session.commit()

            traces = list_recent_retrieval_traces(session, limit=10)
            assert traces[0]["retrieved_count"] == 0
            assert traces[0]["avg_similarity"] is None
            assert traces[0]["filters_applied"] == {}
        finally:
            session.close()


class TestRetrievalTraceStats:
    def test_stats_empty(self):
        session = pg_session_truncate_retrieval_traces()
        try:
            stats = get_retrieval_trace_stats(session)
            assert stats["total_traces"] == 0
            assert stats["by_query_type"] == {}
        finally:
            session.close()

    def test_stats_aggregate_by_query_type(self):
        session = pg_session_truncate_retrieval_traces()
        try:
            record_retrieval_trace(
                session,
                query_type="similar_articles",
                source_id=1,
                source_type="article",
                retrieved_ids=[2],
                similarity_scores=[0.9],
                filters_applied=None,
                duration_ms=10,
            )
            record_retrieval_trace(
                session,
                query_type="similar_articles",
                source_id=2,
                source_type="article",
                retrieved_ids=[],
                similarity_scores=[],
                filters_applied=None,
                duration_ms=20,
            )
            session.commit()

            stats = get_retrieval_trace_stats(session)
            assert stats["total_traces"] == 2
            assert stats["avg_duration_ms"] == pytest.approx(15.0)
            assert stats["zero_result_rate"] == pytest.approx(0.5)
            assert stats["by_query_type"]["similar_articles"]["count"] == 2
            assert stats["by_query_type"]["similar_articles"]["avg_results"] == 0.5
        finally:
            session.close()


class TestRetrievalServiceTracing:
    def test_find_similar_articles_writes_trace(self):
        session = pg_session_truncate_retrieval_traces()
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

            RetrievalService(session).find_similar_articles(1, min_similarity=0.5)
            session.commit()

            traces = list_recent_retrieval_traces(session, limit=10)
            assert len(traces) == 1
            assert traces[0]["query_type"] == "similar_articles"
            assert traces[0]["source_id"] == 1
            assert traces[0]["retrieved_count"] == 1
        finally:
            session.close()

    def test_no_trace_when_source_has_no_embedding(self):
        session = pg_session_truncate_retrieval_traces()
        try:
            _seed_feed(session)
            session.add(
                Item(
                    id=1, feed_id=1, title="No vector", url="http://x/1", url_hash="h1"
                )
            )
            session.commit()

            RetrievalService(session).find_similar_articles(1)
            session.commit()

            assert list_recent_retrieval_traces(session, limit=10) == []
        finally:
            session.close()

    def test_find_related_stories_writes_trace(self):
        session = pg_session_truncate_retrieval_traces()
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
                ]
            )
            session.commit()

            RetrievalService(session).find_related_stories(1, min_similarity=0.5)
            session.commit()

            traces = list_recent_retrieval_traces(session, limit=10)
            assert len(traces) == 1
            assert traces[0]["query_type"] == "related_stories"
            assert traces[0]["source_type"] == "story"
        finally:
            session.close()
