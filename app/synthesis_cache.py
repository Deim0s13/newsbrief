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
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import Session

from .stories import Base

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


class SynthesisCache(Base):  # type: ignore[misc,valid-type]
    """
    ORM model for synthesis_cache table.

    Stores LLM synthesis results keyed by a deterministic hash
    of the input (sorted article IDs + model name).
    """

    __tablename__ = "synthesis_cache"

    id = Column(Integer, primary_key=True)
    cache_key = Column(String(64), unique=True, nullable=False, index=True)
    article_ids_json = Column(Text, nullable=False)  # For verification/debugging
    model = Column(String(50), nullable=False)

    # Synthesis results
    synthesis = Column(Text, nullable=False)
    key_points_json = Column(Text)
    why_it_matters = Column(Text)
    topics_json = Column(Text)
    entities_json = Column(Text)

    # Metrics
    token_count_input = Column(Integer)
    token_count_output = Column(Integer)
    generation_time_ms = Column(Integer)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    expires_at = Column(DateTime, index=True)
    invalidated_at = Column(DateTime)  # Soft invalidation


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

    # Return cached result
    return {
        "synthesis": cache_entry.synthesis,
        "key_points": json.loads(cache_entry.key_points_json or "[]"),
        "why_it_matters": cache_entry.why_it_matters or "",
        "topics": json.loads(cache_entry.topics_json or "[]"),
        "entities": json.loads(cache_entry.entities_json or "[]"),
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

    # Check if entry already exists
    existing = (
        session.query(SynthesisCache)
        .filter(SynthesisCache.cache_key == cache_key)
        .first()
    )

    if existing:
        # Update existing entry
        existing.synthesis = synthesis_result.get("synthesis", "")
        existing.key_points_json = json.dumps(synthesis_result.get("key_points", []))
        existing.why_it_matters = synthesis_result.get("why_it_matters", "")
        existing.topics_json = json.dumps(synthesis_result.get("topics", []))
        existing.entities_json = json.dumps(synthesis_result.get("entities", []))
        existing.generation_time_ms = generation_time_ms
        existing.token_count_input = token_count_input
        existing.token_count_output = token_count_output
        existing.created_at = now
        existing.expires_at = expires_at
        existing.invalidated_at = None  # Clear any invalidation
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
            cached_article_ids = set(json.loads(entry.article_ids_json))
            if cached_article_ids.intersection(set(article_ids)):
                entry.invalidated_at = now
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
