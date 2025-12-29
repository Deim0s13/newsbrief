"""Unified Topic Classification Service.

This module provides centralized topic classification for both articles and stories.
It ensures consistent topic vocabulary across the entire application.

Classification Strategy:
1. LLM-based classification (primary) - More accurate for diverse content
2. Keyword-based fallback - When LLM unavailable or times out

Topic Configuration:
Topics are loaded dynamically from data/topics.json. Edit that file to add/modify
topics without code changes. New topics can be auto-discovered by the LLM.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .llm import get_llm_service

logger = logging.getLogger(__name__)

# =============================================================================
# Dynamic Topic Configuration
# =============================================================================

# Path to topics configuration file
TOPICS_CONFIG_PATH = Path("data/topics.json")

# Cached config - reloaded when needed
_topics_cache: Optional[Dict] = None
_topics_file_mtime: float = 0


def _load_topics_config() -> Dict:
    """
    Load topic definitions from JSON config file.

    Returns:
        Dictionary containing topics and settings from config file
    """
    global _topics_cache, _topics_file_mtime

    if not TOPICS_CONFIG_PATH.exists():
        logger.warning(
            f"Topics config not found at {TOPICS_CONFIG_PATH}, using defaults"
        )
        return _get_default_config()

    try:
        current_mtime = TOPICS_CONFIG_PATH.stat().st_mtime

        # Reload if file has changed or cache is empty
        if _topics_cache is None or current_mtime > _topics_file_mtime:
            with open(TOPICS_CONFIG_PATH, encoding="utf-8") as f:
                loaded_config = json.load(f)
                _topics_cache = loaded_config
                _topics_file_mtime = current_mtime
                logger.debug(
                    f"Loaded {len(loaded_config.get('topics', {}))} topics from config"
                )

        # At this point _topics_cache is guaranteed to be set
        if _topics_cache is not None:
            return _topics_cache
        return _get_default_config()

    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load topics config: {e}")
        return _get_default_config()


def _get_default_config() -> Dict:
    """Return default config if file is missing or invalid."""
    return {
        "settings": {
            "auto_add_new_topics": True,
            "min_confidence_for_new_topic": 0.7,
            "fallback_topic": "general",
        },
        "topics": {
            "general": {
                "name": "General",
                "description": "General news and miscellaneous topics",
                "keywords": [],
            }
        },
    }


def get_topics_config() -> Dict:
    """Get the full topics configuration (topics + settings)."""
    return _load_topics_config()


def get_topic_definitions() -> Dict[str, Dict]:
    """Get current topic definitions (dynamic, from config file)."""
    return _load_topics_config().get("topics", {})


def get_topic_settings() -> Dict:
    """Get topic classification settings."""
    return _load_topics_config().get("settings", {})


def reload_topics() -> None:
    """Force reload of topics config from file."""
    global _topics_cache, _topics_file_mtime
    _topics_cache = None
    _topics_file_mtime = 0
    _load_topics_config()
    logger.info("Topics config reloaded")


# =============================================================================
# Helper Functions for Topic Access
# =============================================================================


def get_valid_topics() -> List[str]:
    """Get list of valid topic IDs (dynamic, from config)."""
    return list(get_topic_definitions().keys())


@dataclass
class TopicClassificationResult:
    """Result of topic classification."""

    topic: str  # Topic ID (e.g., "ai-ml", "politics")
    confidence: float  # 0.0 to 1.0
    method: str  # "llm", "keywords", or "fallback"
    display_name: str  # Human-readable name (e.g., "AI/ML", "Politics")
    matched_keywords: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "topic": self.topic,
            "confidence": self.confidence,
            "method": self.method,
            "display_name": self.display_name,
            "matched_keywords": self.matched_keywords,
        }


def get_topic_display_name(topic_id: str) -> str:
    """Get human-readable display name for a topic ID."""
    topics = get_topic_definitions()
    if topic_id in topics:
        return topics[topic_id]["name"]
    return topic_id.replace("-", "/").title()


def get_available_topics() -> List[Dict[str, str]]:
    """Get list of available topics with their display names."""
    return [
        {"id": topic_id, "name": config["name"], "description": config["description"]}
        for topic_id, config in get_topic_definitions().items()
    ]


# =============================================================================
# LLM-Based Classification (Two-Step: Classify → Normalize)
# =============================================================================


def _call_llm(prompt: str, model: Optional[str] = None) -> Optional[str]:
    """
    Helper to call LLM and return response text.

    Args:
        prompt: The prompt to send
        model: LLM model to use

    Returns:
        Response text or None if failed
    """
    import re

    try:
        llm_service = get_llm_service()
        if not llm_service.is_available():
            return None

        response = llm_service.client.generate(
            model=model or llm_service.model,
            prompt=prompt,
            options={"temperature": 0.1, "num_predict": 150},
        )

        response_text = response.get("response", "").strip()

        # Handle markdown code blocks
        if "```" in response_text:
            json_match = re.search(
                r"```(?:json)?\s*(.*?)\s*```", response_text, re.DOTALL
            )
            if json_match:
                response_text = json_match.group(1)

        return response_text

    except Exception as e:
        logger.warning(f"LLM call failed: {e}")
        return None


def _classify_free_form(
    title: str, summary: str, model: Optional[str] = None
) -> Optional[str]:
    """
    Step A: Free-form classification - ask LLM what the article is about.

    Args:
        title: Article title
        summary: Article summary/content
        model: LLM model to use

    Returns:
        Free-form topic description (e.g., "Gaza peace negotiations") or None
    """
    content = f"Title: {title}\n\nSummary: {summary}".strip()

    prompt = f"""What is this article primarily about? Describe the main topic in 2-5 words.

ARTICLE:
{content}

Respond with ONLY the topic description, nothing else.
Examples: "artificial intelligence research", "political election coverage", "semiconductor manufacturing", "sports championship"

Topic:"""

    response = _call_llm(prompt, model)
    if response:
        # Clean up response
        return response.strip().strip('"').strip("'")
    return None


def _normalize_to_existing_or_new(
    free_form_topic: str,
    title: str,
    model: Optional[str] = None,
) -> Tuple[Optional[str], Optional[Dict], float]:
    """
    Step B: Normalize free-form topic to existing topic or suggest new one.

    Args:
        free_form_topic: Free-form topic from Step A
        title: Article title (for context)
        model: LLM model to use

    Returns:
        Tuple of (existing_topic_id, new_topic_dict, confidence)
        - If existing topic matches: (topic_id, None, confidence)
        - If new topic suggested: (None, {"id": "...", "name": "...", "description": "..."}, confidence)
    """
    topics = get_topic_definitions()
    topic_list = "\n".join(
        f"- {tid}: {config['name']} - {config['description']}"
        for tid, config in topics.items()
        if tid != "general"  # Don't list general, use as fallback
    )

    prompt = f"""Given this article topic: "{free_form_topic}"
Article title: "{title}"

EXISTING TOPIC CATEGORIES:
{topic_list}

TASK: Which existing category best fits this topic?

MATCHING EXAMPLES:
- "Israel-Hamas ceasefire" → politics (international relations, conflicts)
- "OpenAI GPT-5 release" → ai-ml (artificial intelligence)
- "Stock market crash" → business (finance, markets)
- "Climate research findings" → science (research, environment)
- "New iPhone processor" → chips-hardware (processors, semiconductors)

RULES:
1. Match to the most relevant existing topic - be INCLUSIVE not restrictive
2. Politics covers: government, elections, international relations, wars, conflicts, diplomacy
3. For clear new domains (sports, entertainment, travel, food, etc.), SUGGEST A NEW TOPIC
4. Use "general" only for truly ambiguous or mixed content

IMPORTANT: Sports articles → suggest new "sports" topic. Entertainment → suggest new "entertainment" topic.

RESPOND WITH JSON ONLY:
For existing topic: {{"match": "existing", "topic_id": "the-id", "confidence": 0.0-1.0}}
For new topic: {{"match": "new", "topic_id": "sports", "name": "Sports", "description": "Sports news and athletic events", "confidence": 0.85}}
For general: {{"match": "general", "topic_id": "general", "confidence": 0.5}}

JSON:"""

    response = _call_llm(prompt, model)
    if not response:
        return None, None, 0.0

    try:
        data = json.loads(response)
        match_type = data.get("match", "general")
        topic_id = data.get("topic_id", "general").lower().strip().replace(" ", "-")
        confidence = float(data.get("confidence", 0.5))

        if match_type == "existing":
            # Validate it's actually an existing topic
            if topic_id in topics:
                return topic_id, None, confidence
            else:
                logger.warning(f"LLM suggested non-existent topic '{topic_id}'")
                return "general", None, 0.3

        elif match_type == "new":
            new_topic = {
                "id": topic_id,
                "name": data.get("name", topic_id.replace("-", " ").title()),
                "description": data.get("description", f"Articles about {topic_id}"),
            }
            return None, new_topic, confidence

        else:  # general
            return "general", None, confidence

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Failed to parse normalization response: {e}")
        return None, None, 0.0


def _add_topic_to_config(topic_id: str, name: str, description: str) -> bool:
    """
    Add a new topic to the config file.

    Args:
        topic_id: Topic ID (e.g., "sports")
        name: Display name (e.g., "Sports")
        description: Topic description

    Returns:
        True if successfully added, False otherwise
    """
    try:
        config = _load_topics_config()

        # Check if already exists
        if topic_id in config.get("topics", {}):
            logger.debug(f"Topic '{topic_id}' already exists")
            return True

        # Add new topic
        config["topics"][topic_id] = {
            "name": name,
            "description": description,
            "keywords": [],  # Will be populated over time
        }

        # Write back to file
        with open(TOPICS_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        # Clear cache to reload
        reload_topics()

        logger.info(f"Added new topic '{topic_id}' ({name}) to config")
        return True

    except Exception as e:
        logger.error(f"Failed to add topic to config: {e}")
        return False


def classify_topic_with_llm(
    title: str,
    summary: str = "",
    model: Optional[str] = None,
) -> Optional[TopicClassificationResult]:
    """
    Classify article topic using two-step LLM approach.

    Step 1: Free-form classification - what is this article about?
    Step 2: Normalize to existing topic or suggest new one

    Args:
        title: Article title
        summary: Article summary/content
        model: LLM model to use (defaults to configured model)

    Returns:
        TopicClassificationResult or None if classification fails
    """
    if not title:
        return None

    try:
        llm_service = get_llm_service()
        if not llm_service.is_available():
            logger.debug("LLM not available for topic classification")
            return None

        # Step A: Free-form classification
        free_form = _classify_free_form(title, summary or "", model)
        if not free_form:
            logger.debug("Free-form classification failed, using fallback")
            return None

        logger.debug(f"Free-form topic: '{free_form}'")

        # Step B: Normalize to existing or new topic
        existing_topic, new_topic, confidence = _normalize_to_existing_or_new(
            free_form, title, model
        )

        # Handle existing topic
        if existing_topic:
            return TopicClassificationResult(
                topic=existing_topic,
                confidence=confidence,
                method="llm",
                display_name=get_topic_display_name(existing_topic),
            )

        # Handle new topic suggestion
        if new_topic:
            settings = get_topic_settings()
            min_confidence = settings.get("min_confidence_for_new_topic", 0.7)
            auto_add = settings.get("auto_add_new_topics", True)

            if confidence >= min_confidence and auto_add:
                # Add the new topic
                if _add_topic_to_config(
                    new_topic["id"],
                    new_topic["name"],
                    new_topic["description"],
                ):
                    logger.info(f"Auto-added new topic: {new_topic['id']}")
                    return TopicClassificationResult(
                        topic=new_topic["id"],
                        confidence=confidence,
                        method="llm-new",
                        display_name=new_topic["name"],
                    )

            # New topic suggested but not added (low confidence or auto-add disabled)
            logger.debug(
                f"New topic '{new_topic['id']}' suggested but not added "
                f"(confidence={confidence:.2f}, min={min_confidence}, auto_add={auto_add})"
            )

        # Fallback to general
        return TopicClassificationResult(
            topic="general",
            confidence=0.3,
            method="llm",
            display_name=get_topic_display_name("general"),
        )

    except Exception as e:
        logger.warning(f"LLM topic classification failed: {e}")
        return None


# =============================================================================
# Keyword-Based Classification (Fallback)
# =============================================================================


def classify_topic_with_keywords(
    title: str,
    summary: str = "",
) -> TopicClassificationResult:
    """
    Classify article topic using keyword matching.

    This is the fallback method when LLM is unavailable.

    Args:
        title: Article title
        summary: Article summary/content

    Returns:
        TopicClassificationResult (always returns a result, defaults to "general")
    """
    if not title:
        return TopicClassificationResult(
            topic="general",
            confidence=0.0,
            method="fallback",
            display_name="General",
        )

    text = f"{title} {summary}".lower()

    # Score each topic based on keyword matches
    topic_scores: Dict[str, Tuple[float, List[str]]] = {}

    for topic_id, config in get_topic_definitions().items():
        keywords = config.get("keywords", [])
        if not keywords:
            continue

        matched = []
        for keyword in keywords:
            if keyword.lower() in text:
                matched.append(keyword)

        if matched:
            # Score based on matches, with title matches weighted higher
            title_lower = title.lower()
            title_matches = sum(1 for kw in matched if kw.lower() in title_lower)
            base_score = len(matched) / max(len(keywords), 1)
            title_boost = title_matches * 0.15
            score = min(base_score + title_boost, 1.0)
            topic_scores[topic_id] = (score, matched)

    if not topic_scores:
        return TopicClassificationResult(
            topic="general",
            confidence=0.0,
            method="keywords",
            display_name="General",
        )

    # Get best topic
    best_topic = max(topic_scores.keys(), key=lambda k: topic_scores[k][0])
    confidence, matched_keywords = topic_scores[best_topic]

    # Require minimum confidence threshold
    if confidence < 0.1:
        return TopicClassificationResult(
            topic="general",
            confidence=0.0,
            method="keywords",
            display_name="General",
        )

    return TopicClassificationResult(
        topic=best_topic,
        confidence=confidence,
        method="keywords",
        display_name=get_topic_display_name(best_topic),
        matched_keywords=matched_keywords,
    )


# =============================================================================
# Main Classification Function
# =============================================================================


def classify_topic(
    title: str,
    summary: str = "",
    use_llm: bool = True,
    model: Optional[str] = None,
) -> TopicClassificationResult:
    """
    Classify article topic using best available method.

    Strategy:
    1. Try LLM classification (more accurate)
    2. Fall back to keyword matching if LLM unavailable

    Args:
        title: Article title
        summary: Article summary/content
        use_llm: Whether to attempt LLM classification
        model: LLM model to use (defaults to configured model)

    Returns:
        TopicClassificationResult with topic ID and confidence
    """
    # Try LLM first
    if use_llm:
        llm_result = classify_topic_with_llm(title, summary, model)
        if llm_result and llm_result.confidence >= 0.5:
            logger.debug(
                f"LLM classified as '{llm_result.topic}' "
                f"(confidence: {llm_result.confidence:.2f})"
            )
            return llm_result

    # Fall back to keywords
    keyword_result = classify_topic_with_keywords(title, summary)
    logger.debug(
        f"Keywords classified as '{keyword_result.topic}' "
        f"(confidence: {keyword_result.confidence:.2f})"
    )
    return keyword_result


# =============================================================================
# Batch Classification & Migration
# =============================================================================


def reclassify_articles_batch(
    session,
    article_ids: Optional[List[int]] = None,
    use_llm: bool = False,  # Default to keywords for batch operations (faster)
) -> Dict[str, int]:
    """
    Reclassify articles with the unified topic system.

    Args:
        session: SQLAlchemy session
        article_ids: Specific article IDs to reclassify (None = all)
        use_llm: Whether to use LLM for classification

    Returns:
        Dictionary with stats: {"processed": N, "changed": N, "errors": N}
    """
    from sqlalchemy import text

    stats = {"processed": 0, "changed": 0, "errors": 0}

    # Build query
    if article_ids:
        placeholders = ", ".join([f":id_{i}" for i in range(len(article_ids))])
        params = {f"id_{i}": aid for i, aid in enumerate(article_ids)}
        query = (
            f"SELECT id, title, summary, topic FROM items WHERE id IN ({placeholders})"
        )
    else:
        params = {}
        query = "SELECT id, title, summary, topic FROM items"

    rows = session.execute(text(query), params).fetchall()

    for row in rows:
        article_id, title, summary, current_topic = row
        stats["processed"] += 1

        try:
            result = classify_topic(
                title=title or "",
                summary=summary or "",
                use_llm=use_llm,
            )

            if result.topic != current_topic:
                session.execute(
                    text(
                        "UPDATE items SET topic = :topic, topic_confidence = :confidence "
                        "WHERE id = :id"
                    ),
                    {
                        "topic": result.topic,
                        "confidence": result.confidence,
                        "id": article_id,
                    },
                )
                stats["changed"] += 1

        except Exception as e:
            logger.error(f"Error reclassifying article {article_id}: {e}")
            stats["errors"] += 1

    session.commit()
    logger.info(
        f"Reclassified {stats['processed']} articles: "
        f"{stats['changed']} changed, {stats['errors']} errors"
    )

    return stats


def migrate_article_topics_v062() -> Dict[str, Any]:
    """
    One-time migration to reclassify articles using the unified topic system.

    This migration fixes misclassified articles from the old keyword-only system
    (e.g., news about Gaza incorrectly tagged as 'chips-hardware').

    Uses keyword-based classification for speed. For better accuracy,
    use `reclassify_articles_batch` with `use_llm=True`.

    Returns:
        Dictionary with migration stats
    """
    from pathlib import Path

    from .db import session_scope

    # Check for migration marker file
    marker_file = Path("data/.topic_migration_v062_complete")
    if marker_file.exists():
        logger.debug("Topic migration v0.6.2 already completed, skipping")
        return {"skipped": 1, "reason": "already_completed"}

    logger.info("Starting topic migration v0.6.2...")

    try:
        with session_scope() as session:
            stats = reclassify_articles_batch(
                session=session,
                article_ids=None,  # All articles
                use_llm=False,  # Use keywords for speed
            )

        # Create marker file to prevent re-running
        marker_file.parent.mkdir(parents=True, exist_ok=True)
        marker_file.write_text(
            f"Topic migration v0.6.2 completed\n"
            f"Processed: {stats['processed']}\n"
            f"Changed: {stats['changed']}\n"
            f"Errors: {stats['errors']}\n"
        )

        logger.info(
            f"Topic migration v0.6.2 complete: "
            f"{stats['changed']} articles reclassified"
        )
        return stats

    except Exception as e:
        logger.error(f"Topic migration v0.6.2 failed: {e}")
        return {"error": 1, "message": str(e)}
