"""
Source credibility utilities for NewsBrief.

This module provides:
- Domain canonicalization for URL normalization
- Credibility score calculation (factual reporting only)
- Source type classification and synthesis eligibility
- MBFC data mapping

Part of v0.8.2 - Issue #196: Create source_credibility database schema
See ADR-0028: Source Credibility Architecture
See docs/research/SOURCE-CREDIBILITY-RESEARCH.md for data source details
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse

if TYPE_CHECKING:
    from typing import Any

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Enums for type safety
# -----------------------------------------------------------------------------


class SourceType(str, Enum):
    """Source type classification (ADR-0028)."""

    NEWS = "news"
    SATIRE = "satire"
    CONSPIRACY = "conspiracy"
    FAKE_NEWS = "fake_news"
    PRO_SCIENCE = "pro_science"
    STATE_MEDIA = "state_media"
    ADVOCACY = "advocacy"


class FactualReporting(str, Enum):
    """Factual accuracy rating levels."""

    VERY_HIGH = "very_high"
    HIGH = "high"
    MOSTLY_FACTUAL = "mostly_factual"
    MIXED = "mixed"
    LOW = "low"
    VERY_LOW = "very_low"


class PoliticalBias(str, Enum):
    """Political bias classification (metadata only, not used in scoring)."""

    LEFT = "left"
    LEFT_CENTER = "left_center"
    CENTER = "center"
    RIGHT_CENTER = "right_center"
    RIGHT = "right"


# -----------------------------------------------------------------------------
# Source types that are NOT eligible for synthesis (ADR-0028)
# -----------------------------------------------------------------------------

INELIGIBLE_SOURCE_TYPES = frozenset(
    {
        SourceType.SATIRE,
        SourceType.CONSPIRACY,
        SourceType.FAKE_NEWS,
    }
)


# -----------------------------------------------------------------------------
# Credibility Score Calculation (ADR-0028: factual reporting ONLY)
# -----------------------------------------------------------------------------

# Score mapping based on factual reporting level
FACTUAL_REPORTING_SCORES: dict[str, float] = {
    FactualReporting.VERY_HIGH.value: 1.0,
    FactualReporting.HIGH.value: 0.85,
    FactualReporting.MOSTLY_FACTUAL.value: 0.70,
    FactualReporting.MIXED.value: 0.50,
    FactualReporting.LOW.value: 0.30,
    FactualReporting.VERY_LOW.value: 0.15,
}


def calculate_credibility_score(factual_reporting: Optional[str]) -> Optional[float]:
    """
    Calculate credibility score from factual reporting rating.

    Per ADR-0028, credibility score is based ONLY on factual accuracy,
    NOT political bias. This ensures users across the political spectrum
    can trust the scoring system.

    Args:
        factual_reporting: Factual accuracy level (very_high, high, etc.)

    Returns:
        Score between 0.0-1.0, or None if factual_reporting is unknown
    """
    if not factual_reporting:
        return None

    normalized = factual_reporting.lower().replace(" ", "_").replace("-", "_")
    return FACTUAL_REPORTING_SCORES.get(normalized)


# -----------------------------------------------------------------------------
# Domain Canonicalization (ADR-0028)
# -----------------------------------------------------------------------------

# Known domain aliases - maps alternate domains to canonical MBFC domains
# Only include mappings where the target domain exists in MBFC
DOMAIN_ALIASES: dict[str, str] = {
    # BBC variants -> bbc.com (verified in MBFC)
    "bbci.co.uk": "bbc.com",
    "bbc.co.uk": "bbc.com",
    "feeds.bbci.co.uk": "bbc.com",
    "support.bbc.co.uk": "bbc.com",
    # Feed subdomains -> main domain
    "feeds.arstechnica.com": "arstechnica.com",
    "rss.nytimes.com": "nytimes.com",
    "feeds.washingtonpost.com": "washingtonpost.com",
    "feeds.reuters.com": "reuters.com",
    "rss.cnn.com": "cnn.com",
    "feeds.theguardian.com": "theguardian.com",
}


def canonicalize_domain(url_or_domain: str) -> Optional[str]:
    """
    Normalize a URL or domain to a canonical form for lookup.

    Rules (from ADR-0028):
    1. Extract domain from full URL if needed
    2. Strip common prefixes: www., m., mobile., amp.
    3. Lowercase everything
    4. Handle edge cases (trailing slashes, ports)

    Examples:
        >>> canonicalize_domain("https://www.nytimes.com/article/foo")
        'nytimes.com'
        >>> canonicalize_domain("m.bbc.co.uk")
        'bbc.co.uk'
        >>> canonicalize_domain("https://amp.theguardian.com/story")
        'theguardian.com'

    Args:
        url_or_domain: A full URL or bare domain

    Returns:
        Canonical domain string, or None if input is invalid
    """
    if not url_or_domain or not isinstance(url_or_domain, str):
        return None

    url_or_domain = url_or_domain.strip()
    if not url_or_domain:
        return None

    # If it looks like a URL, parse it
    if "://" in url_or_domain or url_or_domain.startswith("//"):
        try:
            parsed = urlparse(url_or_domain)
            domain = parsed.netloc or parsed.path.split("/")[0]
        except Exception:
            return None
    else:
        # Treat as bare domain, but strip any path
        domain = url_or_domain.split("/")[0]

    if not domain:
        return None

    # Lowercase
    domain = domain.lower()

    # Remove port if present
    domain = domain.split(":")[0]

    # Strip common prefixes
    prefixes_to_strip = ("www.", "m.", "mobile.", "amp.", "news.")
    for prefix in prefixes_to_strip:
        if domain.startswith(prefix):
            domain = domain[len(prefix) :]
            break  # Only strip one prefix

    # Validate result
    if not domain or "." not in domain:
        return None

    # Apply domain aliases for known alternate domains
    domain = DOMAIN_ALIASES.get(domain, domain)

    return domain


def extract_domain_from_url(url: str) -> Optional[str]:
    """
    Extract and canonicalize domain from article URL.

    This is the primary entry point for looking up credibility
    when processing articles.

    Args:
        url: Full article URL

    Returns:
        Canonical domain for credibility lookup, or None if invalid
    """
    return canonicalize_domain(url)


# -----------------------------------------------------------------------------
# Synthesis Eligibility (ADR-0028)
# -----------------------------------------------------------------------------


def is_eligible_for_synthesis(source_type: str) -> bool:
    """
    Determine if a source type is eligible for story synthesis.

    Per ADR-0028, certain source types are automatically excluded:
    - satire: Not real news
    - conspiracy: Unreliable speculation
    - fake_news: Known misinformation

    Args:
        source_type: The source_type value (news, satire, etc.)

    Returns:
        True if eligible for synthesis, False otherwise
    """
    if not source_type:
        return True  # Default to eligible if unknown

    try:
        type_enum = SourceType(source_type.lower())
        return type_enum not in INELIGIBLE_SOURCE_TYPES
    except ValueError:
        # Unknown type, default to eligible
        return True


# -----------------------------------------------------------------------------
# MBFC Data Mapping (from research doc)
# -----------------------------------------------------------------------------


@dataclass
class MBFCMapping:
    """Mapped data from MBFC source record."""

    domain: str
    name: str
    source_type: str
    factual_reporting: Optional[str]
    bias: Optional[str]
    credibility_score: Optional[float]
    is_eligible_for_synthesis: bool
    provider_url: Optional[str]
    homepage_url: Optional[str]


# MBFC source type mapping
MBFC_SOURCE_TYPE_MAP: dict[str, str] = {
    # Standard news categories
    "left": SourceType.NEWS.value,
    "left-center": SourceType.NEWS.value,
    "center": SourceType.NEWS.value,
    "right-center": SourceType.NEWS.value,
    "right": SourceType.NEWS.value,
    "pro-science": SourceType.PRO_SCIENCE.value,
    # Special categories
    "satire": SourceType.SATIRE.value,
    "conspiracy-pseudoscience": SourceType.CONSPIRACY.value,
    "conspiracy": SourceType.CONSPIRACY.value,
    "pseudoscience": SourceType.CONSPIRACY.value,
    "questionable": SourceType.FAKE_NEWS.value,  # MBFC's "questionable" = fake news
    "fake-news": SourceType.FAKE_NEWS.value,
}

# MBFC bias mapping (normalize to our enum values)
MBFC_BIAS_MAP: dict[str, str] = {
    "left": PoliticalBias.LEFT.value,
    "left-center": PoliticalBias.LEFT_CENTER.value,
    "center": PoliticalBias.CENTER.value,
    "least biased": PoliticalBias.CENTER.value,
    "right-center": PoliticalBias.RIGHT_CENTER.value,
    "right": PoliticalBias.RIGHT.value,
}

# MBFC factual reporting mapping
MBFC_FACTUAL_MAP: dict[str, str] = {
    "very high": FactualReporting.VERY_HIGH.value,
    "high": FactualReporting.HIGH.value,
    "mostly factual": FactualReporting.MOSTLY_FACTUAL.value,
    "mixed": FactualReporting.MIXED.value,
    "low": FactualReporting.LOW.value,
    "very low": FactualReporting.VERY_LOW.value,
}


def map_mbfc_record(record: dict[str, Any]) -> Optional[MBFCMapping]:
    """
    Map an MBFC source record to our schema.

    Handles the MBFC community dataset JSON format.
    See docs/research/SOURCE-CREDIBILITY-RESEARCH.md for field details.

    Args:
        record: Raw MBFC JSON record

    Returns:
        MBFCMapping dataclass, or None if record is invalid
    """
    # Required: must have a URL or domain
    url = record.get("url") or record.get("domain")
    if not url:
        return None

    domain = canonicalize_domain(url)
    if not domain:
        logger.warning(f"Could not canonicalize MBFC domain: {url}")
        return None

    # Extract name
    name = record.get("name") or record.get("source") or domain

    # Map source type from MBFC 'bias' or 'category' field
    mbfc_category = (
        record.get("category", "").lower()
        or record.get("bias", "").lower()
        or record.get("type", "").lower()
    )
    source_type = MBFC_SOURCE_TYPE_MAP.get(mbfc_category, SourceType.NEWS.value)

    # Map factual reporting
    mbfc_factual = (
        record.get("factual", "").lower() or record.get("factual_reporting", "").lower()
    )
    factual_reporting = MBFC_FACTUAL_MAP.get(mbfc_factual)

    # Map political bias (metadata only)
    mbfc_bias = record.get("bias", "").lower()
    bias = MBFC_BIAS_MAP.get(mbfc_bias)

    # Calculate credibility score (factual reporting only per ADR-0028)
    credibility_score = calculate_credibility_score(factual_reporting)

    # Determine synthesis eligibility
    eligible = is_eligible_for_synthesis(source_type)

    # Provider URL (MBFC review page)
    provider_url = record.get("mbfc_url") or record.get("review_url")

    # Homepage URL
    homepage_url = (
        record.get("url") if record.get("url", "").startswith("http") else None
    )

    return MBFCMapping(
        domain=domain,
        name=name,
        source_type=source_type,
        factual_reporting=factual_reporting,
        bias=bias,
        credibility_score=credibility_score,
        is_eligible_for_synthesis=eligible,
        provider_url=provider_url,
        homepage_url=homepage_url,
    )


# -----------------------------------------------------------------------------
# Batch Import Support
# -----------------------------------------------------------------------------


def validate_mbfc_dataset(records: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Validate MBFC dataset and return statistics.

    Args:
        records: List of raw MBFC records

    Returns:
        Dict with validation stats: total, valid, invalid, by_type, by_factual
    """
    by_type: dict[str, int] = {}
    by_factual: dict[str, int] = {}
    invalid_reasons: dict[str, int] = {}

    valid_count = 0
    invalid_count = 0

    for record in records:
        mapping = map_mbfc_record(record)
        if mapping:
            valid_count += 1
            by_type[mapping.source_type] = by_type.get(mapping.source_type, 0) + 1
            if mapping.factual_reporting:
                by_factual[mapping.factual_reporting] = (
                    by_factual.get(mapping.factual_reporting, 0) + 1
                )
        else:
            invalid_count += 1
            reason = "no_domain" if not record.get("url") else "canonicalization_failed"
            invalid_reasons[reason] = invalid_reasons.get(reason, 0) + 1

    return {
        "total": len(records),
        "valid": valid_count,
        "invalid": invalid_count,
        "by_type": by_type,
        "by_factual": by_factual,
        "invalid_reasons": invalid_reasons,
    }
