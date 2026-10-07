"""Tests for app.anomaly_detection (#219, ADR-0023, v0.10.1)."""

from __future__ import annotations

import os

import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("PostgreSQL required (set DATABASE_URL)", allow_module_level=True)

from datetime import UTC, datetime, timedelta

from app.anomaly_detection import (
    detect_anomalies,
    detect_new_entrants,
    detect_silences,
    detect_spikes,
)
from app.orm_models import Item
from app.trend_detection import clear_trend_cache
from tests.pg_testutil import pg_session_truncate_story_graph, seed_default_feed


def _utc_today():
    return datetime.now(UTC).date()


def _seed_items(session, topic: str, counts_by_days_ago: dict, feed_id: int = 1):
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


class TestDetectSpikes:
    def test_steady_baseline_no_spike(self):
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            # Steady 3/day for 30 days baseline + today also 3 -> no spike.
            _seed_items(session, "ai-ml", {d: 3 for d in range(0, 31)})

            spikes = detect_spikes(session)
            assert spikes == []
        finally:
            session.close()

    def test_statistically_significant_jump_is_spike(self):
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            # Baseline with some natural variation (2-4/day), today jumps to 20.
            baseline = {d: (2 if d % 2 == 0 else 4) for d in range(1, 31)}
            baseline[0] = 20
            _seed_items(session, "politics", baseline)

            spikes = detect_spikes(session)
            assert len(spikes) == 1
            assert spikes[0].topic == "politics"
            assert spikes[0].anomaly_type == "spike"
            assert spikes[0].severity in ("high", "medium")
        finally:
            session.close()

    def test_small_count_not_flagged_as_spike(self):
        """A topic with baseline of 0 getting 1 article today shouldn't be
        a 'spike' -- that's just #217's 'emerging', not statistically
        significant anomaly noise."""
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            _seed_items(session, "sports", {0: 1})

            spikes = detect_spikes(session)
            assert spikes == []
        finally:
            session.close()

    def test_zero_variance_baseline_with_today_difference(self):
        """Baseline always exactly 2/day (stdev=0); today is 5 -> flagged
        high severity even though no z-score is computable."""
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            baseline = {d: 2 for d in range(1, 31)}
            baseline[0] = 5
            _seed_items(session, "business", baseline)

            spikes = detect_spikes(session)
            assert len(spikes) == 1
            assert spikes[0].severity == "high"
        finally:
            session.close()


class TestDetectSilences:
    def test_reliable_topic_going_silent_is_flagged(self):
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            # Covered every day for the last 30 days except today (0).
            counts = {d: 2 for d in range(1, 31)}
            _seed_items(session, "ai-ml", counts)

            silences = detect_silences(session)
            assert len(silences) == 1
            assert silences[0].topic == "ai-ml"
            assert silences[0].anomaly_type == "silence"
        finally:
            session.close()

    def test_rarely_covered_topic_not_flagged(self):
        """A topic that only gets covered once every couple of weeks
        shouldn't trigger a 'silence' alert for an ordinary zero day."""
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            _seed_items(session, "gaming", {15: 1})  # one article, 15 days ago

            silences = detect_silences(session)
            assert silences == []
        finally:
            session.close()

    def test_topic_with_articles_today_not_silent(self):
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            counts = {d: 2 for d in range(0, 31)}  # includes today
            _seed_items(session, "ai-ml", counts)

            silences = detect_silences(session)
            assert silences == []
        finally:
            session.close()


class TestDetectNewEntrants:
    def test_first_time_source_on_established_topic_is_flagged(self):
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session, feed_id=1, name="Established Feed")
            seed_default_feed(
                session, feed_id=2, url="http://example.com/feed2", name="New Feed"
            )
            # Feed 1 has covered "ai-ml" for weeks, including today.
            _seed_items(session, "ai-ml", {d: 1 for d in range(0, 20)}, feed_id=1)
            # Feed 2 covers "ai-ml" for the first time today only.
            _seed_items(session, "ai-ml", {0: 1}, feed_id=2)

            entrants = detect_new_entrants(session)
            assert len(entrants) == 1
            assert entrants[0].topic == "ai-ml"
            assert entrants[0].anomaly_type == "new_entrant"
            assert "New Feed" in entrants[0].description
        finally:
            session.close()

    def test_brand_new_topic_is_not_a_new_entrant(self):
        """If NO feed has covered the topic before today, that's an
        emerging topic (#217), not a 'new entrant' anomaly."""
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            _seed_items(session, "sports", {0: 2})

            entrants = detect_new_entrants(session)
            assert entrants == []
        finally:
            session.close()

    def test_returning_source_not_flagged(self):
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            # Same feed covered this topic 10 days ago AND today.
            _seed_items(session, "ai-ml", {10: 1, 0: 1}, feed_id=1)

            entrants = detect_new_entrants(session)
            assert entrants == []
        finally:
            session.close()


class TestDetectAnomalies:
    def test_combines_and_sorts_by_severity(self):
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session, feed_id=1, name="Feed One")
            seed_default_feed(
                session, feed_id=2, url="http://example.com/feed2", name="Feed Two"
            )

            # Silence (medium): reliable topic goes quiet today.
            _seed_items(session, "ai-ml", {d: 2 for d in range(1, 31)}, feed_id=1)
            # Spike (high): zero-variance baseline, today way above it.
            spike_counts = {d: 2 for d in range(1, 31)}
            spike_counts[0] = 20
            _seed_items(session, "politics", spike_counts, feed_id=1)
            # New entrant (low): feed 2 covers politics for the first time today.
            _seed_items(session, "politics", {0: 1}, feed_id=2)

            anomalies = detect_anomalies(session)
            severities = [a.severity for a in anomalies]
            # high (spike) should sort before medium (silence) before low (new_entrant)
            assert severities.index("high") < severities.index("medium")
            assert severities.index("medium") < severities.index("low")
        finally:
            session.close()

    def test_no_data_no_anomalies(self):
        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            assert detect_anomalies(session) == []
        finally:
            session.close()

    def test_to_dict_is_json_serializable(self):
        import json

        session = pg_session_truncate_story_graph()
        try:
            clear_trend_cache()
            seed_default_feed(session)
            baseline = {d: 2 for d in range(1, 31)}
            baseline[0] = 20
            _seed_items(session, "ai-ml", baseline)

            anomalies = detect_anomalies(session)
            json.dumps([a.to_dict() for a in anomalies])  # must not raise
        finally:
            session.close()
