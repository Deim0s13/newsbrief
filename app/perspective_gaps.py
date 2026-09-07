"""
Rule-based viewpoint gap detection (#229, ADR-0023, v0.9.1).

No LLM call -- operates purely on the per-article perspective tags already
cached by app.entities (#203) for a story's cluster of articles. Flags when
a cluster leans entirely to one side of a known opposing pair (stakeholder,
political leaning, regional scope) with zero representation of the other
side -- a signal (not proof) that the story's coverage may be one-sided.

Deliberately narrower than issue #229's original story-type framing
("political stories: check left/center/right coverage", "science: expert
vs public health") -- there is no story-type/domain classifier in this
codebase, and some of the issue's example categories (e.g. an "expert"
stakeholder) don't exist in PerspectiveOutput's fixed enums (see
app/llm_output.py). This operates only on the 3 dimensions that are
actually populated: stakeholder, political_leaning, regional. ``tone`` is
intentionally excluded -- it describes framing/sentiment, not a
missing-viewpoint signal.

Output shape is adapted from ADR-0023's example (which included an
"expected_sources" field, e.g. ["Local news"]) -- a rule-based check has no
way to know what a missing source's coverage would actually say, so that
field is dropped in favor of "present"/"missing" describing what was
(and wasn't) observed in this cluster.
"""

from typing import Any, Dict, List, Optional, Sequence

from .entities import ArticlePerspective

# Minimum number of articles carrying a value in a given dimension before
# that dimension is evaluated at all -- avoids flagging a gap off a single
# opinionated article (issue #229 acceptance criteria: "not over-sensitive").
MIN_ARTICLES_FOR_DIMENSION = 2

# (dimension attr on ArticlePerspective, side A values, side B values,
#  side A label, side B label)
_GAP_DIMENSIONS: Sequence[tuple] = (
    (
        "stakeholder",
        {"business"},
        {"consumer", "labor"},
        "business",
        "consumer or labor",
    ),
    (
        "political_leaning",
        {"left", "center-left"},
        {"right", "center-right"},
        "left-leaning",
        "right-leaning",
    ),
    ("regional", {"local"}, {"international"}, "local", "international"),
)


def _check_dimension_gap(
    values: List[str],
    side_a: set,
    side_b: set,
    label_a: str,
    label_b: str,
    dimension: str,
) -> Optional[Dict[str, Any]]:
    """
    One dimension's gap check: gap iff one side has >=1 value and the other
    side has none, and there's enough signal overall to bother (see
    MIN_ARTICLES_FOR_DIMENSION). Values outside both sides (e.g. a
    "regulatory"/"environmental" stakeholder, or a "center" political
    leaning) count toward the signal threshold but don't count as either
    side -- they're treated as neutral, not as filling a gap.
    """
    if len(values) < MIN_ARTICLES_FOR_DIMENSION:
        return None

    present_a = sorted({v for v in values if v in side_a})
    present_b = sorted({v for v in values if v in side_b})

    if present_a and not present_b:
        return {
            "dimension": dimension,
            "present": present_a,
            "missing": f"{label_b} viewpoint",
        }
    if present_b and not present_a:
        return {
            "dimension": dimension,
            "present": present_b,
            "missing": f"{label_a} viewpoint",
        }
    return None


def detect_perspective_gaps(
    perspectives: List[Optional[ArticlePerspective]],
) -> List[Dict[str, Any]]:
    """
    Detect one-sided perspective coverage across a story's cluster.

    Args:
        perspectives: Per-article ArticlePerspective values for the
            cluster (e.g. ``list(get_article_perspectives(...).values())``
            from app.entities). None/missing entries are ignored -- an
            article that hasn't been perspective-extracted yet simply
            contributes no signal, it isn't treated as "no perspective".

    Returns:
        List of gap dicts, each ``{"dimension": ..., "present": [...],
        "missing": "..."}``. Empty list is the common/expected case --
        most clusters either have no applicable perspective at all, or
        already have some balance across sides.
    """
    applicable = [p for p in perspectives if p is not None and p.applicable]
    if not applicable:
        return []

    gaps: List[Dict[str, Any]] = []
    for dimension, side_a, side_b, label_a, label_b in _GAP_DIMENSIONS:
        values = [
            getattr(p, dimension) for p in applicable if getattr(p, dimension, None)
        ]
        gap = _check_dimension_gap(values, side_a, side_b, label_a, label_b, dimension)
        if gap:
            gaps.append(gap)

    return gaps
