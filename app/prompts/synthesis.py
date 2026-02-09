"""
Type-specific synthesis prompts.

Different story types require different narrative approaches.
These prompts are tailored to produce the most appropriate
synthesis for each pattern.
"""

from . import AnalysisResult, StoryType


def get_synthesis_prompt(
    story_type: StoryType,
    analysis: AnalysisResult,
    article_summaries: list[dict[str, str]],
) -> str:
    """
    Get the appropriate synthesis prompt for the story type.

    Args:
        story_type: The detected story pattern
        analysis: Results from chain-of-thought analysis
        article_summaries: Original article data

    Returns:
        Prompt string for synthesis LLM call
    """
    # Format analysis context
    analysis_context = _format_analysis_context(analysis)

    # Format article context (abbreviated)
    articles_context = "\n".join(
        f"- {a.get('title', 'Untitled')[:80]}" for a in article_summaries[:8]
    )

    # Get type-specific instructions
    type_instructions = _get_type_instructions(story_type)

    return f"""You are a senior news editor at a respected publication. Your task is to synthesize multiple source articles into a single, compelling story.

STORY TYPE: {story_type.value.upper()}
{type_instructions}

ANALYSIS FROM SOURCES:
{analysis_context}

SOURCE ARTICLES:
{articles_context}

WRITING GUIDELINES:
1. HEADLINE (title): 8-12 words, under 80 characters
   - Capture the narrative thread
   - Use active voice, present tense
   - Include the most newsworthy element
   - Avoid clickbait or sensationalism

2. SYNTHESIS: 2-4 sentences (60-150 words)
   - Lead with the most significant development
   - Connect information across sources
   - Build toward the "so what"
   - Write for informed readers who want depth

3. KEY_POINTS: 3-5 bullet points
   - Mix of facts AND insights (not just restating synthesis)
   - Each point should stand alone
   - Include specific details: numbers, names, dates
   - Avoid generic statements

4. WHY_IT_MATTERS: 2-3 sentences
   - Go beyond "this is important because..."
   - Connect to broader industry/societal trends
   - Consider multiple stakeholder perspectives
   - Include forward-looking implications

5. TOPICS: 1-3 relevant tags (e.g., "AI/ML", "Cloud", "Security", "Business")

6. ENTITIES: 3-7 key entities (companies, products, people)
   - Prioritize entities central to the story
   - Include entities mentioned across multiple sources

Respond with valid JSON only:
{{
  "title": "Compelling headline here",
  "synthesis": "Your synthesized narrative...",
  "key_points": ["Point 1", "Point 2", "Point 3"],
  "why_it_matters": "Significance and implications...",
  "topics": ["Topic1", "Topic2"],
  "entities": ["Entity1", "Entity2", "Entity3"]
}}

JSON:"""


def _format_analysis_context(analysis: AnalysisResult) -> str:
    """Format analysis results for inclusion in synthesis prompt."""
    sections = []

    if analysis.narrative_thread:
        sections.append(f"NARRATIVE THREAD: {analysis.narrative_thread}")

    if analysis.core_facts:
        facts = "\n".join(f"  • {f}" for f in analysis.core_facts)
        sections.append(f"CORE FACTS (confirmed across sources):\n{facts}")

    if analysis.timeline:
        timeline = "\n".join(f"  • {t}" for t in analysis.timeline)
        sections.append(f"TIMELINE:\n{timeline}")

    if analysis.tensions:
        tensions = "\n".join(f"  • {t}" for t in analysis.tensions)
        sections.append(f"TENSIONS/DISAGREEMENTS:\n{tensions}")

    if analysis.key_players:
        players = "\n".join(f"  • {p}" for p in analysis.key_players)
        sections.append(f"KEY PLAYERS:\n{players}")

    if analysis.gaps:
        gaps = "\n".join(f"  • {g}" for g in analysis.gaps)
        sections.append(f"INFORMATION GAPS:\n{gaps}")

    return "\n\n".join(sections)


def _get_type_instructions(story_type: StoryType) -> str:
    """Get type-specific writing instructions."""

    instructions = {
        StoryType.BREAKING: """
BREAKING NEWS APPROACH:
- Lead with the core news event
- Emphasize the 5 W's: Who, What, When, Where, Why
- Focus on confirmed facts, note what's still developing
- Synthesis should answer: "What just happened?"
- Why_it_matters should focus on immediate impact""",
        StoryType.EVOLVING: """
EVOLVING STORY APPROACH:
- Lead with the NEW development
- Briefly contextualize with what was already known
- Highlight what has changed or been revealed
- Synthesis should answer: "What's different now?"
- Why_it_matters should focus on trajectory and what to watch""",
        StoryType.TREND: """
TREND STORY APPROACH:
- Lead with the pattern being observed
- Use specific examples from sources to illustrate
- Connect disparate events into a coherent narrative
- Synthesis should answer: "What pattern is emerging?"
- Why_it_matters should focus on where this is heading""",
        StoryType.COMPARISON: """
COMPARISON/DEBATE APPROACH:
- Present multiple perspectives fairly
- Clearly attribute claims to their sources
- Highlight areas of agreement and disagreement
- Synthesis should answer: "What are the competing views?"
- Why_it_matters should help readers understand the stakes""",
    }

    return instructions.get(story_type, instructions[StoryType.BREAKING])
