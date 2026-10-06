"""Topic velocity and trend detection (#217, ADR-0023, v0.10.1).

Rule-based (no LLM call) -- detects which topics are getting more or less
coverage than their recent baseline, using data that already exists:
``items.topic`` (set by ``app/topics.py`` classification) and
``items.published``.

Scope decisions made at the v0.10.1 planning checkpoint:

1. **Live computation, no new table.** At this app's actual volume
   (~15-70 articles/day across ~10 topics, confirmed against the real prod
   DB while scoping this) a persisted daily-snapshot table + scheduled job
   would be premature infrastructure for what a handful of ``GROUP BY``
   queries over ``items`` already answers cheaply. A short in-process cache
   (mirroring ``app/topics.py``'s ``_topics_cache`` pattern) avoids
   recomputing on every request without needing a migration. This also
   trivially satisfies #217's "near-real-time" acceptance criterion --
   results are always as fresh as the cache TTL.
2. **Daily buckets, not hourly.** #217's issue text mentions "articles per
   hour/day", but at this volume hourly buckets would be almost entirely
   zeros/ones and provide no real signal. Descoped to daily only.
3. **Sentiment-shift is explicitly descoped.** #217's "Trend Metrics" and
   #219's "Sentiment flip" anomaly both want a sentiment signal, but
   ``items.perspective_json.tone`` (v0.9.1) is only populated on ~8% of
   articles and is ``null`` even then unless the article reads as clearly
   opinionated -- a signal built on it would almost always be empty. Flagged
   here rather than silently dropped; revisit if perspective coverage
   improves.

Known limitation: "today"'s bucket is necessarily partial (the UTC day
isn't over yet when this runs), so velocity computed early in the day can
understate a topic that's about to pick up. Acceptable for a first pass --
the dashboard re-queries live, so it corrects itself as the day progresses.

Public API:
- ``compute_topic_trends(session, days=14, baseline_days=7)`` -> List[TopicTrend]
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from .topics import get_topic_display_name

# -----------------------------------------------------------------------------
# Tunables
# -----------------------------------------------------------------------------

DEFAULT_WINDOW_DAYS = 14  # history kept for sparklines + baseline
DEFAULT_BASELINE_DAYS = 7  # trailing days averaged for the baseline (excludes today)

# Velocity thresholds (today_count / baseline_avg) for trend_direction.
HOT_VELOCITY = 2.0  # >= 2x baseline -> "hot"
GROWING_VELOCITY = 1.2  # >= 1.2x baseline -> "growing"
DECLINING_VELOCITY = 0.8  # < 0.8x baseline -> "declining"

MAX_SOURCES_LISTED = 8  # cap on source names returned per topic

_CACHE_TTL_SECONDS = 300  # 5 minutes
_cache: Dict[Tuple[int, int], Tuple[float, List["TopicTrend"]]] = {}


# -----------------------------------------------------------------------------
# Result type
# -----------------------------------------------------------------------------


@dataclass
class TopicTrend:
    """Trend summary for a single topic, as of "today" (UTC)."""

    topic: str
    display_name: str
    today_count: int
    baseline_avg: float
    velocity: Optional[float]  # None when baseline_avg == 0 (see trend_direction)
    acceleration: Optional[
        float
    ]  # velocity(today) - velocity(yesterday); None if either is undefined
    coverage_breadth: int  # distinct sources (feeds) covering this topic today
    trend_direction: str  # "emerging" | "hot" | "growing" | "stable" | "declining"
    is_hot: bool
    sparkline: List[int] = field(default_factory=list)  # daily counts, oldest -> newest
    sources: List[str] = field(default_factory=list)  # source names covering it today

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "display_name": self.display_name,
            "today_count": self.today_count,
            "baseline_avg": round(self.baseline_avg, 2),
            "velocity": round(self.velocity, 2) if self.velocity is not None else None,
            "acceleration": (
                round(self.acceleration, 2) if self.acceleration is not None else None
            ),
            "coverage_breadth": self.coverage_breadth,
            "trend_direction": self.trend_direction,
            "is_hot": self.is_hot,
            "sparkline": self.sparkline,
            "sources": self.sources,
        }


# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------


def get_daily_topic_counts(
    session: Session, start_day: date, end_day: date
) -> Dict[str, Dict[date, int]]:
    """Return ``{topic: {day: count}}`` for ``items.published`` in
    ``[start_day, end_day]`` (inclusive), using whatever topic classification
    is already on each item. Days with zero articles for a topic simply
    don't appear in that topic's inner dict -- callers fill gaps.

    Public (not module-private) because ``app/anomaly_detection.py`` (#219)
    reuses this exact aggregation rather than re-deriving it."""
    rows = session.execute(
        text(
            """
            SELECT topic, (published AT TIME ZONE 'UTC')::date AS day, COUNT(*)
            FROM items
            WHERE published IS NOT NULL
              AND topic IS NOT NULL
              AND (published AT TIME ZONE 'UTC')::date BETWEEN :start_day AND :end_day
            GROUP BY topic, day
            """
        ),
        {"start_day": start_day, "end_day": end_day},
    ).fetchall()

    result: Dict[str, Dict[date, int]] = {}
    for topic, day, count in rows:
        result.setdefault(topic, {})[day] = count
    return result


def _today_coverage(session: Session, today: date) -> Dict[str, List[str]]:
    """Return ``{topic: [source names]}`` for items published "today" (UTC),
    one entry per distinct source. Used for coverage breadth + display."""
    rows = session.execute(
        text(
            """
            SELECT i.topic, f.name
            FROM items i
            JOIN feeds f ON f.id = i.feed_id
            WHERE i.published IS NOT NULL
              AND i.topic IS NOT NULL
              AND (i.published AT TIME ZONE 'UTC')::date = :today
            GROUP BY i.topic, f.name
            """
        ),
        {"today": today},
    ).fetchall()

    result: Dict[str, List[str]] = {}
    for topic, source_name in rows:
        result.setdefault(topic, []).append(source_name or "Unknown source")
    return result


def _velocity(today_count: int, baseline_avg: float) -> Optional[float]:
    """``None`` means "no baseline to compare against" (see trend_direction's
    "emerging" case), not "zero velocity"."""
    if baseline_avg <= 0:
        return None
    return today_count / baseline_avg


def _classify(today_count: int, baseline_avg: float, velocity: Optional[float]) -> str:
    if velocity is None:
        return "emerging" if today_count > 0 else "stable"
    if velocity >= HOT_VELOCITY:
        return "hot"
    if velocity >= GROWING_VELOCITY:
        return "growing"
    if velocity < DECLINING_VELOCITY:
        return "declining"
    return "stable"


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------


def compute_topic_trends(
    session: Session,
    days: int = DEFAULT_WINDOW_DAYS,
    baseline_days: int = DEFAULT_BASELINE_DAYS,
    use_cache: bool = True,
) -> List[TopicTrend]:
    """Compute per-topic velocity/trend data for "today" (UTC), sorted by
    velocity descending (topics with no comparable baseline -- i.e.
    "emerging" -- sort after everything with a real velocity, since there's
    nothing to rank them against; ties broken by today_count descending).

    Topics with zero activity in both "today" and the baseline window are
    omitted entirely -- there's nothing to report.

    Args:
        session: SQLAlchemy session.
        days: Days of history shown in each topic's sparkline (includes
            today).
        baseline_days: Trailing days (immediately before today, excluding
            today) averaged to form each topic's baseline.
        use_cache: Serve/populate the module-level TTL cache. Tests that
            seed data and immediately assert on it should pass
            ``use_cache=False`` to avoid reading a stale cached result.

    Returns:
        List of ``TopicTrend``, one per topic with any recent activity.
    """
    cache_key = (days, baseline_days)
    if use_cache:
        cached = _cache.get(cache_key)
        if cached is not None:
            cached_at, cached_result = cached
            if time.monotonic() - cached_at < _CACHE_TTL_SECONDS:
                return cached_result

    today = datetime.now(UTC).date()
    sparkline_start = today - timedelta(days=days - 1)

    # Acceleration compares *yesterday's* velocity (itself needing a full
    # baseline_days window before yesterday) to today's -- that reaches
    # baseline_days + 1 days further back than "today". Query however far
    # back is actually needed (sparkline window vs. baseline+acceleration
    # window, whichever is larger) and only *display* the last `days`.
    fetch_start = min(sparkline_start, today - timedelta(days=baseline_days + 1))

    daily_counts = get_daily_topic_counts(session, fetch_start, today)
    today_sources = _today_coverage(session, today)

    topics = set(daily_counts.keys())

    trends: List[TopicTrend] = []
    for topic in topics:
        counts_by_day = daily_counts.get(topic, {})

        today_count = counts_by_day.get(today, 0)
        baseline_window = [
            counts_by_day.get(today - timedelta(days=offset), 0)
            for offset in range(1, baseline_days + 1)
        ]
        baseline_avg = sum(baseline_window) / len(baseline_window)

        if today_count == 0 and baseline_avg == 0:
            continue  # nothing to report for this topic right now

        velocity = _velocity(today_count, baseline_avg)

        # Acceleration: compare today's velocity to yesterday's (both using
        # a same-length trailing baseline, just shifted back one day).
        yesterday = today - timedelta(days=1)
        yesterday_count = counts_by_day.get(yesterday, 0)
        yesterday_baseline_window = [
            counts_by_day.get(yesterday - timedelta(days=offset), 0)
            for offset in range(1, baseline_days + 1)
        ]
        yesterday_baseline_avg = sum(yesterday_baseline_window) / len(
            yesterday_baseline_window
        )
        yesterday_velocity = _velocity(yesterday_count, yesterday_baseline_avg)
        acceleration = (
            velocity - yesterday_velocity
            if velocity is not None and yesterday_velocity is not None
            else None
        )

        trend_direction = _classify(today_count, baseline_avg, velocity)

        sparkline = [
            counts_by_day.get(sparkline_start + timedelta(days=i), 0)
            for i in range(days)
        ]

        sources = sorted(set(today_sources.get(topic, [])))[:MAX_SOURCES_LISTED]

        trends.append(
            TopicTrend(
                topic=topic,
                display_name=get_topic_display_name(topic),
                today_count=today_count,
                baseline_avg=baseline_avg,
                velocity=velocity,
                acceleration=acceleration,
                coverage_breadth=len(set(today_sources.get(topic, []))),
                trend_direction=trend_direction,
                is_hot=(trend_direction == "hot"),
                sparkline=sparkline,
                sources=sources,
            )
        )

    trends.sort(
        key=lambda t: (t.velocity is None, -(t.velocity or 0.0), -t.today_count)
    )

    if use_cache:
        _cache[cache_key] = (time.monotonic(), trends)

    return trends


def clear_trend_cache() -> None:
    """Clear the in-process trend cache. Mainly for tests."""
    _cache.clear()
