"""Tests for app.entity_backfill (#199, ADR-0023, v0.9.0)."""

from __future__ import annotations

import json
import os
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal, init_db
from app.entity_backfill import (
    _link_mentions_to_existing_stories,
    _parse_args,
    _pending_count,
    _run_backfill,
)
from tests.pg_testutil import seed_default_feed


def test_parse_args_entity_backfill() -> None:
    args = _parse_args(["entity-backfill", "--dry-run", "--batch-size", "10"])
    assert args.command == "entity-backfill"
    assert args.dry_run is True
    assert args.batch_size == 10


def test_resolve_database_url_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.entity_backfill import resolve_database_url_for_cli

    monkeypatch.delenv("DATABASE_URL", raising=False)
    args = _parse_args(["entity-backfill", "--dry-run"])
    assert resolve_database_url_for_cli(args) == 2


@pytest.fixture
def backfill_db():
    """Fresh session + a feed + one article with a cached entities_json."""
    init_db()
    session = SessionLocal()
    try:
        seed_default_feed(session)
    except Exception:
        session.rollback()
    session.commit()

    unique = uuid.uuid4().hex
    entities_json = json.dumps(
        {
            "version": 2,
            "companies": [
                {
                    "name": "Globex Corp.",
                    "confidence": 0.9,
                    "role": "primary_subject",
                    "disambiguation": None,
                }
            ],
            "products": [],
            "people": [],
            "technologies": [],
            "locations": [],
        }
    )
    result = session.execute(
        text(
            """
            INSERT INTO items
                (feed_id, title, url, url_hash, published, entities_json, entities_model)
            VALUES (1, 'Backfill Test Article', :url, :hash, NOW(), :ejson, 'test-model')
            RETURNING id
            """
        ),
        {
            "url": f"http://test.com/entity-backfill-{unique}",
            "hash": f"entity-backfill-hash-{unique}",
            "ejson": entities_json,
        },
    )
    article_id = result.scalar()
    session.commit()

    yield session, article_id

    try:
        session.execute(
            text("DELETE FROM items WHERE url LIKE 'http://test.com/entity-backfill-%'")
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


class TestBackfillIntegration:
    def test_pending_count_and_run_backfill(self, backfill_db):
        session, article_id = backfill_db

        pending_before = _pending_count(session)
        assert pending_before >= 1

        processed, new_mentions, errors = _run_backfill(
            SessionLocal, batch_size=50, limit=None, total_pending=pending_before
        )

        assert errors == 0
        assert processed >= 1
        assert new_mentions >= 1

        row = session.execute(
            text(
                "SELECT canonical_name FROM entities e "
                "JOIN entity_mentions em ON em.entity_id = e.id "
                "WHERE em.article_id = :aid"
            ),
            {"aid": article_id},
        ).first()
        assert row is not None
        assert row[0] == "Globex"  # "Corp." suffix stripped

        pending_after = _pending_count(session)
        assert pending_after < pending_before

    def test_run_backfill_is_idempotent(self, backfill_db):
        session, article_id = backfill_db

        pending = _pending_count(session)
        _run_backfill(SessionLocal, batch_size=50, limit=None, total_pending=pending)

        # Second pass: nothing left pending, nothing new to do.
        processed, new_mentions, errors = _run_backfill(
            SessionLocal, batch_size=50, limit=None, total_pending=0
        )
        assert processed == 0
        assert new_mentions == 0
        assert errors == 0

    def test_link_mentions_to_existing_stories(self, backfill_db):
        from datetime import UTC, datetime, timedelta

        from tests.pg_testutil import create_test_story, link_test_articles_to_story

        session, article_id = backfill_db
        pending = _pending_count(session)
        _run_backfill(SessionLocal, batch_size=50, limit=None, total_pending=pending)

        now = datetime.now(UTC)
        story_id = create_test_story(
            session,
            title="Backfill Story",
            synthesis="synthesis",
            key_points=["p"],
            why_it_matters="matters",
            topics=["tech"],
            entities=["Globex"],
            importance_score=0.5,
            freshness_score=0.5,
            model="test-model",
            time_window_start=now - timedelta(hours=1),
            time_window_end=now,
        )
        link_test_articles_to_story(session, story_id, [article_id])

        linked = _link_mentions_to_existing_stories(session)
        session.commit()

        assert linked >= 1
        result = session.execute(
            text("SELECT story_id FROM entity_mentions WHERE article_id = :aid"),
            {"aid": article_id},
        ).scalar()
        assert result == story_id
