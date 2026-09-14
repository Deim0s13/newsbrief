"""Structured data extraction from articles using LLM (#211, ADR-0023, v0.9.3).

Pulls discrete data points -- statistics, quotes, claims, dates, amounts --
out of an article's full content and stores them in the ``extracted_data``
table (migration 034) for display on the story detail page (#212) and
cross-story aggregation (#213).

Design notes
------------
- Runs on the article's full ``content``, not the (lossy) AI summary --
  the whole point is to preserve specific numbers/quotes/attributions that
  summarization compresses away. This is a **separate** LLM call from
  summarization/entity extraction, not piggybacked onto either: unlike
  v0.9.1's perspective-on-entities piggyback, cramming extraction into an
  existing prompt/schema would couple its failure modes and prompt-tuning
  cycles to summarization or clustering, which this milestone deliberately
  avoids repeating (see the v0.9.2 ADR-0023 checkpoint notes).
- Fire-and-forget: extraction failures are logged and swallowed, exactly
  like ``item_embeddings.maybe_embed_item_after_summary`` -- a broken
  extraction call must never block summarize/cluster/synthesize.
- No ``location`` data_type: the existing NER pipeline (entities.py)
  already extracts location names; true geographic tagging has no
  supporting infrastructure and is deferred to v0.11.2 (see the migration
  034 docstring for the full rationale).
- Content is capped at ``MAX_EXTRACTION_CONTENT_CHARS`` per call (no
  chunking/map-reduce). Known gap: very long articles may have data points
  beyond the truncation window missed. Full multi-chunk extraction
  (mirroring llm.py's summary chunking) is future work if this turns out
  to matter in practice.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .llm import get_llm_service
from .llm_output import ExtractedDataItem, ExtractedDataOutput, parse_and_validate
from .orm_models import ExtractedData, StoryArticle

logger = logging.getLogger(__name__)

DEFAULT_EXTRACTION_MODEL = "llama3.1:8b"
# Mirrors embedding_service.MAX_EMBED_TEXT_CHARS's single-choke-point-cap
# convention; keeps the prompt within a safe context budget without full
# chunking (see module docstring "Known gap").
MAX_EXTRACTION_CONTENT_CHARS = 6000
CIRCUIT_BREAKER_NAME = "data_extraction"


def is_data_extraction_enabled() -> bool:
    """Master switch, env-only (no model_config.json knob yet -- this is a
    new, smaller-blast-radius feature than embeddings; add one later if
    needed). Default on."""
    raw = os.getenv("NEWSBRIEF_DATA_EXTRACTION_ENABLED", "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    return True


def _create_extraction_prompt(title: str, content: str) -> str:
    """Build the LLM prompt for structured data extraction."""
    body = (content or "").strip()[:MAX_EXTRACTION_CONTENT_CHARS]
    return f"""You are a data extraction AI. Extract key structured data points from this article.

TITLE: {title or ""}

ARTICLE:
{body}

INSTRUCTIONS:
Extract notable data points of these types ONLY:
- statistic: numbers, percentages, rates, metrics (e.g. "unemployment fell to 3.4%")
- quote: direct quotes with a named speaker/attribution
- claim: specific factual assertions worth verifying (e.g. "the policy will create 10,000 jobs")
- date: specific important dates or deadlines mentioned in the article
- amount: financial figures, quantities, counts (e.g. "$2.3 billion", "50,000 units")

OUTPUT FORMAT (JSON only):
{{
  "data_points": [
    {{
      "data_type": "statistic",
      "value": "3.4%",
      "context": "unemployment rate fell to its lowest level in a decade",
      "attribution": null,
      "unit": "percent",
      "confidence": 0.9
    }}
  ]
}}

IMPORTANT:
- Only include data points CLEARLY stated in the article, not inferred
- For quotes, "attribution" MUST be the named speaker (e.g. "Jane Smith, CEO"); skip unattributed quotes
- "context" is the surrounding sentence, for verification -- keep it short
- Use null for "attribution"/"unit" when not applicable
- For amounts/statistics with a currency symbol, copy the symbol EXACTLY as
  written in the article (e.g. keep "£250" as "£250" -- do NOT convert or
  normalize it to "$250" or any other currency)
- Limit to 10 data points maximum, prioritizing the most notable
- Output ONLY valid JSON, no additional text

JSON Response:"""


def extract_data_points(
    title: str,
    content: str,
    model: str = DEFAULT_EXTRACTION_MODEL,
) -> List[ExtractedDataItem]:
    """
    Extract structured data points from an article using the LLM.

    Returns an empty list (never raises) on any failure -- callers should
    treat this as best-effort, matching entities.py's extract_entities().
    """
    if not title and not content:
        return []

    llm_service = get_llm_service()
    if not llm_service.is_available():
        logger.warning("LLM service unavailable, skipping data extraction")
        return []

    if not llm_service.ensure_model(model):
        logger.warning(f"Model {model} not available for data extraction, skipping")
        return []

    try:
        prompt = _create_extraction_prompt(title, content or "")

        response = llm_service.backend.generate(
            model=model,
            prompt=prompt,
            options={
                "temperature": 0.1,  # Low temperature for factual extraction
                "top_k": 40,
                "top_p": 0.8,
                "repeat_penalty": 1.1,
            },
        )

        raw_response = (response.get("response") or "").strip()
        if not raw_response:
            logger.warning("Empty response from LLM for data extraction")
            return []

        parsed, metrics = parse_and_validate(
            raw_response,
            ExtractedDataOutput,
            required_fields=[],
            allow_partial=True,
            circuit_breaker_name=CIRCUIT_BREAKER_NAME,
        )

        if parsed is None:
            logger.warning(
                f"Failed to parse data extraction response: {metrics.error_category}"
            )
            return []

        logger.info(
            f"Extracted {len(parsed.data_points)} data points from article: "
            f"{(title or '')[:50]}..."
        )
        return parsed.data_points

    except Exception as e:
        logger.error(f"Data extraction failed: {e}")
        return []


def store_extracted_data(
    session: Session,
    article_id: int,
    data_points: List[ExtractedDataItem],
    model: str = DEFAULT_EXTRACTION_MODEL,
) -> bool:
    """
    Replace any previously-stored data points for this article with a fresh
    set (idempotent on re-summarize/re-extraction, same as entity cache
    overwrite semantics).
    """
    try:
        session.query(ExtractedData).filter(
            ExtractedData.article_id == article_id
        ).delete(synchronize_session=False)

        for point in data_points:
            data_value: Dict[str, Any] = {"text": point.value}
            if point.unit:
                data_value["unit"] = point.unit
            if point.attribution:
                data_value["speaker"] = point.attribution

            session.add(
                ExtractedData(
                    article_id=article_id,
                    data_type=point.data_type,
                    data_value=data_value,
                    context=point.context,
                    confidence_score=point.confidence,
                    extraction_method="llm",
                )
            )
        session.commit()
        logger.debug(
            f"Stored {len(data_points)} extracted data points for article {article_id}"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to store extracted data: {e}")
        session.rollback()
        return False


def _row_to_dict(row: ExtractedData) -> Dict[str, Any]:
    value: Dict[str, Any] = row.data_value or {}  # type: ignore[assignment]
    return {
        "id": row.id,
        "data_type": row.data_type,
        "value": value.get("text"),
        "unit": value.get("unit"),
        "attribution": value.get("speaker"),
        "context": row.context,
        "confidence_score": row.confidence_score,
        "created_at": row.created_at,
        "article_id": row.article_id,
    }


def get_extracted_data(session: Session, article_id: int) -> List[Dict[str, Any]]:
    """Fetch extracted data points for one article, highest confidence first."""
    rows = (
        session.query(ExtractedData)
        .filter(ExtractedData.article_id == article_id)
        .order_by(ExtractedData.confidence_score.desc().nullslast(), ExtractedData.id)
        .all()
    )
    return [_row_to_dict(r) for r in rows]


def get_extracted_data_for_story(
    session: Session, story_id: int
) -> List[Dict[str, Any]]:
    """
    Fetch extracted data points for every article currently linked to a
    story via ``story_articles`` (#212/#213) -- no denormalized
    ``story_id`` on ``extracted_data`` itself, see migration 034.
    """
    rows = (
        session.query(ExtractedData)
        .join(StoryArticle, StoryArticle.article_id == ExtractedData.article_id)
        .filter(StoryArticle.story_id == story_id)
        .order_by(ExtractedData.confidence_score.desc().nullslast(), ExtractedData.id)
        .all()
    )
    return [_row_to_dict(r) for r in rows]


def maybe_extract_data_after_summary(
    session: Session,
    item_id: int,
    title: Optional[str],
    content: Optional[str],
    *,
    result: "Any",
    model: str = DEFAULT_EXTRACTION_MODEL,
) -> None:
    """
    After a fresh (non-cache) summarization, run data extraction on the
    article's full content and store the results. Failures are logged
    only -- mirrors ``item_embeddings.maybe_embed_item_after_summary``.
    """
    if not is_data_extraction_enabled():
        return
    if not getattr(result, "success", False):
        return
    if getattr(result, "cache_hit", False):
        return
    if not content or not content.strip():
        return

    try:
        data_points = extract_data_points(title or "", content, model=model)
        if data_points:
            store_extracted_data(session, item_id, data_points, model=model)
    except Exception as e:
        logger.warning(
            "Data extraction failed for item %s (article still saved): %s",
            item_id,
            e,
            exc_info=True,
        )
