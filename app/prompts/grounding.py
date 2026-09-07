"""
Shared anti-hallucination / date-grounding instructions injected into every
synthesis-pipeline prompt (hotfix following a real-world quality report,
Sep 2026).

Root cause this addresses: none of the story-type-detection/analysis/
synthesis/refinement/map-reduce prompts told the model what today's actual
date is, or that it must ground strictly in the provided article text
rather than its own training-era knowledge. In practice, on real production
output, this produced two classes of error:

- Wrong year: source articles that never state a year (e.g. "this year's
  festival") got a fabricated "2024" in the synthesis title/text -- the
  model's memorized real-world knowledge of "the 2024-25 Premier League
  season" / "Venice 2024" filled the gap instead of the actual current
  date, since nothing anchored it to "now".
- Wrong facts: a real BBC Sport source article headlined "Havertz and
  Odegaard torment Chelsea" (i.e. they play for Arsenal, opposing Chelsea)
  was synthesized as "internal developments at Chelsea, where Kai Havertz
  and Martin Odegaard have elevated midfield performance" -- a direct
  contradiction of the provided source text, consistent with the model
  falling back on its outdated training-era memory of Havertz's old
  Chelsea career instead of reading what it was actually given.

This is a pure prompt-text change (no schema/migration), injected near the
top of every prompt -- after the framing sentence, before the source
content -- so it can't be missed or truncated out by downstream length
limits.
"""

from datetime import UTC, datetime
from typing import Optional


def grounding_block(
    current_date: Optional[str] = None,
    source_label: str = "the source articles below",
) -> str:
    """
    Anti-hallucination + date-grounding instruction block, meant to be
    spliced into a prompt right after its opening framing sentence.

    Args:
        current_date: Override for testing; defaults to today (UTC),
            formatted as e.g. "September 07, 2026".
        source_label: What to call the grounding material in this specific
            prompt, e.g. "the source articles below" (the common case) or
            "the group summaries and facts below" (map-reduce's reduce
            phase, which only sees condensed group summaries).
    """
    date_str = current_date or datetime.now(UTC).strftime("%B %d, %Y")
    return (
        "IMPORTANT \u2014 GROUNDING RULES:\n"
        f"- Today's actual date is {date_str}. Do not state or assume any "
        f"other date, year, or season unless it is explicitly written in "
        f"{source_label}.\n"
        f"- Base your response STRICTLY on {source_label}. Do NOT use "
        "prior/background knowledge about the people, organizations, or "
        "events mentioned, even if you recognize them \u2014 they may "
        "describe facts that are more recent than, or different from, "
        "what you remember (e.g. which team a player is on, a season's "
        "year, a company's leadership). If something isn't explicitly "
        "stated, do not fill it in from memory."
    )


def refinement_grounding_block(current_date: Optional[str] = None) -> str:
    """
    Variant for the refinement pass, which only sees the draft synthesis
    (not the original source articles) -- so beyond date-grounding, it
    must be told not to introduce any new facts while "improving" the
    draft, since it has no source text to check new claims against.
    """
    date_str = current_date or datetime.now(UTC).strftime("%B %d, %Y")
    return (
        "IMPORTANT \u2014 GROUNDING RULES:\n"
        f"- Today's actual date is {date_str}. Do not introduce or correct "
        "any date/year/season based on assumption \u2014 only touch dates "
        "already present in the draft below.\n"
        "- Do NOT introduce any new facts, names, dates, or claims that "
        "are not already present in the draft below, and do not use "
        'outside/prior knowledge to "correct" facts in it \u2014 you do '
        "not have the original source articles here, only fix wording/"
        "structure/quality issues in the existing content."
    )
