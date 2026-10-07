"""Tests for app.trend_detection (#217, ADR-0023, v0.10.1)."""

from __future__ import annotations

import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from datetime import UTC, datetime, timedelta

from app.orm_models import Item
from app.trend_detection import clear_trend_cache, compute_topic_trends
from tests.pg_testutil import pg_session_truncate_story_graph, seed_default_feed


def _utc_today():
    return datetime.now(UTC).date()


def _seed_items(session, topic: str, counts_by_days_ago: dict, feed_id: int = 1):
    """Insert ``sum(counts_by_days_ago.values())`` items for ``topic``, spread
    across the given {days_ago: count} map. Each item gets a distinct URL/hash
    so the unique constraint on url_hash doesn't collide across calls."""
    today = _utc_today()
    item_id = _seed_items.counter
    for days_ago, count in counts_by_days_ago.items():
        published = datetime.combine(
            today - timedelta(days=days_ago), datetime.min.time(), tzinfo=UTC
        ) + timedelta(hours=12)
        for _ in range(count):
            item_id += 1
            session.add(
                Item(
                    id=item_id,
                    feed_id=feed_id,
                    title=f"{topic} article {item_id}",
                    url=f"http://example.com/{item_id}",
                    url_hash=f"hash-{item_id}",
                    published=published,
                    topic=topic,
                )
            )
    session.commit()
    _seed_items.counter = item_id


_seed_items.counter = 0


class TestComputeTopicTrends:
    def test_no_items_returns_empty_list(self):
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            trends = compute_topic_trends(session, use_cache=False)
            assert trends == []
        finally:
            session.close()

    def test_steady_topic_is_stable(self):
        """Same count every day (including today) -> velocity ~= 1.0, stable."""
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            # 3 articles/day for the last 8 days (today + 7-day baseline).
            _seed_items(session, "ai-ml", {d: 3 for d in range(0, 8)})

            trends = compute_topic_trends(session, use_cache=False)
            assert len(trends) == 1
            t = trends[0]
            assert t.topic == "ai-ml"
            assert t.today_count == 3
            assert t.baseline_avg == pytest.approx(3.0)
            assert t.velocity == pytest.approx(1.0)
            assert t.trend_direction == "stable"
            assert t.is_hot is False
        finally:
            session.close()

    def test_spike_is_hot(self):
        """Baseline of 2/day, today spikes to 10 -> velocity 5.0, hot."""
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            counts = {d: 2 for d in range(1, 8)}  # baseline days 1-7
            counts[0] = 10  # today
            _seed_items(session, "politics", counts)

            trends = compute_topic_trends(session, use_cache=False)
            assert len(trends) == 1
            t = trends[0]
            assert t.today_count == 10
            assert t.baseline_avg == pytest.approx(2.0)
            assert t.velocity == pytest.approx(5.0)
            assert t.trend_direction == "hot"
            assert t.is_hot is True
        finally:
            session.close()

    def test_new_topic_with_no_baseline_is_emerging(self):
        """Articles only today, nothing in the baseline window -> emerging,
        with velocity=None (no baseline to divide by)."""
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            _seed_items(session, "sports", {0: 4})

            trends = compute_topic_trends(session, use_cache=False)
            assert len(trends) == 1
            t = trends[0]
            assert t.today_count == 4
            assert t.baseline_avg == 0.0
            assert t.velocity is None
            assert t.trend_direction == "emerging"
        finally:
            session.close()

    def test_declining_topic(self):
        """Baseline of 10/day, today drops to 1 -> velocity 0.1, declining."""
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            counts = {d: 10 for d in range(1, 8)}
            counts[0] = 1
            _seed_items(session, "business", counts)

            trends = compute_topic_trends(session, use_cache=False)
            assert len(trends) == 1
            t = trends[0]
            assert t.velocity == pytest.approx(0.1)
            assert t.trend_direction == "declining"
        finally:
            session.close()

    def test_topic_with_only_old_activity_is_omitted(self):
        """A topic that had articles only outside the window entirely (older
        than the baseline window) and nothing today shouldn't appear."""
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            # All activity 20 days ago -- outside the default 14-day window.
            _seed_items(session, "science", {20: 5})

            trends = compute_topic_trends(
                session, days=14, baseline_days=7, use_cache=False
            )
            assert trends == []
        finally:
            session.close()

    def test_sorted_hot_before_stable_before_emerging(self):
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            # "hot": baseline 2/day, today 10 (velocity 5.0)
            hot_counts = {d: 2 for d in range(1, 8)}
            hot_counts[0] = 10
            _seed_items(session, "politics", hot_counts)
            # "stable": steady 3/day
            _seed_items(session, "ai-ml", {d: 3 for d in range(0, 8)})
            # "emerging": only today, no baseline
            _seed_items(session, "sports", {0: 1})

            trends = compute_topic_trends(session, use_cache=False)
            directions = [t.trend_direction for t in trends]
            assert directions == ["hot", "stable", "emerging"]
        finally:
            session.close()

    def test_sparkline_length_matches_days_and_fills_gaps(self):
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            # Only today + 3 days ago have articles; everything else should
            # be filled with 0 in the sparkline.
            _seed_items(session, "ai-ml", {0: 2, 3: 5})

            trends = compute_topic_trends(
                session, days=14, baseline_days=7, use_cache=False
            )
            assert len(trends) == 1
            sparkline = trends[0].sparkline
            assert len(sparkline) == 14
            assert sparkline[-1] == 2  # today is the last entry (oldest -> newest)
            assert sparkline[-4] == 5  # 3 days ago
            assert sum(sparkline) == 7

        finally:
            session.close()

    def test_coverage_breadth_counts_distinct_sources(self):
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session, feed_id=1, name="Feed One")
            seed_default_feed(
                session, feed_id=2, url="http://example.com/feed2", name="Feed Two"
            )
            _seed_items(session, "ai-ml", {0: 2}, feed_id=1)
            _seed_items(session, "ai-ml", {0: 1}, feed_id=2)

            trends = compute_topic_trends(session, use_cache=False)
            assert len(trends) == 1
            t = trends[0]
            assert t.coverage_breadth == 2
            assert set(t.sources) == {"Feed One", "Feed Two"}
        finally:
            session.close()

    def test_cache_returns_stale_result_until_cleared(self):
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            _seed_items(session, "ai-ml", {0: 1})

            first = compute_topic_trends(session, use_cache=True)
            assert len(first) == 1

            # Add more data for a NEW topic; cached call shouldn't see it.
            _seed_items(session, "sports", {0: 1})
            cached = compute_topic_trends(session, use_cache=True)
            assert len(cached) == 1  # still the stale cached result

            clear_trend_cache()
            fresh = compute_topic_trends(session, use_cache=True)
            assert len(fresh) == 2
        finally:
            session.close()

    def test_small_days_window_still_computes_correct_baseline(self):
        """Regression: when `days` (sparkline window) is close to or smaller
        than baseline_days + 1, the baseline/acceleration lookback used to
        read past the fetched window and silently undercount. Baseline here
        needs data back to 7 days ago, and acceleration's yesterday-baseline
        needs back to 8 days ago -- both outside a naive `days=7` fetch
        window if not handled."""
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            # Steady 3/day for the last 9 days (today=0 .. 8 days ago),
            # requested with a *small* `days` window (7) but the default
            # 7-day baseline -- acceleration needs day 8 too.
            _seed_items(session, "ai-ml", {d: 3 for d in range(0, 9)})

            trends = compute_topic_trends(
                session, days=7, baseline_days=7, use_cache=False
            )
            assert len(trends) == 1
            t = trends[0]
            # If the fetch window were wrongly clipped to the last 7 days,
            # the baseline would miss day -7's contribution and/or
            # acceleration would see a phantom drop from a missing day -8.
            assert t.baseline_avg == pytest.approx(3.0)
            assert t.velocity == pytest.approx(1.0)
            assert t.acceleration == pytest.approx(0.0)
            assert len(t.sparkline) == 7
        finally:
            session.close()

    def test_to_dict_is_json_serializable(self):
        import json

        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            _seed_items(session, "ai-ml", {0: 1})

            trends = compute_topic_trends(session, use_cache=False)
            json.dumps([t.to_dict() for t in trends])  # must not raise
        finally:
            session.close()
