"""Trace/log semantic retrieval queries for observability (#256, ADR-0026)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from .orm_models import RetrievalTrace

logger = logging.getLogger(__name__)

# Cap on rows scanned when computing aggregate stats, to bound query cost on
# an unbounded append-only log table.
STATS_SAMPLE_LIMIT = 2000


def record_retrieval_trace(
    session: Session,
    *,
    query_type: str,
    source_id: Optional[int],
    source_type: Optional[str],
    retrieved_ids: List[int],
    similarity_scores: List[float],
    filters_applied: Optional[Dict[str, Any]] = None,
    duration_ms: int,
) -> None:
    """Best-effort trace insert; failures are logged and not propagated."""
    try:
        session.add(
            RetrievalTrace(
                query_type=query_type[:50],
                source_id=source_id,
                source_type=(source_type[:20] if source_type else None),
                retrieved_ids_json=json.dumps(retrieved_ids),
                similarity_scores_json=json.dumps(similarity_scores),
                filters_applied_json=(
                    json.dumps(filters_applied) if filters_applied else None
                ),
                duration_ms=duration_ms,
            )
        )
        session.flush()
    except Exception as e:
        logger.warning("Retrieval trace insert failed: %s", e, exc_info=True)


def list_recent_retrieval_traces(
    session: Session, limit: int = 50
) -> List[Dict[str, Any]]:
    """Most recent retrieval traces, newest first."""
    rows = (
        session.query(RetrievalTrace)
        .order_by(desc(RetrievalTrace.created_at))
        .limit(limit)
        .all()
    )
    out = []
    for r in rows:
        retrieved_ids = (
            json.loads(r.retrieved_ids_json)  # type: ignore[arg-type]
            if r.retrieved_ids_json
            else []
        )
        scores = (
            json.loads(r.similarity_scores_json)  # type: ignore[arg-type]
            if r.similarity_scores_json
            else []
        )
        out.append(
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "query_type": r.query_type,
                "source_id": r.source_id,
                "source_type": r.source_type,
                "retrieved_count": len(retrieved_ids),
                "avg_similarity": (
                    round(sum(scores) / len(scores), 4) if scores else None
                ),
                "duration_ms": r.duration_ms,
                "filters_applied": (
                    json.loads(r.filters_applied_json)  # type: ignore[arg-type]
                    if r.filters_applied_json
                    else {}
                ),
            }
        )
    return out


def get_retrieval_trace_stats(session: Session) -> Dict[str, Any]:
    """Aggregate stats over the most recent traces (query volume, latency, hit rate)."""
    total = session.query(func.count(RetrievalTrace.id)).scalar() or 0
    if total == 0:
        return {
            "total_traces": 0,
            "avg_duration_ms": None,
            "avg_results_per_query": None,
            "zero_result_rate": None,
            "by_query_type": {},
        }

    avg_duration = session.query(func.avg(RetrievalTrace.duration_ms)).scalar()

    rows = (
        session.query(RetrievalTrace.query_type, RetrievalTrace.retrieved_ids_json)
        .order_by(desc(RetrievalTrace.created_at))
        .limit(STATS_SAMPLE_LIMIT)
        .all()
    )

    by_type: Dict[str, Dict[str, Any]] = {}
    total_results = 0
    zero_result_count = 0
    for query_type, retrieved_ids_json in rows:
        ids = json.loads(retrieved_ids_json) if retrieved_ids_json else []
        count = len(ids)
        total_results += count
        if count == 0:
            zero_result_count += 1
        bucket = by_type.setdefault(query_type, {"count": 0, "total_results": 0})
        bucket["count"] += 1
        bucket["total_results"] += count

    for bucket in by_type.values():
        bucket["avg_results"] = (
            round(bucket["total_results"] / bucket["count"], 2)
            if bucket["count"]
            else 0
        )
        del bucket["total_results"]

    sample_size = len(rows)
    return {
        "total_traces": total,
        "sample_size": sample_size,
        "avg_duration_ms": (
            round(float(avg_duration), 1) if avg_duration is not None else None
        ),
        "avg_results_per_query": (
            round(total_results / sample_size, 2) if sample_size else None
        ),
        "zero_result_rate": (
            round(zero_result_count / sample_size, 4) if sample_size else None
        ),
        "by_query_type": by_type,
    }
