"""
Story type detection prompts.

Classifies article clusters into story patterns to enable
targeted synthesis strategies.
"""

import json
import logging
from typing import Optional

from . import StoryType, StoryTypeResult

logger = logging.getLogger(__name__)


def create_detection_prompt(article_summaries: list[dict[str, str]]) -> str:
    """
    Create prompt for detecting story type from article cluster.

    Args:
        article_summaries: List of dicts with 'title' and 'summary' keys

    Returns:
        Prompt string for LLM
    """
    articles_text = "\n\n".join(
        f"ARTICLE {i + 1}:\nTitle: {a.get('title', 'Untitled')}\n{a.get('summary', '')[:300]}"
        for i, a in enumerate(article_summaries[:8])  # Limit to 8 for context window
    )

    return f"""Analyze these related news articles and classify the story pattern.

{articles_text}

STORY PATTERNS:
1. BREAKING - A single event being reported by multiple sources (announcement, incident, release)
2. EVOLVING - Updates or developments on an ongoing situation (continuing coverage, new developments)
3. TREND - A pattern or theme emerging across different sources (industry shift, recurring issue)
4. COMPARISON - Different perspectives, competing claims, or debate (controversy, analysis disagreement)

Analyze the articles and respond with JSON:
{{
  "story_type": "BREAKING" | "EVOLVING" | "TREND" | "COMPARISON",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation (1-2 sentences)"
}}

Consider:
- Do all articles describe the SAME specific event? → BREAKING
- Are articles providing NEW information on something already known? → EVOLVING
- Are articles about SIMILAR but SEPARATE occurrences? → TREND
- Do articles present DIFFERENT viewpoints or disagreements? → COMPARISON

JSON:"""


def parse_detection_response(response: str) -> Optional[StoryTypeResult]:
    """
    Parse LLM response into StoryTypeResult.

    Args:
        response: Raw LLM response text

    Returns:
        StoryTypeResult or None if parsing fails
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
            logger.warning("No JSON object found in detection response")
            return None

        json_str = response[start_idx:end_idx]
        data = json.loads(json_str)

        # Parse story type
        type_str = data.get("story_type", "").upper()
        try:
            story_type = StoryType[type_str]
        except KeyError:
            logger.warning(f"Unknown story type: {type_str}, defaulting to BREAKING")
            story_type = StoryType.BREAKING

        return StoryTypeResult(
            story_type=story_type,
            confidence=float(data.get("confidence", 0.7)),
            reasoning=data.get("reasoning", ""),
        )

    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(f"Failed to parse detection response: {e}")
        return None
