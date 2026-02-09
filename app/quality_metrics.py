"""
Quality metrics calculation and tracking for LLM outputs.

This module provides:
- Quality scoring algorithms for synthesis, entities, and titles
- Metrics logging to database for historical analysis
- Aggregation functions for dashboard and API reporting

Created for Issue #105: Add output quality metrics and tracking.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from .llm_output import LLMParseMetrics

logger = logging.getLogger(__name__)


@dataclass
class QualityBreakdown:
    """Breakdown of quality score components."""

    completeness: float  # Presence of required fields
    coverage: float  # Synthesis length relative to input
    entity_consistency: float  # Entities appearing in synthesis
    parse_success: float  # Parsing quality (strategy, repairs)
    title_quality: float  # Title source and length
    overall: float  # Weighted composite score

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "QualityBreakdown":
        """Create from dictionary."""
        return cls(**data)


# =============================================================================
# Scoring Functions
# =============================================================================


def score_completeness(synthesis: Dict[str, Any]) -> float:
    """
    Score based on presence and quality of required fields.

    Criteria:
    - Key points count (target 3-5)
    - Synthesis text length (target 100-2000 chars)
    - Has why_it_matters
    - Has topics

    Returns:
        Score from 0.0 to 1.0
    """
    score = 0.0

    # Key points (target 3-5)
    key_points = synthesis.get("key_points", [])
    if isinstance(key_points, list):
        if 3 <= len(key_points) <= 5:
            score += 0.4
        elif len(key_points) >= 2:
            score += 0.2
        elif len(key_points) >= 1:
            score += 0.1

    # Has synthesis text of reasonable length
    synthesis_text = synthesis.get("synthesis", "")
    if isinstance(synthesis_text, str):
        if 100 <= len(synthesis_text) <= 2000:
            score += 0.3
        elif len(synthesis_text) > 50:
            score += 0.15

    # Has why_it_matters
    why_it_matters = synthesis.get("why_it_matters", "")
    if why_it_matters and len(str(why_it_matters)) > 20:
        score += 0.2

    # Has topics
    topics = synthesis.get("topics", [])
    if topics and len(topics) > 0:
        score += 0.1

    return min(score, 1.0)


def score_coverage(synthesis: Dict[str, Any], article_count: int) -> float:
    """
    Score based on synthesis length relative to input article count.

    Expectation: ~100-200 characters per article for good coverage.

    Args:
        synthesis: Synthesis result dictionary
        article_count: Number of source articles

    Returns:
        Score from 0.0 to 1.0
    """
    if article_count <= 0:
        return 0.5  # Neutral if no articles

    synthesis_text = synthesis.get("synthesis", "")
    if not isinstance(synthesis_text, str):
        return 0.0

    synthesis_len = len(synthesis_text)

    # Expected ~100-200 chars per article for good coverage
    expected_min = article_count * 80
    expected_max = article_count * 300

    if expected_min <= synthesis_len <= expected_max:
        return 1.0
    elif synthesis_len < expected_min:
        return max(0.3, synthesis_len / expected_min)
    else:
        # Too long - slight penalty
        return max(0.5, 1.0 - (synthesis_len - expected_max) / expected_max)


def score_entity_consistency(synthesis: Dict[str, Any]) -> float:
    """
    Score based on extracted entities appearing in synthesis text.

    Good syntheses should mention most extracted entities.

    Returns:
        Score from 0.0 to 1.0
    """
    entities = synthesis.get("entities", [])
    if not entities or not isinstance(entities, list):
        return 0.5  # Neutral if no entities

    synthesis_text = synthesis.get("synthesis", "")
    if not synthesis_text:
        return 0.0

    synthesis_lower = synthesis_text.lower()
    found = sum(1 for e in entities if str(e).lower() in synthesis_lower)

    return found / len(entities)


def score_parse_success(parse_metrics: "LLMParseMetrics") -> float:
    """
    Score based on parsing success and strategy used.

    Direct parsing = best, repairs/fallbacks reduce score.

    Args:
        parse_metrics: Metrics from LLM output parsing

    Returns:
        Score from 0.0 to 1.0
    """
    if not parse_metrics.success:
        return 0.0

    # Strategy scores - direct is best
    strategy_scores = {
        "direct": 1.0,
        "markdown_block": 0.9,
        "brace_match": 0.7,
        "greedy_regex": 0.5,
        "line_by_line": 0.3,
        "none": 0.0,
    }

    base_score = strategy_scores.get(parse_metrics.strategy_used, 0.5)

    # Penalty for repairs applied
    repairs = parse_metrics.repairs_made or []
    repair_penalty = len(repairs) * 0.05

    # Penalty for retries
    retry_penalty = (parse_metrics.retry_count or 0) * 0.1

    return max(0.0, base_score - repair_penalty - retry_penalty)


def score_title_quality(synthesis: Dict[str, Any], title_source: str = "llm") -> float:
    """
    Score title quality based on source and characteristics.

    LLM-generated titles are preferred. Good titles are 40-80 chars, 6-12 words.

    Args:
        synthesis: Synthesis result dictionary
        title_source: 'llm' or 'fallback'

    Returns:
        Score from 0.0 to 1.0
    """
    title = synthesis.get("title", "")
    if not title:
        return 0.0

    score = 0.0

    # Source (LLM preferred)
    if title_source == "llm":
        score += 0.4
    else:
        score += 0.2

    # Length (target 40-80 chars)
    title_len = len(title)
    if 40 <= title_len <= 80:
        score += 0.3
    elif 20 <= title_len <= 100:
        score += 0.2
    else:
        score += 0.1

    # Word count (target 6-12 words)
    word_count = len(title.split())
    if 6 <= word_count <= 12:
        score += 0.3
    elif 4 <= word_count <= 15:
        score += 0.2
    else:
        score += 0.1

    return min(score, 1.0)


def calculate_quality_score(
    synthesis: Dict[str, Any],
    parse_metrics: "LLMParseMetrics",
    article_count: int,
    title_source: str = "llm",
) -> QualityBreakdown:
    """
    Calculate comprehensive quality breakdown for a synthesis.

    Combines multiple scoring factors with configurable weights.

    Args:
        synthesis: Synthesis result dictionary
        parse_metrics: Metrics from LLM output parsing
        article_count: Number of source articles
        title_source: 'llm' or 'fallback'

    Returns:
        QualityBreakdown with individual and overall scores
    """
    breakdown = QualityBreakdown(
        completeness=score_completeness(synthesis),
        coverage=score_coverage(synthesis, article_count),
        entity_consistency=score_entity_consistency(synthesis),
        parse_success=score_parse_success(parse_metrics),
        title_quality=score_title_quality(synthesis, title_source),
        overall=0.0,
    )

    # Weighted composite score
    weights = {
        "completeness": 0.25,
        "coverage": 0.25,
        "entity_consistency": 0.20,
        "parse_success": 0.15,
        "title_quality": 0.15,
    }

    breakdown.overall = sum(getattr(breakdown, k) * v for k, v in weights.items())

    return breakdown


# =============================================================================
# Metrics Logging
# =============================================================================


def log_llm_metrics(
    session: Session,
    operation_type: str,
    model: str,
    parse_metrics: "LLMParseMetrics",
    quality_breakdown: Optional[QualityBreakdown] = None,
    story_id: Optional[int] = None,
    article_id: Optional[int] = None,
    article_count: Optional[int] = None,
    token_count_input: Optional[int] = None,
    token_count_output: Optional[int] = None,
    generation_time_ms: Optional[int] = None,
) -> int:
    """
    Log LLM operation metrics to database.

    Args:
        session: Database session
        operation_type: 'synthesis', 'entity_extraction', 'topic_classification'
        model: LLM model name
        parse_metrics: Parsing metrics from llm_output module
        quality_breakdown: Quality scores (optional)
        story_id: Associated story ID (optional)
        article_id: Associated article ID (optional)
        article_count: Number of articles processed (optional)
        token_count_input: Input tokens (optional)
        token_count_output: Output tokens (optional)
        generation_time_ms: Generation time in ms (optional)

    Returns:
        ID of the created metrics record
    """
    from .orm_models import LLMMetrics

    metrics_record = LLMMetrics(
        operation_type=operation_type,
        model=model,
        created_at=datetime.now(UTC),
        generation_time_ms=generation_time_ms or parse_metrics.total_time_ms,
        parse_success=parse_metrics.success,
        parse_strategy=parse_metrics.strategy_used,
        repairs_applied=json.dumps(parse_metrics.repairs_made or []),
        retry_count=parse_metrics.retry_count or 0,
        quality_score=quality_breakdown.overall if quality_breakdown else None,
        quality_breakdown=(
            json.dumps(quality_breakdown.to_dict()) if quality_breakdown else None
        ),
        token_count_input=token_count_input,
        token_count_output=token_count_output,
        story_id=story_id,
        article_id=article_id,
        article_count=article_count,
        error_category=(
            parse_metrics.error_category if not parse_metrics.success else None
        ),
        error_message=(
            parse_metrics.error_message if not parse_metrics.success else None
        ),
    )

    session.add(metrics_record)
    session.flush()

    logger.debug(
        f"Logged LLM metrics: {operation_type}, "
        f"success={parse_metrics.success}, "
        f"quality={quality_breakdown.overall if quality_breakdown else 'N/A'}"
    )

    return int(metrics_record.id)  # type: ignore[arg-type]


# =============================================================================
# Aggregation Functions
# =============================================================================


def get_quality_summary(session: Session, days: int = 7) -> Dict[str, Any]:
    """
    Get overall quality summary across all LLM operations.

    Args:
        session: Database session
        days: Number of days to include

    Returns:
        Dictionary with quality metrics by operation type
    """
    from sqlalchemy import Integer

    from .orm_models import LLMMetrics

    cutoff = datetime.now(UTC) - timedelta(days=days)

    # Overall stats by operation type
    stats_query = (
        session.query(
            LLMMetrics.operation_type,
            func.count(LLMMetrics.id).label("total"),
            func.sum(func.cast(LLMMetrics.parse_success, Integer)).label("successes"),
            func.avg(LLMMetrics.quality_score).label("avg_quality"),
            func.avg(LLMMetrics.generation_time_ms).label("avg_time_ms"),
        )
        .filter(LLMMetrics.created_at >= cutoff)
        .group_by(LLMMetrics.operation_type)
    )

    results = {}
    for row in stats_query:
        op_type = row.operation_type
        total = row.total or 0
        successes = row.successes or 0
        results[op_type] = {
            "total_operations": total,
            "success_rate": round(successes / total, 3) if total > 0 else 0,
            "avg_quality_score": round(row.avg_quality or 0, 3),
            "avg_generation_time_ms": int(row.avg_time_ms or 0),
        }

    return results


def get_quality_distribution(session: Session, days: int = 7) -> Dict[str, int]:
    """
    Get distribution of quality scores.

    Returns:
        Dictionary with count per quality tier
    """
    from .orm_models import LLMMetrics

    cutoff = datetime.now(UTC) - timedelta(days=days)

    query = text(
        """
        SELECT
            CASE
                WHEN quality_score >= 0.9 THEN 'excellent'
                WHEN quality_score >= 0.7 THEN 'good'
                WHEN quality_score >= 0.5 THEN 'fair'
                WHEN quality_score IS NOT NULL THEN 'poor'
                ELSE 'unknown'
            END as tier,
            COUNT(*) as count
        FROM llm_metrics
        WHERE created_at >= :cutoff
          AND operation_type = 'synthesis'
        GROUP BY tier
        ORDER BY count DESC
    """
    )

    rows = session.execute(query, {"cutoff": cutoff}).fetchall()
    return {row[0]: row[1] for row in rows}


def get_strategy_distribution(session: Session, days: int = 7) -> Dict[str, int]:
    """
    Get distribution of parsing strategies used.

    Returns:
        Dictionary with count per strategy
    """
    from .orm_models import LLMMetrics

    cutoff = datetime.now(UTC) - timedelta(days=days)

    query = (
        session.query(
            LLMMetrics.parse_strategy,
            func.count(LLMMetrics.id).label("count"),
        )
        .filter(LLMMetrics.created_at >= cutoff)
        .filter(LLMMetrics.parse_strategy.isnot(None))
        .group_by(LLMMetrics.parse_strategy)
    )

    return {str(row.parse_strategy): int(row.count) for row in query}


def get_quality_trends(
    session: Session, days: int = 7, operation_type: str = "synthesis"
) -> List[Dict[str, Any]]:
    """
    Get quality score trends over time.

    Args:
        session: Database session
        days: Number of days to include
        operation_type: Filter by operation type

    Returns:
        List of daily averages
    """
    cutoff = datetime.now(UTC) - timedelta(days=days)

    query = text(
        """
        SELECT
            DATE(created_at) as date,
            AVG(quality_score) as avg_quality,
            COUNT(*) as count,
            SUM(CASE WHEN parse_success THEN 1 ELSE 0 END) as successes
        FROM llm_metrics
        WHERE created_at >= :cutoff
          AND operation_type = :op_type
          AND quality_score IS NOT NULL
        GROUP BY DATE(created_at)
        ORDER BY date
    """
    )

    rows = session.execute(
        query, {"cutoff": cutoff, "op_type": operation_type}
    ).fetchall()

    return [
        {
            "date": str(row[0]),
            "avg_quality": round(row[1], 3) if row[1] else 0,
            "count": row[2],
            "success_rate": round(row[3] / row[2], 3) if row[2] > 0 else 0,
        }
        for row in rows
    ]


def get_component_averages(session: Session, days: int = 7) -> Dict[str, float]:
    """
    Get average scores for each quality component.

    Parses quality_breakdown JSON to aggregate component scores.

    Returns:
        Dictionary of component name to average score
    """
    from .orm_models import LLMMetrics

    cutoff = datetime.now(UTC) - timedelta(days=days)

    # Get all quality breakdowns
    query = (
        session.query(LLMMetrics.quality_breakdown)
        .filter(LLMMetrics.created_at >= cutoff)
        .filter(LLMMetrics.quality_breakdown.isnot(None))
        .filter(LLMMetrics.operation_type == "synthesis")
    )

    component_totals: Dict[str, float] = {}
    component_counts: Dict[str, int] = {}

    for (breakdown_json,) in query:
        try:
            breakdown = json.loads(breakdown_json)
            for key, value in breakdown.items():
                if key != "overall" and isinstance(value, (int, float)):
                    component_totals[key] = component_totals.get(key, 0) + value
                    component_counts[key] = component_counts.get(key, 0) + 1
        except (json.JSONDecodeError, TypeError):
            continue

    return {
        key: round(component_totals[key] / component_counts[key], 3)
        for key in component_totals
        if component_counts.get(key, 0) > 0
    }


def get_recent_low_quality_stories(
    session: Session, threshold: float = 0.5, limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get recent stories with low quality scores.

    Useful for identifying issues and debugging.

    Args:
        session: Database session
        threshold: Quality score threshold
        limit: Maximum results

    Returns:
        List of low-quality story summaries
    """
    from .orm_models import LLMMetrics, Story

    query = (
        session.query(
            LLMMetrics.id,
            LLMMetrics.story_id,
            LLMMetrics.quality_score,
            LLMMetrics.quality_breakdown,
            LLMMetrics.parse_strategy,
            LLMMetrics.error_category,
            LLMMetrics.created_at,
            Story.title,
        )
        .outerjoin(Story, LLMMetrics.story_id == Story.id)
        .filter(LLMMetrics.operation_type == "synthesis")
        .filter(
            (LLMMetrics.quality_score < threshold)
            | (LLMMetrics.parse_success == False)  # noqa: E712
        )
        .order_by(LLMMetrics.created_at.desc())
        .limit(limit)
    )

    results = []
    for row in query:
        breakdown = {}
        if row.quality_breakdown:
            try:
                breakdown = json.loads(row.quality_breakdown)
            except json.JSONDecodeError:
                pass

        results.append(
            {
                "metrics_id": row.id,
                "story_id": row.story_id,
                "story_title": row.title,
                "quality_score": row.quality_score,
                "quality_breakdown": breakdown,
                "parse_strategy": row.parse_strategy,
                "error": row.error_category,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )

    return results
