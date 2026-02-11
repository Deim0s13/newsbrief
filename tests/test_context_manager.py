"""
Tests for context window management.

Tests article prioritization, token budgeting, and synthesis strategy selection.
Part of Issue #106: Context window handling for large clusters.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.context_manager import (
    ArticleForSynthesis,
    ContextConfig,
    ContextMetrics,
    ModelConfig,
    SelectionResult,
    calculate_context_metrics,
    create_article_groups,
    determine_strategy,
    get_context_summary,
    get_model_config,
    load_config,
    prepare_articles_from_data,
    prioritize_articles,
    select_articles_for_budget,
    select_articles_for_synthesis,
)


class TestModelConfig:
    """Tests for model configuration loading."""

    def test_load_config_returns_context_config(self):
        """Test that load_config returns a ContextConfig object."""
        config = load_config(force_reload=True)
        assert isinstance(config, ContextConfig)

    def test_load_config_has_defaults(self):
        """Test that config has default values."""
        config = load_config(force_reload=True)
        assert config.max_articles_per_prompt >= 1
        assert config.summary_chars_per_article >= 100
        assert 0 < config.token_safety_margin <= 1.0

    def test_get_model_config_known_model(self):
        """Test getting config for a known model."""
        config = get_model_config("llama3.1:8b")
        assert isinstance(config, ModelConfig)
        assert config.context_window > 0
        assert config.synthesis_budget > 0

    def test_get_model_config_unknown_model(self):
        """Test getting config for unknown model returns defaults."""
        config = get_model_config("unknown-model-xyz")
        assert isinstance(config, ModelConfig)
        assert config.context_window == 8192  # Default


class TestArticleForSynthesis:
    """Tests for ArticleForSynthesis dataclass."""

    def test_article_creation(self):
        """Test creating an article object."""
        article = ArticleForSynthesis(
            id=1,
            title="Test Article",
            summary="This is a test summary.",
            ranking_score=0.85,
        )
        assert article.id == 1
        assert article.title == "Test Article"
        assert article.ranking_score == 0.85

    def test_estimated_tokens(self):
        """Test token estimation for an article."""
        article = ArticleForSynthesis(
            id=1,
            title="Short Title",
            summary="A brief summary.",
        )
        tokens = article.estimated_tokens
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_estimated_tokens_longer_content(self):
        """Test that longer content produces more tokens."""
        short = ArticleForSynthesis(id=1, title="Short", summary="Brief")
        long_content = ArticleForSynthesis(
            id=2,
            title="A Much Longer Title for Testing",
            summary="This is a much longer summary with more content. " * 10,
        )
        assert long_content.estimated_tokens > short.estimated_tokens


class TestArticlePrioritization:
    """Tests for article prioritization logic."""

    def test_prioritize_by_ranking_score(self):
        """Test that articles are sorted by ranking_score descending."""
        articles = [
            ArticleForSynthesis(id=1, title="Low", summary="", ranking_score=0.3),
            ArticleForSynthesis(id=2, title="High", summary="", ranking_score=0.9),
            ArticleForSynthesis(id=3, title="Medium", summary="", ranking_score=0.6),
        ]

        prioritized = prioritize_articles(articles)

        assert prioritized[0].id == 2  # Highest score
        assert prioritized[1].id == 3  # Medium score
        assert prioritized[2].id == 1  # Lowest score

    def test_prioritize_with_tie_uses_published(self):
        """Test that ties are broken by published date."""
        articles = [
            ArticleForSynthesis(
                id=1, title="Old", summary="", ranking_score=0.8, published="2024-01-01"
            ),
            ArticleForSynthesis(
                id=2, title="New", summary="", ranking_score=0.8, published="2024-01-15"
            ),
        ]

        prioritized = prioritize_articles(articles)

        # Both have same score, newer should come first
        assert prioritized[0].id == 2
        assert prioritized[1].id == 1

    def test_prioritize_empty_list(self):
        """Test prioritizing empty list returns empty list."""
        result = prioritize_articles([])
        assert result == []


class TestStrategyDetermination:
    """Tests for synthesis strategy selection."""

    def test_direct_strategy_small_cluster(self):
        """Test that small clusters use direct strategy."""
        assert determine_strategy(1) == "direct"
        assert determine_strategy(5) == "direct"
        assert determine_strategy(8) == "direct"

    def test_map_reduce_strategy_medium_cluster(self):
        """Test that medium clusters use map_reduce strategy."""
        assert determine_strategy(9) == "map_reduce"
        assert determine_strategy(12) == "map_reduce"
        assert determine_strategy(15) == "map_reduce"

    def test_hierarchical_strategy_large_cluster(self):
        """Test that large clusters use hierarchical strategy."""
        assert determine_strategy(16) == "hierarchical"
        assert determine_strategy(20) == "hierarchical"
        assert determine_strategy(50) == "hierarchical"


class TestArticleSelection:
    """Tests for token-aware article selection."""

    def test_select_within_budget(self):
        """Test selecting articles within token budget."""
        articles = [
            ArticleForSynthesis(
                id=i,
                title=f"Article {i}",
                summary="Short summary",
                ranking_score=1.0 - (i * 0.1),
            )
            for i in range(5)
        ]

        selected, dropped, tokens = select_articles_for_budget(
            articles, token_budget=10000, max_articles=10
        )

        assert len(selected) == 5
        assert len(dropped) == 0
        assert tokens > 0

    def test_select_respects_max_articles(self):
        """Test that max_articles limit is respected."""
        articles = [
            ArticleForSynthesis(
                id=i, title=f"Article {i}", summary="Summary", ranking_score=0.5
            )
            for i in range(10)
        ]

        selected, dropped, tokens = select_articles_for_budget(
            articles, token_budget=100000, max_articles=5
        )

        assert len(selected) == 5
        assert len(dropped) == 5

    def test_select_respects_token_budget(self):
        """Test that token budget is respected."""
        # Create articles with substantial content
        articles = [
            ArticleForSynthesis(
                id=i,
                title=f"Article {i}",
                summary="This is a longer summary. " * 20,
                ranking_score=0.5,
            )
            for i in range(20)
        ]

        # Very small budget should result in fewer articles
        selected, dropped, tokens = select_articles_for_budget(
            articles, token_budget=500, max_articles=20, base_prompt_tokens=100
        )

        # With small budget, not all articles should fit
        assert len(selected) < 20

    def test_select_preserves_priority_order(self):
        """Test that selection preserves priority order."""
        articles = [
            ArticleForSynthesis(
                id=i, title=f"Article {i}", summary="", ranking_score=1.0 - (i * 0.1)
            )
            for i in range(10)
        ]

        selected, dropped, _ = select_articles_for_budget(
            articles, token_budget=10000, max_articles=5
        )

        # First 5 (highest priority) should be selected
        selected_ids = [a.id for a in selected]
        assert selected_ids == [0, 1, 2, 3, 4]


class TestArticleGroups:
    """Tests for article group creation."""

    def test_create_groups_exact_division(self):
        """Test creating groups with exact division."""
        articles = [
            ArticleForSynthesis(id=i, title=f"Article {i}", summary="")
            for i in range(10)
        ]

        groups = create_article_groups(articles, group_size=5)

        assert len(groups) == 2
        assert len(groups[0]) == 5
        assert len(groups[1]) == 5

    def test_create_groups_remainder(self):
        """Test creating groups with remainder."""
        articles = [
            ArticleForSynthesis(id=i, title=f"Article {i}", summary="")
            for i in range(12)
        ]

        groups = create_article_groups(articles, group_size=5)

        assert len(groups) == 3
        assert len(groups[0]) == 5
        assert len(groups[1]) == 5
        assert len(groups[2]) == 2  # Remainder

    def test_create_groups_single_group(self):
        """Test creating groups when all fit in one."""
        articles = [
            ArticleForSynthesis(id=i, title=f"Article {i}", summary="")
            for i in range(3)
        ]

        groups = create_article_groups(articles, group_size=5)

        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_create_groups_empty(self):
        """Test creating groups from empty list."""
        groups = create_article_groups([], group_size=5)
        assert len(groups) == 0


class TestSelectArticlesForSynthesis:
    """Tests for the main selection function."""

    def test_select_returns_selection_result(self):
        """Test that select function returns SelectionResult."""
        articles = [
            ArticleForSynthesis(
                id=i, title=f"Article {i}", summary="Summary", ranking_score=0.5
            )
            for i in range(5)
        ]

        result = select_articles_for_synthesis(articles, "llama3.1:8b")

        assert isinstance(result, SelectionResult)
        assert len(result.selected) > 0
        assert result.strategy == "direct"
        assert result.budget_used >= 0

    def test_select_empty_returns_empty_result(self):
        """Test that empty input returns empty result."""
        result = select_articles_for_synthesis([], "llama3.1:8b")

        assert len(result.selected) == 0
        assert len(result.dropped) == 0
        assert result.strategy == "direct"

    def test_select_large_cluster_uses_different_strategy(self):
        """Test that large clusters get appropriate strategy."""
        articles = [
            ArticleForSynthesis(
                id=i, title=f"Article {i}", summary="Summary", ranking_score=0.5
            )
            for i in range(20)
        ]

        result = select_articles_for_synthesis(articles, "llama3.1:8b")

        assert result.strategy == "hierarchical"


class TestPrepareArticlesFromData:
    """Tests for converting raw data to ArticleForSynthesis."""

    def test_prepare_from_dict_format(self):
        """Test preparing articles from dict format."""
        data = [
            {
                "id": 1,
                "title": "Test Article",
                "summary": "A summary",
                "ai_summary": "AI summary",
                "ranking_score": 0.8,
                "topic": "tech",
            },
            {
                "id": 2,
                "title": None,  # Missing title
                "summary": "Only summary",
                "ranking_score": None,  # Missing score
            },
        ]

        articles = prepare_articles_from_data(data)

        assert len(articles) == 2
        assert articles[0].id == 1
        assert articles[0].title == "Test Article"
        assert articles[0].summary == "AI summary"  # Prefers ai_summary
        assert articles[0].ranking_score == 0.8
        assert articles[1].title == "Untitled"  # Default for None
        assert articles[1].ranking_score == 0.0  # Default for None

    def test_prepare_from_tuple_format(self):
        """Test preparing articles from tuple format."""
        data = [
            (1, "Title", "Summary", "AI Summary", "tech"),
            (2, None, "Only Summary", None, None),
        ]

        articles = prepare_articles_from_data(data)

        assert len(articles) == 2
        assert articles[0].id == 1
        assert articles[0].summary == "AI Summary"
        assert articles[1].title == "Untitled"


class TestContextMetrics:
    """Tests for context metrics calculation."""

    def test_calculate_metrics(self):
        """Test calculating context metrics."""
        selection = SelectionResult(
            selected=[
                ArticleForSynthesis(id=i, title=f"Article {i}", summary="")
                for i in range(5)
            ],
            dropped=[
                ArticleForSynthesis(id=i, title=f"Dropped {i}", summary="")
                for i in range(3)
            ],
            total_tokens=3000,
            budget_used=50.0,
            strategy="direct",
        )

        metrics = calculate_context_metrics(8, selection, "llama3.1:8b")

        assert isinstance(metrics, ContextMetrics)
        assert metrics.cluster_size == 8
        assert metrics.articles_used == 5
        assert metrics.articles_dropped == 3
        assert metrics.utilization_percent == 50.0
        assert metrics.strategy == "direct"

    def test_context_summary_format(self):
        """Test context summary string generation."""
        metrics = ContextMetrics(
            cluster_size=10,
            articles_used=8,
            articles_dropped=2,
            token_budget=6000,
            tokens_used=4500,
            utilization_percent=75.0,
            strategy="direct",
        )

        summary = get_context_summary(metrics)

        assert "8/10 articles" in summary
        assert "4500/6000 tokens" in summary
        assert "75.0%" in summary
        assert "direct" in summary


class TestMapReducePrompts:
    """Tests for map-reduce prompt creation."""

    def test_group_summary_prompt_created(self):
        """Test that group summary prompt is created correctly."""
        from app.prompts.map_reduce import create_group_summary_prompt

        articles = [
            {"title": "Article 1", "summary": "Summary 1"},
            {"title": "Article 2", "summary": "Summary 2"},
        ]

        prompt = create_group_summary_prompt(articles, 1, 3, "BREAKING")

        assert "ARTICLE 1" in prompt
        assert "ARTICLE 2" in prompt
        assert "group 1 of 3" in prompt
        assert "BREAKING" in prompt

    def test_reduce_prompt_created(self):
        """Test that reduce prompt is created correctly."""
        from app.prompts.map_reduce import create_reduce_prompt

        summaries = [
            {
                "summary": "Group 1 summary",
                "key_facts": ["Fact 1"],
                "entities": ["Entity A"],
                "unique_angle": "Unique angle 1",
            },
            {
                "summary": "Group 2 summary",
                "key_facts": ["Fact 2"],
                "entities": ["Entity B"],
                "unique_angle": "",
            },
        ]

        prompt = create_reduce_prompt(summaries, "TREND", 12)

        assert "GROUP 1" in prompt
        assert "GROUP 2" in prompt
        assert "12 articles" in prompt
        assert "TREND" in prompt

    def test_parse_group_summary_response(self):
        """Test parsing group summary response."""
        from app.prompts.map_reduce import parse_group_summary_response

        response = """
        ```json
        {
            "summary": "A test summary",
            "key_facts": ["Fact 1", "Fact 2"],
            "entities": ["Entity A"],
            "unique_angle": "Test angle"
        }
        ```
        """

        result = parse_group_summary_response(response)

        assert result is not None
        assert result["summary"] == "A test summary"
        assert len(result["key_facts"]) == 2
        assert "Entity A" in result["entities"]
