"""Tests for app.story_events (#206/#207, ADR-0023, v0.9.2)."""

from __future__ import annotations

import json
import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from datetime import UTC, datetime, timedelta

from app.orm_models import Feed, Item, Story, StoryEvent
from app.story_events import (
    _derive_story_status,
    create_broke_event,
    create_update_event,
    get_story_events,
    refresh_stale_story_statuses,
)
from tests.pg_testutil import (
    create_test_story,
    link_test_articles_to_story,
    pg_session_truncate_story_graph,
)


def _seed_feed(session, feed_id: int = 1, name: str = "Feed A") -> None:
    session.add(Feed(id=feed_id, url=f"http://example.com/feed{feed_id}", name=name))
    session.commit()


def _seed_item(session, item_id: int, feed_id: int) -> None:
    session.add(
        Item(
            id=item_id,
            feed_id=feed_id,
            title=f"Article {item_id}",
            url=f"http://example.com/a{item_id}",
            url_hash=f"hash{item_id}",
        )
    )
    session.commit()


class TestCreateBrokeEvent:
    def test_creates_event_and_sets_lifecycle_fields(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session, 1, "Feed A")
            _seed_feed(session, 2, "Feed B")
            _seed_item(session, 1, 1)
            _seed_item(session, 2, 2)

            now = datetime.now(UTC)
            story = Story(
                id=1,
                title="Breaking story",
                synthesis="x" * 60,
                generated_at=now,
            )
            session.add(story)
            session.flush()

            create_broke_event(session, story, [1, 2])
            session.commit()

            refreshed = session.get(Story, 1)
            assert refreshed.story_status == "breaking"
            assert refreshed.update_count == 0
            assert refreshed.first_reported_at is not None
            assert refreshed.last_major_update is not None

            events = get_story_events(session, 1)
            assert len(events) == 1
            assert events[0]["event_type"] == "broke"
            assert events[0]["source_articles"] == [1, 2]
            assert "2 articles" in events[0]["event_description"]
            assert "2 sources" in events[0]["event_description"]
            assert 0.0 <= events[0]["significance_score"] <= 1.0
        finally:
            session.close()

    def test_singular_wording_for_one_article(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session, 1, "Feed A")
            _seed_item(session, 1, 1)
            story = Story(id=1, title="S", synthesis="x" * 60)
            session.add(story)
            session.flush()

            create_broke_event(session, story, [1])
            session.commit()

            events = get_story_events(session, 1)
            assert (
                events[0]["event_description"]
                == "First reported with 1 article from 1 source"
            )
        finally:
            session.close()


class TestCreateUpdateEvent:
    def _make_old_story(
        self, session, first_reported_at, last_major_update, update_count=0
    ):
        story = Story(
            id=1,
            title="Old story",
            synthesis="x" * 60,
            status="superseded",
            first_reported_at=first_reported_at,
            last_major_update=last_major_update,
            update_count=update_count,
        )
        session.add(story)
        session.flush()
        return story

    def test_small_addition_classified_as_update(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session, 1)
            for i in range(1, 11):
                _seed_item(session, i, 1)

            now = datetime.now(UTC)
            old_story = self._make_old_story(
                session, now - timedelta(hours=1), now - timedelta(hours=1)
            )
            new_story = Story(
                id=2,
                title="New story",
                synthesis="x" * 60,
                previous_version_id=1,
                version=2,
            )
            session.add(new_story)
            session.flush()

            # 1 new article out of 10 total -- well below the development ratio
            create_update_event(session, new_story, old_story, [10], 10)
            session.commit()

            refreshed = session.get(Story, 2)
            assert refreshed.update_count == 1
            assert refreshed.first_reported_at == old_story.first_reported_at

            events = get_story_events(session, 2)
            assert events[0]["event_type"] == "update"
        finally:
            session.close()

    def test_large_addition_classified_as_development(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session, 1)
            for i in range(1, 6):
                _seed_item(session, i, 1)

            now = datetime.now(UTC)
            old_story = self._make_old_story(
                session, now - timedelta(hours=1), now - timedelta(hours=1)
            )
            new_story = Story(
                id=2, title="New", synthesis="x" * 60, previous_version_id=1, version=2
            )
            session.add(new_story)
            session.flush()

            # 3 new articles out of 5 total -- 0.6 ratio, above the 0.4 threshold
            create_update_event(session, new_story, old_story, [3, 4, 5], 5)
            session.commit()

            events = get_story_events(session, 2)
            assert events[0]["event_type"] == "development"
        finally:
            session.close()

    def test_reactivation_after_dormancy_classified_as_development(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session, 1)
            for i in range(1, 11):
                _seed_item(session, i, 1)

            now = datetime.now(UTC)
            # Dormant for well over the dormancy threshold
            old_story = self._make_old_story(
                session, now - timedelta(days=3), now - timedelta(days=3)
            )
            new_story = Story(
                id=2, title="New", synthesis="x" * 60, previous_version_id=1, version=2
            )
            session.add(new_story)
            session.flush()

            # Only 1 new article, but reactivating a dormant story
            create_update_event(session, new_story, old_story, [10], 10)
            session.commit()

            events = get_story_events(session, 2)
            assert events[0]["event_type"] == "development"
        finally:
            session.close()

    def test_carries_forward_update_count_and_first_reported_at(self):
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session, 1)
            for i in range(1, 4):
                _seed_item(session, i, 1)

            now = datetime.now(UTC)
            first_reported = now - timedelta(days=2)
            old_story = self._make_old_story(
                session, first_reported, now - timedelta(hours=1), update_count=2
            )
            new_story = Story(
                id=2, title="New", synthesis="x" * 60, previous_version_id=1, version=3
            )
            session.add(new_story)
            session.flush()

            create_update_event(session, new_story, old_story, [3], 3)
            session.commit()

            refreshed = session.get(Story, 2)
            assert refreshed.update_count == 3
            assert refreshed.first_reported_at == first_reported
        finally:
            session.close()


class TestDeriveStoryStatus:
    def test_no_first_reported_at_is_breaking(self):
        assert (
            _derive_story_status(
                first_reported_at=None, last_major_update=None, update_count=0
            )
            == "breaking"
        )

    def test_fresh_story_no_updates_is_breaking(self):
        now = datetime.now(UTC)
        assert (
            _derive_story_status(
                first_reported_at=now, last_major_update=now, update_count=0, now=now
            )
            == "breaking"
        )

    def test_any_update_makes_it_developing(self):
        now = datetime.now(UTC)
        assert (
            _derive_story_status(
                first_reported_at=now, last_major_update=now, update_count=1, now=now
            )
            == "developing"
        )

    def test_old_breaking_story_becomes_developing(self):
        now = datetime.now(UTC)
        first_reported = now - timedelta(hours=7)
        assert (
            _derive_story_status(
                first_reported_at=first_reported,
                last_major_update=first_reported,
                update_count=0,
                now=now,
            )
            == "developing"
        )

    def test_long_quiet_story_becomes_established(self):
        now = datetime.now(UTC)
        last_update = now - timedelta(hours=49)
        assert (
            _derive_story_status(
                first_reported_at=now - timedelta(days=5),
                last_major_update=last_update,
                update_count=3,
                now=now,
            )
            == "established"
        )

    def test_naive_datetime_handled_without_error(self):
        """Rows written before tz-aware columns existed shouldn't crash this."""
        now = datetime.now(UTC)
        naive_first_reported = (now - timedelta(hours=1)).replace(tzinfo=None)
        status = _derive_story_status(
            first_reported_at=naive_first_reported,
            last_major_update=naive_first_reported,
            update_count=0,
            now=now,
        )
        assert status == "breaking"


class TestRefreshStaleStoryStatuses:
    def test_transitions_stale_breaking_to_developing(self):
        session = pg_session_truncate_story_graph()
        try:
            now = datetime.now(UTC)
            old_breaking = Story(
                id=1,
                title="S",
                synthesis="x" * 60,
                status="active",
                story_status="breaking",
                first_reported_at=now - timedelta(hours=7),
                last_major_update=now - timedelta(hours=7),
                update_count=0,
            )
            session.add(old_breaking)
            session.commit()

            updated = refresh_stale_story_statuses(session)
            assert updated == 1

            refreshed = session.get(Story, 1)
            assert refreshed.story_status == "developing"
        finally:
            session.close()

    def test_transitions_stale_developing_to_established(self):
        session = pg_session_truncate_story_graph()
        try:
            now = datetime.now(UTC)
            stale = Story(
                id=1,
                title="S",
                synthesis="x" * 60,
                status="active",
                story_status="developing",
                first_reported_at=now - timedelta(days=5),
                last_major_update=now - timedelta(hours=49),
                update_count=2,
            )
            session.add(stale)
            session.commit()

            updated = refresh_stale_story_statuses(session)
            assert updated == 1

            refreshed = session.get(Story, 1)
            assert refreshed.story_status == "established"
        finally:
            session.close()

    def test_leaves_fresh_breaking_story_untouched(self):
        session = pg_session_truncate_story_graph()
        try:
            now = datetime.now(UTC)
            fresh = Story(
                id=1,
                title="S",
                synthesis="x" * 60,
                status="active",
                story_status="breaking",
                first_reported_at=now,
                last_major_update=now,
                update_count=0,
            )
            session.add(fresh)
            session.commit()

            updated = refresh_stale_story_statuses(session)
            assert updated == 0

            refreshed = session.get(Story, 1)
            assert refreshed.story_status == "breaking"
        finally:
            session.close()

    def test_ignores_superseded_stories(self):
        session = pg_session_truncate_story_graph()
        try:
            now = datetime.now(UTC)
            superseded = Story(
                id=1,
                title="S",
                synthesis="x" * 60,
                status="superseded",
                story_status="breaking",
                first_reported_at=now - timedelta(hours=7),
                last_major_update=now - timedelta(hours=7),
                update_count=0,
            )
            session.add(superseded)
            session.commit()

            updated = refresh_stale_story_statuses(session)
            assert updated == 0
        finally:
            session.close()


class TestGetStoryEvents:
    def test_returns_events_in_chronological_order(self):
        session = pg_session_truncate_story_graph()
        try:
            story = Story(id=1, title="S", synthesis="x" * 60)
            session.add(story)
            session.flush()

            now = datetime.now(UTC)
            session.add_all(
                [
                    StoryEvent(
                        story_id=1,
                        event_type="update",
                        occurred_at=now,
                        source_articles_json=json.dumps([2]),
                    ),
                    StoryEvent(
                        story_id=1,
                        event_type="broke",
                        occurred_at=now - timedelta(hours=1),
                        source_articles_json=json.dumps([1]),
                    ),
                ]
            )
            session.commit()

            events = get_story_events(session, 1)
            assert [e["event_type"] for e in events] == ["broke", "update"]
        finally:
            session.close()

    def test_handles_malformed_source_articles_json(self):
        session = pg_session_truncate_story_graph()
        try:
            story = Story(id=1, title="S", synthesis="x" * 60)
            session.add(story)
            session.flush()
            session.add(
                StoryEvent(
                    story_id=1,
                    event_type="broke",
                    occurred_at=datetime.now(UTC),
                    source_articles_json="not json",
                )
            )
            session.commit()

            events = get_story_events(session, 1)
            assert events[0]["source_articles"] == []
        finally:
            session.close()

    def test_no_events_returns_empty_list(self):
        session = pg_session_truncate_story_graph()
        try:
            story = Story(id=1, title="S", synthesis="x" * 60)
            session.add(story)
            session.commit()

            assert get_story_events(session, 1) == []
        finally:
            session.close()


class TestGetStoryByIdLifecycleFields:
    """app.stories.get_story_by_id() surfacing story_status/first_reported_at/
    last_major_update/update_count/events on StoryOut (v0.9.2, #283/#208)."""

    def test_fresh_story_exposes_broke_event_and_lifecycle_fields(self):
        from app.stories import get_story_by_id

        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session, 1)
            _seed_item(session, 1, 1)

            now = datetime.now(UTC)
            story_id = create_test_story(
                session,
                title="Test story",
                synthesis="A test synthesis sentence that is long enough to pass the fifty character minimum length validator.",
                key_points=["point"],
                why_it_matters="It matters.",
                topics=["General"],
                entities=["TestCo"],
                importance_score=0.5,
                freshness_score=0.5,
                model="test-model",
                time_window_start=now,
                time_window_end=now,
                story_hash="test-events-fresh",
            )
            link_test_articles_to_story(session, story_id, [1], 1)

            story = session.get(Story, story_id)
            create_broke_event(session, story, [1])
            session.commit()

            out = get_story_by_id(session, story_id)
            assert out is not None
            assert out.story_status == "breaking"
            assert out.update_count == 0
            assert out.first_reported_at is not None
            assert len(out.events) == 1
            assert out.events[0]["event_type"] == "broke"
        finally:
            session.close()

    def test_story_with_no_events_has_empty_list_and_defaults(self):
        """Pre-migration rows (no events, default lifecycle columns) shouldn't error."""
        from app.stories import get_story_by_id

        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session, 1)
            _seed_item(session, 1, 1)

            now = datetime.now(UTC)
            story_id = create_test_story(
                session,
                title="Old-style story",
                synthesis="A test synthesis sentence that is long enough to pass the fifty character minimum length validator.",
                key_points=["point"],
                why_it_matters="It matters.",
                topics=["General"],
                entities=["TestCo"],
                importance_score=0.5,
                freshness_score=0.5,
                model="test-model",
                time_window_start=now,
                time_window_end=now,
                story_hash="test-events-defaults",
            )
            link_test_articles_to_story(session, story_id, [1], 1)

            out = get_story_by_id(session, story_id)
            assert out is not None
            assert out.events == []
            assert out.story_status == "breaking"
            assert out.update_count == 0
            assert out.first_reported_at is None
        finally:
            session.close()


class TestGetStoriesOrderByUpdated:
    """app.stories.get_stories(order_by='updated') (v0.9.2, #209 descoped)."""

    def test_sorts_by_last_major_update_descending(self):
        from app.stories import get_stories

        session = pg_session_truncate_story_graph()
        try:
            now = datetime.now(UTC)
            # Story 1: generated a day ago, never updated -- falls back to
            # its (stale) generated_at for the coalesce.
            session.add(
                Story(
                    id=1,
                    title="Stale, never updated",
                    synthesis="x" * 60,
                    article_count=1,
                    status="active",
                    generated_at=now - timedelta(days=1),
                    last_major_update=None,
                )
            )
            # Story 2: generated two days ago, but updated 5 minutes ago --
            # its actual last_major_update should outrank story 1's stale
            # generated_at fallback.
            session.add(
                Story(
                    id=2,
                    title="Older but just updated",
                    synthesis="x" * 60,
                    article_count=1,
                    status="active",
                    generated_at=now - timedelta(days=2),
                    last_major_update=now - timedelta(minutes=5),
                )
            )
            session.commit()

            results = get_stories(session, order_by="updated")
            assert [s.id for s in results] == [2, 1]
        finally:
            session.close()
