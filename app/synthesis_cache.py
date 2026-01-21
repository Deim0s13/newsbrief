"""
Synthesis caching for LLM-generated story content.

Implements database-backed caching of LLM synthesis results to avoid
redundant API calls for identical article combinations.

Key Features:
- Cache key: hash of sorted article IDs + model name
- TTL-based expiration
- Invalidation on source article changes
- Token usage tracking
- Performance metrics

See ADR 0003 for architectural decisions.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional, cast

from sqlalchemy.orm import Session

from .orm_models import SynthesisCache

logger = logging.getLogger(__name__)

# Token counting encoding (compatible with most modern LLMs)
TOKEN_ENCODING = "cl100k_base"


def count_tokens(text: str) -> int:
    """
    Count tokens in text using tiktoken.

    Uses cl100k_base encoding which is compatible with GPT-4, GPT-3.5,
    and provides reasonable estimates for Llama-based models.

    Args:
        text: Text to count tokens for

    Returns:
        Estimated token count
    """
    if not text:
        return 0

    try:
        import tiktoken

        encoding = tiktoken.get_encoding(TOKEN_ENCODING)
        return len(encoding.encode(text))
    except ImportError:
        logger.debug("tiktoken not available, using character-based estimate")
        # Rough estimate: 1 token ≈ 4 characters
        return len(text) // 4
    except Exception as e:
        logger.warning(f"Token counting failed: {e}, using estimate")
        return len(text) // 4


# Configuration
SYNTHESIS_CACHE_ENABLED = os.getenv("SYNTHESIS_CACHE_ENABLED", "true").lower() == "true"
SYNTHESIS_CACHE_TTL_HOURS = int(os.getenv("SYNTHESIS_CACHE_TTL_HOURS", "168"))  # 7 days
SYNTHESIS_TOKEN_TRACKING = (
    os.getenv("SYNTHESIS_TOKEN_TRACKING", "true").lower() == "true"
)

# SynthesisCache ORM model is imported from orm_models


def generate_cache_key(article_ids: List[int], model: str) -> str:
    """
    Generate a deterministic cache key from article IDs and model.

    Args:
        article_ids: List of article IDs (order doesn't matter)
        model: LLM model name

    Returns:
        SHA-256 hash string (64 characters)
    """
    # Sort IDs for order-independence
    sorted_ids = sorted(article_ids)
    key_string = f"{sorted_ids}:{model}"
    return hashlib.sha256(key_string.encode()).hexdigest()


def get_cached_synthesis(
    session: Session,
    article_ids: List[int],
    model: str,
) -> Optional[Dict[str, Any]]:
    """
    Look up cached synthesis for the given articles and model.

    Args:
        session: Database session
        article_ids: List of article IDs
        model: LLM model name

    Returns:
        Cached synthesis dict if found and valid, None otherwise
    """
    if not SYNTHESIS_CACHE_ENABLED:
        logger.debug("Synthesis cache disabled")
        return None

    cache_key = generate_cache_key(article_ids, model)
    now = datetime.now(UTC)

    # Query cache
    cache_entry = (
        session.query(SynthesisCache)
        .filter(SynthesisCache.cache_key == cache_key)
        .first()
    )

    if cache_entry is None:
        logger.debug(f"Cache MISS: no entry for key {cache_key[:12]}...")
        return None

    # Check if invalidated
    if cache_entry.invalidated_at is not None:
        logger.debug(f"Cache MISS: entry invalidated at {cache_entry.invalidated_at}")
        return None

    # Check if expired (handle timezone-naive datetimes from SQLite)
    expires_at = cache_entry.expires_at
    if expires_at:
        # Make timezone-aware if needed
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < now:
            logger.debug(f"Cache MISS: entry expired at {cache_entry.expires_at}")
            return None

    logger.info(f"Cache HIT: using cached synthesis for key {cache_key[:12]}...")

    # Return cached result - cast Column types to str for json.loads
    return {
        "synthesis": cache_entry.synthesis,
        "key_points": json.loads(cast(str, cache_entry.key_points_json) or "[]"),
        "why_it_matters": cache_entry.why_it_matters or "",
        "topics": json.loads(cast(str, cache_entry.topics_json) or "[]"),
        "entities": json.loads(cast(str, cache_entry.entities_json) or "[]"),
        "_cached": True,
        "_cache_key": cache_key,
        "_cached_at": (
            cache_entry.created_at.isoformat() if cache_entry.created_at else None
        ),
    }


def store_synthesis_in_cache(
    session: Session,
    article_ids: List[int],
    model: str,
    synthesis_result: Dict[str, Any],
    generation_time_ms: Optional[int] = None,
    token_count_input: Optional[int] = None,
    token_count_output: Optional[int] = None,
) -> str:
    """
    Store a synthesis result in the cache.

    Args:
        session: Database session
        article_ids: List of article IDs
        model: LLM model name
        synthesis_result: The synthesis dict from LLM
        generation_time_ms: How long synthesis took (optional)
        token_count_input: Input token count (optional)
        token_count_output: Output token count (optional)

    Returns:
        The cache key used
    """
    if not SYNTHESIS_CACHE_ENABLED:
        return ""

    cache_key = generate_cache_key(article_ids, model)
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=SYNTHESIS_CACHE_TTL_HOURS)

    try:
        # Check if entry already exists
        existing = (
            session.query(SynthesisCache)
            .filter(SynthesisCache.cache_key == cache_key)
            .first()
        )

        if existing:
            # Update existing entry (type: ignore for SQLAlchemy Column assignments)
            existing.synthesis = synthesis_result.get("synthesis", "")  # type: ignore[assignment]
            existing.key_points_json = json.dumps(synthesis_result.get("key_points", []))  # type: ignore[assignment]
            existing.why_it_matters = synthesis_result.get("why_it_matters", "")  # type: ignore[assignment]
            existing.topics_json = json.dumps(synthesis_result.get("topics", []))  # type: ignore[assignment]
            existing.entities_json = json.dumps(synthesis_result.get("entities", []))  # type: ignore[assignment]
            existing.generation_time_ms = generation_time_ms  # type: ignore[assignment]
            existing.token_count_input = token_count_input  # type: ignore[assignment]
            existing.token_count_output = token_count_output  # type: ignore[assignment]
            existing.created_at = now  # type: ignore[assignment]
            existing.expires_at = expires_at  # type: ignore[assignment]
            existing.invalidated_at = None  # type: ignore[assignment]
            logger.debug(f"Cache UPDATE: refreshed entry for key {cache_key[:12]}...")
        else:
            # Create new entry
            cache_entry = SynthesisCache(
                cache_key=cache_key,
                article_ids_json=json.dumps(sorted(article_ids)),
                model=model,
                synthesis=synthesis_result.get("synthesis", ""),
                key_points_json=json.dumps(synthesis_result.get("key_points", [])),
                why_it_matters=synthesis_result.get("why_it_matters", ""),
                topics_json=json.dumps(synthesis_result.get("topics", [])),
                entities_json=json.dumps(synthesis_result.get("entities", [])),
                generation_time_ms=generation_time_ms,
                token_count_input=token_count_input,
                token_count_output=token_count_output,
                created_at=now,
                expires_at=expires_at,
            )
            session.add(cache_entry)
            logger.debug(f"Cache STORE: new entry for key {cache_key[:12]}...")

        # Flush to detect any constraint violations early
        session.flush()

    except Exception as e:
        # Handle race condition: another process may have inserted the same key
        logger.warning(f"Cache store failed for key {cache_key[:12]}...: {e}")
        session.rollback()

        # Try to update existing entry (may have been inserted by another process)
        try:
            existing = (
                session.query(SynthesisCache)
                .filter(SynthesisCache.cache_key == cache_key)
                .first()
            )
            if existing:
                existing.synthesis = synthesis_result.get("synthesis", "")  # type: ignore[assignment]
                existing.key_points_json = json.dumps(synthesis_result.get("key_points", []))  # type: ignore[assignment]
                existing.why_it_matters = synthesis_result.get("why_it_matters", "")  # type: ignore[assignment]
                existing.topics_json = json.dumps(synthesis_result.get("topics", []))  # type: ignore[assignment]
                existing.entities_json = json.dumps(synthesis_result.get("entities", []))  # type: ignore[assignment]
                existing.generation_time_ms = generation_time_ms  # type: ignore[assignment]
                existing.token_count_input = token_count_input  # type: ignore[assignment]
                existing.token_count_output = token_count_output  # type: ignore[assignment]
                existing.created_at = now  # type: ignore[assignment]
                existing.expires_at = expires_at  # type: ignore[assignment]
                existing.invalidated_at = None  # type: ignore[assignment]
                session.flush()
                logger.debug(
                    f"Cache UPDATE (after conflict): updated entry for key {cache_key[:12]}..."
                )
            else:
                # Entry doesn't exist after rollback - something else went wrong
                logger.error(
                    f"Cache store failed permanently for key {cache_key[:12]}..."
                )
        except Exception as retry_error:
            logger.error(
                f"Cache store retry failed for key {cache_key[:12]}...: {retry_error}"
            )
            # Don't re-raise - caching failures shouldn't break story generation

    return cache_key


def invalidate_cache_for_articles(
    session: Session,
    article_ids: List[int],
) -> int:
    """
    Invalidate all cache entries that include any of the given articles.

    Called when article content changes to ensure stale synthesis isn't used.

    Args:
        session: Database session
        article_ids: List of article IDs whose content changed

    Returns:
        Number of cache entries invalidated
    """
    if not article_ids:
        return 0

    now = datetime.now(UTC)
    invalidated_count = 0

    # Find all cache entries that include any of these articles
    # We need to check the article_ids_json field
    all_entries = (
        session.query(SynthesisCache)
        .filter(SynthesisCache.invalidated_at.is_(None))
        .all()
    )

    for entry in all_entries:
        try:
            cached_article_ids = set(json.loads(cast(str, entry.article_ids_json)))
            if cached_article_ids.intersection(set(article_ids)):
                entry.invalidated_at = now  # type: ignore[assignment]
                invalidated_count += 1
                logger.debug(
                    f"Invalidated cache entry {entry.cache_key[:12]}... "
                    f"(contains article(s) {cached_article_ids.intersection(set(article_ids))})"
                )
        except json.JSONDecodeError:
            continue

    if invalidated_count > 0:
        logger.info(
            f"Invalidated {invalidated_count} cache entries for article changes"
        )

    return invalidated_count


def cleanup_expired_cache(session: Session) -> int:
    """
    Remove expired and invalidated cache entries.

    Should be run periodically (e.g., daily) to prevent unbounded growth.

    Args:
        session: Database session

    Returns:
        Number of entries deleted
    """
    now = datetime.now(UTC)

    # Delete expired entries
    expired_count = (
        session.query(SynthesisCache)
        .filter(SynthesisCache.expires_at < now)
        .delete(synchronize_session=False)
    )

    # Delete invalidated entries older than 24 hours
    old_invalidated = now - timedelta(hours=24)
    invalidated_count = (
        session.query(SynthesisCache)
        .filter(
            SynthesisCache.invalidated_at.isnot(None),
            SynthesisCache.invalidated_at < old_invalidated,
        )
        .delete(synchronize_session=False)
    )

    total_deleted = expired_count + invalidated_count
    if total_deleted > 0:
        logger.info(
            f"Cache cleanup: deleted {expired_count} expired + "
            f"{invalidated_count} invalidated = {total_deleted} total entries"
        )

    return total_deleted


def get_cache_stats(session: Session) -> Dict[str, Any]:
    """
    Get statistics about the synthesis cache.

    Args:
        session: Database session

    Returns:
        Dict with cache statistics
    """
    now = datetime.now(UTC)

    total_entries = session.query(SynthesisCache).count()
    valid_entries = (
        session.query(SynthesisCache)
        .filter(
            SynthesisCache.invalidated_at.is_(None),
            (SynthesisCache.expires_at.is_(None)) | (SynthesisCache.expires_at >= now),
        )
        .count()
    )
    expired_entries = (
        session.query(SynthesisCache).filter(SynthesisCache.expires_at < now).count()
    )
    invalidated_entries = (
        session.query(SynthesisCache)
        .filter(SynthesisCache.invalidated_at.isnot(None))
        .count()
    )

    # Calculate average metrics
    from sqlalchemy import func

    metrics = session.query(
        func.avg(SynthesisCache.generation_time_ms).label("avg_generation_ms"),
        func.sum(SynthesisCache.token_count_input).label("total_tokens_input"),
        func.sum(SynthesisCache.token_count_output).label("total_tokens_output"),
    ).first()

    return {
        "enabled": SYNTHESIS_CACHE_ENABLED,
        "ttl_hours": SYNTHESIS_CACHE_TTL_HOURS,
        "total_entries": total_entries,
        "valid_entries": valid_entries,
        "expired_entries": expired_entries,
        "invalidated_entries": invalidated_entries,
        "avg_generation_time_ms": round(metrics.avg_generation_ms or 0, 2),
        "total_tokens_input": metrics.total_tokens_input or 0,
        "total_tokens_output": metrics.total_tokens_output or 0,
    }
