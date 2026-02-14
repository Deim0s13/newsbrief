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
from .llm_output import TopicOutput, parse_and_validate

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
class SecondaryTopic:
    """A secondary topic with its confidence score."""

    topic: str
    confidence: float
    display_name: str
    reasoning: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "topic": self.topic,
            "confidence": self.confidence,
            "display_name": self.display_name,
            "reasoning": self.reasoning,
        }


@dataclass
class TopicClassificationResult:
    """
    Result of topic classification.

    Enhanced in v0.8.1 (Issue #104) with:
    - Secondary topics support
    - Classification reasoning
    - Edge case flags
    """

    topic: str  # Topic ID (e.g., "ai-ml", "politics")
    confidence: float  # 0.0 to 1.0
    method: str  # "llm", "llm-enhanced", "keywords", or "fallback"
    display_name: str  # Human-readable name (e.g., "AI/ML", "Politics")
    matched_keywords: List[str] = field(default_factory=list)
    # v0.8.1 additions
    secondary_topics: List[SecondaryTopic] = field(default_factory=list)
    reasoning: Optional[str] = None
    edge_case: Optional[str] = (
        None  # "overlapping", "ambiguous", "emerging", "multi-domain"
    )

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "topic": self.topic,
            "confidence": self.confidence,
            "method": self.method,
            "display_name": self.display_name,
            "matched_keywords": self.matched_keywords,
        }
        # Add v0.8.1 fields if present
        if self.secondary_topics:
            result["secondary_topics"] = [st.to_dict() for st in self.secondary_topics]
        if self.reasoning:
            result["reasoning"] = self.reasoning
        if self.edge_case:
            result["edge_case"] = self.edge_case
        return result

    def all_topics(self) -> List[str]:
        """Get all topic IDs (primary + secondary)."""
        topics = [self.topic]
        topics.extend(st.topic for st in self.secondary_topics)
        return topics


def get_topic_display_name(topic_id: str) -> str:
    """Get human-readable display name for a topic ID."""
    topics = get_topic_definitions()
    if topic_id in topics:
        return topics[topic_id]["name"]
    return topic_id.replace("-", "/").title()


def get_available_topics() -> List[Dict[str, str]]:
    """Get list of available topics with their display names."""
    return [
        {
            "key": topic_id,
            "name": config["name"],
            "description": config.get("description", ""),
        }
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

    # Parse and validate with robust parser
    parsed_output, parse_metrics = parse_and_validate(
        response,
        TopicOutput,
        required_fields=["match", "topic_id"],
        allow_partial=True,
        circuit_breaker_name="topic_classification",
    )

    if parsed_output is None:
        logger.warning(
            f"Failed to parse normalization response: {parse_metrics.error_category}"
        )
        return None, None, 0.0

    match_type = parsed_output.match
    topic_id = parsed_output.topic_id
    confidence = parsed_output.confidence

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
            "name": parsed_output.name or topic_id.replace("-", " ").title(),
            "description": parsed_output.description or f"Articles about {topic_id}",
        }
        return None, new_topic, confidence

    else:  # general
        return "general", None, confidence


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
# Enhanced LLM Classification (v0.8.1 - Issue #104)
# =============================================================================


def _create_enhanced_classification_prompt(
    title: str,
    summary: str,
    topics: Dict[str, Dict],
) -> str:
    """
    Create enhanced classification prompt with few-shot examples and
    multi-topic support.

    Args:
        title: Article title
        summary: Article summary
        topics: Topic definitions

    Returns:
        Prompt string
    """
    content = f"Title: {title}\n\nSummary: {summary[:500]}".strip()

    # Build topic list with descriptions
    topic_list = "\n".join(
        f"  - {tid}: {config['name']} - {config['description']}"
        for tid, config in topics.items()
        if tid != "general"
    )

    return f"""You are an expert news classifier. Classify the following article into topic categories.

ARTICLE:
{content}

AVAILABLE TOPICS:
{topic_list}
  - general: General - Miscellaneous content that doesn't fit other categories

=== CLASSIFICATION GUIDELINES ===

CONFIDENCE CALIBRATION:
- 0.90-1.00: Perfectly clear match, article is entirely about this topic
- 0.75-0.89: Strong match, topic is central to the article
- 0.60-0.74: Good match, topic is clearly relevant
- 0.45-0.59: Moderate match, topic is somewhat relevant
- Below 0.45: Weak match, consider different topic

MULTI-TOPIC ARTICLES:
Some articles span multiple domains. For example:
- "OpenAI raises $10B funding" → Primary: ai-ml, Secondary: business
- "AWS announces new security features" → Primary: cloud-k8s, Secondary: security
- "NVIDIA releases new AI chip" → Primary: chips-hardware, Secondary: ai-ml

Only include secondary topics if confidence > 0.5

EDGE CASES:
- "overlapping": Article clearly belongs to 2+ topics equally
- "ambiguous": Hard to categorize, could fit multiple topics poorly
- "emerging": Topic seems new/emerging, not well covered by existing categories
- "multi-domain": Spans multiple unrelated domains

=== FEW-SHOT EXAMPLES ===

Example 1 - Clear single topic:
Article: "Google DeepMind announces Gemini 2.0 with improved reasoning"
Output:
{{
  "primary_topic": {{"topic_id": "ai-ml", "confidence": 0.95, "is_primary": true, "reasoning": "Article is entirely about AI model announcement"}},
  "secondary_topics": [],
  "edge_case": null,
  "classification_notes": "Clear AI/ML article about new model release"
}}

Example 2 - Multi-topic:
Article: "Microsoft invests $10B in OpenAI, stock surges 5%"
Output:
{{
  "primary_topic": {{"topic_id": "business", "confidence": 0.85, "is_primary": true, "reasoning": "Focus is on investment and stock movement"}},
  "secondary_topics": [{{"topic_id": "ai-ml", "confidence": 0.70, "is_primary": false, "reasoning": "OpenAI is an AI company"}}],
  "edge_case": "overlapping",
  "classification_notes": "Business news with AI context"
}}

Example 3 - Edge case:
Article: "SpaceX Starlink helps restore internet in Gaza conflict zone"
Output:
{{
  "primary_topic": {{"topic_id": "politics", "confidence": 0.75, "is_primary": true, "reasoning": "Gaza conflict is political/international relations"}},
  "secondary_topics": [{{"topic_id": "science", "confidence": 0.55, "is_primary": false, "reasoning": "Space technology application"}}],
  "edge_case": "multi-domain",
  "classification_notes": "Political context with technology angle"
}}

=== YOUR TASK ===

Classify the article above. Output valid JSON only:
{{
  "primary_topic": {{"topic_id": "...", "confidence": 0.0-1.0, "is_primary": true, "reasoning": "..."}},
  "secondary_topics": [{{"topic_id": "...", "confidence": 0.0-1.0, "is_primary": false, "reasoning": "..."}}],
  "edge_case": null | "overlapping" | "ambiguous" | "emerging" | "multi-domain",
  "classification_notes": "Brief note on classification decision"
}}

JSON:"""


def classify_topic_enhanced(
    title: str,
    summary: str = "",
    model: Optional[str] = None,
) -> Optional[TopicClassificationResult]:
    """
    Enhanced topic classification with multi-topic support and reasoning.

    Added in v0.8.1 (Issue #104) for improved classification accuracy.

    Features:
    - Single-pass classification (more efficient)
    - Multi-topic support (primary + secondary)
    - Confidence calibration guidance
    - Edge case detection
    - Classification reasoning

    Args:
        title: Article title
        summary: Article summary/content
        model: LLM model to use

    Returns:
        TopicClassificationResult with enhanced metadata, or None if failed
    """
    from .llm_output import EnhancedTopicOutput, parse_and_validate

    if not title:
        return None

    try:
        llm_service = get_llm_service()
        if not llm_service.is_available():
            logger.debug("LLM not available for enhanced topic classification")
            return None

        topics = get_topic_definitions()
        prompt = _create_enhanced_classification_prompt(title, summary or "", topics)

        # Call LLM with slightly higher token limit for detailed response
        response = llm_service.client.generate(
            model=model or llm_service.model,
            prompt=prompt,
            options={"temperature": 0.1, "num_predict": 350},
        )

        raw_response = response.get("response", "").strip()
        if not raw_response:
            logger.warning("Empty response from enhanced topic classification")
            return None

        # Parse with robust parser
        parsed_output, parse_metrics = parse_and_validate(
            raw_response,
            EnhancedTopicOutput,
            required_fields=["primary_topic"],
            allow_partial=True,
            circuit_breaker_name="topic_classification_enhanced",
        )

        if parsed_output is None:
            logger.warning(
                f"Failed to parse enhanced topic response: {parse_metrics.error_category}"
            )
            return None

        # Extract primary topic
        primary = parsed_output.primary_topic
        primary_topic_id = primary.topic_id

        # Validate primary topic exists (or use general)
        if primary_topic_id not in topics and primary_topic_id != "general":
            logger.warning(f"Unknown topic '{primary_topic_id}', using general")
            primary_topic_id = "general"

        # Build secondary topics
        secondary_topics: List[SecondaryTopic] = []
        for st in parsed_output.secondary_topics:
            if st.topic_id in topics and st.confidence >= 0.5:
                secondary_topics.append(
                    SecondaryTopic(
                        topic=st.topic_id,
                        confidence=st.confidence,
                        display_name=get_topic_display_name(st.topic_id),
                        reasoning=st.reasoning,
                    )
                )

        result = TopicClassificationResult(
            topic=primary_topic_id,
            confidence=primary.confidence,
            method="llm-enhanced",
            display_name=get_topic_display_name(primary_topic_id),
            secondary_topics=secondary_topics,
            reasoning=primary.reasoning,
            edge_case=parsed_output.edge_case,
        )

        logger.info(
            f"Enhanced classification: {primary_topic_id} ({primary.confidence:.2f})"
            + (f" + {len(secondary_topics)} secondary" if secondary_topics else "")
            + (f" [edge: {parsed_output.edge_case}]" if parsed_output.edge_case else "")
        )

        return result

    except Exception as e:
        logger.warning(f"Enhanced topic classification failed: {e}")
        return None


# =============================================================================
# Keyword-Based Classification (Fallback)
# =============================================================================


def classify_topic_with_keywords(
    title: str,
    summary: str = "",
    include_secondary: bool = True,
) -> TopicClassificationResult:
    """
    Classify article topic using keyword matching.

    This is the fallback method when LLM is unavailable.

    Enhanced in v0.8.1 (Issue #104) with:
    - Phrase matching (multi-word keywords matched as phrases)
    - Title weighting (keywords in title count more)
    - Secondary topic detection
    - Core keyword boosting (first 5 keywords per topic are "core")

    Args:
        title: Article title
        summary: Article summary/content
        include_secondary: Whether to detect secondary topics (v0.8.1)

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
    title_lower = title.lower()

    # Score each topic based on keyword matches
    topic_scores: Dict[str, Tuple[float, List[str]]] = {}

    for topic_id, config in get_topic_definitions().items():
        keywords = config.get("keywords", [])
        if not keywords:
            continue

        matched = []
        core_matches = 0  # First 5 keywords are "core" terms

        for idx, keyword in enumerate(keywords):
            kw_lower = keyword.lower()

            # Phrase matching: check if multi-word keyword appears as phrase
            if " " in kw_lower:
                # Multi-word keyword - must appear as complete phrase
                if kw_lower in text:
                    matched.append(keyword)
                    if idx < 5:  # Core keyword
                        core_matches += 1
            else:
                # Single word - use word boundary matching for better accuracy
                # Simple check: word must be surrounded by non-alphanumeric or at boundaries
                import re

                pattern = rf"\b{re.escape(kw_lower)}\b"
                if re.search(pattern, text):
                    matched.append(keyword)
                    if idx < 5:
                        core_matches += 1

        if matched:
            # Enhanced scoring (v0.8.1)
            # Base score from match ratio
            base_score = len(matched) / max(len(keywords), 1)

            # Title boost: keywords in title are more significant
            title_matches = sum(1 for kw in matched if kw.lower() in title_lower)
            title_boost = title_matches * 0.12

            # Core keyword boost: matching core keywords is more significant
            core_boost = core_matches * 0.08

            # Calculate final score (capped at 0.95 for keywords)
            score = min(base_score + title_boost + core_boost, 0.95)
            topic_scores[topic_id] = (score, matched)

    if not topic_scores:
        return TopicClassificationResult(
            topic="general",
            confidence=0.0,
            method="keywords",
            display_name="General",
        )

    # Sort topics by score
    sorted_topics = sorted(topic_scores.items(), key=lambda x: x[1][0], reverse=True)

    # Get best topic
    best_topic, (confidence, matched_keywords) = sorted_topics[0]

    # Require minimum confidence threshold
    if confidence < 0.1:
        return TopicClassificationResult(
            topic="general",
            confidence=0.0,
            method="keywords",
            display_name="General",
        )

    # Build secondary topics (v0.8.1)
    secondary_topics: List[SecondaryTopic] = []
    if include_secondary and len(sorted_topics) > 1:
        # Get topic relationships for validation
        config = get_topics_config()
        relationships = config.get("topic_relationships", {}).get("overlaps", {})
        related_to_primary = relationships.get(best_topic, [])

        for topic_id, (score, _) in sorted_topics[1:3]:  # Max 2 secondary
            # Only include if score is decent and topic is related
            if score >= 0.3 and (topic_id in related_to_primary or score >= 0.5):
                secondary_topics.append(
                    SecondaryTopic(
                        topic=topic_id,
                        confidence=score,
                        display_name=get_topic_display_name(topic_id),
                        reasoning=f"Matched {len(topic_scores.get(topic_id, (0, []))[1])} keywords",
                    )
                )

    return TopicClassificationResult(
        topic=best_topic,
        confidence=confidence,
        method="keywords",
        display_name=get_topic_display_name(best_topic),
        matched_keywords=matched_keywords,
        secondary_topics=secondary_topics,
    )


# =============================================================================
# Main Classification Function
# =============================================================================


def classify_topic(
    title: str,
    summary: str = "",
    use_llm: bool = True,
    use_enhanced: bool = True,
    model: Optional[str] = None,
) -> TopicClassificationResult:
    """
    Classify article topic using best available method.

    Strategy (v0.8.1 - Issue #104):
    1. Try enhanced LLM classification (multi-topic, reasoning)
    2. Fall back to legacy LLM classification
    3. Fall back to keyword matching if LLM unavailable

    Args:
        title: Article title
        summary: Article summary/content
        use_llm: Whether to attempt LLM classification
        use_enhanced: Use enhanced classification (v0.8.1, default True)
        model: LLM model to use (defaults to configured model)

    Returns:
        TopicClassificationResult with topic ID, confidence, and optional
        secondary topics (v0.8.1)
    """
    # Try enhanced LLM first (v0.8.1)
    if use_llm and use_enhanced:
        enhanced_result = classify_topic_enhanced(title, summary, model)
        if enhanced_result and enhanced_result.confidence >= 0.5:
            logger.debug(
                f"Enhanced LLM classified as '{enhanced_result.topic}' "
                f"(confidence: {enhanced_result.confidence:.2f})"
                + (
                    f", secondary: {[st.topic for st in enhanced_result.secondary_topics]}"
                    if enhanced_result.secondary_topics
                    else ""
                )
            )
            return enhanced_result

    # Fall back to legacy LLM
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


# =============================================================================
# Async Reclassification Job System (v0.8.1 - Issue #248)
# =============================================================================

# In-memory store for active job cancellation flags
_active_jobs: Dict[int, bool] = {}


def create_reclassify_job(
    batch_size: int = 100,
    use_llm: bool = True,
) -> int:
    """
    Create a new reclassification job record.

    Args:
        batch_size: Number of articles to process
        use_llm: Whether to use LLM for classification

    Returns:
        The job ID
    """
    from datetime import UTC, datetime

    from sqlalchemy import text

    from .db import session_scope

    with session_scope() as session:
        result = session.execute(
            text(
                """
                INSERT INTO reclassify_jobs
                (status, total_articles, processed_articles, changed_articles,
                 error_count, batch_size, use_llm, created_at)
                VALUES ('pending', 0, 0, 0, 0, :batch_size, :use_llm, NOW())
                RETURNING id
                """
            ),
            {"batch_size": batch_size, "use_llm": use_llm},
        )
        job_id = result.scalar()
        logger.info(
            f"Created reclassify job {job_id}: batch_size={batch_size}, use_llm={use_llm}"
        )
        return job_id


def get_reclassify_job(job_id: int) -> Optional[Dict[str, Any]]:
    """
    Get the status of a reclassification job.

    Args:
        job_id: The job ID

    Returns:
        Job details dict or None if not found
    """
    from sqlalchemy import text

    from .db import session_scope

    with session_scope() as session:
        result = session.execute(
            text(
                """
                SELECT id, status, total_articles, processed_articles, changed_articles,
                       error_count, batch_size, use_llm, created_at, started_at,
                       completed_at, error_message
                FROM reclassify_jobs
                WHERE id = :job_id
                """
            ),
            {"job_id": job_id},
        ).fetchone()

        if not result:
            return None

        # Calculate progress percentage
        total = result[2] or 0
        processed = result[3] or 0
        progress_percent = (processed / total * 100) if total > 0 else 0

        # Calculate elapsed time
        started_at = result[9]
        completed_at = result[10]
        elapsed_seconds = None
        if started_at:
            from datetime import UTC, datetime

            end_time = completed_at or datetime.now(UTC)
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=UTC)
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=UTC)
            elapsed_seconds = (end_time - started_at).total_seconds()

        return {
            "job_id": result[0],
            "status": result[1],
            "total_articles": total,
            "processed_articles": processed,
            "changed_articles": result[4],
            "error_count": result[5],
            "batch_size": result[6],
            "use_llm": result[7],
            "created_at": result[8].isoformat() if result[8] else None,
            "started_at": started_at.isoformat() if started_at else None,
            "completed_at": completed_at.isoformat() if completed_at else None,
            "error_message": result[11],
            "progress_percent": round(progress_percent, 1),
            "elapsed_seconds": round(elapsed_seconds, 1) if elapsed_seconds else None,
        }


def update_reclassify_job(
    job_id: int,
    status: Optional[str] = None,
    total_articles: Optional[int] = None,
    processed_articles: Optional[int] = None,
    changed_articles: Optional[int] = None,
    error_count: Optional[int] = None,
    error_message: Optional[str] = None,
    started: bool = False,
    completed: bool = False,
) -> None:
    """
    Update a reclassification job's progress.

    Args:
        job_id: The job ID
        status: New status (pending, running, completed, cancelled, failed)
        total_articles: Total articles to process
        processed_articles: Articles processed so far
        changed_articles: Articles with topic changed
        error_count: Number of errors
        error_message: Error message if failed
        started: Whether to set started_at timestamp
        completed: Whether to set completed_at timestamp
    """
    from typing import Any as AnyType

    from sqlalchemy import text

    from .db import session_scope

    updates: List[str] = []
    params: Dict[str, AnyType] = {"job_id": job_id}

    if status is not None:
        updates.append("status = :status")
        params["status"] = status
    if total_articles is not None:
        updates.append("total_articles = :total_articles")
        params["total_articles"] = total_articles
    if processed_articles is not None:
        updates.append("processed_articles = :processed_articles")
        params["processed_articles"] = processed_articles
    if changed_articles is not None:
        updates.append("changed_articles = :changed_articles")
        params["changed_articles"] = changed_articles
    if error_count is not None:
        updates.append("error_count = :error_count")
        params["error_count"] = error_count
    if error_message is not None:
        updates.append("error_message = :error_message")
        params["error_message"] = error_message
    if started:
        updates.append("started_at = NOW()")
    if completed:
        updates.append("completed_at = NOW()")

    if not updates:
        return

    with session_scope() as session:
        session.execute(
            text(f"UPDATE reclassify_jobs SET {', '.join(updates)} WHERE id = :job_id"),
            params,
        )


def cancel_reclassify_job(job_id: int) -> bool:
    """
    Cancel a running reclassification job.

    Args:
        job_id: The job ID

    Returns:
        True if cancellation was initiated, False if job not found or not running
    """
    job = get_reclassify_job(job_id)
    if not job:
        return False

    if job["status"] not in ("pending", "running"):
        return False

    # Set cancellation flag
    _active_jobs[job_id] = False

    # Update status
    update_reclassify_job(job_id, status="cancelled", completed=True)
    logger.info(f"Cancelled reclassify job {job_id}")
    return True


def is_job_cancelled(job_id: int) -> bool:
    """Check if a job has been cancelled."""
    return _active_jobs.get(job_id) is False


def get_reclassification_stats() -> Dict[str, Any]:
    """
    Get statistics about articles needing reclassification.

    Returns:
        Dict with counts for general/unclassified and low-confidence articles
    """
    from sqlalchemy import text

    from .db import session_scope

    with session_scope() as session:
        # Count articles with 'general' topic (unclassified)
        general_count = session.execute(
            text("SELECT COUNT(*) FROM items WHERE topic = 'general' OR topic IS NULL")
        ).scalar()

        # Count articles with low confidence (< 0.5)
        low_confidence_count = session.execute(
            text(
                """
                SELECT COUNT(*) FROM items
                WHERE topic_confidence IS NOT NULL
                AND topic_confidence < 0.5
                AND topic != 'general'
                """
            )
        ).scalar()

        # Total articles
        total_count = session.execute(text("SELECT COUNT(*) FROM items")).scalar()

        # Get last completed job info
        last_job = session.execute(
            text(
                """
                SELECT completed_at, changed_articles, processed_articles
                FROM reclassify_jobs
                WHERE status = 'completed'
                ORDER BY completed_at DESC
                LIMIT 1
                """
            )
        ).fetchone()

        last_run = None
        if last_job and last_job[0]:
            last_run = {
                "completed_at": last_job[0].isoformat(),
                "changed_articles": last_job[1],
                "processed_articles": last_job[2],
            }

        # Check if there's an active job
        active_job = session.execute(
            text(
                """
                SELECT id FROM reclassify_jobs
                WHERE status IN ('pending', 'running')
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
        ).scalar()

        return {
            "general_count": general_count or 0,
            "low_confidence_count": low_confidence_count or 0,
            "total_articles": total_count or 0,
            "needs_reclassification": (general_count or 0)
            + (low_confidence_count or 0),
            "last_run": last_run,
            "active_job_id": active_job,
        }


def run_reclassify_job_async(job_id: int) -> None:
    """
    Background worker for async reclassification.

    This function is designed to be run as a background task.
    It processes articles in batches and updates progress periodically.

    Args:
        job_id: The job ID to process
    """
    from sqlalchemy import text

    from .db import session_scope

    logger.info(f"Starting reclassify job {job_id}")

    # Mark job as active
    _active_jobs[job_id] = True

    try:
        # Get job configuration
        job = get_reclassify_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        batch_size = job["batch_size"]
        use_llm = job["use_llm"]

        # Get articles needing reclassification
        with session_scope() as session:
            articles = session.execute(
                text(
                    """
                    SELECT id, title, summary, topic
                    FROM items
                    WHERE topic = 'general'
                       OR topic IS NULL
                       OR (topic_confidence IS NOT NULL AND topic_confidence < 0.5)
                    ORDER BY id
                    LIMIT :batch_size
                    """
                ),
                {"batch_size": batch_size},
            ).fetchall()

            total_articles = len(articles)

        # Update job with total and mark as running
        update_reclassify_job(
            job_id,
            status="running",
            total_articles=total_articles,
            started=True,
        )

        if total_articles == 0:
            update_reclassify_job(
                job_id,
                status="completed",
                completed=True,
            )
            logger.info(f"Job {job_id} completed: no articles to process")
            return

        # Process articles
        processed = 0
        changed = 0
        errors = 0

        for row in articles:
            # Check for cancellation
            if is_job_cancelled(job_id):
                logger.info(
                    f"Job {job_id} cancelled after processing {processed} articles"
                )
                break

            article_id, title, summary, current_topic = row
            processed += 1

            try:
                result = classify_topic(
                    title=title or "",
                    summary=summary or "",
                    use_llm=use_llm,
                )

                if result.topic != current_topic:
                    with session_scope() as session:
                        session.execute(
                            text(
                                """
                                UPDATE items
                                SET topic = :topic, topic_confidence = :confidence
                                WHERE id = :id
                                """
                            ),
                            {
                                "topic": result.topic,
                                "confidence": result.confidence,
                                "id": article_id,
                            },
                        )
                    changed += 1

            except Exception as e:
                logger.error(f"Error reclassifying article {article_id}: {e}")
                errors += 1

            # Update progress every 10 articles
            if processed % 10 == 0:
                update_reclassify_job(
                    job_id,
                    processed_articles=processed,
                    changed_articles=changed,
                    error_count=errors,
                )

        # Final update
        final_status = "cancelled" if is_job_cancelled(job_id) else "completed"
        update_reclassify_job(
            job_id,
            status=final_status,
            processed_articles=processed,
            changed_articles=changed,
            error_count=errors,
            completed=True,
        )

        logger.info(
            f"Job {job_id} {final_status}: processed={processed}, changed={changed}, errors={errors}"
        )

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        update_reclassify_job(
            job_id,
            status="failed",
            error_message=str(e),
            completed=True,
        )

    finally:
        # Clean up active job flag
        _active_jobs.pop(job_id, None)
