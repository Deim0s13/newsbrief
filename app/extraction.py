"""
Tiered content extraction module with automatic fallback.

This module implements a multi-tier extraction strategy:
1. Primary: trafilatura - Best quality, handles most news/blog sites
2. Fallback: readability-lxml - When trafilatura fails
3. Salvage: RSS summary - Last resort when all extraction fails

Each tier tracks success/failure with standardized reasons for observability.

Part of v0.8.0 - Content Extraction Pipeline Upgrade
See ADR-0024 for library selection rationale.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Minimum content length to consider extraction successful
DEFAULT_MIN_CONTENT_LENGTH = 200

# Quality score ranges by extraction method
QUALITY_SCORES = {
    "trafilatura": (0.90, 1.0),
    "readability": (0.70, 0.89),
    "rss_summary": (0.30, 0.50),
    "failed": (0.0, 0.0),
}

# Standardized failure reasons
FAILURE_REASONS = {
    "empty_content": "Extraction returned no text",
    "content_too_short": "Content below minimum length threshold",
    "parse_error": "HTML parsing failed",
    "encoding_error": "Character encoding issues",
    "timeout": "Extraction exceeded time limit",
    "import_error": "Required library not available",
    "unknown_error": "Unexpected error during extraction",
}


@dataclass
class StageResult:
    """Result from a single extraction stage attempt."""

    stage_name: str  # 'trafilatura', 'readability', 'salvage'
    attempted: bool
    success: bool
    failure_reason: str | None = None
    execution_time_ms: int = 0
    content_length: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "stage_name": self.stage_name,
            "attempted": self.attempted,
            "success": self.success,
            "failure_reason": self.failure_reason,
            "execution_time_ms": self.execution_time_ms,
            "content_length": self.content_length,
        }


@dataclass
class ExtractionMetadata:
    """
    Rich metadata extracted from content.

    This metadata is captured for use in downstream milestones:
    - author: v0.8.2 Source Credibility
    - date: Supplement RSS published date
    - images: v0.11.2 Enhanced Visualizations
    - categories/tags: v0.9.0 Entity Intelligence seeding
    """

    author: str | None = None
    date: datetime | None = None
    images: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    site_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "author": self.author,
            "date": self.date.isoformat() if self.date else None,
            "images": self.images,
            "categories": self.categories,
            "tags": self.tags,
            "site_name": self.site_name,
        }


@dataclass
class ExtractionResult:
    """Complete result from tiered content extraction."""

    content: str | None
    title: str | None
    method: str  # 'trafilatura', 'readability', 'rss_summary', 'failed'
    quality_score: float  # 0.0 - 1.0
    metadata: ExtractionMetadata
    error: str | None
    stage_results: list[StageResult]
    extraction_time_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "content": self.content,
            "title": self.title,
            "method": self.method,
            "quality_score": self.quality_score,
            "metadata": self.metadata.to_dict(),
            "error": self.error,
            "stage_results": [sr.to_dict() for sr in self.stage_results],
            "extraction_time_ms": self.extraction_time_ms,
        }

    @property
    def success(self) -> bool:
        """Whether extraction produced usable content."""
        return self.content is not None and len(self.content) > 0


def _calculate_quality_score(
    method: str, content_length: int, min_length: int = DEFAULT_MIN_CONTENT_LENGTH
) -> float:
    """
    Calculate quality score based on extraction method and content length.

    Score is determined by:
    1. Base range from extraction method
    2. Adjustment based on content length relative to minimum
    """
    if method not in QUALITY_SCORES:
        return 0.0

    min_score, max_score = QUALITY_SCORES[method]

    if content_length < min_length:
        # Penalize short content
        ratio = content_length / min_length
        return min_score * ratio

    # Scale within range based on content length
    # More content generally means better extraction (up to a point)
    length_factor = min(content_length / 1000, 1.0)  # Cap at 1000 chars
    return min_score + (max_score - min_score) * length_factor


def _try_trafilatura(
    html: str, url: str | None = None, min_length: int = DEFAULT_MIN_CONTENT_LENGTH
) -> tuple[StageResult, str | None, str | None, ExtractionMetadata]:
    """
    Attempt extraction using trafilatura (primary tier).

    Returns:
        Tuple of (StageResult, content, title, metadata)
    """
    start_time = time.time()
    metadata = ExtractionMetadata()

    try:
        import trafilatura  # type: ignore[import-untyped]
        from trafilatura.settings import use_config  # type: ignore[import-untyped]

        # Configure trafilatura for best extraction
        config = use_config()
        config.set("DEFAULT", "EXTRACTION_TIMEOUT", "30")

        # Extract with metadata
        result = trafilatura.bare_extraction(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            include_images=True,
            include_links=False,
            favor_recall=True,  # Prefer getting more content
            config=config,
        )

        elapsed_ms = int((time.time() - start_time) * 1000)

        if result is None:
            return (
                StageResult(
                    stage_name="trafilatura",
                    attempted=True,
                    success=False,
                    failure_reason="empty_content",
                    execution_time_ms=elapsed_ms,
                    content_length=0,
                ),
                None,
                None,
                metadata,
            )

        # Extract content and title
        content = result.get("text", "")
        title = result.get("title", "")

        # Check content length
        if len(content) < min_length:
            return (
                StageResult(
                    stage_name="trafilatura",
                    attempted=True,
                    success=False,
                    failure_reason="content_too_short",
                    execution_time_ms=elapsed_ms,
                    content_length=len(content),
                ),
                None,
                None,
                metadata,
            )

        # Extract rich metadata
        metadata = ExtractionMetadata(
            author=result.get("author"),
            date=_parse_date(result.get("date")),
            images=result.get("images", []) or [],
            categories=result.get("categories", []) or [],
            tags=result.get("tags", []) or [],
            site_name=result.get("sitename"),
        )

        return (
            StageResult(
                stage_name="trafilatura",
                attempted=True,
                success=True,
                failure_reason=None,
                execution_time_ms=elapsed_ms,
                content_length=len(content),
            ),
            content,
            title,
            metadata,
        )

    except ImportError:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.warning("trafilatura not installed, skipping primary extraction")
        return (
            StageResult(
                stage_name="trafilatura",
                attempted=True,
                success=False,
                failure_reason="import_error",
                execution_time_ms=elapsed_ms,
                content_length=None,
            ),
            None,
            None,
            metadata,
        )
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.warning(f"trafilatura extraction failed: {e}")
        return (
            StageResult(
                stage_name="trafilatura",
                attempted=True,
                success=False,
                failure_reason="unknown_error",
                execution_time_ms=elapsed_ms,
                content_length=None,
            ),
            None,
            None,
            metadata,
        )


def _try_readability(
    html: str, min_length: int = DEFAULT_MIN_CONTENT_LENGTH
) -> tuple[StageResult, str | None, str | None]:
    """
    Attempt extraction using readability-lxml (fallback tier).

    Returns:
        Tuple of (StageResult, content, title)
    """
    start_time = time.time()

    try:
        from readability import Document  # type: ignore[import-untyped]

        doc = Document(html)
        title = doc.short_title()
        summary_html = doc.summary(html_partial=True)

        # Extract text from HTML
        soup = BeautifulSoup(summary_html, "lxml")
        content = " ".join(soup.get_text(separator=" ").split())

        elapsed_ms = int((time.time() - start_time) * 1000)

        if not content or len(content) < min_length:
            return (
                StageResult(
                    stage_name="readability",
                    attempted=True,
                    success=False,
                    failure_reason="content_too_short" if content else "empty_content",
                    execution_time_ms=elapsed_ms,
                    content_length=len(content) if content else 0,
                ),
                None,
                None,
            )

        return (
            StageResult(
                stage_name="readability",
                attempted=True,
                success=True,
                failure_reason=None,
                execution_time_ms=elapsed_ms,
                content_length=len(content),
            ),
            content,
            title,
        )

    except ImportError:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.warning("readability-lxml not installed, skipping fallback extraction")
        return (
            StageResult(
                stage_name="readability",
                attempted=True,
                success=False,
                failure_reason="import_error",
                execution_time_ms=elapsed_ms,
                content_length=None,
            ),
            None,
            None,
        )
    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.warning(f"readability extraction failed: {e}")
        return (
            StageResult(
                stage_name="readability",
                attempted=True,
                success=False,
                failure_reason="parse_error",
                execution_time_ms=elapsed_ms,
                content_length=None,
            ),
            None,
            None,
        )


def _try_salvage(
    rss_summary: str | None, min_length: int = 50
) -> tuple[StageResult, str | None]:
    """
    Salvage mode: use RSS summary as last resort.

    Returns:
        Tuple of (StageResult, content)
    """
    start_time = time.time()

    if not rss_summary:
        elapsed_ms = int((time.time() - start_time) * 1000)
        return (
            StageResult(
                stage_name="salvage",
                attempted=True,
                success=False,
                failure_reason="empty_content",
                execution_time_ms=elapsed_ms,
                content_length=0,
            ),
            None,
        )

    # Clean the RSS summary (remove HTML tags if present)
    try:
        soup = BeautifulSoup(rss_summary, "lxml")
        content = " ".join(soup.get_text(separator=" ").split())
    except Exception:
        content = rss_summary

    elapsed_ms = int((time.time() - start_time) * 1000)

    if len(content) < min_length:
        return (
            StageResult(
                stage_name="salvage",
                attempted=True,
                success=False,
                failure_reason="content_too_short",
                execution_time_ms=elapsed_ms,
                content_length=len(content),
            ),
            None,
        )

    return (
        StageResult(
            stage_name="salvage",
            attempted=True,
            success=True,
            failure_reason=None,
            execution_time_ms=elapsed_ms,
            content_length=len(content),
        ),
        content,
    )


def _parse_date(date_str: str | None) -> datetime | None:
    """Parse date string from trafilatura into datetime."""
    if not date_str:
        return None

    try:
        # trafilatura typically returns dates in YYYY-MM-DD format
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


def extract_content(
    html: str,
    url: str | None = None,
    rss_summary: str | None = None,
    min_content_length: int = DEFAULT_MIN_CONTENT_LENGTH,
) -> ExtractionResult:
    """
    Extract article content using tiered extraction strategy.

    Tries extractors in order of quality:
    1. trafilatura (primary) - Best quality, rich metadata
    2. readability-lxml (fallback) - Good for when trafilatura fails
    3. RSS summary (salvage) - Last resort

    Args:
        html: Raw HTML content to extract from
        url: Original URL (helps trafilatura with relative links)
        rss_summary: RSS feed summary to use as fallback
        min_content_length: Minimum chars to consider extraction successful

    Returns:
        ExtractionResult with content, method used, quality score, and metadata
    """
    start_time = time.time()
    stage_results: list[StageResult] = []
    metadata = ExtractionMetadata()

    # Tier 1: Try trafilatura (primary)
    traf_result, traf_content, traf_title, traf_metadata = _try_trafilatura(
        html, url, min_content_length
    )
    stage_results.append(traf_result)

    if traf_result.success and traf_content:
        elapsed_ms = int((time.time() - start_time) * 1000)
        quality_score = _calculate_quality_score(
            "trafilatura", len(traf_content), min_content_length
        )

        logger.info(
            f"Extraction successful with trafilatura: {len(traf_content)} chars, "
            f"quality={quality_score:.2f}"
        )

        return ExtractionResult(
            content=traf_content,
            title=traf_title,
            method="trafilatura",
            quality_score=quality_score,
            metadata=traf_metadata,
            error=None,
            stage_results=stage_results,
            extraction_time_ms=elapsed_ms,
        )

    # Tier 2: Try readability-lxml (fallback)
    read_result, read_content, read_title = _try_readability(html, min_content_length)
    stage_results.append(read_result)

    if read_result.success and read_content:
        elapsed_ms = int((time.time() - start_time) * 1000)
        quality_score = _calculate_quality_score(
            "readability", len(read_content), min_content_length
        )

        logger.info(
            f"Extraction successful with readability: {len(read_content)} chars, "
            f"quality={quality_score:.2f}"
        )

        # Use any metadata from trafilatura attempt even if content failed
        return ExtractionResult(
            content=read_content,
            title=read_title,
            method="readability",
            quality_score=quality_score,
            metadata=traf_metadata if traf_metadata.author else metadata,
            error=None,
            stage_results=stage_results,
            extraction_time_ms=elapsed_ms,
        )

    # Tier 3: Salvage mode (RSS summary)
    salvage_result, salvage_content = _try_salvage(rss_summary)
    stage_results.append(salvage_result)

    if salvage_result.success and salvage_content:
        elapsed_ms = int((time.time() - start_time) * 1000)
        quality_score = _calculate_quality_score(
            "rss_summary", len(salvage_content), min_content_length
        )

        logger.info(
            f"Extraction salvaged with RSS summary: {len(salvage_content)} chars, "
            f"quality={quality_score:.2f}"
        )

        return ExtractionResult(
            content=salvage_content,
            title=None,  # RSS summary doesn't provide title
            method="rss_summary",
            quality_score=quality_score,
            metadata=metadata,
            error=None,
            stage_results=stage_results,
            extraction_time_ms=elapsed_ms,
        )

    # All tiers failed
    elapsed_ms = int((time.time() - start_time) * 1000)

    # Determine primary failure reason
    failure_reasons = [sr.failure_reason for sr in stage_results if sr.failure_reason]
    primary_error = failure_reasons[0] if failure_reasons else "unknown_error"

    logger.warning(f"All extraction tiers failed. Reasons: {failure_reasons}")

    return ExtractionResult(
        content=None,
        title=None,
        method="failed",
        quality_score=0.0,
        metadata=metadata,
        error=primary_error,
        stage_results=stage_results,
        extraction_time_ms=elapsed_ms,
    )
