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
) -> None:
    row = session.get(PipelineStageRun, row_id)
    if row is None:
        logger.error("pipeline_stage_run missing for finalize id=%s", row_id)
        return
    row.finished_at = datetime.now(UTC)
    row.success = success
    row.error_message = error_message
    row.stats_json = json.dumps(stats) if stats else None


def execute_ingest_stage(*, trigger: TriggerKind, run_group_id: str) -> StageResult:
    from app.feeds import fetch_and_store

    row_id: Optional[int] = None
    with session_scope() as session:
        row_id = _insert_stage_start(
            session, run_group_id, PipelineStage.INGEST.value, trigger
        )

    stats: Dict[str, Any] = {}
    ok = True
    err: Optional[str] = None
    try:
        result = fetch_and_store()
        stats = {
            "articles_ingested": result.total_items,
            "feeds_processed": result.total_feeds_processed,
            "feeds_error": result.feeds_error,
            "feeds_cached_304": result.feeds_cached_304,
        }
    except Exception as e:
        ok = False
        err = str(e)
        logger.error("Pipeline ingest stage failed: %s", e, exc_info=True)

    with session_scope() as session:
        assert row_id is not None
        _finalize_stage_row(session, row_id, success=ok, error_message=err, stats=stats)

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

    stats: Dict[str, Any] = {}
    ok = True
    err: Optional[str] = None
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
            )
        ids = gen_out.get("story_ids", []) if isinstance(gen_out, dict) else []
        stats = {
            "stories_created": len(ids),
            "stories_archived": archived,
            "articles_found": (
                gen_out.get("articles_found") if isinstance(gen_out, dict) else None
            ),
            "clusters_created": (
                gen_out.get("clusters_created") if isinstance(gen_out, dict) else None
            ),
            "duplicates_skipped": (
                gen_out.get("duplicates_skipped") if isinstance(gen_out, dict) else None
            ),
            "stories_updated": (
                gen_out.get("stories_updated") if isinstance(gen_out, dict) else None
            ),
        }
    except Exception as e:
        ok = False
        err = str(e)
        logger.error("Pipeline story_generation stage failed: %s", e, exc_info=True)

    with session_scope() as session:
        assert row_id is not None
        _finalize_stage_row(session, row_id, success=ok, error_message=err, stats=stats)

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

    stats: Dict[str, Any] = {"item_id": item_id}
    ok = True
    err: Optional[str] = None
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
    except Exception as e:
        ok = False
        err = str(e)
        logger.error(
            "Pipeline enrich stage failed for item %s: %s", item_id, e, exc_info=True
        )

    with session_scope() as session:
        assert row_id is not None
        _finalize_stage_row(session, row_id, success=ok, error_message=err, stats=stats)

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

    stats: Dict[str, Any] = {"story_id": story_id}
    ok = True
    err: Optional[str] = None
    try:
        with session_scope() as session:
            out = regenerate_story_synthesis(session, story_id, model=model)
            stats.update(out)
    except Exception as e:
        ok = False
        err = str(e)
        logger.error(
            "Pipeline targeted story_generation failed for story %s: %s",
            story_id,
            e,
            exc_info=True,
        )

    with session_scope() as session:
        assert row_id is not None
        _finalize_stage_row(session, row_id, success=ok, error_message=err, stats=stats)

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


def list_recent_stage_runs(limit: int = 50) -> List[Dict[str, Any]]:
    from sqlalchemy import desc

    with session_scope() as session:
        rows = (
            session.query(PipelineStageRun)
            .order_by(desc(PipelineStageRun.started_at))
            .limit(limit)
            .all()
        )
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
                }
            )
        return out
