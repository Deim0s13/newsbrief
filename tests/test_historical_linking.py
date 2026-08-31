"""Integration tests for app.historical_linking (#258, ADR-0026)."""

from __future__ import annotations

import json
import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.historical_linking import (
    _entity_overlap_counts,
    _rerank_by_entity_overlap,
    maybe_link_historical_context,
)
from app.orm_models import Story
from app.retrieval import SimilarityResult
from tests.pg_testutil import (
    _vec,
    create_test_story,
    pg_session_truncate_entity_graph,
    pg_session_truncate_story_graph,
    seed_default_feed,
)


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

    def test_merges_continuation_into_context_anchors(self):
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
                # Pre-synthesis retrieval hook (#279) already flagged story 1
                # as background context before this story was synthesized.
                context_anchors_json=json.dumps(
                    [
                        {
                            "story_id": 1,
                            "title": "Old related story",
                            "similarity": 0.7,
                            "published_at": None,
                            "kind": "background",
                            "rationale": "Related prior coverage identified "
                            "before synthesis (similarity 70%)",
                        }
                    ]
                ),
            )
            session.add_all([old_story, new_story])
            session.commit()

            maybe_link_historical_context(session, new_story, threshold=0.5)
            session.commit()

            refreshed = session.get(Story, 2)
            anchors = json.loads(refreshed.context_anchors_json)
            assert len(anchors) == 1
            assert anchors[0]["story_id"] == 1
            # Promoted from "background" (#279) to "current" since it's the
            # closest post-synthesis match (#258).
            assert anchors[0]["kind"] == "current"
            assert "rationale" in anchors[0]
        finally:
            session.close()

    def test_context_anchors_empty_when_no_matches(self):
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
            assert json.loads(refreshed.context_anchors_json) == []
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


def _make_article(session, article_id: int) -> None:
    session.execute(
        text(
            "INSERT INTO items (id, feed_id, title, url, url_hash, published) "
            "VALUES (:id, 1, :title, :url, :hash, NOW())"
        ),
        {
            "id": article_id,
            "title": f"Article {article_id}",
            "url": f"http://x/{article_id}",
            "hash": f"h{article_id}",
        },
    )


def _make_entity(session, entity_id: int, name: str) -> None:
    session.execute(
        text(
            "INSERT INTO entities (id, canonical_name, entity_type) "
            "VALUES (:id, :name, 'company')"
        ),
        {"id": entity_id, "name": name},
    )


def _make_mention(session, entity_id: int, article_id: int, story_id: int) -> None:
    session.execute(
        text(
            "INSERT INTO entity_mentions (entity_id, article_id, story_id) "
            "VALUES (:eid, :aid, :sid)"
        ),
        {"eid": entity_id, "aid": article_id, "sid": story_id},
    )


class TestEntityOverlapCounts:
    def test_counts_shared_entities_per_candidate(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            now = datetime.now(UTC)
            source_id = create_test_story(
                session,
                title="Source",
                synthesis="x" * 60,
                key_points=["p"],
                why_it_matters="m",
                topics=["t"],
                entities=[],
                importance_score=0.5,
                freshness_score=0.5,
                model="test",
                time_window_start=now,
                time_window_end=now,
            )
            candidate_a = create_test_story(
                session,
                title="Candidate A",
                synthesis="x" * 60,
                key_points=["p"],
                why_it_matters="m",
                topics=["t"],
                entities=[],
                importance_score=0.5,
                freshness_score=0.5,
                model="test",
                time_window_start=now,
                time_window_end=now,
            )
            candidate_b = create_test_story(
                session,
                title="Candidate B",
                synthesis="x" * 60,
                key_points=["p"],
                why_it_matters="m",
                topics=["t"],
                entities=[],
                importance_score=0.5,
                freshness_score=0.5,
                model="test",
                time_window_start=now,
                time_window_end=now,
            )
            for i in range(1, 5):
                _make_article(session, i)
            _make_entity(session, 1, "CompanyA")
            _make_entity(session, 2, "CompanyB")
            session.commit()

            # Source shares both entities with candidate_a, only one with candidate_b.
            _make_mention(session, 1, 1, source_id)
            _make_mention(session, 2, 2, source_id)
            _make_mention(session, 1, 3, candidate_a)
            _make_mention(session, 2, 3, candidate_a)
            _make_mention(session, 1, 4, candidate_b)
            session.commit()

            counts = _entity_overlap_counts(
                session, source_id, [candidate_a, candidate_b]
            )
            assert counts == {candidate_a: 2, candidate_b: 1}
        finally:
            session.close()

    def test_no_candidates_returns_empty(self):
        session = pg_session_truncate_entity_graph()
        try:
            assert _entity_overlap_counts(session, 1, []) == {}
        finally:
            session.close()


class TestRerankByEntityOverlap:
    def test_reorders_near_tie_toward_higher_overlap(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            now = datetime.now(UTC)
            source_id = create_test_story(
                session,
                title="Source",
                synthesis="x" * 60,
                key_points=["p"],
                why_it_matters="m",
                topics=["t"],
                entities=[],
                importance_score=0.5,
                freshness_score=0.5,
                model="test",
                time_window_start=now,
                time_window_end=now,
            )
            for i in range(1, 4):
                _make_article(session, i)
            _make_entity(session, 1, "CompanyA")
            _make_entity(session, 2, "CompanyB")
            session.add(Story(id=20, title="Candidate", synthesis="x" * 60))
            session.commit()

            # No overlap data for story 10 (e.g. pre-#199); story 20 shares
            # 2 entities.
            _make_mention(session, 1, 1, source_id)
            _make_mention(session, 2, 2, source_id)
            _make_mention(session, 1, 3, 20)
            _make_mention(session, 2, 3, 20)
            session.commit()

            results = [
                SimilarityResult(id=10, title="Higher raw similarity", similarity=0.80),
                SimilarityResult(id=20, title="Strong entity overlap", similarity=0.78),
            ]
            reranked = _rerank_by_entity_overlap(session, source_id, results)
            assert [r.id for r in reranked] == [20, 10]
        finally:
            session.close()

    def test_does_not_override_a_much_stronger_embedding_match(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            now = datetime.now(UTC)
            source_id = create_test_story(
                session,
                title="Source",
                synthesis="x" * 60,
                key_points=["p"],
                why_it_matters="m",
                topics=["t"],
                entities=[],
                importance_score=0.5,
                freshness_score=0.5,
                model="test",
                time_window_start=now,
                time_window_end=now,
            )
            for i in range(1, 4):
                _make_article(session, i)
            _make_entity(session, 1, "CompanyA")
            _make_entity(session, 2, "CompanyB")
            session.add(Story(id=20, title="Candidate", synthesis="x" * 60))
            session.commit()

            _make_mention(session, 1, 1, source_id)
            _make_mention(session, 2, 2, source_id)
            _make_mention(session, 1, 3, 20)
            _make_mention(session, 2, 3, 20)
            session.commit()

            results = [
                SimilarityResult(id=10, title="Far stronger match", similarity=0.95),
                SimilarityResult(
                    id=20, title="Weaker but overlapping", similarity=0.70
                ),
            ]
            reranked = _rerank_by_entity_overlap(session, source_id, results)
            # 0.70 + capped boost (0.12) = 0.82, still well below 0.95.
            assert [r.id for r in reranked] == [10, 20]
        finally:
            session.close()

    def test_no_overlap_data_preserves_original_order(self):
        session = pg_session_truncate_entity_graph()
        try:
            results = [
                SimilarityResult(id=10, title="A", similarity=0.9),
                SimilarityResult(id=20, title="B", similarity=0.8),
            ]
            reranked = _rerank_by_entity_overlap(session, 1, results)
            assert [r.id for r in reranked] == [10, 20]
        finally:
            session.close()


class TestMaybeLinkHistoricalContextWithEntityOverlap:
    def test_entity_overlap_can_change_the_continuation_pick(self):
        session = pg_session_truncate_entity_graph()
        try:
            seed_default_feed(session)
            now = datetime.now(UTC)

            # Two near-tied embedding matches within threshold; story 10 has
            # a marginally higher raw similarity, story 20 shares entities
            # with the new story.
            session.add_all(
                [
                    Story(
                        id=10,
                        title="Marginally closer, no shared entities",
                        synthesis="x" * 60,
                        embedding=_vec(1.0),
                        generated_at=now - timedelta(days=1),
                    ),
                    Story(
                        id=20,
                        title="Slightly further, shares entities",
                        synthesis="x" * 60,
                        embedding=_vec(0.999),
                        generated_at=now - timedelta(days=1),
                    ),
                    Story(
                        id=30,
                        title="New story",
                        synthesis="x" * 60,
                        embedding=_vec(1.0001),
                        generated_at=now,
                    ),
                ]
            )
            session.commit()

            for i in range(1, 3):
                _make_article(session, i)
            _make_entity(session, 1, "SharedCo")
            session.commit()

            _make_mention(session, 1, 1, 20)
            _make_mention(session, 1, 2, 30)
            session.commit()

            new_story = session.get(Story, 30)
            maybe_link_historical_context(session, new_story, threshold=0.5)
            session.commit()

            refreshed = session.get(Story, 30)
            # Without the entity-overlap signal this would pick story 10
            # (very slightly higher cosine similarity); the shared-entity
            # boost tips it to story 20 instead.
            assert refreshed.continues_story_id == 20
        finally:
            session.close()
