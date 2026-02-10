"""
Map-reduce synthesis prompts for large article clusters.

These prompts handle multi-stage synthesis where large clusters
are broken into groups, summarized separately, and then combined.

Used when clusters have 9+ articles that exceed single-pass context limits.
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def create_group_summary_prompt(
    article_summaries: list[dict[str, str]],
    group_number: int,
    total_groups: int,
    story_type: str = "BREAKING",
) -> str:
    """
    Create prompt for summarizing a group of articles (MAP phase).

    This produces a condensed summary that preserves key information
    for the final synthesis pass.

    Args:
        article_summaries: List of dicts with 'title' and 'summary' keys
        group_number: Which group this is (1-indexed)
        total_groups: Total number of groups being processed
        story_type: The detected story type

    Returns:
        Prompt string for LLM
    """
    articles_text = "\n\n".join(
        f"ARTICLE {i + 1}:\nTitle: {a.get('title', 'Untitled')}\n"
        f"{a.get('summary', '')[:400]}"
        for i, a in enumerate(article_summaries)
    )

    return f"""You are condensing a group of related news articles into a summary for further synthesis.
This is group {group_number} of {total_groups} groups covering a {story_type} story.

{articles_text}

Create a condensed summary that preserves:
1. Key facts and events mentioned
2. Important entities (companies, people, products)
3. Any unique information not likely in other groups
4. Timeline information if present

Respond with JSON:
{{
  "summary": "2-4 sentence condensed summary of key information",
  "key_facts": ["Fact 1", "Fact 2", "Fact 3"],
  "entities": ["Entity1", "Entity2", "Entity3"],
  "unique_angle": "What makes this group's coverage distinct (if anything)"
}}

JSON:"""


def parse_group_summary_response(response: str) -> Optional[Dict[str, Any]]:
    """
    Parse LLM response from group summary.

    Args:
        response: Raw LLM response text

    Returns:
        Dict with summary, key_facts, entities, unique_angle or None
    """
    try:
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
            logger.warning("No JSON object found in group summary response")
            return None

        json_str = response[start_idx:end_idx]
        data = json.loads(json_str)

        return {
            "summary": data.get("summary", ""),
            "key_facts": data.get("key_facts", [])[:5],
            "entities": data.get("entities", [])[:5],
            "unique_angle": data.get("unique_angle", ""),
        }

    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse group summary response: {e}")
        return None


def create_reduce_prompt(
    group_summaries: list[dict[str, Any]],
    story_type: str,
    total_articles: int,
) -> str:
    """
    Create prompt for combining group summaries (REDUCE phase).

    This takes the condensed summaries from all groups and produces
    the final synthesis.

    Args:
        group_summaries: List of parsed group summary dicts
        story_type: The detected story type
        total_articles: Total number of original articles

    Returns:
        Prompt string for final synthesis
    """
    # Format group summaries
    groups_text = ""
    all_entities = set()
    all_facts = []

    for i, group in enumerate(group_summaries, 1):
        groups_text += f"\nGROUP {i} SUMMARY:\n{group.get('summary', 'No summary')}\n"
        if group.get("unique_angle"):
            groups_text += f"Unique angle: {group['unique_angle']}\n"

        # Collect entities and facts
        all_entities.update(group.get("entities", []))
        all_facts.extend(group.get("key_facts", []))

    # Deduplicate facts (rough dedup by checking overlap)
    unique_facts: List[str] = []
    for fact in all_facts:
        is_duplicate = any(
            _text_similarity(fact, existing) > 0.7 for existing in unique_facts
        )
        if not is_duplicate:
            unique_facts.append(fact)

    facts_text = "\n".join(f"• {f}" for f in unique_facts[:10])
    entities_text = ", ".join(sorted(all_entities)[:10])

    return f"""You are a senior news editor synthesizing coverage from {total_articles} articles
organized into {len(group_summaries)} thematic groups. Story type: {story_type}

GROUP SUMMARIES:
{groups_text}

CONSOLIDATED FACTS:
{facts_text}

KEY ENTITIES: {entities_text}

Write the final synthesis. This should be a cohesive narrative that:
1. Leads with the most significant development
2. Integrates information from all groups
3. Maintains consistency across potentially different angles
4. Provides context appropriate to {total_articles} sources covering this story

Respond with valid JSON:
{{
  "title": "Compelling headline (8-12 words, under 80 characters)",
  "synthesis": "2-4 sentence narrative (60-150 words)",
  "key_points": ["Point 1", "Point 2", "Point 3", "Point 4"],
  "why_it_matters": "2-3 sentences on significance",
  "topics": ["Topic1", "Topic2"],
  "entities": ["Entity1", "Entity2", "Entity3"]
}}

JSON:"""


def _text_similarity(text1: str, text2: str) -> float:
    """Simple word overlap similarity for deduplication."""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def create_hierarchical_tier1_prompt(
    article_summaries: list[dict[str, str]],
    tier_number: int,
    total_tiers: int,
) -> str:
    """
    Create prompt for tier 1 of hierarchical synthesis.

    Tier 1 produces detailed summaries from article groups,
    which will be further condensed in tier 2.

    Args:
        article_summaries: Articles in this tier 1 group
        tier_number: Which tier 1 group (1-indexed)
        total_tiers: Total tier 1 groups

    Returns:
        Prompt string
    """
    articles_text = "\n\n".join(
        f"ARTICLE {i + 1}:\nTitle: {a.get('title', 'Untitled')}\n"
        f"{a.get('summary', '')[:300]}"
        for i, a in enumerate(article_summaries)
    )

    return f"""Summarize this cluster of {len(article_summaries)} related articles.
This is cluster {tier_number} of {total_tiers} being processed for a large story.

{articles_text}

Create a detailed summary preserving all important information:

Respond with JSON:
{{
  "headline": "Brief descriptive headline for this cluster",
  "summary": "3-5 sentence detailed summary",
  "key_facts": ["Fact 1", "Fact 2", "Fact 3", "Fact 4"],
  "entities": ["Entity1", "Entity2", "Entity3"],
  "timeline_events": ["Event 1 (with date if known)", "Event 2"]
}}

JSON:"""


def create_hierarchical_tier2_prompt(
    tier1_summaries: list[dict[str, Any]],
    total_articles: int,
) -> str:
    """
    Create prompt for tier 2 of hierarchical synthesis.

    Tier 2 combines tier 1 summaries into the final synthesis.

    Args:
        tier1_summaries: Summaries from tier 1 processing
        total_articles: Total original articles

    Returns:
        Prompt string for final synthesis
    """
    # Compile tier 1 information
    summaries_text = ""
    all_entities = set()
    all_facts = []
    all_timeline = []

    for i, t1 in enumerate(tier1_summaries, 1):
        summaries_text += f"\nCLUSTER {i}: {t1.get('headline', 'Untitled')}\n"
        summaries_text += f"{t1.get('summary', '')}\n"

        all_entities.update(t1.get("entities", []))
        all_facts.extend(t1.get("key_facts", []))
        all_timeline.extend(t1.get("timeline_events", []))

    # Deduplicate
    unique_facts = list(dict.fromkeys(all_facts))[:12]
    unique_timeline = list(dict.fromkeys(all_timeline))[:6]

    return f"""You are synthesizing a major story covered by {total_articles} articles.
The articles have been pre-processed into {len(tier1_summaries)} thematic clusters.

CLUSTER SUMMARIES:
{summaries_text}

KEY FACTS ACROSS ALL CLUSTERS:
{chr(10).join(f'• {f}' for f in unique_facts)}

TIMELINE:
{chr(10).join(f'• {t}' for t in unique_timeline)}

KEY ENTITIES: {', '.join(sorted(all_entities)[:12])}

Write a comprehensive synthesis that:
1. Captures the full scope of this {total_articles}-article story
2. Weaves together different angles from each cluster
3. Maintains accuracy by sticking to confirmed facts
4. Provides appropriate context for a story of this magnitude

Respond with valid JSON:
{{
  "title": "Compelling headline capturing the full story",
  "synthesis": "3-5 sentence comprehensive narrative (100-200 words)",
  "key_points": ["Point 1", "Point 2", "Point 3", "Point 4", "Point 5"],
  "why_it_matters": "3-4 sentences on broader significance",
  "topics": ["Topic1", "Topic2"],
  "entities": ["Entity1", "Entity2", "Entity3", "Entity4", "Entity5"]
}}

JSON:"""
