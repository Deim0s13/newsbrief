"""
Prompt templates for LLM-based story synthesis.

This module contains structured prompts for the multi-pass synthesis pipeline:
1. Story Type Detection - Classify the cluster pattern
2. Chain-of-Thought Analysis - Extract facts, timeline, tensions
3. Type-Specific Synthesis - Generate narrative appropriate to story type
4. Quality Refinement - Polish and self-critique
5. Map-Reduce Synthesis - Handle large clusters (9+ articles)
6. Hierarchical Synthesis - Handle very large clusters (16+ articles)

Part of Issue #102: Improve synthesis prompts for better narratives.
Part of Issue #106: Context window handling for large clusters.
"""

from enum import Enum
from typing import NamedTuple


class StoryType(Enum):
    """Classification of story patterns for targeted synthesis."""

    BREAKING = "breaking"  # Single event, multiple sources reporting same thing
    EVOLVING = "evolving"  # Updates/developments on ongoing story
    TREND = "trend"  # Pattern emerging across multiple sources
    COMPARISON = "comparison"  # Different perspectives or competing claims


class StoryTypeResult(NamedTuple):
    """Result of story type detection."""

    story_type: StoryType
    confidence: float  # 0.0-1.0
    reasoning: str  # Brief explanation of classification


class AnalysisResult(NamedTuple):
    """Result of chain-of-thought analysis pass."""

    timeline: list[str]  # Events in chronological order
    core_facts: list[str]  # Facts all sources agree on
    tensions: list[str]  # Where sources differ/conflict
    key_players: list[str]  # Stakeholders and their positions
    gaps: list[str]  # What's not being covered
    narrative_thread: str  # The unifying theme


# Re-export prompt functions
from .analysis import create_analysis_prompt, parse_analysis_response
from .detection import create_detection_prompt, parse_detection_response
from .map_reduce import (
    create_group_summary_prompt,
    create_hierarchical_tier1_prompt,
    create_hierarchical_tier2_prompt,
    create_reduce_prompt,
    parse_group_summary_response,
)
from .refinement import create_refinement_prompt, parse_refinement_response
from .synthesis import get_synthesis_prompt

__all__ = [
    "StoryType",
    "StoryTypeResult",
    "AnalysisResult",
    "create_detection_prompt",
    "parse_detection_response",
    "create_analysis_prompt",
    "parse_analysis_response",
    "get_synthesis_prompt",
    "create_refinement_prompt",
    "parse_refinement_response",
    # Map-reduce prompts (Issue #106)
    "create_group_summary_prompt",
    "parse_group_summary_response",
    "create_reduce_prompt",
    "create_hierarchical_tier1_prompt",
    "create_hierarchical_tier2_prompt",
]
