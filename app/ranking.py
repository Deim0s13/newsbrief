#!/usr/bin/env python3
"""
NewsbrieF Ranking and Topic Classification System

This module implements the article ranking algorithm and topic classification
system introduced in v0.4.0.

Ranking Algorithm:
- Recency boost: Newer articles get higher scores
- Source weight: Important sources get preference
- Keyword matching: Articles matching popular keywords get boosted

Topic Classification:
- Primary: Keyword-based classification for speed
- Fallback: LLM-based classification for edge cases
- Topics: AI/ML, Cloud/K8s, Security, DevTools, Chips/Hardware
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any

# Configure logging
logger = logging.getLogger(__name__)

# Topic classification configuration
TOPICS = {
    "ai-ml": {
        "name": "AI/ML",
        "keywords": [
            # Core AI/ML terms
            "artificial intelligence",
            "machine learning",
            "deep learning",
            "neural network",
            "transformer",
            "llm",
            "gpt",
            "chatgpt",
            "openai",
            "anthropic",
            "claude",
            "gemini",
            "ollama",
            # Specific ML concepts
            "embeddings",
            "vector",
            "rag",
            "fine-tuning",
            "training",
            "inference",
            "pytorch",
            "tensorflow",
            "hugging face",
            "stable diffusion",
            "computer vision",
            "nlp",
            "generative",
            # Business AI
            "ai startup",
            "ai tools",
            "copilot",
            "ai assistant",
        ],
        "weight": 1.2,  # AI/ML gets slight boost as it's hot topic
    },
    "cloud-k8s": {
        "name": "Cloud/K8s",
        "keywords": [
            # Cloud platforms
            "aws",
            "azure",
            "gcp",
            "google cloud",
            "amazon web services",
            "cloud computing",
            "serverless",
            "lambda",
            "functions",
            # Container/orchestration
            "kubernetes",
            "k8s",
            "docker",
            "container",
            "podman",
            "helm",
            "istio",
            "service mesh",
            "microservices",
            # Infrastructure
            "terraform",
            "infrastructure as code",
            "iac",
            "devops",
            "ci/cd",
            "github actions",
            "gitlab",
            "jenkins",
        ],
        "weight": 1.1,
    },
    "security": {
        "name": "Security",
        "keywords": [
            # Cybersecurity
            "security",
            "vulnerability",
            "exploit",
            "breach",
            "hack",
            "malware",
            "ransomware",
            "phishing",
            "cybersecurity",
            # Crypto/blockchain
            "blockchain",
            "cryptocurrency",
            "bitcoin",
            "ethereum",
            "web3",
            "smart contract",
            "defi",
            "nft",
            # Security practices
            "authentication",
            "authorization",
            "encryption",
            "tls",
            "certificate",
            "zero trust",
            "penetration test",
        ],
        "weight": 1.15,  # Security is always important
    },
    "devtools": {
        "name": "DevTools",
        "keywords": [
            # Programming languages
            "python",
            "javascript",
            "typescript",
            "rust",
            "go",
            "java",
            "c++",
            "swift",
            "kotlin",
            "ruby",
            "php",
            # Development tools
            "vscode",
            "github",
            "gitlab",
            "git",
            "ide",
            "editor",
            "framework",
            "library",
            "api",
            "rest",
            "graphql",
            # Web development
            "react",
            "vue",
            "angular",
            "node",
            "fastapi",
            "django",
            "nextjs",
            "svelte",
            "web development",
            "frontend",
            "backend",
        ],
        "weight": 1.0,
    },
    "chips-hardware": {
        "name": "Chips/Hardware",
        "keywords": [
            # Chip companies
            "nvidia",
            "amd",
            "intel",
            "qualcomm",
            "apple silicon",
            "m1",
            "m2",
            "m3",
            "arm",
            "risc-v",
            # Hardware concepts
            "semiconductor",
            "chip",
            "processor",
            "cpu",
            "gpu",
            "memory",
            "storage",
            "ssd",
            "ram",
            "silicon",
            # Manufacturing
            "tsmc",
            "samsung",
            "fab",
            "foundry",
            "node",
            "nm",
            "manufacturing",
            "yield",
            "wafer",
        ],
        "weight": 1.1,
    },
}


@dataclass
class RankingResult:
    """Result of ranking calculation."""

    score: float
    components: Dict[str, float]  # Breakdown of score components


@dataclass
class TopicResult:
    """Result of topic classification."""

    topic: Optional[str]
    confidence: float
    method: str  # "keywords" or "llm" or "fallback"
    matched_keywords: List[str] = field(default_factory=list)


class RankingCalculator:
    """Calculates article ranking scores."""

    def __init__(self):
        self.max_age_days = 7  # Articles older than this get minimal recency boost
        self.recency_weight = 0.4
        self.source_weight_factor = 0.3
        self.keyword_weight = 0.3

    def calculate_score(
        self,
        published: Optional[datetime],
        source_weight: float,
        title: str,
        content: str = "",
        topic: Optional[str] = None,
    ) -> RankingResult:
        """Calculate ranking score for an article."""

        # Recency component (0.0 - 1.0)
        recency_score = self._calculate_recency_score(published)

        # Source weight component (0.0 - 2.0, typically 0.5 - 1.5)
        source_score = min(source_weight, 2.0)

        # Keyword matching component (0.0 - 1.0)
        keyword_score = self._calculate_keyword_score(title, content, topic)

        # Weighted total
        total_score = (
            recency_score * self.recency_weight
            + source_score * self.source_weight_factor
            + keyword_score * self.keyword_weight
        )

        # Apply topic weight if available
        if topic and topic in TOPICS:
            topic_multiplier = TOPICS[topic]["weight"]
            total_score *= topic_multiplier

        components = {
            "recency": recency_score,
            "source": source_score,
            "keywords": keyword_score,
            "topic_multiplier": (
                TOPICS.get(topic, {}).get("weight", 1.0) if topic else 1.0
            ),
            "final": total_score,
        }

        return RankingResult(score=total_score, components=components)

    def _calculate_recency_score(self, published: Optional[datetime]) -> float:
        """Calculate recency component (newer = higher score)."""
        if not published:
            return 0.2  # Default low score for unknown publish date

        now = datetime.now(timezone.utc)

        # Handle timezone-naive datetimes
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)

        age_hours = (now - published).total_seconds() / 3600
        age_days = age_hours / 24

        if age_days <= 0.5:  # Less than 12 hours
            return 1.0
        elif age_days <= 1:  # 12-24 hours
            return 0.9
        elif age_days <= 2:  # 1-2 days
            return 0.7
        elif age_days <= 7:  # 2-7 days
            return 0.4 - (age_days - 2) * 0.06  # Linear decay
        else:
            return 0.1  # Older than 7 days

    def _calculate_keyword_score(
        self, title: str, content: str = "", topic: Optional[str] = None
    ) -> float:
        """Calculate keyword matching component."""
        if not title:
            return 0.0

        text = (title + " " + content).lower()

        # Get keywords for the classified topic, or check all topics
        topics_to_check = [topic] if topic and topic in TOPICS else TOPICS.keys()

        max_score = 0.0
        for topic_key in topics_to_check:
            topic_config = TOPICS[topic_key]
            keywords = topic_config.get("keywords", [])
            matches = sum(1 for keyword in keywords if keyword in text)

            if matches > 0:
                # Score based on number of matches, diminishing returns
                score = min(matches * 0.2, 1.0)
                max_score = max(max_score, score)

        return max_score


class TopicClassifier:
    """Classifies articles into topics."""

    def __init__(self):
        self.confidence_threshold = 0.6  # Minimum confidence for classification

    def classify_article(
        self, title: str, content: str = "", use_llm_fallback: bool = True
    ) -> TopicResult:
        """Classify article into a topic."""

        # Primary: Keyword-based classification
        result = self._classify_by_keywords(title, content)

        if result.confidence >= self.confidence_threshold:
            return result

        # Fallback: LLM classification (if enabled)
        if use_llm_fallback:
            llm_result = self._classify_by_llm(title, content)
            if llm_result and llm_result.confidence > result.confidence:
                return llm_result

        # Return keyword result even if low confidence
        return (
            result
            if result.topic
            else TopicResult(
                topic=None, confidence=0.0, method="fallback", matched_keywords=[]
            )
        )

    def _classify_by_keywords(self, title: str, content: str = "") -> TopicResult:
        """Classify using keyword matching."""
        if not title:
            return TopicResult(topic=None, confidence=0.0, method="keywords")

        text = (title + " " + content).lower()

        # Score each topic based on keyword matches
        topic_scores = {}
        all_matches = {}

        for topic_key, topic_config in TOPICS.items():
            matches = []
            keywords = topic_config.get("keywords", [])
            for keyword in keywords:
                if keyword in text:
                    matches.append(keyword)

            if matches and keywords:
                # Score based on unique matches and keyword importance
                base_score = len(matches) / len(keywords)

                # Boost for title matches
                title_matches = sum(1 for kw in matches if kw in title.lower())
                title_boost = title_matches * 0.1

                topic_scores[topic_key] = min(base_score + title_boost, 1.0)
                all_matches[topic_key] = matches

        if not topic_scores:
            return TopicResult(topic=None, confidence=0.0, method="keywords")

        # Get best topic
        best_topic = max(topic_scores.items(), key=lambda x: x[1])
        topic_key, confidence = best_topic

        return TopicResult(
            topic=topic_key,
            confidence=confidence,
            method="keywords",
            matched_keywords=all_matches.get(topic_key, []),
        )

    def _classify_by_llm(self, title: str, content: str = "") -> Optional[TopicResult]:
        """Classify using LLM (fallback method)."""
        # TODO: Implement LLM-based classification
        # For now, return None to indicate LLM is not available
        logger.info("LLM topic classification not yet implemented")
        return None


# Convenience functions for easy import
def calculate_ranking_score(
    published: Optional[datetime],
    source_weight: float,
    title: str,
    content: str = "",
    topic: Optional[str] = None,
) -> RankingResult:
    """Calculate ranking score for an article."""
    calculator = RankingCalculator()
    return calculator.calculate_score(published, source_weight, title, content, topic)


def classify_article_topic(
    title: str, content: str = "", use_llm_fallback: bool = True
) -> TopicResult:
    """Classify an article into a topic."""
    classifier = TopicClassifier()
    return classifier.classify_article(title, content, use_llm_fallback)


def get_topic_display_name(topic_key: str) -> str:
    """Get human-readable name for a topic."""
    topic_config = TOPICS.get(topic_key, {})
    return (
        topic_config.get("name", topic_key)
        if isinstance(topic_config, dict)
        else topic_key
    )


def get_available_topics() -> List[Dict[str, str]]:
    """Get list of available topics with their display names."""
    return [
        {"key": key, "name": config.get("name", key)}
        for key, config in TOPICS.items()
        if isinstance(config, dict)
    ]
