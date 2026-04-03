"""
Pipeline runner: orchestrated stages with persisted metadata (ADR-0029, #274).

Maps today's jobs to coarse stages:
- ``ingest`` — RSS fetch + store (``fetch_and_store``)
- ``story_generation`` — archive + cluster/synthesize/publish (``generate_stories_simple``)

Finer stages (extract, enrich, quality-check as separate runners) can split out later.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from sqlalchemy.orm import Session

from app.db import session_scope
from app.orm_models import PipelineStageRun
from app.stories import generate_stories_simple

logger = logging.getLogger(__name__)

TriggerKind = Literal["scheduled", "manual"]
StageName = Literal["ingest", "story_generation"]
ReplayStage = Literal["enrich", "story_generation"]
TargetType = Literal["item", "story"]


class PipelineStage(str, Enum):
    """Named pipeline stages (coarse; extend as steps split)."""

    INGEST = "ingest"
    ENRICH = "enrich"
    STORY_GENERATION = "story_generation"


@dataclass
class StageResult:
    stage: str
    success: bool
    stats: Dict[str, Any]
    error: Optional[str] = None


def _insert_stage_start(
    session: Session,
    run_group_id: str,
    stage: str,
    trigger: TriggerKind,
    *,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
) -> int:
    started = datetime.now(UTC)
    row = PipelineStageRun(
        run_group_id=run_group_id,
        stage=stage,
        trigger=trigger,
        started_at=started,
        success=None,
        target_type=target_type,
        target_id=target_id,
    )
    session.add(row)
    session.flush()
    return int(row.id)


def _finalize_stage_row(
    session: Session,
    row_id: int,
    *,
    success: bool,
    error_message: Optional[str],
    stats: Dict[str, Any],
    attempts: int = 1,
) -> None:
    row = session.get(PipelineStageRun, row_id)
    if row is None:
        logger.error("pipeline_stage_run missing for finalize id=%s", row_id)
        return
    row.finished_at = datetime.now(UTC)
    row.success = success
    row.error_message = error_message
    row.stats_json = json.dumps(stats) if stats else None
    row.attempts = max(1, attempts)


def _stage_retry_settings() -> tuple[int, float, float]:
    """Max automatic retries after first failure, base seconds, backoff cap (#275)."""
    max_auto = int(os.environ.get("PIPELINE_STAGE_MAX_AUTO_RETRIES", "3"))
    base = float(os.environ.get("PIPELINE_STAGE_BACKOFF_BASE_SECONDS", "2"))
    cap = float(os.environ.get("PIPELINE_STAGE_BACKOFF_MAX_SECONDS", "60"))
    return max(0, max_auto), max(0.0, base), max(0.0, cap)


def _sleep_before_retry(failed_attempt_index: int, base: float, cap: float) -> None:
    """Sleep after failure ``failed_attempt_index`` (0 = after first failure)."""
    delay = min(cap, base * (2**failed_attempt_index))
    if delay > 0:
        time.sleep(delay)


def pipeline_retry_backoff_seconds(
    max_auto_retries: int, base_seconds: float, cap_seconds: float
) -> List[float]:
    """Pure helper: delays after each failure before the next attempt (for tests)."""
    return [min(cap_seconds, base_seconds * (2**i)) for i in range(max_auto_retries)]


def execute_ingest_stage(*, trigger: TriggerKind, run_group_id: str) -> StageResult:
    from app.feeds import fetch_and_store

    row_id: Optional[int] = None
    with session_scope() as session:
        row_id = _insert_stage_start(
            session, run_group_id, PipelineStage.INGEST.value, trigger
        )

    max_auto, base, cap = _stage_retry_settings()
    stats: Dict[str, Any] = {}
    ok = False
    err: Optional[str] = None
    attempts = 0
    for attempt in range(max_auto + 1):
        attempts = attempt + 1
        try:
            result = fetch_and_store()
            stats = {
                "articles_ingested": result.total_items,
                "feeds_processed": result.total_feeds_processed,
                "feeds_error": result.feeds_error,
                "feeds_cached_304": result.feeds_cached_304,
            }
            ok = True
            err = None
            break
        except Exception as e:
            err = str(e)
            logger.error(
                "Pipeline ingest stage failed (attempt %s/%s): %s",
                attempts,
                max_auto + 1,
                e,
                exc_info=True,
            )
            if attempt < max_auto:
                _sleep_before_retry(attempt, base, cap)
            else:
                ok = False

    with session_scope() as session:
        assert row_id is not None
        _finalize_stage_row(
            session,
            row_id,
            success=ok,
            error_message=err,
            stats=stats,
            attempts=attempts,
        )

    return StageResult(
        stage=PipelineStage.INGEST.value, success=ok, stats=stats, error=err
    )


def execute_story_generation_stage(
    *,
    trigger: TriggerKind,
    run_group_id: str,
    time_window_hours: int,
    min_articles_per_story: int,
    model: str,
    max_workers: int = 3,
) -> StageResult:
    # Deferred import: avoids cycles with scheduler at module import time
    from app.scheduler import archive_old_stories

    row_id: Optional[int] = None
    with session_scope() as session:
        row_id = _insert_stage_start(
            session, run_group_id, PipelineStage.STORY_GENERATION.value, trigger
        )

    max_auto, base, cap = _stage_retry_settings()
    stats: Dict[str, Any] = {}
    ok = False
    err: Optional[str] = None
    attempts = 0
    for attempt in range(max_auto + 1):
        attempts = attempt + 1
        try:
            archived = archive_old_stories()
            with session_scope() as session:
                gen_out = generate_stories_simple(
                    session=session,
                    time_window_hours=time_window_hours,
                    min_articles_per_story=min_articles_per_story,
                    similarity_threshold=0.25,
                    model=model,
                    max_workers=max_workers,
                    pipeline_run_group_id=run_group_id,
                )
            ids = gen_out.get("story_ids", []) if isinstance(gen_out, dict) else []
            stats = {
                "stories_created": len(ids),
                "stories_archived": archived,
                "articles_found": (
                    gen_out.get("articles_found") if isinstance(gen_out, dict) else None
                ),
                "clusters_created": (
                    gen_out.get("clusters_created")
                    if isinstance(gen_out, dict)
                    else None
                ),
                "duplicates_skipped": (
                    gen_out.get("duplicates_skipped")
                    if isinstance(gen_out, dict)
                    else None
                ),
                "stories_updated": (
                    gen_out.get("stories_updated")
                    if isinstance(gen_out, dict)
                    else None
                ),
            }
            ok = True
            err = None
            break
        except Exception as e:
            err = str(e)
            logger.error(
                "Pipeline story_generation stage failed (attempt %s/%s): %s",
                attempts,
                max_auto + 1,
                e,
                exc_info=True,
            )
            if attempt < max_auto:
                _sleep_before_retry(attempt, base, cap)
            else:
                ok = False

    with session_scope() as session:
        assert row_id is not None
        _finalize_stage_row(
            session,
            row_id,
            success=ok,
            error_message=err,
            stats=stats,
            attempts=attempts,
        )

    return StageResult(
        stage=PipelineStage.STORY_GENERATION.value,
        success=ok,
        stats=stats,
        error=err,
    )


def execute_enrich_item_stage(
    *,
    trigger: TriggerKind,
    run_group_id: str,
    item_id: int,
    model: str,
) -> StageResult:
    """Re-run entity extraction/enrichment for one article (``use_cache=False``)."""
    from sqlalchemy import text

    from app.entities import extract_and_cache_entities

    row_id: Optional[int] = None
    with session_scope() as session:
        row_id = _insert_stage_start(
            session,
            run_group_id,
            PipelineStage.ENRICH.value,
            trigger,
            target_type="item",
            target_id=item_id,
        )

    max_auto, base, cap = _stage_retry_settings()
    stats: Dict[str, Any] = {"item_id": item_id}
    ok = False
    err: Optional[str] = None
    attempts = 0
    for attempt in range(max_auto + 1):
        attempts = attempt + 1
        try:
            with session_scope() as session:
                row = session.execute(
                    text(
                        """
                        SELECT id, title, summary, content
                        FROM items WHERE id = :id
                        """
                    ),
                    {"id": item_id},
                ).fetchone()
                if not row:
                    raise ValueError(f"Item {item_id} not found")
                title = row[1] or ""
                body = (row[2] or row[3] or "").strip()
                summary = body[:8000] if body else ""
                extract_and_cache_entities(
                    article_id=item_id,
                    title=title,
                    summary=summary,
                    session=session,
                    model=model,
                    use_cache=False,
                )
            stats["model"] = model
            ok = True
            err = None
            break
        except Exception as e:
            err = str(e)
            logger.error(
                "Pipeline enrich stage failed for item %s (attempt %s/%s): %s",
                item_id,
                attempts,
                max_auto + 1,
                e,
                exc_info=True,
            )
            if attempt < max_auto:
                _sleep_before_retry(attempt, base, cap)
            else:
                ok = False

    if not ok and err:
        try:
            from app.processing_states import mark_article_failed

            with session_scope() as session:
                mark_article_failed(
                    session,
                    item_id,
                    err,
                    failure_stage="enrich",
                    run_group_id=run_group_id,
                    context="execute_enrich_item_stage",
                )
        except Exception as mark_exc:
            logger.warning(
                "Could not mark item %s failed after enrich: %s",
                item_id,
                mark_exc,
            )

    with session_scope() as session:
        assert row_id is not None
        _finalize_stage_row(
            session,
            row_id,
            success=ok,
            error_message=err,
            stats=stats,
            attempts=attempts,
        )

    return StageResult(
        stage=PipelineStage.ENRICH.value, success=ok, stats=stats, error=err
    )


def execute_story_targeted_regeneration_stage(
    *,
    trigger: TriggerKind,
    run_group_id: str,
    story_id: int,
    model: str,
) -> StageResult:
    """Re-synthesize one story (new version); same linked articles."""
    from app.stories import regenerate_story_synthesis

    row_id: Optional[int] = None
    with session_scope() as session:
        row_id = _insert_stage_start(
            session,
            run_group_id,
            PipelineStage.STORY_GENERATION.value,
            trigger,
            target_type="story",
            target_id=story_id,
        )

    max_auto, base, cap = _stage_retry_settings()
    stats: Dict[str, Any] = {"story_id": story_id}
    ok = False
    err: Optional[str] = None
    attempts = 0
    for attempt in range(max_auto + 1):
        attempts = attempt + 1
        try:
            with session_scope() as session:
                out = regenerate_story_synthesis(session, story_id, model=model)
                stats.update(out)
            ok = True
            err = None
            break
        except Exception as e:
            err = str(e)
            logger.error(
                "Pipeline targeted story_generation failed for story %s "
                "(attempt %s/%s): %s",
                story_id,
                attempts,
                max_auto + 1,
                e,
                exc_info=True,
            )
            if attempt < max_auto:
                _sleep_before_retry(attempt, base, cap)
            else:
                ok = False

    if not ok and err:
        try:
            from app.processing_states import mark_story_failed

            with session_scope() as session:
                mark_story_failed(
                    session,
                    story_id,
                    err,
                    failure_stage="story_generation",
                    run_group_id=run_group_id,
                    context="execute_story_targeted_regeneration_stage",
                )
        except Exception as mark_exc:
            logger.warning(
                "Could not mark story %s failed after targeted regen: %s",
                story_id,
                mark_exc,
            )

    with session_scope() as session:
        assert row_id is not None
        _finalize_stage_row(
            session,
            row_id,
            success=ok,
            error_message=err,
            stats=stats,
            attempts=attempts,
        )

    return StageResult(
        stage=PipelineStage.STORY_GENERATION.value,
        success=ok,
        stats=stats,
        error=err,
    )


def run_targeted_replay(
    *,
    trigger: TriggerKind = "manual",
    target_type: TargetType,
    target_id: int,
    from_stage: ReplayStage,
    model: str,
) -> Dict[str, Any]:
    """
    Run a single targeted stage (#274): item+enrich or story+story_generation.
    """
    if target_type == "item" and from_stage != "enrich":
        raise ValueError("target_type=item requires from_stage=enrich")
    if target_type == "story" and from_stage != "story_generation":
        raise ValueError("target_type=story requires from_stage=story_generation")

    run_group_id = str(uuid.uuid4())
    if target_type == "item":
        r = execute_enrich_item_stage(
            trigger=trigger,
            run_group_id=run_group_id,
            item_id=target_id,
            model=model,
        )
    else:
        r = execute_story_targeted_regeneration_stage(
            trigger=trigger,
            run_group_id=run_group_id,
            story_id=target_id,
            model=model,
        )

    return {
        "run_group_id": run_group_id,
        "success": r.success,
        "stages": [
            {
                "stage": r.stage,
                "success": r.success,
                "stats": r.stats,
                "error": r.error,
            }
        ],
    }


def run_pipeline(
    *,
    trigger: TriggerKind,
    from_stage: Optional[StageName] = None,
    time_window_hours: int = 24,
    min_articles_per_story: int = 2,
    model: str = "llama3.1:8b",
    max_workers: int = 3,
) -> Dict[str, Any]:
    """
    Run one or more stages in order.

    ``from_stage``:
    - ``None`` — run full default chain (ingest → story_generation)
    - ``ingest`` — only ingest
    - ``story_generation`` — only story generation (skips ingest)
    """
    run_group_id = str(uuid.uuid4())
    results: List[StageResult] = []

    if from_stage is None:
        run_ingest, run_story = True, True
    elif from_stage == "ingest":
        run_ingest, run_story = True, False
    elif from_stage == "story_generation":
        run_ingest, run_story = False, True
    else:
        raise ValueError(f"Unknown from_stage: {from_stage!r}")

    def _stage_payload() -> List[Dict[str, Any]]:
        return [
            {
                "stage": r.stage,
                "success": r.success,
                "stats": r.stats,
                "error": r.error,
            }
            for r in results
        ]

    if run_ingest:
        results.append(execute_ingest_stage(trigger=trigger, run_group_id=run_group_id))
        if not results[-1].success:
            return {
                "run_group_id": run_group_id,
                "success": False,
                "stages": _stage_payload(),
            }

    if run_story:
        results.append(
            execute_story_generation_stage(
                trigger=trigger,
                run_group_id=run_group_id,
                time_window_hours=time_window_hours,
                min_articles_per_story=min_articles_per_story,
                model=model,
                max_workers=max_workers,
            )
        )

    overall_ok = all(r.success for r in results) if results else True
    return {
        "run_group_id": run_group_id,
        "success": overall_ok,
        "stages": _stage_payload(),
    }


def list_recent_stage_runs(
    limit: int = 50,
    *,
    outcome: str = "all",
) -> List[Dict[str, Any]]:
    """List recent stage runs. ``outcome``: all | failed | dead_letter | succeeded (#275)."""
    from sqlalchemy import desc

    outcome = outcome.strip().lower()
    if outcome not in ("all", "failed", "dead_letter", "succeeded"):
        raise ValueError("outcome must be one of: all, failed, dead_letter, succeeded")

    with session_scope() as session:
        q = session.query(PipelineStageRun).order_by(desc(PipelineStageRun.started_at))
        if outcome == "dead_letter":
            q = q.filter(
                PipelineStageRun.success.is_(False),
                PipelineStageRun.discarded_at.is_(None),
                PipelineStageRun.finished_at.isnot(None),
            )
        elif outcome == "failed":
            q = q.filter(
                PipelineStageRun.success.is_(False),
                PipelineStageRun.finished_at.isnot(None),
            )
        elif outcome == "succeeded":
            q = q.filter(PipelineStageRun.success.is_(True))
        rows = q.limit(limit).all()
        out = []
        for r in rows:
            out.append(
                {
                    "id": r.id,
                    "run_group_id": r.run_group_id,
                    "stage": r.stage,
                    "trigger": r.trigger,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                    "success": r.success,
                    "error_message": r.error_message,
                    "stats_json": r.stats_json,
                    "target_type": r.target_type,
                    "target_id": r.target_id,
                    "attempts": r.attempts,
                    "discarded_at": (
                        r.discarded_at.isoformat() if r.discarded_at else None
                    ),
                }
            )
        return out


def discard_pipeline_stage_run(run_id: int) -> Dict[str, Any]:
    """Mark a failed finished run as discarded (dead-letter dismiss, #275)."""
    with session_scope() as session:
        row = session.get(PipelineStageRun, run_id)
        if row is None:
            raise ValueError("pipeline stage run not found")
        if row.finished_at is None:
            raise ValueError("run has not finished")
        if row.success is True:
            raise ValueError("cannot discard a successful run")
        if row.discarded_at is not None:
            raise ValueError("run is already discarded")
        row.discarded_at = datetime.now(UTC)
        discarded_at = row.discarded_at
    return {
        "id": run_id,
        "discarded_at": discarded_at.isoformat() if discarded_at else None,
    }


def retry_pipeline_stage_run(run_id: int) -> Dict[str, Any]:
    """
    Re-execute the same stage type as a new run group (manual trigger, #275).

    Coarse ``story_generation`` without target replays full cluster/synthesize path.
    """
    from app import scheduler as scheduler_mod

    with session_scope() as session:
        row = session.get(PipelineStageRun, run_id)
        if row is None:
            raise ValueError("pipeline stage run not found")
        if row.finished_at is None:
            raise ValueError("run has not finished")
        if row.success is True:
            raise ValueError("cannot retry a successful run")
        if row.discarded_at is not None:
            raise ValueError("cannot retry a discarded run")
        stage = row.stage
        tgt_type = row.target_type
        tgt_id = row.target_id

    trigger: TriggerKind = "manual"
    new_group = str(uuid.uuid4())

    if stage == PipelineStage.INGEST.value:
        r = execute_ingest_stage(trigger=trigger, run_group_id=new_group)
    elif stage == PipelineStage.STORY_GENERATION.value:
        if tgt_type == "story" and tgt_id:
            r = execute_story_targeted_regeneration_stage(
                trigger=trigger,
                run_group_id=new_group,
                story_id=int(tgt_id),
                model=scheduler_mod.STORY_MODEL,
            )
        elif tgt_type is None:
            r = execute_story_generation_stage(
                trigger=trigger,
                run_group_id=new_group,
                time_window_hours=scheduler_mod.STORY_TIME_WINDOW_HOURS,
                min_articles_per_story=scheduler_mod.STORY_MIN_ARTICLES,
                model=scheduler_mod.STORY_MODEL,
                max_workers=3,
            )
        else:
            raise ValueError(
                f"cannot retry story_generation with target_type={tgt_type!r}"
            )
    elif stage == PipelineStage.ENRICH.value:
        if tgt_type != "item" or not tgt_id:
            raise ValueError("enrich stage requires item target_id")
        r = execute_enrich_item_stage(
            trigger=trigger,
            run_group_id=new_group,
            item_id=int(tgt_id),
            model=scheduler_mod.STORY_MODEL,
        )
    else:
        raise ValueError(f"unknown stage: {stage!r}")

    return {
        "original_run_id": run_id,
        "new_run_group_id": new_group,
        "success": r.success,
        "stages": [
            {
                "stage": r.stage,
                "success": r.success,
                "stats": r.stats,
                "error": r.error,
            }
        ],
    }
