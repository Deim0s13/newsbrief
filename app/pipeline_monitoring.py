"""
Stage-aware pipeline monitoring (#276, #291): entity counts by processing state,
run aggregates from ``pipeline_stage_runs``, stuck in-flight runs, and unified
health metrics with throughput (#291).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import case, func

from app.db import session_scope
from app.orm_models import Item, PipelineStageRun, Story
from app.processing_states import ArticleProcessingState, StoryProcessingState

# Non-terminal states where items/stories can become stuck
_ARTICLE_STUCK_STATES: frozenset[str] = frozenset(
    s.value
    for s in (
        ArticleProcessingState.DISCOVERED,
        ArticleProcessingState.FETCHED,
        ArticleProcessingState.EXTRACTED,
        ArticleProcessingState.ENRICHED,
        ArticleProcessingState.EMBEDDED,
    )
)

_STORY_STUCK_STATES: frozenset[str] = frozenset(
    s.value
    for s in (
        StoryProcessingState.CANDIDATE,
        StoryProcessingState.SYNTHESIZING,
        StoryProcessingState.CONTEXT_ENRICHED,
        StoryProcessingState.QUALITY_CHECKED,
    )
)


def pipeline_stuck_threshold_seconds(override: Optional[int] = None) -> int:
    """Minimum age (seconds) before an unfinished run is considered stuck."""
    if override is not None:
        return max(60, int(override))
    return max(60, int(os.environ.get("PIPELINE_STUCK_AFTER_SECONDS", "3600")))


def _iso_utc(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC).isoformat()
    return dt.isoformat()


def _entity_snapshot_rows(
    *,
    counts: Dict[str, int],
    oldest: Dict[str, Optional[datetime]],
    states_ordered: List[str],
) -> Dict[str, Any]:
    by_state: Dict[str, int] = {k: int(counts.get(k, 0)) for k in states_ordered}
    for k, v in counts.items():
        if k not in by_state:
            by_state[k] = int(v)

    oldest_out: Dict[str, Optional[str]] = {}
    for k, c in by_state.items():
        if c > 0 and k in oldest and oldest[k] is not None:
            oldest_out[k] = _iso_utc(oldest[k])

    return {
        "by_state": by_state,
        "states_ordered": states_ordered,
        "oldest_waiting_at_by_state": oldest_out,
    }


def get_processing_stage_snapshot() -> Dict[str, Any]:
    """Counts and oldest row per ``processing_state`` for items and stories."""
    article_states = [s.value for s in ArticleProcessingState]
    story_states = [s.value for s in StoryProcessingState]

    with session_scope() as session:
        item_counts = dict(
            session.query(Item.processing_state, func.count(Item.id))
            .group_by(Item.processing_state)
            .all()
        )
        story_counts = dict(
            session.query(Story.processing_state, func.count(Story.id))
            .group_by(Story.processing_state)
            .all()
        )
        item_oldest = dict(
            session.query(Item.processing_state, func.min(Item.created_at))
            .group_by(Item.processing_state)
            .all()
        )
        story_oldest_rows = (
            session.query(
                Story.processing_state,
                func.min(func.coalesce(Story.last_updated, Story.generated_at)),
            )
            .group_by(Story.processing_state)
            .all()
        )
        story_oldest = dict(story_oldest_rows)

    return {
        "articles": _entity_snapshot_rows(
            counts=item_counts,
            oldest=item_oldest,
            states_ordered=article_states,
        ),
        "stories": _entity_snapshot_rows(
            counts=story_counts,
            oldest=story_oldest,
            states_ordered=story_states,
        ),
        "generated_at": datetime.now(UTC).isoformat(),
    }


def get_pipeline_run_metrics(window_hours: float = 24.0) -> Dict[str, Any]:
    """Aggregate ``pipeline_stage_runs`` by ``stage`` for rows started in the window."""
    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    ok_sum = func.sum(case((PipelineStageRun.success.is_(True), 1), else_=0))
    finished_sum = func.sum(
        case((PipelineStageRun.finished_at.isnot(None), 1), else_=0)
    )
    in_flight_sum = func.sum(case((PipelineStageRun.finished_at.is_(None), 1), else_=0))
    dur_case = case(
        (
            PipelineStageRun.finished_at.isnot(None),
            func.extract(
                "epoch",
                PipelineStageRun.finished_at - PipelineStageRun.started_at,
            ),
        ),
        else_=None,
    )
    retries_sum = func.sum(case((PipelineStageRun.attempts > 1, 1), else_=0))

    with session_scope() as session:
        rows = (
            session.query(
                PipelineStageRun.stage,
                func.count().label("n"),
                ok_sum.label("ok"),
                finished_sum.label("finished"),
                in_flight_sum.label("in_flight"),
                func.avg(dur_case).label("avg_duration_sec"),
                func.sum(PipelineStageRun.attempts).label("attempts_sum"),
                retries_sum.label("retries"),
            )
            .filter(PipelineStageRun.started_at >= cutoff)
            .group_by(PipelineStageRun.stage)
            .all()
        )

    by_stage: List[Dict[str, Any]] = []
    for (
        stage,
        n,
        ok,
        finished,
        in_flight,
        avg_dur,
        attempts_sum,
        retried,
    ) in rows:
        fin = int(finished or 0)
        ok_i = int(ok or 0)
        success_rate = round(ok_i / fin, 4) if fin else None
        by_stage.append(
            {
                "stage": stage,
                "started_in_window": int(n),
                "finished": fin,
                "unfinished_started_in_window": int(in_flight or 0),
                "succeeded_among_finished": ok_i,
                "success_rate_finished": success_rate,
                "avg_duration_seconds": float(avg_dur) if avg_dur is not None else None,
                "sum_attempts": int(attempts_sum or 0),
                "runs_with_attempts_gt_1": int(retried or 0),
            }
        )

    by_stage.sort(key=lambda x: x["stage"] or "")

    return {
        "window_hours": window_hours,
        "cutoff_started_at": cutoff.isoformat(),
        "by_stage": by_stage,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def list_stuck_pipeline_runs(
    *,
    max_age_seconds: Optional[int] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """
    In-flight stage runs (no ``finished_at``, not discarded) older than the
    stuck threshold.
    """
    sec = pipeline_stuck_threshold_seconds(max_age_seconds)
    threshold = datetime.now(UTC) - timedelta(seconds=sec)
    now = datetime.now(UTC)

    with session_scope() as session:
        rows = (
            session.query(PipelineStageRun)
            .filter(
                PipelineStageRun.finished_at.is_(None),
                PipelineStageRun.discarded_at.is_(None),
                PipelineStageRun.started_at < threshold,
            )
            .order_by(PipelineStageRun.started_at)
            .limit(limit)
            .all()
        )

    out: List[Dict[str, Any]] = []
    for r in rows:
        if r.started_at is None:
            continue
        age = (now - r.started_at).total_seconds()
        out.append(
            {
                "id": r.id,
                "run_group_id": r.run_group_id,
                "stage": r.stage,
                "trigger": r.trigger,
                "started_at": r.started_at.isoformat(),
                "age_seconds": int(age),
                "threshold_seconds": sec,
                "target_type": r.target_type,
                "target_id": r.target_id,
                "attempts": r.attempts,
            }
        )

    return {
        "threshold_seconds": sec,
        "count": len(out),
        "runs": out,
        "generated_at": now.isoformat(),
    }


def get_stuck_items_by_processing_state(
    *,
    max_age_hours: float = 2.0,
) -> Dict[str, Any]:
    """
    Counts of items/stories that have been in an intermediate processing state
    longer than ``max_age_hours`` (#291).

    Uses ``items.created_at`` for articles (always set) and
    ``coalesce(stories.last_updated, stories.generated_at)`` for stories.
    Rows with no usable timestamp are excluded — they represent brand-new
    candidates not yet old enough to flag.
    """
    now = datetime.now(UTC)
    threshold = now - timedelta(hours=max_age_hours)

    with session_scope() as session:
        article_rows = (
            session.query(
                Item.processing_state,
                func.count(Item.id).label("count"),
                func.min(Item.created_at).label("oldest"),
            )
            .filter(
                Item.processing_state.in_(list(_ARTICLE_STUCK_STATES)),
                Item.created_at < threshold,
            )
            .group_by(Item.processing_state)
            .all()
        )

        story_ts = func.coalesce(Story.last_updated, Story.generated_at)
        story_rows = (
            session.query(
                Story.processing_state,
                func.count(Story.id).label("count"),
                func.min(story_ts).label("oldest"),
            )
            .filter(
                Story.processing_state.in_(list(_STORY_STUCK_STATES)),
                story_ts.isnot(None),
                story_ts < threshold,
            )
            .group_by(Story.processing_state)
            .all()
        )

    def _age_hours(dt: Optional[datetime]) -> Optional[float]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return round((now - dt).total_seconds() / 3600, 1)

    articles_out: List[Dict[str, Any]] = [
        {
            "state": state,
            "count": int(count),
            "oldest_at": _iso_utc(oldest),
            "oldest_age_hours": _age_hours(oldest),
        }
        for state, count, oldest in article_rows
    ]
    stories_out: List[Dict[str, Any]] = [
        {
            "state": state,
            "count": int(count),
            "oldest_at": _iso_utc(oldest),
            "oldest_age_hours": _age_hours(oldest),
        }
        for state, count, oldest in story_rows
    ]

    total = sum(r["count"] for r in articles_out) + sum(r["count"] for r in stories_out)
    return {
        "max_age_hours": max_age_hours,
        "total_stuck": total,
        "articles": articles_out,
        "stories": stories_out,
        "generated_at": now.isoformat(),
    }


def get_unified_pipeline_metrics(
    *,
    window_hours: float = 24.0,
    stuck_max_age_hours: float = 2.0,
) -> Dict[str, Any]:
    """
    Single-call summary combining snapshot, run metrics, throughput, and stuck
    items by processing state (#291).

    Throughput is derived from stories published within ``window_hours``.
    """
    snapshot = get_processing_stage_snapshot()
    run_metrics = get_pipeline_run_metrics(window_hours=window_hours)
    stuck = get_stuck_items_by_processing_state(max_age_hours=stuck_max_age_hours)

    cutoff = datetime.now(UTC) - timedelta(hours=window_hours)
    with session_scope() as session:
        published_count = (
            session.query(func.count(Story.id))
            .filter(
                Story.processing_state == StoryProcessingState.PUBLISHED.value,
                Story.generated_at >= cutoff,
            )
            .scalar()
        ) or 0

    stories_per_hour = (
        round(published_count / window_hours, 2) if window_hours > 0 else 0.0
    )

    return {
        "window_hours": window_hours,
        "throughput": {
            "stories_published_in_window": int(published_count),
            "stories_per_hour": stories_per_hour,
        },
        "snapshot": snapshot,
        "run_metrics": run_metrics,
        "stuck_items": stuck,
        "generated_at": datetime.now(UTC).isoformat(),
    }
