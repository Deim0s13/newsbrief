"""Rule-based cross-source/cross-version data point tracking (#213, ADR-0023, v0.9.3).

Reduced scope vs. the original issue #213: "aggregate statistics across
ALL stories" would need a corpus-wide subject-matching index this codebase
has no infrastructure for (no canonical "topic of this statistic" label
anywhere). Scoped down at the v0.9.3 proposal checkpoint to two cheaper,
well-bounded checks instead:

1. ``find_data_conflicts`` -- within ONE story's own extracted_data
   (already bounded to that story's supporting articles), flag when two
   different articles report a different value for what looks like the
   same statistic/amount.
2. ``find_data_changes`` -- when a story continues an earlier one
   (``continues_story_id``, v0.8.6 historical linking -- already a
   same-subject link, unlike a corpus-wide search), diff the two
   stories' extracted_data for "previously reported as X, now Y".

No LLM call for either -- "same subject" is approximated by word-overlap
(Jaccard similarity) between each data point's ``context`` string, the
same style of simple, explainable heuristic as app/perspective_gaps.py and
app/story_events.py's rule-based classification. This is intentionally
coarse: it will miss same-subject pairs phrased very differently, and can
occasionally false-positive on two unrelated stats that happen to share
several context words. Acceptable for a first pass because both outputs
are advisory annotations on already-displayed data points, not
gatekeeping/hidden decisions -- a wrong flag is just a slightly wrong
badge, not a dropped fact.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from typing import Set as SetType

from sqlalchemy.orm import Session

# Data types for which comparing "value" numerically/textually makes sense.
# quote/claim/date are not tracked -- there's no useful notion of a quote
# or claim "changing" the way a number does, and comparing dates by word
# overlap of surrounding context is unreliable.
_TRACKABLE_TYPES = {"statistic", "amount"}

# Small, self-contained stopword list (not imported from stories.py's
# `_extract_keywords` -- that's a private helper in another module, and this
# needs a much shorter list than keyword-extraction-for-clustering does).
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "that",
    "the",
    "to",
    "was",
    "were",
    "will",
    "with",
    "this",
}

# Jaccard similarity threshold on context word overlap to treat two data
# points as "about the same subject". Deliberately conservative (higher
# false-negative rate is safer than false-positive here, see module
# docstring) -- tuned by eye against the checkpoint's real extraction
# samples, not a formal calibration.
_SUBJECT_SIMILARITY_THRESHOLD = 0.34


def _context_words(text: Optional[str]) -> SetType[str]:
    if not text:
        return set()
    words = re.findall(r"\b[a-z0-9]+\b", text.lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def _same_subject(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Word-overlap heuristic -- see module docstring."""
    words_a = _context_words(a.get("context"))
    words_b = _context_words(b.get("context"))
    if not words_a or not words_b:
        return False
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    if union == 0:
        return False
    return (intersection / union) >= _SUBJECT_SIMILARITY_THRESHOLD


def find_data_conflicts(data_points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Within a single story's aggregated extracted_data (see
    app.data_extraction.get_extracted_data_for_story), find pairs of
    statistic/amount data points from DIFFERENT articles that appear to be
    about the same subject but report a different value.

    Returns a list of conflict groups:
        {"data_type", "reported_values": [{"value","unit","article_id"}, ...]}

    Note: the key is "reported_values", not "values" -- Jinja2 attribute
    access on a dict tries ``getattr()`` first, and ``dict`` has a real
    ``.values()`` method that would shadow a ``"values"`` key in any
    template using ``conflict.values`` (see app/templates/story_detail.html).

    Each data point can appear in at most one conflict group (first match
    wins) -- this is a simple advisory signal, not a full clustering pass.
    """
    conflicts: List[Dict[str, Any]] = []
    used_ids: set = set()

    trackable = [
        p
        for p in data_points
        if p.get("data_type") in _TRACKABLE_TYPES and p.get("context")
    ]

    for i, point in enumerate(trackable):
        if point["id"] in used_ids:
            continue
        group = [point]
        for other in trackable[i + 1 :]:
            if other["id"] in used_ids:
                continue
            if other.get("data_type") != point.get("data_type"):
                continue
            if other.get("article_id") == point.get("article_id"):
                continue  # same article can't "conflict" with itself
            if other.get("value") == point.get("value"):
                continue  # same value isn't a conflict, it's corroboration
            if _same_subject(point, other):
                group.append(other)

        if len(group) > 1:
            for p in group:
                used_ids.add(p["id"])
            conflicts.append(
                {
                    "data_type": point["data_type"],
                    # First point's context as the display label -- good
                    # enough for a one-line UI hint, not meant to be a
                    # canonical subject name.
                    "context": point.get("context"),
                    "reported_values": [
                        {
                            "value": p.get("value"),
                            "unit": p.get("unit"),
                            "article_id": p.get("article_id"),
                        }
                        for p in group
                    ],
                }
            )

    return conflicts


def find_data_changes(
    session: Session, story_id: int, continues_story_id: Optional[int]
) -> List[Dict[str, Any]]:
    """
    If this story continues an earlier one (``continues_story_id``, v0.8.6),
    diff their extracted_data for statistic/amount points about the same
    subject with a different value -- "previously reported as X, now Y".

    Returns [] if there's no continuation link, or no trackable points
    matched -- the common case, not a failure.
    """
    if not continues_story_id:
        return []

    from .data_extraction import get_extracted_data_for_story

    current_points = [
        p
        for p in get_extracted_data_for_story(session, story_id)
        if p.get("data_type") in _TRACKABLE_TYPES and p.get("context")
    ]
    if not current_points:
        return []

    previous_points = [
        p
        for p in get_extracted_data_for_story(session, continues_story_id)
        if p.get("data_type") in _TRACKABLE_TYPES and p.get("context")
    ]
    if not previous_points:
        return []

    changes: List[Dict[str, Any]] = []
    matched_previous_ids: set = set()

    for current in current_points:
        for previous in previous_points:
            if previous["id"] in matched_previous_ids:
                continue
            if previous.get("data_type") != current.get("data_type"):
                continue
            if previous.get("value") == current.get("value"):
                continue  # unchanged -- nothing to report
            if _same_subject(current, previous):
                matched_previous_ids.add(previous["id"])
                changes.append(
                    {
                        "data_type": current["data_type"],
                        "context": current.get("context"),
                        "previous_value": previous.get("value"),
                        "current_value": current.get("value"),
                        "unit": current.get("unit") or previous.get("unit"),
                        "previous_story_id": continues_story_id,
                        "current_article_id": current.get("article_id"),
                    }
                )
                break  # each current point matches at most one previous point

    return changes
