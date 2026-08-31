"""Tests for the entity normalization/dedup layer (#199, ADR-0023, v0.9.0)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import bindparam, text

from app.entities import EntityWithMetadata, ExtractedEntities
from app.entity_normalization import (
    canonicalize_entity_name,
    link_entity_mentions_to_story,
    normalize_and_store_entities,
)
from tests.pg_testutil import create_test_story, seed_default_feed


class TestCanonicalizeEntityName:
    """Exact-match normalization rules (no fuzzy matching in this pass)."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Apple Inc.", "Apple"),
            ("Apple Inc", "Apple"),
            ("Apple, Inc.", "Apple"),
            ("apple inc.", "apple"),
            ("Cisco Systems", "Cisco Systems"),
            ("  Google  ", "Google"),
            ("OpenAI Corp", "OpenAI"),
            ("Acme LLC", "Acme"),
            ("Acme Group", "Acme"),
            ("Splunk", "Splunk"),
        ],
    )
    def test_suffix_stripping(self, raw, expected):
        assert canonicalize_entity_name(raw) == expected

    def test_collapses_whitespace(self):
        assert canonicalize_entity_name("San   Francisco") == "San Francisco"


def _make_entities(company="Apple Inc.", confidence=0.9, role="primary_subject"):
    return ExtractedEntities(
        companies=[EntityWithMetadata(company, confidence, role, "Tech company")],
        products=[],
        people=[],
        technologies=[],
        locations=[],
    )


@pytest.fixture
def setup_test_db():
    """Fresh session with a feed + two test articles for normalization tests."""
    from app.db import SessionLocal, init_db

    init_db()
    session = SessionLocal()
    try:
        seed_default_feed(session)
    except Exception:
        session.rollback()
    session.commit()

    unique = uuid.uuid4().hex
    article_ids = []
    for i in range(2):
        result = session.execute(
            text(
                """
                INSERT INTO items (feed_id, title, url, url_hash, published)
                VALUES (1, :title, :url, :hash, NOW())
                RETURNING id
                """
            ),
            {
                "title": f"Test Article {i}",
                "url": f"http://test.com/entity-norm-{unique}-{i}",
                "hash": f"entity-norm-hash-{unique}-{i}",
            },
        )
        article_ids.append(result.scalar())
    session.commit()

    yield session, article_ids

    try:
        # Deleting the test articles cascades their entity_mentions rows;
        # also clean up any entities left with zero mentions as a result
        # (e.g. "Apple") so mention_count doesn't accumulate across test runs
        # -- entities has no FK back to items, so it isn't cascade-deleted.
        session.execute(
            text("DELETE FROM items WHERE url LIKE 'http://test.com/entity-norm-%'")
        )
        session.execute(
            text(
                "DELETE FROM entities WHERE id NOT IN "
                "(SELECT DISTINCT entity_id FROM entity_mentions)"
            )
        )
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


class TestNormalizeAndStoreEntities:
    def test_creates_entity_and_mention(self, setup_test_db):
        session, (article_id, _) = setup_test_db

        new_count = normalize_and_store_entities(session, article_id, _make_entities())
        session.commit()

        assert new_count == 1
        row = session.execute(
            text(
                "SELECT canonical_name, entity_type, mention_count FROM entities "
                "WHERE lower(canonical_name) = 'apple'"
            )
        ).first()
        assert row is not None
        assert row[0] == "Apple"
        assert row[1] == "company"
        assert row[2] == 1

        mention = session.execute(
            text(
                "SELECT article_id, story_id, mention_context, prominence_score "
                "FROM entity_mentions em JOIN entities e ON e.id = em.entity_id "
                "WHERE lower(e.canonical_name) = 'apple'"
            )
        ).first()
        assert mention is not None
        assert mention[0] == article_id
        assert mention[1] is None
        assert mention[2] == "Tech company"
        # confidence 0.9 * primary_subject multiplier 1.5, capped at 1.0
        assert mention[3] == 1.0

    def test_dedups_suffix_variants_across_articles(self, setup_test_db):
        """'Apple Inc.' and 'Apple' collapse into a single entity row."""
        session, (article_a, article_b) = setup_test_db

        normalize_and_store_entities(
            session, article_a, _make_entities(company="Apple Inc.")
        )
        normalize_and_store_entities(
            session, article_b, _make_entities(company="Apple")
        )
        session.commit()

        rows = session.execute(
            text(
                "SELECT id, mention_count FROM entities "
                "WHERE lower(canonical_name) = 'apple'"
            )
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][1] == 2

        mention_count = session.execute(
            text("SELECT COUNT(*) FROM entity_mentions WHERE entity_id = :id"),
            {"id": rows[0][0]},
        ).scalar()
        assert mention_count == 2

    def test_different_entity_types_stay_separate(self, setup_test_db):
        """Same name, different type (e.g. a person named 'Amazon') doesn't merge."""
        session, (article_id, _) = setup_test_db

        entities = ExtractedEntities(
            companies=[EntityWithMetadata("Amazon", 0.9, "primary_subject", None)],
            products=[],
            people=[EntityWithMetadata("Amazon", 0.6, "mentioned", None)],
            technologies=[],
            locations=[],
        )
        normalize_and_store_entities(session, article_id, entities)
        session.commit()

        rows = session.execute(
            text(
                "SELECT entity_type FROM entities "
                "WHERE lower(canonical_name) = 'amazon' ORDER BY entity_type"
            )
        ).fetchall()
        assert [r[0] for r in rows] == ["company", "person"]

    def test_idempotent_on_repeat_call(self, setup_test_db):
        """Re-normalizing the same article (e.g. cached re-read) is a no-op."""
        session, (article_id, _) = setup_test_db

        first = normalize_and_store_entities(session, article_id, _make_entities())
        session.commit()
        second = normalize_and_store_entities(session, article_id, _make_entities())
        session.commit()

        assert first == 1
        assert second == 0

        mention_count = session.execute(
            text("SELECT COUNT(*) FROM entity_mentions WHERE article_id = :aid"),
            {"aid": article_id},
        ).scalar()
        assert mention_count == 1

        entity_mention_count = session.execute(
            text(
                "SELECT mention_count FROM entities "
                "WHERE lower(canonical_name) = 'apple'"
            )
        ).scalar()
        assert entity_mention_count == 1

    def test_empty_entities_is_noop(self, setup_test_db):
        session, (article_id, _) = setup_test_db

        empty = ExtractedEntities(
            companies=[], products=[], people=[], technologies=[], locations=[]
        )
        new_count = normalize_and_store_entities(session, article_id, empty)
        session.commit()

        assert new_count == 0


class TestLinkEntityMentionsToStory:
    def test_backfills_story_id(self, setup_test_db):
        session, (article_a, article_b) = setup_test_db

        normalize_and_store_entities(session, article_a, _make_entities())
        normalize_and_store_entities(
            session, article_b, _make_entities(company="Apple")
        )
        session.commit()

        now = datetime.now(UTC)
        story_id = create_test_story(
            session,
            title="Test Story",
            synthesis="Synthesis text",
            key_points=["point"],
            why_it_matters="matters",
            topics=["tech"],
            entities=["Apple"],
            importance_score=0.5,
            freshness_score=0.5,
            model="test-model",
            time_window_start=now - timedelta(hours=1),
            time_window_end=now,
        )

        updated = link_entity_mentions_to_story(
            session, story_id=story_id, article_ids=[article_a, article_b]
        )
        session.commit()

        assert updated == 2
        story_ids = session.execute(
            text(
                "SELECT DISTINCT story_id FROM entity_mentions "
                "WHERE article_id IN :ids"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": [article_a, article_b]},
        ).fetchall()
        assert story_ids == [(story_id,)]

    def test_empty_article_list_is_noop(self, setup_test_db):
        session, _ = setup_test_db
        assert link_entity_mentions_to_story(session, 1, []) == 0
