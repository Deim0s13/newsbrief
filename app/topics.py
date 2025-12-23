"""Unified Topic Classification Service.

This module provides centralized topic classification for both articles and stories.
It ensures consistent topic vocabulary across the entire application.

Classification Strategy:
1. LLM-based classification (primary) - More accurate for diverse content
2. Keyword-based fallback - When LLM unavailable or times out

Topic Vocabulary:
- Tech-focused: ai-ml, security, cloud-k8s, devtools, chips-hardware
- General: politics, business, science, entertainment, sports, general
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .llm import get_llm_service

logger = logging.getLogger(__name__)


# =============================================================================
# Unified Topic Vocabulary
# =============================================================================

TOPIC_DEFINITIONS: Dict[str, Dict] = {
    # Tech-focused topics
    "ai-ml": {
        "name": "AI/ML",
        "description": "Artificial intelligence, machine learning, neural networks, LLMs",
        "keywords": [
            "artificial intelligence", "machine learning", "deep learning",
            "neural network", "llm", "gpt", "chatgpt", "openai", "anthropic",
            "claude", "gemini", "ollama", "embeddings", "vector", "rag",
            "fine-tuning", "training", "inference", "pytorch", "tensorflow",
            "hugging face", "stable diffusion", "computer vision", "nlp",
            "generative ai", "copilot", "ai assistant", "transformer",
        ],
    },
    "security": {
        "name": "Security",
        "description": "Cybersecurity, vulnerabilities, privacy, encryption",
        "keywords": [
            "cybersecurity", "security", "vulnerability", "exploit", "breach",
            "hack", "malware", "ransomware", "phishing", "encryption", "tls",
            "ssl", "authentication", "authorization", "zero trust", "cve",
            "penetration test", "firewall", "intrusion", "ddos", "privacy",
            "gdpr", "data breach", "cyber attack",
        ],
    },
    "cloud-k8s": {
        "name": "Cloud/K8s",
        "description": "Cloud computing, Kubernetes, containers, DevOps",
        "keywords": [
            "kubernetes", "k8s", "docker", "container", "aws", "azure",
            "google cloud", "gcp", "serverless", "lambda", "terraform",
            "helm", "istio", "microservices", "devops", "ci/cd", "jenkins",
            "github actions", "infrastructure", "cloud computing",
        ],
    },
    "devtools": {
        "name": "DevTools",
        "description": "Programming languages, frameworks, development tools",
        "keywords": [
            "programming", "python", "javascript", "typescript", "rust", "go",
            "java", "swift", "kotlin", "github", "git", "vscode", "ide",
            "framework", "library", "api", "rest", "graphql", "react", "vue",
            "angular", "node", "fastapi", "django", "web development",
            "frontend", "backend", "software development",
        ],
    },
    "chips-hardware": {
        "name": "Chips/Hardware",
        "description": "Semiconductors, processors, computer hardware",
        "keywords": [
            "semiconductor", "chip", "processor", "cpu", "gpu", "nvidia",
            "amd", "intel", "qualcomm", "apple silicon", "arm", "risc-v",
            "memory", "ram", "ssd", "tsmc", "samsung", "fabrication",
            "transistor", "silicon", "manufacturing",
        ],
    },
    # General topics
    "politics": {
        "name": "Politics",
        "description": "Government, elections, policy, international relations",
        "keywords": [
            "president", "congress", "senate", "parliament", "election",
            "government", "policy", "legislation", "law", "regulation",
            "democracy", "vote", "campaign", "diplomat", "treaty", "sanctions",
            "minister", "prime minister", "political", "bipartisan",
        ],
    },
    "business": {
        "name": "Business",
        "description": "Finance, markets, companies, economics",
        "keywords": [
            "stock", "market", "investment", "ipo", "acquisition", "merger",
            "revenue", "profit", "earnings", "ceo", "startup", "funding",
            "venture capital", "economy", "inflation", "recession", "layoffs",
            "quarterly", "shareholders", "valuation",
        ],
    },
    "science": {
        "name": "Science",
        "description": "Research, discoveries, space, medicine, environment",
        "keywords": [
            "research", "study", "discovery", "scientist", "laboratory",
            "experiment", "nasa", "space", "climate", "environment", "medical",
            "health", "disease", "vaccine", "biology", "physics", "chemistry",
            "astronomy", "archaeology", "fossil",
        ],
    },
    "general": {
        "name": "General",
        "description": "General news and miscellaneous topics",
        "keywords": [],  # Fallback category
    },
}

# List of valid topic IDs
VALID_TOPICS = list(TOPIC_DEFINITIONS.keys())


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
    if topic_id in TOPIC_DEFINITIONS:
        return TOPIC_DEFINITIONS[topic_id]["name"]
    return topic_id.replace("-", "/").title()


def get_available_topics() -> List[Dict[str, str]]:
    """Get list of available topics with their display names."""
    return [
        {"id": topic_id, "name": config["name"], "description": config["description"]}
        for topic_id, config in TOPIC_DEFINITIONS.items()
    ]


# =============================================================================
# LLM-Based Classification
# =============================================================================


def _create_topic_classification_prompt(title: str, summary: str) -> str:
    """Create LLM prompt for topic classification."""
    content = f"Title: {title}\n\nSummary: {summary}".strip()

    # Build topic list for prompt
    topic_list = "\n".join(
        f"- {tid}: {config['description']}"
        for tid, config in TOPIC_DEFINITIONS.items()
    )

    prompt = f"""You are a news article classifier. Classify this article into ONE topic category.

ARTICLE:
{content}

AVAILABLE TOPICS:
{topic_list}

INSTRUCTIONS:
1. Read the article carefully
2. Choose the SINGLE most appropriate topic based on the main subject
3. For tech news, prefer specific categories (ai-ml, security, etc.) over "general"
4. For non-tech news (politics, disasters, sports), use appropriate general categories
5. Only use "general" if the article doesn't fit any other category

OUTPUT FORMAT (JSON only):
{{"topic": "topic-id", "confidence": 0.0-1.0}}

Example outputs:
{{"topic": "ai-ml", "confidence": 0.95}}
{{"topic": "politics", "confidence": 0.85}}
{{"topic": "general", "confidence": 0.6}}

Respond with ONLY the JSON object, no other text."""

    return prompt


def classify_topic_with_llm(
    title: str,
    summary: str = "",
    model: Optional[str] = None,
) -> Optional[TopicClassificationResult]:
    """
    Classify article topic using LLM.

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

        prompt = _create_topic_classification_prompt(title, summary or "")

        # Call LLM
        response = llm_service.client.generate(
            model=model or llm_service.model,
            prompt=prompt,
            options={"temperature": 0.1, "num_predict": 100},
        )

        response_text = response.get("response", "").strip()

        # Parse JSON response
        # Handle potential markdown code blocks
        if "```" in response_text:
            import re
            json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", response_text, re.DOTALL)
            if json_match:
                response_text = json_match.group(1)

        data = json.loads(response_text)
        topic_id = data.get("topic", "general").lower().strip()
        confidence = float(data.get("confidence", 0.5))

        # Validate topic
        if topic_id not in VALID_TOPICS:
            logger.warning(f"LLM returned invalid topic '{topic_id}', falling back to 'general'")
            topic_id = "general"
            confidence = 0.3

        return TopicClassificationResult(
            topic=topic_id,
            confidence=min(max(confidence, 0.0), 1.0),  # Clamp to 0-1
            method="llm",
            display_name=get_topic_display_name(topic_id),
        )

    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM topic response: {e}")
        return None
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

    for topic_id, config in TOPIC_DEFINITIONS.items():
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
        query = f"SELECT id, title, summary, topic FROM items WHERE id IN ({placeholders})"
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

