"""
Interest-based story ranking.

Provides personalized story ordering based on user topic preferences.
Interests are configured in data/interests.json.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cache for loaded interests config
_interests_config: Optional[Dict[str, Any]] = None
_interests_config_path = Path(__file__).parent.parent / "data" / "interests.json"


def _get_default_config() -> Dict[str, Any]:
    """Return default interests configuration."""
    return {
        "version": "1.0",
        "enabled": True,
        "blend": {
            "importance_weight": 0.6,
            "interest_weight": 0.4,
        },
        "topic_weights": {},
        "default_weight": 1.0,
    }


def load_interests_config(force_reload: bool = False) -> Dict[str, Any]:
    """
    Load interests configuration from JSON file.

    Args:
        force_reload: If True, bypass cache and reload from disk

    Returns:
        Interests configuration dictionary
    """
    global _interests_config

    if _interests_config is not None and not force_reload:
        return _interests_config

    if not _interests_config_path.exists():
        logger.warning(
            f"Interests config not found at {_interests_config_path}, using defaults"
        )
        _interests_config = _get_default_config()
        return _interests_config

    try:
        with open(_interests_config_path, "r") as f:
            _interests_config = json.load(f)
        logger.debug(f"Loaded interests config from {_interests_config_path}")
        return _interests_config
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in interests config: {e}")
        _interests_config = _get_default_config()
        return _interests_config
    except Exception as e:
        logger.error(f"Failed to load interests config: {e}")
        _interests_config = _get_default_config()
        return _interests_config


def is_interest_ranking_enabled() -> bool:
    """Check if interest-based ranking is enabled in config."""
    config = load_interests_config()
    return config.get("enabled", True)


def get_topic_weight(topic: str) -> float:
    """
    Get the interest weight for a specific topic.

    Args:
        topic: Topic ID (e.g., 'ai-ml', 'security')

    Returns:
        Weight value (default 1.0 if not configured)
    """
    config = load_interests_config()
    topic_weights = config.get("topic_weights", {})
    default_weight = config.get("default_weight", 1.0)
    return topic_weights.get(topic, default_weight)


def get_blend_weights() -> tuple[float, float]:
    """
    Get the importance and interest blend weights.

    Returns:
        Tuple of (importance_weight, interest_weight)
    """
    config = load_interests_config()
    blend = config.get("blend", {})
    importance_weight = blend.get("importance_weight", 0.6)
    interest_weight = blend.get("interest_weight", 0.4)
    return importance_weight, interest_weight


def _normalize_topic(topic: str) -> str:
    """
    Normalize a topic name to match config keys.
    
    Handles both display names ("AI/ML") and IDs ("ai-ml").
    """
    # Common mappings from display name to config ID
    mappings = {
        "ai/ml": "ai-ml",
        "ai": "ai-ml",
        "ml": "ai-ml",
        "artificial intelligence": "ai-ml",
        "machine learning": "ai-ml",
        "cloud": "cloud-k8s",
        "cloud computing": "cloud-k8s",
        "kubernetes": "cloud-k8s",
        "k8s": "cloud-k8s",
        "devtools": "devtools",
        "development": "devtools",
        "software development": "devtools",
        "programming": "devtools",
        "programming languages": "devtools",
        "security": "security",
        "cybersecurity": "security",
        "counter-terrorism": "security",
        "chips": "chips-hardware",
        "hardware": "chips-hardware",
        "chips/hardware": "chips-hardware",
        "semiconductors": "chips-hardware",
        "politics": "politics",
        "political": "politics",
        "international relations": "politics",
        "uk news": "politics",
        "military": "politics",
        "business": "business",
        "finance": "business",
        "economy": "business",
        "science": "science",
        "research": "science",
        "computer science": "science",
        "technology": "general",
        "entertainment": "general",
        "education": "general",
        "productivity": "general",
        "sports": "sports",
        "general": "general",
    }
    
    normalized = topic.lower().strip()
    return mappings.get(normalized, normalized)


def calculate_interest_score(story_topics: List[str]) -> float:
    """
    Calculate interest score for a story based on its topics.

    The interest score is the average of all topic weights for the story.
    Stories with multiple topics get the average of their weights.

    Args:
        story_topics: List of topic names (can be display names or IDs)

    Returns:
        Interest score (typically 0.0 to 2.0, with 1.0 being neutral)
    """
    config = load_interests_config()
    topic_weights = config.get("topic_weights", {})
    default_weight = config.get("default_weight", 1.0)

    if not story_topics:
        return default_weight

    # Normalize topics before looking up weights
    weights = []
    for topic in story_topics:
        normalized = _normalize_topic(topic)
        weight = topic_weights.get(normalized, default_weight)
        weights.append(weight)
    
    return sum(weights) / len(weights)


def calculate_blended_score(
    importance_score: float,
    interest_score: float,
    max_interest_weight: float = 2.0,
) -> float:
    """
    Calculate blended score combining importance and interest.

    The interest score is normalized to 0-1 range before blending.

    Args:
        importance_score: Story's importance score (0.0 to 1.0)
        interest_score: Story's interest score (typically 0.0 to 2.0)
        max_interest_weight: Maximum expected interest weight for normalization

    Returns:
        Blended score (0.0 to 1.0)
    """
    importance_weight, interest_weight = get_blend_weights()

    # Normalize interest score to 0-1 range
    normalized_interest = min(interest_score / max_interest_weight, 1.0)

    # Calculate blended score
    blended = (importance_score * importance_weight) + (
        normalized_interest * interest_weight
    )

    return blended


def get_story_blended_score(
    importance_score: float,
    story_topics: List[str],
) -> float:
    """
    Convenience function to get the blended score for a story.

    Combines interest calculation and blending in one call.

    Args:
        importance_score: Story's importance score
        story_topics: List of topic IDs for the story

    Returns:
        Blended score for ranking
    """
    interest_score = calculate_interest_score(story_topics)
    return calculate_blended_score(importance_score, interest_score)


def get_interests_summary() -> Dict[str, Any]:
    """
    Get a summary of the current interests configuration.

    Useful for debugging and API responses.

    Returns:
        Dictionary with enabled status, blend weights, and topic weights
    """
    config = load_interests_config()
    return {
        "enabled": config.get("enabled", True),
        "blend": config.get("blend", {}),
        "topic_weights": config.get("topic_weights", {}),
        "default_weight": config.get("default_weight", 1.0),
    }

