"""Tests for anti-hallucination / date-grounding instructions injected into
every synthesis-pipeline prompt (hotfix, Sep 2026).

Regression coverage for a real production quality issue: source articles
with no explicit year got a fabricated "2024" in the synthesis, and a
source article was misread against the model's outdated training-era
knowledge (see app/prompts/grounding.py's module docstring for the full
writeup). None of these prompt-building functions previously told the
model what today's actual date is or that it must ground strictly in the
provided content -- these tests assert that every one of them now does.
"""

from app.prompts import StoryType
from app.prompts.analysis import create_analysis_prompt
from app.prompts.detection import create_detection_prompt
from app.prompts.grounding import grounding_block, refinement_grounding_block
from app.prompts.map_reduce import (
    create_group_summary_prompt,
    create_hierarchical_tier1_prompt,
    create_hierarchical_tier2_prompt,
    create_reduce_prompt,
)
from app.prompts.refinement import create_refinement_prompt
from app.prompts.synthesis import get_deep_synthesis_prompt, get_synthesis_prompt

_SAMPLE_ARTICLES = [{"title": "Test article", "summary": "A test summary."}]
_SAMPLE_ANALYSIS = None  # populated below to avoid importing AnalysisResult twice


def _sample_analysis():
    from app.prompts import AnalysisResult

    return AnalysisResult(
        timeline=[],
        core_facts=[],
        tensions=[],
        key_players=[],
        gaps=[],
        narrative_thread="A unifying theme.",
    )


class TestGroundingBlock:
    def test_default_mentions_source_articles(self):
        block = grounding_block()
        assert "source articles" in block
        assert "GROUNDING RULES" in block

    def test_current_date_override(self):
        block = grounding_block(current_date="January 01, 2030")
        assert "January 01, 2030" in block

    def test_default_uses_todays_date(self):
        from datetime import UTC, datetime

        block = grounding_block()
        expected = datetime.now(UTC).strftime("%B %d, %Y")
        assert expected in block

    def test_custom_source_label(self):
        block = grounding_block(source_label="the group summaries and facts below")
        assert "the group summaries and facts below" in block
        # No leftover artifacts from string surgery (e.g. duplicated "the the")
        assert "the the" not in block

    def test_instructs_against_outside_knowledge(self):
        block = grounding_block()
        assert (
            "prior/background knowledge" in block.lower() or "outside" in block.lower()
        )


class TestRefinementGroundingBlock:
    def test_mentions_draft_not_articles(self):
        block = refinement_grounding_block()
        assert "draft" in block
        assert "GROUNDING RULES" in block

    def test_instructs_no_new_facts(self):
        block = refinement_grounding_block()
        assert "new facts" in block.lower() or "not already present" in block.lower()

    def test_current_date_override(self):
        block = refinement_grounding_block(current_date="January 01, 2030")
        assert "January 01, 2030" in block


class TestEveryPromptFunctionIsGrounded:
    """Every synthesis-pipeline prompt-building function must include a
    grounding block -- this is a flat regression list so a new prompt
    function added later without grounding fails loudly here."""

    def test_analysis_prompt(self):
        prompt = create_analysis_prompt(_SAMPLE_ARTICLES, "BREAKING")
        assert "GROUNDING RULES" in prompt

    def test_detection_prompt(self):
        prompt = create_detection_prompt(_SAMPLE_ARTICLES)
        assert "GROUNDING RULES" in prompt

    def test_synthesis_prompt(self):
        prompt = get_synthesis_prompt(
            StoryType.BREAKING, _sample_analysis(), _SAMPLE_ARTICLES
        )
        assert "GROUNDING RULES" in prompt

    def test_deep_synthesis_prompt(self):
        prompt = get_deep_synthesis_prompt(
            StoryType.COMPARISON, _sample_analysis(), _SAMPLE_ARTICLES
        )
        assert "GROUNDING RULES" in prompt

    def test_refinement_prompt(self):
        prompt = create_refinement_prompt({"title": "t"}, "BREAKING", 2)
        assert "GROUNDING RULES" in prompt

    def test_group_summary_prompt(self):
        prompt = create_group_summary_prompt(_SAMPLE_ARTICLES, 1, 2)
        assert "GROUNDING RULES" in prompt

    def test_reduce_prompt(self):
        prompt = create_reduce_prompt(
            [{"summary": "s", "key_facts": [], "entities": []}], "BREAKING", 5
        )
        assert "GROUNDING RULES" in prompt

    def test_hierarchical_tier1_prompt(self):
        prompt = create_hierarchical_tier1_prompt(_SAMPLE_ARTICLES, 1, 2)
        assert "GROUNDING RULES" in prompt

    def test_hierarchical_tier2_prompt(self):
        prompt = create_hierarchical_tier2_prompt(
            [
                {
                    "headline": "h",
                    "summary": "s",
                    "entities": [],
                    "key_facts": [],
                    "timeline_events": [],
                }
            ],
            10,
        )
        assert "GROUNDING RULES" in prompt
