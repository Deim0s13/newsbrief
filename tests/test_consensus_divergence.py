"""Tests for consensus/divergence detection in story synthesis (#204,
ADR-0023, v0.9.1).

Covers the ConsensusPointOutput/DivergencePointOutput/SynthesisOutput
schema extensions (app.llm_output), the prompt-formatting helpers that
tag each article with its source name + cached perspective hint
(app.stories._format_perspective_hint, app.prompts.synthesis), the batched
per-article perspective lookup (app.entities.get_article_perspectives),
and the Story ORM <-> StoryOut round-trip for the new
consensus_points_json/divergence_points_json/source_agreement_score
columns.
"""

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from app.entities import ArticlePerspective, get_article_perspectives
from app.llm_output import (
    ConsensusPointOutput,
    DivergencePerspectiveOutput,
    DivergencePointOutput,
    SynthesisOutput,
)
from app.models import serialize_story_json_field
from app.prompts.synthesis import _format_article_line
from app.stories import _format_perspective_hint, _story_db_to_model


class TestSynthesisOutputSchema:
    """SynthesisOutput's consensus/divergence field extensions."""

    def test_defaults_are_empty(self):
        output = SynthesisOutput.model_validate(
            {"synthesis": "A sufficiently long test synthesis.", "key_points": ["a"]}
        )
        assert output.consensus_points == []
        assert output.divergence_points == []
        assert output.source_agreement_score is None

    def test_valid_consensus_and_divergence(self):
        output = SynthesisOutput.model_validate(
            {
                "synthesis": "A sufficiently long test synthesis.",
                "key_points": ["a"],
                "consensus_points": [
                    {"claim": "10,000 jobs cut", "sources": ["Reuters", "AP"]}
                ],
                "divergence_points": [
                    {
                        "topic": "Cause",
                        "perspectives": [
                            {"view": "AI automation", "sources": ["TechCrunch"]},
                            {"view": "Economic downturn", "sources": ["Bloomberg"]},
                        ],
                    }
                ],
                "source_agreement_score": 0.6,
            }
        )
        assert len(output.consensus_points) == 1
        assert output.consensus_points[0].claim == "10,000 jobs cut"
        assert output.consensus_points[0].sources == ["Reuters", "AP"]
        assert output.consensus_points[0].confidence == 0.7  # default
        assert len(output.divergence_points) == 1
        assert output.divergence_points[0].topic == "Cause"
        assert len(output.divergence_points[0].perspectives) == 2
        assert output.source_agreement_score == 0.6

    def test_agreement_score_out_of_range_is_clamped(self):
        output = SynthesisOutput.model_validate(
            {
                "synthesis": "A sufficiently long test synthesis.",
                "key_points": ["a"],
                "source_agreement_score": 1.7,
            }
        )
        assert output.source_agreement_score == 1.0

    def test_agreement_score_invalid_type_degrades_to_none(self):
        output = SynthesisOutput.model_validate(
            {
                "synthesis": "A sufficiently long test synthesis.",
                "key_points": ["a"],
                "source_agreement_score": "not-a-number",
            }
        )
        assert output.source_agreement_score is None

    def test_consensus_point_sources_string_coerced_to_list(self):
        cp = ConsensusPointOutput.model_validate(
            {"claim": "Test claim", "sources": "Reuters"}
        )
        assert cp.sources == ["Reuters"]

    def test_consensus_point_confidence_clamped(self):
        cp = ConsensusPointOutput.model_validate(
            {"claim": "Test claim", "confidence": 5.0}
        )
        assert cp.confidence == 1.0

    def test_divergence_perspective_sources_string_coerced(self):
        dp = DivergencePerspectiveOutput.model_validate(
            {"view": "Test view", "sources": "Bloomberg"}
        )
        assert dp.sources == ["Bloomberg"]

    def test_divergence_point_requires_topic(self):
        with pytest.raises(Exception):
            DivergencePointOutput.model_validate({"perspectives": []})

    def test_malformed_consensus_points_degrades_gracefully(self):
        """A malformed list entry shouldn't take down the whole synthesis
        parse -- allow_partial handling lives in parse_and_validate, but
        the schema itself should reject cleanly so that path can kick in."""
        with pytest.raises(Exception):
            SynthesisOutput.model_validate(
                {
                    "synthesis": "A sufficiently long test synthesis.",
                    "key_points": ["a"],
                    "consensus_points": [{"sources": ["Reuters"]}],  # missing claim
                }
            )


class TestFormatPerspectiveHint:
    """app.stories._format_perspective_hint"""

    def test_none_perspective_returns_empty(self):
        assert _format_perspective_hint(None) == ""

    def test_not_applicable_returns_empty(self):
        p = ArticlePerspective(applicable=False)
        assert _format_perspective_hint(p) == ""

    def test_applicable_formats_present_fields_only(self):
        p = ArticlePerspective(applicable=True, stakeholder="business", tone="critical")
        hint = _format_perspective_hint(p)
        assert "stakeholder=business" in hint
        assert "tone=critical" in hint
        assert "political=" not in hint
        assert "regional=" not in hint

    def test_applicable_all_fields(self):
        p = ArticlePerspective(
            applicable=True,
            political_leaning="center-left",
            stakeholder="consumer",
            regional="national",
            tone="analytical",
        )
        hint = _format_perspective_hint(p)
        assert hint == (
            "stakeholder=consumer, political=center-left, "
            "regional=national, tone=analytical"
        )


class TestFormatArticleLine:
    """app.prompts.synthesis._format_article_line"""

    def test_plain_title_no_source_no_hint(self):
        line = _format_article_line({"title": "Just a headline"}, 80)
        assert line == "- Just a headline"

    def test_source_only(self):
        line = _format_article_line({"title": "Headline here", "source": "Reuters"}, 80)
        assert line == "- [Reuters] Headline here"

    def test_source_and_hint(self):
        line = _format_article_line(
            {
                "title": "Headline here",
                "source": "Reuters",
                "perspective_hint": "stakeholder=business",
            },
            80,
        )
        assert line == "- [Reuters] (stakeholder=business) Headline here"

    def test_hint_without_source(self):
        line = _format_article_line(
            {"title": "Headline here", "perspective_hint": "tone=critical"}, 80
        )
        assert line == "- (tone=critical) Headline here"

    def test_missing_title_falls_back_to_untitled(self):
        line = _format_article_line({}, 80)
        assert line == "- Untitled"

    def test_title_truncated(self):
        line = _format_article_line({"title": "x" * 200}, 10)
        assert line == f"- {'x' * 10}"


@pytest.fixture
def perspective_test_db():
    """Set up test feed + isolated cleanup for perspective/consensus tests."""
    from app.db import SessionLocal, init_db

    init_db()
    session = SessionLocal()

    try:
        session.execute(
            text(
                """
                INSERT INTO feeds (id, url, name)
                VALUES (9101, 'http://test-consensus.example/feed', 'Reuters Test Feed')
                ON CONFLICT (id) DO NOTHING
                """
            )
        )
        session.commit()
    except Exception:
        session.rollback()

    yield session

    try:
        session.execute(
            text("DELETE FROM items WHERE url LIKE 'http://test-consensus.example/%'")
        )
        session.execute(
            text("DELETE FROM stories WHERE story_hash LIKE 'test-consensus-%'")
        )
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


class TestGetArticlePerspectives:
    """app.entities.get_article_perspectives batch lookup."""

    def test_empty_ids_returns_empty(self, perspective_test_db):
        assert get_article_perspectives(perspective_test_db, []) == {}

    def test_batch_lookup_mixed_hits_and_misses(self, perspective_test_db):
        session = perspective_test_db
        url_a = f"http://test-consensus.example/{uuid.uuid4()}"
        url_b = f"http://test-consensus.example/{uuid.uuid4()}"

        perspective = ArticlePerspective(
            applicable=True, stakeholder="business", tone="critical"
        )
        row_a = session.execute(
            text(
                """
                INSERT INTO items (feed_id, title, url, url_hash, published, perspective_json)
                VALUES (9101, 'Has perspective', :url, :hash, NOW(), :pj)
                RETURNING id
                """
            ),
            {
                "url": url_a,
                "hash": str(uuid.uuid4()),
                "pj": perspective.to_json_string(),
            },
        )
        article_with_perspective = row_a.scalar()

        row_b = session.execute(
            text(
                """
                INSERT INTO items (feed_id, title, url, url_hash, published)
                VALUES (9101, 'No perspective', :url, :hash, NOW())
                RETURNING id
                """
            ),
            {"url": url_b, "hash": str(uuid.uuid4())},
        )
        article_without_perspective = row_b.scalar()
        session.commit()

        result = get_article_perspectives(
            session, [article_with_perspective, article_without_perspective, 999999]
        )
        assert article_with_perspective in result
        assert article_without_perspective not in result
        assert 999999 not in result
        assert result[article_with_perspective].stakeholder == "business"


class TestGetStoryByIdPerspectiveFields:
    """app.stories.get_story_by_id() surfacing source_name/perspective on
    ItemOut for supporting articles (v0.9.1, #205 UI backend wiring)."""

    def test_supporting_articles_include_source_name_and_perspective(
        self, perspective_test_db
    ):
        from app.stories import get_story_by_id
        from tests.pg_testutil import create_test_story, link_test_articles_to_story

        session = perspective_test_db
        perspective = ArticlePerspective(
            applicable=True, stakeholder="business", tone="critical"
        )
        row = session.execute(
            text(
                """
                INSERT INTO items (feed_id, title, url, url_hash, published, perspective_json)
                VALUES (9101, 'Has perspective', :url, :hash, NOW(), :pj)
                RETURNING id
                """
            ),
            {
                "url": f"http://test-consensus.example/{uuid.uuid4()}",
                "hash": str(uuid.uuid4()),
                "pj": perspective.to_json_string(),
            },
        )
        article_id = row.scalar()
        session.commit()

        story_id = create_test_story(
            session,
            title="Test story",
            synthesis="A test synthesis sentence that is long enough to pass the fifty character minimum length validator.",
            key_points=["point"],
            why_it_matters="It matters for testing purposes.",
            topics=["Business"],
            entities=["TestCo"],
            importance_score=0.5,
            freshness_score=0.5,
            model="test-model",
            time_window_start=datetime.now(UTC),
            time_window_end=datetime.now(UTC),
            story_hash=f"test-consensus-{uuid.uuid4()}",
        )
        link_test_articles_to_story(session, story_id, [article_id], article_id)

        story = get_story_by_id(session, story_id)
        assert story is not None
        assert len(story.supporting_articles) == 1
        article = story.supporting_articles[0]
        assert article.source_name == "Reuters Test Feed"
        assert article.perspective == perspective.to_dict()

    def test_not_applicable_perspective_is_none_on_article(self, perspective_test_db):
        from app.stories import get_story_by_id
        from tests.pg_testutil import create_test_story, link_test_articles_to_story

        session = perspective_test_db
        not_applicable = ArticlePerspective(applicable=False)
        row = session.execute(
            text(
                """
                INSERT INTO items (feed_id, title, url, url_hash, published, perspective_json)
                VALUES (9101, 'Neutral article', :url, :hash, NOW(), :pj)
                RETURNING id
                """
            ),
            {
                "url": f"http://test-consensus.example/{uuid.uuid4()}",
                "hash": str(uuid.uuid4()),
                "pj": not_applicable.to_json_string(),
            },
        )
        article_id = row.scalar()
        session.commit()

        story_id = create_test_story(
            session,
            title="Test story",
            synthesis="A test synthesis sentence that is long enough to pass the fifty character minimum length validator.",
            key_points=["point"],
            why_it_matters="It matters for testing purposes.",
            topics=["Tech"],
            entities=["TestCo"],
            importance_score=0.5,
            freshness_score=0.5,
            model="test-model",
            time_window_start=datetime.now(UTC),
            time_window_end=datetime.now(UTC),
            story_hash=f"test-consensus-{uuid.uuid4()}",
        )
        link_test_articles_to_story(session, story_id, [article_id], article_id)

        story = get_story_by_id(session, story_id)
        assert story is not None
        article = story.supporting_articles[0]
        assert article.source_name == "Reuters Test Feed"
        assert article.perspective is None


class TestStoryPersistenceRoundTrip:
    """Story ORM <-> StoryOut for consensus_points_json/divergence_points_json/
    source_agreement_score (v0.9.1, #204)."""

    def test_empty_defaults_round_trip(self, perspective_test_db):
        from app.orm_models import Story

        session = perspective_test_db
        story = Story(
            title="Test story",
            synthesis="A test synthesis sentence that is long enough to pass the fifty character minimum length validator.",
            key_points_json=serialize_story_json_field(["point"]),
            article_count=1,
            importance_score=0.5,
            freshness_score=0.5,
            cluster_method="test",
            story_hash=f"test-consensus-{uuid.uuid4()}",
            generated_at=datetime.now(UTC),
            first_seen=datetime.now(UTC),
            last_updated=datetime.now(UTC),
            time_window_start=datetime.now(UTC),
            time_window_end=datetime.now(UTC),
            model="test-model",
            status="active",
            version=1,
        )
        session.add(story)
        session.commit()
        session.refresh(story)

        out = _story_db_to_model(story, articles=[])
        assert out.consensus_points == []
        assert out.divergence_points == []
        assert out.source_agreement_score is None
        assert out.coverage_gaps == []

    def test_coverage_gaps_round_trip(self, perspective_test_db):
        import json

        from app.orm_models import Story

        session = perspective_test_db
        gaps = [
            {
                "dimension": "stakeholder",
                "present": ["business"],
                "missing": "consumer or labor viewpoint",
            }
        ]
        story = Story(
            title="Test story",
            synthesis="A test synthesis sentence that is long enough to pass the fifty character minimum length validator.",
            key_points_json=serialize_story_json_field(["point"]),
            coverage_gaps_json=json.dumps(gaps),
            article_count=1,
            importance_score=0.5,
            freshness_score=0.5,
            cluster_method="test",
            story_hash=f"test-consensus-{uuid.uuid4()}",
            generated_at=datetime.now(UTC),
            first_seen=datetime.now(UTC),
            last_updated=datetime.now(UTC),
            time_window_start=datetime.now(UTC),
            time_window_end=datetime.now(UTC),
            model="test-model",
            status="active",
            version=1,
        )
        session.add(story)
        session.commit()
        session.refresh(story)

        out = _story_db_to_model(story, articles=[])
        assert out.coverage_gaps == gaps

    def test_populated_fields_round_trip(self, perspective_test_db):
        import json

        from app.orm_models import Story

        session = perspective_test_db
        consensus = [
            {"claim": "10,000 jobs cut", "sources": ["Reuters"], "confidence": 0.9}
        ]
        divergence = [
            {
                "topic": "Cause",
                "perspectives": [
                    {"view": "AI automation", "sources": ["TechCrunch"]},
                ],
            }
        ]
        story = Story(
            title="Test story",
            synthesis="A test synthesis sentence that is long enough to pass the fifty character minimum length validator.",
            key_points_json=serialize_story_json_field(["point"]),
            consensus_points_json=json.dumps(consensus),
            divergence_points_json=json.dumps(divergence),
            source_agreement_score=0.55,
            article_count=1,
            importance_score=0.5,
            freshness_score=0.5,
            cluster_method="test",
            story_hash=f"test-consensus-{uuid.uuid4()}",
            generated_at=datetime.now(UTC),
            first_seen=datetime.now(UTC),
            last_updated=datetime.now(UTC),
            time_window_start=datetime.now(UTC),
            time_window_end=datetime.now(UTC),
            model="test-model",
            status="active",
            version=1,
        )
        session.add(story)
        session.commit()
        session.refresh(story)

        out = _story_db_to_model(story, articles=[])
        assert out.consensus_points == consensus
        assert out.divergence_points == divergence
        assert out.source_agreement_score == 0.55
