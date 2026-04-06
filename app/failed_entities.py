"""List / discard / retry failed pipeline entities (#293 M3, ADR-0030)."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from sqlalchemy import text

from app.db import session_scope
from app.processing_states import discard_article_failure, discard_story_failure


def list_failed_entities(
    *, limit_items: int = 50, limit_stories: int = 50
) -> Dict[str, List[Dict[str, Any]]]:
    """Articles and stories with ``processing_state = 'failed'``, newest first."""
    cap_i = max(1, min(int(limit_items), 200))
    cap_s = max(1, min(int(limit_stories), 200))
    with session_scope() as session:
        item_rows = session.execute(
            text(
                """
                SELECT id,
                       COALESCE(title, '') AS title,
                       processing_error,
                       processing_failed_at,
                       failure_stage,
                       last_failed_run_group_id
                FROM items
                WHERE processing_state = 'failed'
                ORDER BY processing_failed_at DESC NULLS LAST, id DESC
                LIMIT :lim
                """
            ),
            {"lim": cap_i},
        ).fetchall()
        story_rows = session.execute(
            text(
                """
                SELECT id,
                       title,
                       processing_error,
                       processing_failed_at,
                       failure_stage,
                       last_failed_run_group_id
                FROM stories
                WHERE processing_state = 'failed'
                ORDER BY processing_failed_at DESC NULLS LAST, id DESC
                LIMIT :lim
                """
            ),
            {"lim": cap_s},
        ).fetchall()

    def _item_row(r: Any) -> Dict[str, Any]:
        return {
            "id": int(r[0]),
            "title": (r[1] or "")[:200],
            "processing_error": r[2],
            "processing_failed_at": r[3].isoformat() if r[3] else None,
            "failure_stage": r[4],
            "last_failed_run_group_id": r[5],
        }

    return {
        "items": [_item_row(r) for r in item_rows],
        "stories": [_item_row(r) for r in story_rows],
    }


def discard_failed_item(item_id: int) -> Dict[str, Any]:
    """Clear failure metadata and move item to default retry target (``enriched``)."""
    with session_scope() as session:
        row = session.execute(
            text("SELECT processing_state FROM items WHERE id = :id"),
            {"id": item_id},
        ).first()
        if not row:
            raise ValueError("item not found")
        if row[0] != "failed":
            raise ValueError("item is not in failed processing state")
        if not discard_article_failure(session, item_id):
            raise ValueError("could not discard failure for item")
    return {"id": item_id, "entity": "item", "discarded": True}


def discard_failed_story(story_id: int) -> Dict[str, Any]:
    """Clear failure metadata and move story to default retry target (``candidate``)."""
    with session_scope() as session:
        row = session.execute(
            text("SELECT processing_state FROM stories WHERE id = :id"),
            {"id": story_id},
        ).first()
        if not row:
            raise ValueError("story not found")
        if row[0] != "failed":
            raise ValueError("story is not in failed processing state")
        if not discard_story_failure(session, story_id):
            raise ValueError("could not discard failure for story")
    return {"id": story_id, "entity": "story", "discarded": True}


def retry_failed_item(item_id: int, *, model: str) -> Dict[str, Any]:
    """Discard failure then run targeted enrich for the article."""
    from app.pipeline_runner import execute_enrich_item_stage

    discard_failed_item(item_id)
    new_group = str(uuid.uuid4())
    r = execute_enrich_item_stage(
        trigger="manual",
        run_group_id=new_group,
        item_id=item_id,
        model=model,
    )
    return {
        "id": item_id,
        "entity": "item",
        "run_group_id": new_group,
        "success": r.success,
        "error": r.error,
    }


def retry_failed_story(story_id: int, *, model: str) -> Dict[str, Any]:
    """Discard failure then run targeted story regeneration."""
    from app.pipeline_runner import execute_story_targeted_regeneration_stage

    discard_failed_story(story_id)
    new_group = str(uuid.uuid4())
    r = execute_story_targeted_regeneration_stage(
        trigger="manual",
        run_group_id=new_group,
        story_id=story_id,
        model=model,
    )
    return {
        "id": story_id,
        "entity": "story",
        "run_group_id": new_group,
        "success": r.success,
        "error": r.error,
    }
