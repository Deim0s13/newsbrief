"""
Context window management for LLM synthesis.

Handles article prioritization, token budgeting, and selection strategies
for story synthesis with different cluster sizes.

Key Features:
- Model-specific context window configuration
- Article prioritization by importance/ranking
- Token-aware article selection
- Strategy selection (direct, map-reduce, hierarchical)
- Context utilization metrics

See Issue #106 for implementation details.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .synthesis_cache import count_tokens

logger = logging.getLogger(__name__)

# Configuration file path
CONFIG_PATH = Path(__file__).parent.parent / "data" / "model_config.json"


@dataclass
class ModelConfig:
    """Configuration for a specific LLM model."""

    context_window: int = 8192
    synthesis_budget: int = 6000
    output_reserved: int = 1000
    description: str = ""

    @property
    def available_for_input(self) -> int:
        """Tokens available for input (context - output reserved)."""
        return self.context_window - self.output_reserved


@dataclass
class ContextConfig:
    """Global context configuration settings."""

    max_articles_per_prompt: int = 8
    summary_chars_per_article: int = 500
    title_chars_per_article: int = 80
    token_safety_margin: float = 0.9
    models: Dict[str, ModelConfig] = field(default_factory=dict)

    # Strategy thresholds
    map_reduce_min: int = 9
    map_reduce_max: int = 15
    map_reduce_group_size: int = 5
    hierarchical_min: int = 16
    hierarchical_tier1_group_size: int = 5
    hierarchical_tier2_max_summaries: int = 4


@dataclass
class ArticleForSynthesis:
    """Article data prepared for synthesis."""

    id: int
    title: str
    summary: str
    ranking_score: float = 0.0
    published: Optional[str] = None
    topic: Optional[str] = None
    feed_id: Optional[int] = None

    @property
    def estimated_tokens(self) -> int:
        """Estimate token count for this article in a prompt."""
        # Title + summary + formatting overhead
        text = f"ARTICLE:\nTitle: {self.title}\n{self.summary}"
        return count_tokens(text)


@dataclass
class SelectionResult:
    """Result of article selection for context window."""

    selected: List[ArticleForSynthesis]
    dropped: List[ArticleForSynthesis]
    total_tokens: int
    budget_used: float  # Percentage of budget used
    strategy: str  # "direct", "map_reduce", "hierarchical"


@dataclass
class ContextMetrics:
    """Metrics for context window usage."""

    cluster_size: int
    articles_used: int
    articles_dropped: int
    token_budget: int
    tokens_used: int
    utilization_percent: float
    strategy: str
    groups_created: int = 0  # For map-reduce/hierarchical


# Global config cache
_config_cache: Optional[ContextConfig] = None


def load_config(force_reload: bool = False) -> ContextConfig:
    """
    Load context configuration from JSON file.

    Args:
        force_reload: If True, reload from disk even if cached

    Returns:
        ContextConfig with all settings
    """
    global _config_cache

    if _config_cache is not None and not force_reload:
        return _config_cache

    config = ContextConfig()

    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                data = json.load(f)

            # Load defaults
            defaults = data.get("defaults", {})
            config.max_articles_per_prompt = defaults.get("max_articles_per_prompt", 8)
            config.summary_chars_per_article = defaults.get(
                "summary_chars_per_article", 500
            )
            config.title_chars_per_article = defaults.get("title_chars_per_article", 80)
            config.token_safety_margin = defaults.get("token_safety_margin", 0.9)

            # Load model configs
            for model_name, model_data in data.get("models", {}).items():
                config.models[model_name] = ModelConfig(
                    context_window=model_data.get("context_window", 8192),
                    synthesis_budget=model_data.get("synthesis_budget", 6000),
                    output_reserved=model_data.get("output_reserved", 1000),
                    description=model_data.get("description", ""),
                )

            # Load strategy thresholds
            strategies = data.get("synthesis_strategies", {})
            if "map_reduce" in strategies:
                mr = strategies["map_reduce"]
                config.map_reduce_min = mr.get("min_articles", 9)
                config.map_reduce_max = mr.get("max_articles", 15)
                config.map_reduce_group_size = mr.get("group_size", 5)
            if "hierarchical" in strategies:
                hier = strategies["hierarchical"]
                config.hierarchical_min = hier.get("min_articles", 16)
                config.hierarchical_tier1_group_size = hier.get("tier1_group_size", 5)
                config.hierarchical_tier2_max_summaries = hier.get(
                    "tier2_max_summaries", 4
                )

            logger.debug(f"Loaded context config with {len(config.models)} models")
        else:
            logger.warning(f"Config file not found at {CONFIG_PATH}, using defaults")

    except Exception as e:
        logger.error(f"Failed to load context config: {e}, using defaults")

    _config_cache = config
    return config


def get_model_config(model: str) -> ModelConfig:
    """
    Get configuration for a specific model.

    Args:
        model: Model name (e.g., "llama3.1:8b")

    Returns:
        ModelConfig for the model (defaults if not found)
    """
    config = load_config()
    return config.models.get(model, ModelConfig())


def determine_strategy(article_count: int) -> str:
    """
    Determine synthesis strategy based on cluster size.

    Args:
        article_count: Number of articles in cluster

    Returns:
        Strategy name: "direct", "map_reduce", or "hierarchical"
    """
    config = load_config()

    if article_count >= config.hierarchical_min:
        return "hierarchical"
    elif article_count >= config.map_reduce_min:
        return "map_reduce"
    else:
        return "direct"


def prioritize_articles(
    articles: List[ArticleForSynthesis],
) -> List[ArticleForSynthesis]:
    """
    Sort articles by importance for synthesis.

    Priority order:
    1. Higher ranking_score first
    2. More recent published date (tie-breaker)

    Args:
        articles: List of articles to prioritize

    Returns:
        Sorted list with most important articles first
    """
    return sorted(
        articles,
        key=lambda a: (a.ranking_score, a.published or ""),
        reverse=True,
    )


def select_articles_for_budget(
    articles: List[ArticleForSynthesis],
    token_budget: int,
    max_articles: Optional[int] = None,
    base_prompt_tokens: int = 500,
) -> Tuple[List[ArticleForSynthesis], List[ArticleForSynthesis], int]:
    """
    Select articles that fit within token budget.

    Articles should be pre-prioritized (most important first).

    Args:
        articles: Prioritized list of articles
        token_budget: Maximum tokens allowed
        max_articles: Optional hard limit on article count
        base_prompt_tokens: Tokens used by prompt template (overhead)

    Returns:
        Tuple of (selected_articles, dropped_articles, total_tokens_used)
    """
    config = load_config()

    if max_articles is None:
        max_articles = config.max_articles_per_prompt

    # Apply safety margin
    effective_budget = int(token_budget * config.token_safety_margin)
    available_budget = effective_budget - base_prompt_tokens

    selected: List[ArticleForSynthesis] = []
    dropped: List[ArticleForSynthesis] = []
    tokens_used = base_prompt_tokens

    for article in articles:
        # Check article limit
        if len(selected) >= max_articles:
            dropped.append(article)
            continue

        # Estimate tokens for this article
        article_tokens = article.estimated_tokens

        # Check if it fits
        if tokens_used + article_tokens <= effective_budget:
            selected.append(article)
            tokens_used += article_tokens
        else:
            dropped.append(article)

    return selected, dropped, tokens_used


def select_articles_for_synthesis(
    articles: List[ArticleForSynthesis],
    model: str,
    max_articles: Optional[int] = None,
) -> SelectionResult:
    """
    Select and prioritize articles for synthesis within context limits.

    This is the main entry point for article selection. It:
    1. Determines the appropriate strategy
    2. Prioritizes articles by importance
    3. Selects articles that fit the token budget
    4. Returns selection result with metrics

    Args:
        articles: List of articles to consider
        model: LLM model name for budget calculation
        max_articles: Optional override for max articles

    Returns:
        SelectionResult with selected/dropped articles and metrics
    """
    if not articles:
        return SelectionResult(
            selected=[],
            dropped=[],
            total_tokens=0,
            budget_used=0.0,
            strategy="direct",
        )

    # Get model config
    model_config = get_model_config(model)
    token_budget = model_config.synthesis_budget

    # Determine strategy based on cluster size
    strategy = determine_strategy(len(articles))

    # Prioritize articles
    prioritized = prioritize_articles(articles)

    # For direct strategy, select within budget
    if strategy == "direct":
        selected, dropped, tokens_used = select_articles_for_budget(
            prioritized, token_budget, max_articles
        )
    else:
        # For map-reduce/hierarchical, we'll use all articles but track the selection
        # The actual grouping happens in the synthesis pipeline
        config = load_config()
        effective_max = max_articles or config.max_articles_per_prompt

        # Still prioritize and track what would be "primary" articles
        selected = prioritized[:effective_max]
        dropped = prioritized[effective_max:]
        tokens_used = sum(a.estimated_tokens for a in selected) + 500

    budget_used = (tokens_used / token_budget) * 100 if token_budget > 0 else 0

    logger.info(
        f"Article selection: {len(selected)}/{len(articles)} articles, "
        f"strategy={strategy}, budget={budget_used:.1f}%"
    )

    if dropped:
        logger.debug(
            f"Dropped {len(dropped)} lower-priority articles: "
            f"{[a.id for a in dropped[:5]]}{'...' if len(dropped) > 5 else ''}"
        )

    return SelectionResult(
        selected=selected,
        dropped=dropped,
        total_tokens=tokens_used,
        budget_used=budget_used,
        strategy=strategy,
    )


def create_article_groups(
    articles: List[ArticleForSynthesis],
    group_size: int,
) -> List[List[ArticleForSynthesis]]:
    """
    Split articles into groups for map-reduce processing.

    Args:
        articles: List of articles (should be pre-prioritized)
        group_size: Target size for each group

    Returns:
        List of article groups
    """
    groups: List[List[ArticleForSynthesis]] = []

    for i in range(0, len(articles), group_size):
        group = articles[i : i + group_size]
        groups.append(group)

    logger.debug(f"Created {len(groups)} groups from {len(articles)} articles")
    return groups


def prepare_articles_from_data(
    articles_data: List[Dict[str, Any]],
) -> List[ArticleForSynthesis]:
    """
    Convert raw article data to ArticleForSynthesis objects.

    Args:
        articles_data: List of article dicts from database/cache

    Returns:
        List of ArticleForSynthesis objects
    """
    result = []

    for data in articles_data:
        # Handle both dict and tuple formats
        if isinstance(data, dict):
            article = ArticleForSynthesis(
                id=data.get("id", 0),
                title=data.get("title", "Untitled") or "Untitled",
                summary=data.get("ai_summary") or data.get("summary") or "",
                ranking_score=data.get("ranking_score", 0.0) or 0.0,
                published=data.get("published"),
                topic=data.get("topic"),
                feed_id=data.get("feed_id"),
            )
        else:
            # Tuple format: (id, title, summary, ai_summary, topic, ...)
            article = ArticleForSynthesis(
                id=data[0] if len(data) > 0 else 0,
                title=data[1] or "Untitled" if len(data) > 1 else "Untitled",
                summary=data[3] or data[2] or "" if len(data) > 3 else "",
                ranking_score=0.0,  # Not available in tuple format
                topic=data[4] if len(data) > 4 else None,
            )

        result.append(article)

    return result


def calculate_context_metrics(
    cluster_size: int,
    selection_result: SelectionResult,
    model: str,
) -> ContextMetrics:
    """
    Calculate detailed context utilization metrics.

    Args:
        cluster_size: Original number of articles in cluster
        selection_result: Result from article selection
        model: Model name for budget reference

    Returns:
        ContextMetrics with detailed usage statistics
    """
    model_config = get_model_config(model)

    return ContextMetrics(
        cluster_size=cluster_size,
        articles_used=len(selection_result.selected),
        articles_dropped=len(selection_result.dropped),
        token_budget=model_config.synthesis_budget,
        tokens_used=selection_result.total_tokens,
        utilization_percent=selection_result.budget_used,
        strategy=selection_result.strategy,
    )


def get_context_summary(metrics: ContextMetrics) -> str:
    """
    Generate human-readable summary of context usage.

    Args:
        metrics: Context metrics to summarize

    Returns:
        Summary string for logging
    """
    return (
        f"Context: {metrics.articles_used}/{metrics.cluster_size} articles, "
        f"{metrics.tokens_used}/{metrics.token_budget} tokens "
        f"({metrics.utilization_percent:.1f}%), "
        f"strategy={metrics.strategy}"
    )
