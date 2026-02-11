"""
Chain-of-thought analysis prompts.

Extracts structured information from article clusters before synthesis,
enabling more coherent and insightful story generation.
"""

import json
import logging
from typing import Optional

from . import AnalysisResult

logger = logging.getLogger(__name__)


def create_analysis_prompt(
    article_summaries: list[dict[str, str]],
    story_type: str,
    max_articles: int = 8,
    max_summary_chars: int = 400,
) -> str:
    """
    Create chain-of-thought analysis prompt.

    This prompt extracts structured information that will inform
    the synthesis pass, including timeline, facts, tensions, and gaps.

    Args:
        article_summaries: List of dicts with 'title' and 'summary' keys
            (should be pre-prioritized with most important first)
        story_type: The detected story type (BREAKING, EVOLVING, etc.)
        max_articles: Maximum articles to include (default: 8)
        max_summary_chars: Maximum characters per summary (default: 400)

    Returns:
        Prompt string for LLM
    """
    articles_text = "\n\n".join(
        f"ARTICLE {i + 1}:\nTitle: {a.get('title', 'Untitled')}\n"
        f"{a.get('summary', '')[:max_summary_chars]}"
        for i, a in enumerate(article_summaries[:max_articles])
    )

    return f"""You are a senior news analyst preparing to write a synthesized story from multiple sources.
Before writing, carefully analyze these articles to extract key information.

STORY TYPE: {story_type}

{articles_text}

Perform a thorough analysis and respond with JSON:
{{
  "timeline": [
    "Event/fact in chronological order (earliest first)",
    "Include dates/times when mentioned",
    "Max 5 items"
  ],
  "core_facts": [
    "Facts that ALL or MOST sources agree on",
    "These are the bedrock of your synthesis",
    "Max 5 items"
  ],
  "tensions": [
    "Where sources DISAGREE or present different perspectives",
    "Include competing claims or interpretations",
    "Empty list if sources are in agreement"
  ],
  "key_players": [
    "Person/Company: Their role or position on this story",
    "Include stakeholders affected by the news",
    "Max 5 items"
  ],
  "gaps": [
    "Important questions NOT answered by these sources",
    "What a reader might want to know that isn't covered",
    "Max 3 items"
  ],
  "narrative_thread": "One sentence describing the unifying theme that connects all articles"
}}

ANALYSIS GUIDELINES:
- Be specific and factual, not generic
- For timeline: Use actual dates/events from articles, not generic descriptions
- For core_facts: Only include what multiple sources confirm
- For tensions: Note genuine disagreements, not just different emphasis
- For key_players: Include their specific stake or action
- For gaps: Think like a curious reader - what's missing?
- For narrative_thread: This will guide the synthesis headline and opening

JSON:"""


def parse_analysis_response(response: str) -> Optional[AnalysisResult]:
    """
    Parse LLM response into AnalysisResult.

    Args:
        response: Raw LLM response text

    Returns:
        AnalysisResult or None if parsing fails
    """
    try:
        # Try to extract JSON from response
        response = response.strip()

        # Handle markdown code blocks
        if "```" in response:
            start = response.find("```")
            end = response.rfind("```")
            if start != end:
                response = response[start:end]
                response = response.lstrip("`json\n").lstrip("`\n")

        # Find JSON object
        start_idx = response.find("{")
        end_idx = response.rfind("}") + 1
        if start_idx == -1 or end_idx == 0:
            logger.warning("No JSON object found in analysis response")
            return None

        json_str = response[start_idx:end_idx]
        data = json.loads(json_str)

        return AnalysisResult(
            timeline=data.get("timeline", [])[:5],
            core_facts=data.get("core_facts", [])[:5],
            tensions=data.get("tensions", [])[:3],
            key_players=data.get("key_players", [])[:5],
            gaps=data.get("gaps", [])[:3],
            narrative_thread=data.get("narrative_thread", ""),
        )

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(f"Failed to parse analysis response: {e}")
        return None
