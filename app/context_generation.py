"""Post-synthesis context generation (#214/#215/#285, ADR-0023, v0.10.0).

Generates richer "why this matters"/background context for a story after
it has been synthesized, storing the result in the ``story_context``
table (migration 035) -- deliberately a **separate** LLM call from
synthesis, not blended into the core synthesis prompt, per #285's
acceptance criteria ("core story and context payloads are separable",
"provenance exists for context statements where possible").

Context types (one LLM call produces whichever subset applies, see
``_create_context_prompt``):
- ``significance`` (#214): 2-4 angles on why the story matters
  (economic/social/political/personal).
- ``background`` (#215): only requested for "complex" stories (gated in
  code, not left to the LLM to decide -- see ``_is_complex_story``),
  since the #215 acceptance criteria specifically scope this to complex
  stories, not every story.
- ``glossary`` (#215): jargon/technical terms explained inline; requested
  for every story since even a short story can use an unfamiliar term.
- ``precedent`` (#215): only requested when the story already has a
  resolved prior-story link (``continues_story_id`` / a light_rag
  anchor) -- grounded in a story this codebase has already identified as
  related, not free-text historical trivia the LLM might invent.

Design notes
------------
- Additive alongside the pre-existing ``Story.why_it_matters`` column (a
  single free-text paragraph generated inline in the core synthesis
  prompt since early versions), and alongside the existing
  ``context_anchors_json``/``continues_story_id`` "related stories"
  linking (#258/#279/#281, already surfaced via ``StoryOut``) -- this
  module does not re-implement related-story linking, it only *uses* the
  already-resolved links as grounding/provenance for ``precedent``.
- Runs on the story's own synthesis text (title + synthesis + topics +
  entities) -- NOT the raw articles -- so every context type is grounded
  in what was actually published, avoiding the "invents new facts"
  failure mode a synthesis-adjacent LLM call risks (cf. v0.9.1's
  date-grounding hotfix).
- Fire-and-forget: failures are logged and swallowed, exactly like
  ``data_extraction.maybe_extract_data_after_summary`` -- a broken
  context call must never block story generation.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Sequence, Union

from sqlalchemy.orm import Session

from .llm import get_llm_service
from .llm_output import (
    BackgroundItem,
    ContextGenerationOutput,
    GlossaryTerm,
    PrecedentItem,
    SignificanceAngle,
    parse_and_validate,
)
from .orm_models import Story, StoryContext

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_MODEL = "llama3.1:8b"
# Mirrors data_extraction.py's single-choke-point content cap convention.
MAX_SYNTHESIS_CHARS_FOR_CONTEXT = 4000
CIRCUIT_BREAKER_NAME = "context_generation"

# "Complex story" gate for the background section (#215 AC: "Complex
# stories include background section", not every story). Reuses fields
# already computed during synthesis rather than introducing a new
# config knob for a first pass -- article_count is always populated;
# complexity_score (#280, ADR-0026) is best-effort/nullable, so it's an
# OR, not an AND: either signal alone is enough to call a story complex.
_COMPLEX_ARTICLE_COUNT_THRESHOLD = 5
_COMPLEX_SCORE_THRESHOLD = 0.5

ContextItem = Union[SignificanceAngle, BackgroundItem, GlossaryTerm, PrecedentItem]


def is_context_generation_enabled() -> bool:
    """Master switch, env-only (mirrors data_extraction.py's convention).
    Default on."""
    raw = os.getenv("NEWSBRIEF_CONTEXT_GENERATION_ENABLED", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return True


def _is_complex_story(story: Story) -> bool:
    """See module docstring / threshold constants above."""
    article_count = getattr(story, "article_count", None) or 0
    if article_count >= _COMPLEX_ARTICLE_COUNT_THRESHOLD:
        return True
    complexity_score = getattr(story, "complexity_score", None)
    if complexity_score is not None and complexity_score >= _COMPLEX_SCORE_THRESHOLD:
        return True
    return False


def _story_source_story_ids(story: Story) -> List[int]:
    """
    Prior stories that already ground this story, for provenance
    (``source_story_ids``) -- the continuation match plus any light_rag
    anchors already resolved onto the story by the time this stage runs.
    Best-effort: malformed JSON yields an empty list, never raises.
    """
    ids: List[int] = []
    continues_id = getattr(story, "continues_story_id", None)
    if continues_id is not None:
        ids.append(int(continues_id))
    try:
        anchors_raw = getattr(story, "synthesis_anchors_json", None)
        if anchors_raw:
            for a in json.loads(str(anchors_raw)):
                sid = a.get("story_id") if isinstance(a, dict) else None
                if sid is not None and int(sid) not in ids:
                    ids.append(int(sid))
    except Exception as e:
        logger.debug("source_story_ids: failed to parse anchors for context: %s", e)
    return ids


def _create_context_prompt(
    title: str,
    synthesis: str,
    topics: List[str],
    entities: List[str],
    include_background: bool,
    include_precedent: bool,
) -> str:
    """Build the LLM prompt for the context generation stage."""
    body = (synthesis or "").strip()[:MAX_SYNTHESIS_CHARS_FOR_CONTEXT]
    topics_str = ", ".join(topics[:5]) if topics else "none identified"
    entities_str = ", ".join(entities[:8]) if entities else "none identified"

    sections = [
        '"significance": [ {"dimension": "economic", "text": "...", "confidence": 0.8} ]',
        '"glossary": [ {"term": "...", "definition": "...", "confidence": 0.8} ]',
    ]
    instructions = [
        "SIGNIFICANCE: identify which of these dimensions genuinely apply -- "
        "most stories only have 2-3 real angles, not all four:\n"
        "  - economic: effects on markets, jobs, costs, businesses\n"
        "  - social: effects on people, communities, daily life\n"
        "  - political: policy implications, governance, power\n"
        "  - personal: why an ordinary reader should personally care",
        "GLOSSARY: list any jargon/technical terms used in the story that an "
        "average reader may not know, with a one-sentence plain-English "
        'definition each. Return an empty list ("glossary": []) if the '
        "story uses no unfamiliar terms -- do not invent terms to fill this.",
    ]

    if include_background:
        sections.append('"background": [ {"text": "...", "confidence": 0.8} ]')
        instructions.append(
            "BACKGROUND: this is a complex, multi-faceted story. Provide 1-3 "
            "background facts/paragraphs a reader needs to understand how "
            "this situation developed, based ONLY on the STORY text below."
        )
    if include_precedent:
        sections.append(
            '"precedent": [ {"text": "...", "related_story_id": null, '
            '"confidence": 0.8} ]'
        )
        instructions.append(
            "PRECEDENT: this story is understood to relate to a previous "
            "story this system already tracked. In 1-3 sentences, explain "
            "how the current story compares to or follows on from that "
            "prior situation, based ONLY on what's in the STORY text below "
            "(do not invent details about the earlier event)."
        )

    output_format = "{{\n  " + ",\n  ".join(sections) + "\n}}"

    return f"""You are a news analysis AI. Provide context to help readers understand this already-published story.

TITLE: {title or ""}
TOPICS: {topics_str}
KEY ENTITIES: {entities_str}

STORY:
{body}

INSTRUCTIONS:
{chr(10).join(f"- {i}" for i in instructions)}

OUTPUT FORMAT (JSON only):
{output_format}

IMPORTANT:
- Base every statement ONLY on facts in the STORY text above; do not
  invent statistics, dates, names, or outcomes not present in it
- Omit any dimension/type that doesn't clearly apply -- empty lists are fine
- Output ONLY valid JSON, no additional text

JSON Response:"""


def generate_context_items(
    title: str,
    synthesis: str,
    topics: Optional[List[str]] = None,
    entities: Optional[List[str]] = None,
    include_background: bool = False,
    include_precedent: bool = False,
    model: str = DEFAULT_CONTEXT_MODEL,
) -> ContextGenerationOutput:
    """
    Generate context items for an already-synthesized story.

    Returns an empty ``ContextGenerationOutput`` (never raises) on any
    failure -- callers should treat this as best-effort, matching
    data_extraction.extract_data_points().
    """
    empty = ContextGenerationOutput()
    if not title and not synthesis:
        return empty

    llm_service = get_llm_service()
    if not llm_service.is_available():
        logger.warning("LLM service unavailable, skipping context generation")
        return empty

    if not llm_service.ensure_model(model):
        logger.warning(f"Model {model} not available for context generation, skipping")
        return empty

    try:
        prompt = _create_context_prompt(
            title,
            synthesis or "",
            topics or [],
            entities or [],
            include_background=include_background,
            include_precedent=include_precedent,
        )

        response = llm_service.backend.generate(
            model=model,
            prompt=prompt,
            options={
                "temperature": 0.2,
                "top_k": 40,
                "top_p": 0.85,
                "repeat_penalty": 1.1,
            },
        )

        raw_response = (response.get("response") or "").strip()
        if not raw_response:
            logger.warning("Empty response from LLM for context generation")
            return empty

        parsed, metrics = parse_and_validate(
            raw_response,
            ContextGenerationOutput,
            required_fields=[],
            allow_partial=True,
            circuit_breaker_name=CIRCUIT_BREAKER_NAME,
        )

        if parsed is None:
            logger.warning(
                f"Failed to parse context generation response: {metrics.error_category}"
            )
            return empty

        # Defensive: drop background/precedent even if the LLM volunteered
        # them despite not being asked (code-level gate stays authoritative).
        if not include_background:
            parsed.background = []
        if not include_precedent:
            parsed.precedent = []

        logger.info(
            f"Generated context for story '{(title or '')[:50]}...': "
            f"{len(parsed.significance)} significance, {len(parsed.background)} "
            f"background, {len(parsed.glossary)} glossary, "
            f"{len(parsed.precedent)} precedent"
        )
        return parsed

    except Exception as e:
        logger.error(f"Context generation failed: {e}")
        return empty


def _item_to_content(context_type: str, item: ContextItem) -> Dict[str, Any]:
    if context_type == "significance":
        assert isinstance(item, SignificanceAngle)
        return {"dimension": item.dimension, "text": item.text}
    if context_type == "background":
        assert isinstance(item, BackgroundItem)
        return {"text": item.text}
    if context_type == "glossary":
        assert isinstance(item, GlossaryTerm)
        return {"term": item.term, "definition": item.definition}
    if context_type == "precedent":
        assert isinstance(item, PrecedentItem)
        return {"text": item.text, "related_story_id": item.related_story_id}
    raise ValueError(f"Unknown context_type: {context_type}")


def store_story_context(
    session: Session,
    story_id: int,
    context_type: str,
    items: Sequence[ContextItem],
    source_story_ids: Optional[List[int]] = None,
) -> bool:
    """
    Replace any previously-stored context of ``context_type`` for this
    story with a fresh set (idempotent on regeneration/re-synthesis, same
    overwrite semantics as data_extraction.store_extracted_data).
    """
    try:
        session.query(StoryContext).filter(
            StoryContext.story_id == story_id,
            StoryContext.context_type == context_type,
        ).delete(synchronize_session=False)

        for item in items:
            content = _item_to_content(context_type, item)
            session.add(
                StoryContext(
                    story_id=story_id,
                    context_type=context_type,
                    content=content,
                    source_story_ids=source_story_ids or None,
                    confidence_score=item.confidence,
                    generation_method="llm",
                )
            )
        session.commit()
        logger.debug(
            f"Stored {len(items)} {context_type} context items for story {story_id}"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to store story context: {e}")
        session.rollback()
        return False


def _row_to_dict(row: StoryContext) -> Dict[str, Any]:
    content: Dict[str, Any] = row.content or {}  # type: ignore[assignment]
    return {
        "id": row.id,
        "context_type": row.context_type,
        "dimension": content.get("dimension"),
        "text": content.get("text"),
        "term": content.get("term"),
        "definition": content.get("definition"),
        "related_story_id": content.get("related_story_id"),
        "confidence_score": row.confidence_score,
        "source_story_ids": row.source_story_ids or [],
        "created_at": row.created_at,
    }


def get_story_context(session: Session, story_id: int) -> List[Dict[str, Any]]:
    """Fetch all context items for a story, highest confidence first."""
    rows = (
        session.query(StoryContext)
        .filter(StoryContext.story_id == story_id)
        .order_by(StoryContext.confidence_score.desc().nullslast(), StoryContext.id)
        .all()
    )
    return [_row_to_dict(r) for r in rows]


def maybe_generate_context_after_synthesis(
    session: Session,
    story: Story,
    model: str = DEFAULT_CONTEXT_MODEL,
) -> None:
    """
    After a story has been persisted (flushed so ``story.id`` is set),
    generate context items and store them. Failures are logged only --
    mirrors ``data_extraction.maybe_extract_data_after_summary``.
    """
    if not is_context_generation_enabled():
        return
    if story.id is None:
        logger.debug("Skipping context generation for story without id")
        return

    try:
        topics = json.loads(str(story.topics_json)) if story.topics_json else []
    except Exception:
        topics = []
    try:
        entities = json.loads(str(story.entities_json)) if story.entities_json else []
    except Exception:
        entities = []

    source_ids = _story_source_story_ids(story)
    include_background = _is_complex_story(story)
    include_precedent = bool(source_ids)

    try:
        output = generate_context_items(
            str(story.title or ""),
            str(story.synthesis or ""),
            topics=topics,
            entities=entities,
            include_background=include_background,
            include_precedent=include_precedent,
            model=model,
        )

        story_id = int(story.id)  # type: ignore[arg-type]
        if output.significance:
            store_story_context(session, story_id, "significance", output.significance)
        if output.background:
            store_story_context(session, story_id, "background", output.background)
        if output.glossary:
            store_story_context(session, story_id, "glossary", output.glossary)
        if output.precedent:
            store_story_context(
                session,
                story_id,
                "precedent",
                output.precedent,
                source_story_ids=source_ids or None,
            )
    except Exception as e:
        logger.warning(
            "Context generation failed for story %s (story row still saved): %s",
            story.id,
            e,
            exc_info=True,
        )
