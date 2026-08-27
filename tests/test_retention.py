#!/usr/bin/env python3
"""
Tests for the story-purge leg of retention.py (#346).

cleanup_archived_stories() previously existed in app.stories with no
caller anywhere in the codebase -- get_retention_counts() reported
archived stories as "eligible for purge" but run_retention() never
actually deleted them, so archived stories grew unbounded. This wires
cleanup_archived_stories() into run_retention() via a new _purge_stories()
helper and covers that it now actually deletes what it reports as eligible.

Uses PostgreSQL via DATABASE_URL (ADR-0022).
"""
import os
from datetime import UTC, datetime, timedelta

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from app.retention import get_retention_counts, run_retention
from app.stories import Story
from tests.pg_testutil import (
    create_test_story,
    pg_session_truncate_story_graph,
    seed_default_feed,
)


def setup_test_db():
    session = pg_session_truncate_story_graph()
    seed_default_feed(session)
    session.commit()
    return session


def _make_archived_story(session, title: str, days_old: int) -> int:
    story_id = create_test_story(
        session=session,
        title=title,
        synthesis="X" * 100,
        key_points=["A", "B", "C"],
        why_it_matters="Test",
        topics=["Test"],
        entities=["Test"],
        importance_score=0.5,
        freshness_score=0.5,
        model="test",
        time_window_start=datetime.now(UTC),
        time_window_end=datetime.now(UTC),
    )
    story = session.query(Story).filter(Story.id == story_id).first()
    story.status = "archived"
    story.last_updated = datetime.now(UTC) - timedelta(days=days_old)
    session.commit()
    return story_id


def test_get_retention_counts_reports_eligible_archived_stories():
    session = setup_test_db()
    try:
        _make_archived_story(session, "Old", days_old=100)
        _make_archived_story(session, "Recent", days_old=1)

        counts = get_retention_counts(session)
        assert counts["stories"]["total"] == 2
        assert counts["stories"]["eligible_for_purge"] == 1
    finally:
        session.close()


def test_run_retention_dry_run_does_not_delete_stories():
    session = setup_test_db()
    try:
        old_id = _make_archived_story(session, "Old", days_old=100)

        result = run_retention(session, dry_run=True)
        assert result["stories"]["eligible"] == 1
        assert result["stories"]["deleted"] == 0

        assert session.query(Story).filter(Story.id == old_id).first() is not None
    finally:
        session.close()


def test_run_retention_deletes_old_archived_stories():
    session = setup_test_db()
    try:
        old_id = _make_archived_story(session, "Old", days_old=100)
        recent_id = _make_archived_story(session, "Recent", days_old=1)

        result = run_retention(session, dry_run=False)
        assert result["stories"]["eligible"] == 1
        assert result["stories"]["deleted"] == 1
        assert result["total_deleted"] >= 1

        assert session.query(Story).filter(Story.id == old_id).first() is None
        assert session.query(Story).filter(Story.id == recent_id).first() is not None
    finally:
        session.close()


def test_run_retention_leaves_active_stories_alone():
    session = setup_test_db()
    try:
        story_id = create_test_story(
            session=session,
            title="Active Story",
            synthesis="Y" * 100,
            key_points=["A"],
            why_it_matters="Test",
            topics=["Test"],
            entities=["Test"],
            importance_score=0.5,
            freshness_score=0.5,
            model="test",
            time_window_start=datetime.now(UTC) - timedelta(days=200),
            time_window_end=datetime.now(UTC) - timedelta(days=200),
        )
        story = session.query(Story).filter(Story.id == story_id).first()
        story.last_updated = datetime.now(UTC) - timedelta(days=200)
        session.commit()

        result = run_retention(session, dry_run=False)
        assert result["stories"]["eligible"] == 0
        assert result["stories"]["deleted"] == 0
        assert session.query(Story).filter(Story.id == story_id).first() is not None
    finally:
        session.close()
