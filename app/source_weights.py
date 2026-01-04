"""
Source quality weighting for story ranking.

Provides source reputation-based ranking based on feed/domain weights.
Weights are configured in data/source_weights.json.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Cache for loaded source weights config
_source_weights_config: Optional[Dict[str, Any]] = None
_source_weights_config_path = (
    Path(__file__).parent.parent / "data" / "source_weights.json"
)


def _get_default_config() -> Dict[str, Any]:
    """Return default source weights configuration."""
    return {
        "version": "1.0",
        "enabled": True,
        "blend_weight": 0.2,
        "feed_weights": {},
        "domain_weights": {},
        "default_weight": 1.0,
    }


def load_source_weights_config(force_reload: bool = False) -> Dict[str, Any]:
    """
    Load source weights configuration from JSON file.

    Args:
        force_reload: If True, bypass cache and reload from disk

    Returns:
        Source weights configuration dictionary
    """
    global _source_weights_config

    if _source_weights_config is not None and not force_reload:
        return _source_weights_config

    if not _source_weights_config_path.exists():
        logger.warning(
            f"Source weights config not found at {_source_weights_config_path}, using defaults"
        )
        _source_weights_config = _get_default_config()
        return _source_weights_config

    try:
        with open(_source_weights_config_path, "r") as f:
            _source_weights_config = json.load(f)
        logger.debug(f"Loaded source weights config from {_source_weights_config_path}")
        return _source_weights_config
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in source weights config: {e}")
        _source_weights_config = _get_default_config()
        return _source_weights_config
    except Exception as e:
        logger.error(f"Failed to load source weights config: {e}")
        _source_weights_config = _get_default_config()
        return _source_weights_config


def is_source_weighting_enabled() -> bool:
    """Check if source quality weighting is enabled in config."""
    config = load_source_weights_config()
    return config.get("enabled", True)


def get_blend_weight() -> float:
    """Get the blend weight for source quality (default: 0.2 = 20%)."""
    config = load_source_weights_config()
    return config.get("blend_weight", 0.2)


def _extract_domain(url: str) -> str:
    """
    Extract domain from a URL.

    Args:
        url: Full URL (e.g., 'https://news.ycombinator.com/rss')

    Returns:
        Domain without subdomain for common cases (e.g., 'ycombinator.com')
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Remove 'www.' prefix if present
        if domain.startswith("www."):
            domain = domain[4:]

        return domain
    except Exception:
        return ""


def get_feed_weight(feed_name: str) -> Optional[float]:
    """
    Get weight for a feed by name.

    Args:
        feed_name: Name of the feed (e.g., 'Hacker News')

    Returns:
        Weight if found, None otherwise
    """
    config = load_source_weights_config()
    feed_weights = config.get("feed_weights", {})

    # Try exact match first
    if feed_name in feed_weights:
        return feed_weights[feed_name]

    # Try case-insensitive match
    feed_name_lower = feed_name.lower()
    for name, weight in feed_weights.items():
        if name.lower() == feed_name_lower:
            return weight

    return None


def get_domain_weight(url: str) -> Optional[float]:
    """
    Get weight for a feed by its domain.

    Args:
        url: Feed URL

    Returns:
        Weight if domain found, None otherwise
    """
    config = load_source_weights_config()
    domain_weights = config.get("domain_weights", {})

    domain = _extract_domain(url)
    if not domain:
        return None

    # Try exact match
    if domain in domain_weights:
        return domain_weights[domain]

    # Try without subdomain (e.g., 'news.bbc.co.uk' -> 'bbc.co.uk')
    parts = domain.split(".")
    if len(parts) > 2:
        # Handle .co.uk, .com.au etc.
        if parts[-2] in ("co", "com", "org", "net"):
            shorter_domain = ".".join(parts[-3:])
        else:
            shorter_domain = ".".join(parts[-2:])

        if shorter_domain in domain_weights:
            return domain_weights[shorter_domain]

    return None


def get_source_weight(feed_name: str, feed_url: str) -> float:
    """
    Get the source weight for a feed, trying name first then domain.

    Args:
        feed_name: Name of the feed
        feed_url: URL of the feed

    Returns:
        Weight value (default 1.0 if not configured)
    """
    config = load_source_weights_config()
    default_weight = config.get("default_weight", 1.0)

    # Try feed name first
    weight = get_feed_weight(feed_name)
    if weight is not None:
        return weight

    # Try domain
    weight = get_domain_weight(feed_url)
    if weight is not None:
        return weight

    return default_weight


def calculate_story_source_weight(
    feed_names: List[str],
    feed_urls: List[str],
) -> float:
    """
    Calculate average source weight for a story based on its articles' feeds.

    Args:
        feed_names: List of feed names for articles in the story
        feed_urls: List of feed URLs for articles in the story

    Returns:
        Average source weight (typically 0.5 to 2.0, with 1.0 being neutral)
    """
    config = load_source_weights_config()
    default_weight = config.get("default_weight", 1.0)

    if not feed_names and not feed_urls:
        return default_weight

    # Pair up names and URLs
    weights = []
    for i in range(max(len(feed_names), len(feed_urls))):
        name = feed_names[i] if i < len(feed_names) else ""
        url = feed_urls[i] if i < len(feed_urls) else ""
        weight = get_source_weight(name, url)
        weights.append(weight)

    return sum(weights) / len(weights) if weights else default_weight


def get_source_weights_summary() -> Dict[str, Any]:
    """
    Get a summary of the current source weights configuration.

    Useful for debugging and API responses.

    Returns:
        Dictionary with enabled status, blend weight, and configured sources
    """
    config = load_source_weights_config()
    return {
        "enabled": config.get("enabled", True),
        "blend_weight": config.get("blend_weight", 0.2),
        "feed_weights_count": len(config.get("feed_weights", {})),
        "domain_weights_count": len(config.get("domain_weights", {})),
        "default_weight": config.get("default_weight", 1.0),
    }
