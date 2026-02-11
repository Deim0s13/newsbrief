"""
Quality refinement prompts.

Final pass to polish and self-critique the generated synthesis,
ensuring high quality output.
"""

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def create_refinement_prompt(
    draft_synthesis: dict[str, Any],
    story_type: str,
    article_count: int,
) -> str:
    """
    Create prompt for quality refinement pass.

    This prompt asks the LLM to critique and improve its own output,
    focusing on common quality issues.

    Args:
        draft_synthesis: The initial synthesis output
        story_type: The detected story type
        article_count: Number of source articles

    Returns:
        Prompt string for LLM
    """
    draft_json = json.dumps(draft_synthesis, indent=2)

    return f"""You are a senior editor reviewing a synthesized news story before publication.
Critique and improve this draft, focusing on quality issues.

STORY TYPE: {story_type}
SOURCE COUNT: {article_count} articles

DRAFT:
{draft_json}

QUALITY CHECKLIST - Review each item:

1. HEADLINE QUALITY
   - Is it specific and informative (not generic)?
   - Does it capture the most newsworthy element?
   - Is it 8-12 words, under 80 characters?
   - Does it avoid clickbait language?

2. SYNTHESIS QUALITY
   - Does it add value beyond any single source?
   - Is the opening sentence strong and specific?
   - Does it flow logically?
   - Is it the right length (60-150 words)?

3. KEY_POINTS QUALITY
   - Are they distinct from the synthesis (not redundant)?
   - Do they include specific details (numbers, names, dates)?
   - Do they stand alone without context?
   - Is there a mix of facts and insights?

4. WHY_IT_MATTERS QUALITY
   - Does it go beyond "this is important"?
   - Does it connect to broader trends or implications?
   - Does it consider multiple perspectives/stakeholders?
   - Is it forward-looking?

5. ENTITIES & TOPICS
   - Are the most important entities captured?
   - Are topics accurate and relevant?

TASK: Output an IMPROVED version fixing any issues found.
If the draft is already high quality, you may return it with minor polish.

Respond with the improved JSON only:
{{
  "title": "...",
  "synthesis": "...",
  "key_points": ["...", "...", "..."],
  "why_it_matters": "...",
  "topics": ["..."],
  "entities": ["..."]
}}

IMPROVED JSON:"""


def parse_refinement_response(response: str) -> Optional[dict[str, Any]]:
    """
    Parse LLM response from refinement pass.

    Args:
        response: Raw LLM response text

    Returns:
        Refined synthesis dict or None if parsing fails
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
            logger.warning("No JSON object found in refinement response")
            return None

        json_str = response[start_idx:end_idx]
        data = json.loads(json_str)

        # Validate required fields
        required = ["title", "synthesis", "key_points", "why_it_matters"]
        for field in required:
            if field not in data:
                logger.warning(f"Missing required field in refinement: {field}")
                return None

        return data

    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse refinement response: {e}")
        return None
