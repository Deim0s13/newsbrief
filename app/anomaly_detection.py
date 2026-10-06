"""Rule-based anomaly and pattern detection over topic coverage (#219, ADR-0023, v0.10.1).

Builds on ``app.trend_detection.get_daily_topic_counts`` rather than
re-deriving per-topic/per-day counts. Three anomaly types, all rule-based /
statistical -- no LLM call:

- **spike**: today's count is a statistically significant jump above a
  longer trailing baseline (z-score over ``ANOMALY_BASELINE_DAYS`` days).
  This is a different, stricter check than #217's "hot" classification
  (a fixed 2x-baseline ratio): a topic that normally varies a lot needs a
  bigger jump to count as anomalous than one that's always rock-steady.
- **silence**: a topic that reliably got covered on most days over the
  baseline window has zero articles today.
- **new_entrant**: a source (feed) covers an *already-established* topic
  for the first time in ``NEW_ENTRANT_LOOKBACK_DAYS`` days. (A source
  covering a brand-new topic isn't a "new entrant" anomaly -- that's just
  #217's "emerging" topic; see the ``other_feed_coverage_before_today``
  check below.)

**Sentiment flip is explicitly descoped** -- see
``app/trend_detection.py``'s module docstring for why
(``items.perspective_json.tone`` coverage is too sparse, ~8% of articles,
to build a meaningful signal on).

Advisory only, same spirit as ``app/data_trends.py`` and
``app/perspective_gaps.py``: a false positive here is a slightly-wrong
badge on the dashboard, not a hidden/gatekept decision, so a reasonably
coarse heuristic is an acceptable first pass. False positive rate isn't
formally measured (no labeled anomaly dataset exists for this corpus) --
if the thresholds below prove too noisy/too quiet in practice, tune the
constants rather than redesigning the approach.

Public API:
- ``detect_anomalies(session)`` -> List[TopicAnomaly] (all three types combined)
- ``detect_spikes`` / ``detect_silences`` / ``detect_new_entrants`` individually
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Dict, List, Set

from sqlalchemy import text
from sqlalchemy.orm import Session

from .topics import get_topic_display_name
from .trend_detection import get_daily_topic_counts

# -----------------------------------------------------------------------------
# Tunables
# -----------------------------------------------------------------------------

ANOMALY_BASELINE_DAYS = 30  # wider than trend_detection's 7-day velocity baseline

SPIKE_Z_THRESHOLD = 2.0
SPIKE_HIGH_SEVERITY_Z = 3.0
SPIKE_MIN_TODAY_COUNT = 3  # don't flag e.g. "1 article vs typical 0" as a spike

SILENCE_MIN_BASELINE_AVG = 1.0  # topic must typically get >= 1/day on average
SILENCE_MIN_COVERAGE_DAYS = 5  # ...and have been covered on most baseline days

NEW_ENTRANT_LOOKBACK_DAYS = 30


# -----------------------------------------------------------------------------
# Result type
# -----------------------------------------------------------------------------


@dataclass
class TopicAnomaly:
    """A single detected anomaly for one topic."""

    topic: str
    display_name: str
    anomaly_type: str  # "spike" | "silence" | "new_entrant"
    description: (
        str  # human-readable, e.g. "14 articles today vs typical 3.2/day (z=3.1)"
    )
    severity: str  # "high" | "medium" | "low"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "display_name": self.display_name,
            "anomaly_type": self.anomaly_type,
            "description": self.description,
            "severity": self.severity,
        }


# -----------------------------------------------------------------------------
# Spike detection
# -----------------------------------------------------------------------------


def detect_spikes(
    session: Session,
    baseline_days: int = ANOMALY_BASELINE_DAYS,
    z_threshold: float = SPIKE_Z_THRESHOLD,
    min_today_count: int = SPIKE_MIN_TODAY_COUNT,
) -> List[TopicAnomaly]:
    """Flag topics whose today's count is a statistically significant jump
    above their trailing ``baseline_days``-day mean (z-score)."""
    today = datetime.now(UTC).date()
    window_start = today - timedelta(days=baseline_days)
    counts = get_daily_topic_counts(session, window_start, today)

    anomalies: List[TopicAnomaly] = []
    for topic, by_day in counts.items():
        today_count = by_day.get(today, 0)
        if today_count < min_today_count:
            continue

        baseline_window = [
            by_day.get(today - timedelta(days=offset), 0)
            for offset in range(1, baseline_days + 1)
        ]
        mean = statistics.mean(baseline_window)
        stdev = statistics.pstdev(baseline_window)

        if stdev == 0:
            # No historical variation at all -- any difference is notable,
            # but there's no z-score to report (division by zero).
            if today_count > mean:
                anomalies.append(
                    TopicAnomaly(
                        topic=topic,
                        display_name=get_topic_display_name(topic),
                        anomaly_type="spike",
                        description=(
                            f"{today_count} articles today vs a steady "
                            f"{mean:.0f}/day over the last {baseline_days} days"
                        ),
                        severity="high",
                    )
                )
            continue

        z = (today_count - mean) / stdev
        if z >= z_threshold:
            severity = "high" if z >= SPIKE_HIGH_SEVERITY_Z else "medium"
            anomalies.append(
                TopicAnomaly(
                    topic=topic,
                    display_name=get_topic_display_name(topic),
                    anomaly_type="spike",
                    description=(
                        f"{today_count} articles today vs typical "
                        f"{mean:.1f}/day (z={z:.1f})"
                    ),
                    severity=severity,
                )
            )

    return anomalies


# -----------------------------------------------------------------------------
# Silence detection
# -----------------------------------------------------------------------------


def detect_silences(
    session: Session,
    baseline_days: int = ANOMALY_BASELINE_DAYS,
    min_baseline_avg: float = SILENCE_MIN_BASELINE_AVG,
    min_coverage_days: int = SILENCE_MIN_COVERAGE_DAYS,
) -> List[TopicAnomaly]:
    """Flag topics that reliably get coverage but have zero articles today."""
    today = datetime.now(UTC).date()
    window_start = today - timedelta(days=baseline_days)
    counts = get_daily_topic_counts(session, window_start, today)

    anomalies: List[TopicAnomaly] = []
    for topic, by_day in counts.items():
        if by_day.get(today, 0) > 0:
            continue  # not silent today

        baseline_window = [
            by_day.get(today - timedelta(days=offset), 0)
            for offset in range(1, baseline_days + 1)
        ]
        days_with_coverage = sum(1 for c in baseline_window if c > 0)
        baseline_avg = sum(baseline_window) / len(baseline_window)

        if days_with_coverage >= min_coverage_days and baseline_avg >= min_baseline_avg:
            anomalies.append(
                TopicAnomaly(
                    topic=topic,
                    display_name=get_topic_display_name(topic),
                    anomaly_type="silence",
                    description=(
                        f"No articles today; typically {baseline_avg:.1f}/day "
                        f"over the last {baseline_days} days"
                    ),
                    severity="medium",
                )
            )

    return anomalies


# -----------------------------------------------------------------------------
# New entrant detection
# -----------------------------------------------------------------------------


def detect_new_entrants(
    session: Session,
    lookback_days: int = NEW_ENTRANT_LOOKBACK_DAYS,
) -> List[TopicAnomaly]:
    """Flag sources covering an already-established topic for the first
    time in ``lookback_days`` days."""
    today = datetime.now(UTC).date()
    window_start = today - timedelta(days=lookback_days)

    rows = session.execute(
        text(
            """
            SELECT i.topic, i.feed_id, f.name, (i.published AT TIME ZONE 'UTC')::date AS day
            FROM items i
            JOIN feeds f ON f.id = i.feed_id
            WHERE i.topic IS NOT NULL
              AND i.published IS NOT NULL
              AND (i.published AT TIME ZONE 'UTC')::date BETWEEN :start AND :today
            """
        ),
        {"start": window_start, "today": today},
    ).fetchall()

    # topic -> feed_id -> set of days covered; feed_id -> display name
    activity: Dict[str, Dict[int, Set[date]]] = {}
    feed_names: Dict[int, str] = {}
    for topic, feed_id, name, day in rows:
        activity.setdefault(topic, {}).setdefault(feed_id, set()).add(day)
        feed_names[feed_id] = name or "Unknown source"

    anomalies: List[TopicAnomaly] = []
    for topic, by_feed in activity.items():
        other_feed_coverage_before_today = any(
            any(d < today for d in days) for days in by_feed.values()
        )
        if not other_feed_coverage_before_today:
            # The whole topic is new in this window -- that's #217's
            # "emerging", not a specific source being a "new entrant".
            continue

        for feed_id, days in by_feed.items():
            if today not in days:
                continue
            prior_days = {d for d in days if d < today}
            if prior_days:
                continue  # this feed has covered this topic before

            anomalies.append(
                TopicAnomaly(
                    topic=topic,
                    display_name=get_topic_display_name(topic),
                    anomaly_type="new_entrant",
                    description=(
                        f"{feed_names[feed_id]} is covering "
                        f"{get_topic_display_name(topic)} for the first time "
                        f"in {lookback_days} days"
                    ),
                    severity="low",
                )
            )

    return anomalies


# -----------------------------------------------------------------------------
# Combined entry point
# -----------------------------------------------------------------------------

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def detect_anomalies(
    session: Session,
    baseline_days: int = ANOMALY_BASELINE_DAYS,
    lookback_days: int = NEW_ENTRANT_LOOKBACK_DAYS,
) -> List[TopicAnomaly]:
    """Run all anomaly detectors and return a combined, severity-sorted list."""
    anomalies = (
        detect_spikes(session, baseline_days=baseline_days)
        + detect_silences(session, baseline_days=baseline_days)
        + detect_new_entrants(session, lookback_days=lookback_days)
    )
    anomalies.sort(key=lambda a: _SEVERITY_ORDER.get(a.severity, 99))
    return anomalies
