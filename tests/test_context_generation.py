"""Tests for app.context_generation (#214/#215/#285, ADR-0023, v0.10.0)."""

from __future__ import annotations

import json
import os
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest

from app.context_generation import (
    _is_complex_story,
    _story_source_story_ids,
    generate_context_items,
    is_context_generation_enabled,
    maybe_generate_context_after_synthesis,
)

# --- Unit tests (mocked LLM, no DB) -----------------------------------------


class TestIsContextGenerationEnabled:
    def test_default_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NEWSBRIEF_CONTEXT_GENERATION_ENABLED", raising=False)
        assert is_context_generation_enabled() is True

    def test_env_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NEWSBRIEF_CONTEXT_GENERATION_ENABLED", "false")
        assert is_context_generation_enabled() is False

    def test_env_off_variants(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for val in ("0", "no", "off", "FALSE"):
            monkeypatch.setenv("NEWSBRIEF_CONTEXT_GENERATION_ENABLED", val)
            assert is_context_generation_enabled() is False

    def test_env_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NEWSBRIEF_CONTEXT_GENERATION_ENABLED", "true")
        assert is_context_generation_enabled() is True


class TestIsComplexStory:
    def test_low_article_count_low_score_not_complex(self) -> None:
        story = MagicMock(article_count=2, complexity_score=0.2)
        assert _is_complex_story(story) is False

    def test_high_article_count_is_complex(self) -> None:
        story = MagicMock(article_count=6, complexity_score=None)
        assert _is_complex_story(story) is True

    def test_high_complexity_score_is_complex(self) -> None:
        story = MagicMock(article_count=2, complexity_score=0.75)
        assert _is_complex_story(story) is True

    def test_none_values_not_complex(self) -> None:
        story = MagicMock(article_count=None, complexity_score=None)
        assert _is_complex_story(story) is False


class TestGenerateContextItems:
    def test_no_title_or_synthesis(self) -> None:
        result = generate_context_items("", "")
        assert result.significance == []
        assert result.background == []

    @patch("app.context_generation.get_llm_service")
    def test_llm_unavailable(self, mock_get_llm: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.is_available.return_value = False
        mock_get_llm.return_value = mock_service

        result = generate_context_items("Title", "Some synthesis text")
        assert result.significance == []

    @patch("app.context_generation.get_llm_service")
    def test_model_not_ensurable_returns_empty(self, mock_get_llm: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = False
        mock_get_llm.return_value = mock_service

        result = generate_context_items("Title", "synthesis", model="qwen2.5:14b")

        assert result.significance == []
        mock_service.backend.generate.assert_not_called()

    @patch("app.context_generation.get_llm_service")
    def test_empty_llm_response(self, mock_get_llm: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = True
        mock_service.backend.generate.return_value = {"response": ""}
        mock_get_llm.return_value = mock_service

        assert generate_context_items("Title", "synthesis").significance == []

    @patch("app.context_generation.get_llm_service")
    def test_invalid_json_response(self, mock_get_llm: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = True
        mock_service.backend.generate.return_value = {"response": "not json"}
        mock_get_llm.return_value = mock_service

        assert generate_context_items("Title", "synthesis").significance == []

    @patch("app.context_generation.get_llm_service")
    def test_success_parses_significance_and_glossary(
        self, mock_get_llm: MagicMock
    ) -> None:
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = True
        mock_service.backend.generate.return_value = {
            "response": json.dumps(
                {
                    "significance": [
                        {
                            "dimension": "economic",
                            "text": "This affects markets and jobs.",
                            "confidence": 0.85,
                        },
                    ],
                    "glossary": [
                        {
                            "term": "quantitative easing",
                            "definition": "Central bank bond buying to boost money supply.",
                            "confidence": 0.7,
                        }
                    ],
                }
            )
        }
        mock_get_llm.return_value = mock_service

        result = generate_context_items("Title", "Full synthesis text here")

        assert len(result.significance) == 1
        assert result.significance[0].dimension == "economic"
        assert len(result.glossary) == 1
        assert result.glossary[0].term == "quantitative easing"

    @patch("app.context_generation.get_llm_service")
    def test_invalid_dimension_dropped(self, mock_get_llm: MagicMock) -> None:
        """A hallucinated dimension outside the fixed set is dropped, not
        raised -- same degrade-rather-than-fail philosophy as
        ExtractedDataOutput."""
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = True
        mock_service.backend.generate.return_value = {
            "response": json.dumps(
                {
                    "significance": [
                        {
                            "dimension": "environmental",
                            "text": "Not a real dimension",
                            "confidence": 0.7,
                        },
                        {
                            "dimension": "social",
                            "text": "Communities are affected.",
                            "confidence": 0.6,
                        },
                    ]
                }
            )
        }
        mock_get_llm.return_value = mock_service

        result = generate_context_items("Title", "synthesis")

        assert len(result.significance) == 1
        assert result.significance[0].dimension == "social"

    @patch("app.context_generation.get_llm_service")
    def test_background_dropped_when_not_included(
        self, mock_get_llm: MagicMock
    ) -> None:
        """Code-level gate is authoritative even if the LLM volunteers a
        background section it wasn't asked for."""
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = True
        mock_service.backend.generate.return_value = {
            "response": json.dumps(
                {"background": [{"text": "Unrequested background", "confidence": 0.5}]}
            )
        }
        mock_get_llm.return_value = mock_service

        result = generate_context_items("Title", "synthesis", include_background=False)

        assert result.background == []

    @patch("app.context_generation.get_llm_service")
    def test_background_kept_when_included(self, mock_get_llm: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = True
        mock_service.backend.generate.return_value = {
            "response": json.dumps(
                {"background": [{"text": "Requested background", "confidence": 0.5}]}
            )
        }
        mock_get_llm.return_value = mock_service

        result = generate_context_items("Title", "synthesis", include_background=True)

        assert len(result.background) == 1
        assert result.background[0].text == "Requested background"

    @patch("app.context_generation.get_llm_service")
    def test_precedent_dropped_when_not_included(self, mock_get_llm: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = True
        mock_service.backend.generate.return_value = {
            "response": json.dumps(
                {"precedent": [{"text": "Unrequested precedent", "confidence": 0.5}]}
            )
        }
        mock_get_llm.return_value = mock_service

        result = generate_context_items("Title", "synthesis", include_precedent=False)

        assert result.precedent == []

    @patch("app.context_generation.get_llm_service")
    def test_precedent_kept_with_related_story_id(
        self, mock_get_llm: MagicMock
    ) -> None:
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = True
        mock_service.backend.generate.return_value = {
            "response": json.dumps(
                {
                    "precedent": [
                        {
                            "text": "Similar to a prior event",
                            "related_story_id": 42,
                            "confidence": 0.6,
                        }
                    ]
                }
            )
        }
        mock_get_llm.return_value = mock_service

        result = generate_context_items("Title", "synthesis", include_precedent=True)

        assert len(result.precedent) == 1
        assert result.precedent[0].related_story_id == 42

    @patch("app.context_generation.get_llm_service")
    def test_synthesis_truncated_to_max_chars(self, mock_get_llm: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = True
        mock_service.backend.generate.return_value = {
            "response": json.dumps({"significance": []})
        }
        mock_get_llm.return_value = mock_service

        long_synthesis = "x" * 20000
        generate_context_items("Title", long_synthesis)

        call_kwargs = mock_service.backend.generate.call_args.kwargs
        assert len(call_kwargs["prompt"]) < 20000


class TestStorySourceStoryIds:
    def test_no_continuation_or_anchors(self) -> None:
        story = MagicMock(continues_story_id=None, synthesis_anchors_json=None)
        assert _story_source_story_ids(story) == []

    def test_continues_story_id_included(self) -> None:
        story = MagicMock(continues_story_id=42, synthesis_anchors_json=None)
        assert _story_source_story_ids(story) == [42]

    def test_anchors_merged_and_deduped(self) -> None:
        story = MagicMock(
            continues_story_id=1,
            synthesis_anchors_json=json.dumps(
                [{"story_id": 1}, {"story_id": 2}, {"story_id": 3}]
            ),
        )
        ids = _story_source_story_ids(story)
        assert ids == [1, 2, 3]

    def test_malformed_anchors_json_yields_continuation_only(self) -> None:
        story = MagicMock(continues_story_id=7, synthesis_anchors_json="not json")
        assert _story_source_story_ids(story) == [7]


class TestMaybeGenerateContextAfterSynthesis:
    def _story(self, **overrides: object) -> MagicMock:
        defaults: Dict[str, object] = dict(
            id=42,
            title="Title",
            synthesis="Synthesis text",
            topics_json=None,
            entities_json=None,
            continues_story_id=None,
            synthesis_anchors_json=None,
            article_count=1,
            complexity_score=None,
        )
        defaults.update(overrides)
        return MagicMock(**defaults)

    def test_skips_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NEWSBRIEF_CONTEXT_GENERATION_ENABLED", "false")
        session = MagicMock()
        maybe_generate_context_after_synthesis(session, self._story())
        session.add.assert_not_called()

    def test_skips_when_story_has_no_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NEWSBRIEF_CONTEXT_GENERATION_ENABLED", raising=False)
        session = MagicMock()
        maybe_generate_context_after_synthesis(session, self._story(id=None))
        session.add.assert_not_called()

    @patch("app.context_generation.store_story_context")
    @patch("app.context_generation.generate_context_items")
    def test_calls_generate_and_store_on_success(
        self,
        mock_generate: MagicMock,
        mock_store: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("NEWSBRIEF_CONTEXT_GENERATION_ENABLED", raising=False)
        session = MagicMock()
        from app.llm_output import ContextGenerationOutput, SignificanceAngle

        mock_generate.return_value = ContextGenerationOutput(
            significance=[
                SignificanceAngle(dimension="economic", text="x", confidence=0.5)
            ]
        )

        maybe_generate_context_after_synthesis(session, self._story())

        mock_generate.assert_called_once()
        mock_store.assert_called_once()
        assert mock_store.call_args.args[2] == "significance"

    @patch("app.context_generation.generate_context_items")
    def test_generation_exception_is_swallowed(
        self, mock_generate: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NEWSBRIEF_CONTEXT_GENERATION_ENABLED", raising=False)
        mock_generate.side_effect = RuntimeError("boom")
        session = MagicMock()

        # Should not raise -- fire-and-forget, mirrors
        # data_extraction.maybe_extract_data_after_summary.
        maybe_generate_context_after_synthesis(session, self._story())

    @patch("app.context_generation.generate_context_items")
    def test_no_store_when_nothing_generated(
        self, mock_generate: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NEWSBRIEF_CONTEXT_GENERATION_ENABLED", raising=False)
        from app.llm_output import ContextGenerationOutput

        mock_generate.return_value = ContextGenerationOutput()
        session = MagicMock()

        maybe_generate_context_after_synthesis(session, self._story())

        session.add.assert_not_called()

    @patch("app.context_generation.generate_context_items")
    def test_complex_story_requests_background(
        self, mock_generate: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NEWSBRIEF_CONTEXT_GENERATION_ENABLED", raising=False)
        from app.llm_output import ContextGenerationOutput

        mock_generate.return_value = ContextGenerationOutput()
        session = MagicMock()

        maybe_generate_context_after_synthesis(session, self._story(article_count=10))

        assert mock_generate.call_args.kwargs["include_background"] is True

    @patch("app.context_generation.generate_context_items")
    def test_story_with_continuation_requests_precedent(
        self, mock_generate: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NEWSBRIEF_CONTEXT_GENERATION_ENABLED", raising=False)
        from app.llm_output import ContextGenerationOutput

        mock_generate.return_value = ContextGenerationOutput()
        session = MagicMock()

        maybe_generate_context_after_synthesis(
            session, self._story(continues_story_id=7)
        )

        assert mock_generate.call_args.kwargs["include_precedent"] is True


# --- DB integration tests (real Postgres, ADR-0022) -------------------------

if not os.environ.get("DATABASE_URL"):
    pytest.skip(
        "PostgreSQL required for DB integration tests below (set DATABASE_URL)",
        allow_module_level=True,
    )

from app.context_generation import get_story_context, store_story_context  # noqa: E402
from app.llm_output import (  # noqa: E402
    BackgroundItem,
    GlossaryTerm,
    PrecedentItem,
    SignificanceAngle,
)
from tests.pg_testutil import (  # noqa: E402
    create_test_story,
    pg_session_truncate_story_graph,
)


def _make_story(session) -> int:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return create_test_story(
        session,
        title="Story",
        synthesis="x" * 60,
        key_points=[],
        why_it_matters="",
        topics=[],
        entities=[],
        importance_score=0.5,
        freshness_score=0.5,
        model="m",
        time_window_start=now,
        time_window_end=now,
    )


class TestStoreAndGetStoryContext:
    def test_store_then_fetch_roundtrip(self) -> None:
        session = pg_session_truncate_story_graph()
        try:
            story_id = _make_story(session)

            angles = [
                SignificanceAngle(
                    dimension="economic",
                    text="Markets react to this.",
                    confidence=0.9,
                ),
                SignificanceAngle(
                    dimension="personal",
                    text="Readers should care.",
                    confidence=0.6,
                ),
            ]

            ok = store_story_context(
                session, story_id, "significance", angles, source_story_ids=[5, 6]
            )
            assert ok is True

            fetched = get_story_context(session, story_id)
            assert len(fetched) == 2
            by_dim = {f["dimension"]: f for f in fetched}
            assert by_dim["economic"]["text"] == "Markets react to this."
            assert by_dim["economic"]["source_story_ids"] == [5, 6]
            assert by_dim["personal"]["confidence_score"] == 0.6
        finally:
            session.close()

    def test_store_background_glossary_precedent(self) -> None:
        session = pg_session_truncate_story_graph()
        try:
            story_id = _make_story(session)

            store_story_context(
                session,
                story_id,
                "background",
                [BackgroundItem(text="How it started.", confidence=0.7)],
            )
            store_story_context(
                session,
                story_id,
                "glossary",
                [
                    GlossaryTerm(
                        term="QE", definition="Quantitative easing", confidence=0.6
                    )
                ],
            )
            store_story_context(
                session,
                story_id,
                "precedent",
                [
                    PrecedentItem(
                        text="Similar to a prior case.",
                        related_story_id=9,
                        confidence=0.5,
                    )
                ],
                source_story_ids=[9],
            )

            fetched = get_story_context(session, story_id)
            by_type = {f["context_type"]: f for f in fetched}
            assert by_type["background"]["text"] == "How it started."
            assert by_type["glossary"]["term"] == "QE"
            assert by_type["glossary"]["definition"] == "Quantitative easing"
            assert by_type["precedent"]["related_story_id"] == 9
            assert by_type["precedent"]["source_story_ids"] == [9]
        finally:
            session.close()

    def test_store_replaces_previous_context_of_same_type(self) -> None:
        """Regeneration (e.g. story update/re-synthesis) replaces old rows
        of the same context_type rather than accumulating duplicates."""
        session = pg_session_truncate_story_graph()
        try:
            story_id = _make_story(session)

            store_story_context(
                session,
                story_id,
                "significance",
                [SignificanceAngle(dimension="economic", text="v1", confidence=0.5)],
            )
            store_story_context(
                session,
                story_id,
                "significance",
                [SignificanceAngle(dimension="social", text="v2", confidence=0.5)],
            )

            fetched = get_story_context(session, story_id)
            assert len(fetched) == 1
            assert fetched[0]["dimension"] == "social"
        finally:
            session.close()

    def test_get_story_context_empty_for_unknown_story(self) -> None:
        session = pg_session_truncate_story_graph()
        try:
            assert get_story_context(session, 999) == []
        finally:
            session.close()

    def test_cascade_delete_on_story_removal(self) -> None:
        """story_context rows are removed when the parent story is deleted
        (ON DELETE CASCADE, migration 035)."""
        session = pg_session_truncate_story_graph()
        try:
            from app.orm_models import Story

            story_id = _make_story(session)
            store_story_context(
                session,
                story_id,
                "significance",
                [SignificanceAngle(dimension="economic", text="v1", confidence=0.5)],
            )
            assert len(get_story_context(session, story_id)) == 1

            session.query(Story).filter(Story.id == story_id).delete()
            session.commit()

            assert get_story_context(session, story_id) == []
        finally:
            session.close()
