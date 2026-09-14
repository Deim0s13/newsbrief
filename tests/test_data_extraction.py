"""Tests for app.data_extraction (#210/#211, ADR-0023, v0.9.3)."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from app.data_extraction import (
    extract_data_points,
    is_data_extraction_enabled,
    maybe_extract_data_after_summary,
)
from app.llm import SummaryResult

# --- Unit tests (mocked LLM, no DB) -----------------------------------------


class TestIsDataExtractionEnabled:
    def test_default_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NEWSBRIEF_DATA_EXTRACTION_ENABLED", raising=False)
        assert is_data_extraction_enabled() is True

    def test_env_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NEWSBRIEF_DATA_EXTRACTION_ENABLED", "false")
        assert is_data_extraction_enabled() is False

    def test_env_off_variants(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for val in ("0", "no", "off", "FALSE"):
            monkeypatch.setenv("NEWSBRIEF_DATA_EXTRACTION_ENABLED", val)
            assert is_data_extraction_enabled() is False

    def test_env_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NEWSBRIEF_DATA_EXTRACTION_ENABLED", "true")
        assert is_data_extraction_enabled() is True


class TestExtractDataPoints:
    def test_no_title_or_content(self) -> None:
        assert extract_data_points("", "") == []

    @patch("app.data_extraction.get_llm_service")
    def test_llm_unavailable(self, mock_get_llm: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.is_available.return_value = False
        mock_get_llm.return_value = mock_service

        assert extract_data_points("Title", "Some article content") == []

    @patch("app.data_extraction.get_llm_service")
    def test_model_not_ensurable_returns_empty(self, mock_get_llm: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = False
        mock_get_llm.return_value = mock_service

        result = extract_data_points("Title", "content", model="qwen2.5:14b")

        assert result == []
        mock_service.backend.generate.assert_not_called()

    @patch("app.data_extraction.get_llm_service")
    def test_empty_llm_response(self, mock_get_llm: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = True
        mock_service.backend.generate.return_value = {"response": ""}
        mock_get_llm.return_value = mock_service

        assert extract_data_points("Title", "content") == []

    @patch("app.data_extraction.get_llm_service")
    def test_invalid_json_response(self, mock_get_llm: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = True
        mock_service.backend.generate.return_value = {"response": "not json"}
        mock_get_llm.return_value = mock_service

        assert extract_data_points("Title", "content") == []

    @patch("app.data_extraction.get_llm_service")
    def test_success_parses_data_points(self, mock_get_llm: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = True
        mock_service.backend.generate.return_value = {
            "response": json.dumps(
                {
                    "data_points": [
                        {
                            "data_type": "statistic",
                            "value": "3.4%",
                            "context": "unemployment fell",
                            "attribution": None,
                            "unit": "percent",
                            "confidence": 0.9,
                        },
                        {
                            "data_type": "quote",
                            "value": "This is unprecedented",
                            "context": "at a press conference",
                            "attribution": "Jane Smith, CEO",
                            "unit": None,
                            "confidence": 0.8,
                        },
                    ]
                }
            )
        }
        mock_get_llm.return_value = mock_service

        points = extract_data_points("Title", "Unemployment fell to 3.4%...")

        assert len(points) == 2
        assert points[0].data_type == "statistic"
        assert points[0].value == "3.4%"
        assert points[0].unit == "percent"
        assert points[1].data_type == "quote"
        assert points[1].attribution == "Jane Smith, CEO"

    @patch("app.data_extraction.get_llm_service")
    def test_invalid_data_type_dropped(self, mock_get_llm: MagicMock) -> None:
        """A hallucinated data_type (e.g. 'location', explicitly out of
        scope -- see migration 034 docstring) is dropped, not raised."""
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = True
        mock_service.backend.generate.return_value = {
            "response": json.dumps(
                {
                    "data_points": [
                        {"data_type": "location", "value": "Paris", "confidence": 0.7},
                        {"data_type": "statistic", "value": "42%", "confidence": 0.6},
                    ]
                }
            )
        }
        mock_get_llm.return_value = mock_service

        points = extract_data_points("Title", "content")

        assert len(points) == 1
        assert points[0].data_type == "statistic"

    @patch("app.data_extraction.get_llm_service")
    def test_content_truncated_to_max_chars(self, mock_get_llm: MagicMock) -> None:
        mock_service = MagicMock()
        mock_service.is_available.return_value = True
        mock_service.ensure_model.return_value = True
        mock_service.backend.generate.return_value = {
            "response": json.dumps({"data_points": []})
        }
        mock_get_llm.return_value = mock_service

        long_content = "x" * 20000
        extract_data_points("Title", long_content)

        call_kwargs = mock_service.backend.generate.call_args.kwargs
        assert len(call_kwargs["prompt"]) < 20000


class TestMaybeExtractDataAfterSummary:
    def _success_result(self, cache_hit: bool = False) -> SummaryResult:
        return SummaryResult(summary="s", model="m", success=True, cache_hit=cache_hit)

    def test_skips_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NEWSBRIEF_DATA_EXTRACTION_ENABLED", "false")
        session = MagicMock()
        maybe_extract_data_after_summary(
            session, 1, "Title", "content", result=self._success_result()
        )
        session.add.assert_not_called()

    def test_skips_when_summary_failed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NEWSBRIEF_DATA_EXTRACTION_ENABLED", raising=False)
        session = MagicMock()
        failed = SummaryResult(summary="", model="m", success=False)
        maybe_extract_data_after_summary(session, 1, "Title", "content", result=failed)
        session.add.assert_not_called()

    def test_skips_on_cache_hit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NEWSBRIEF_DATA_EXTRACTION_ENABLED", raising=False)
        session = MagicMock()
        maybe_extract_data_after_summary(
            session,
            1,
            "Title",
            "content",
            result=self._success_result(cache_hit=True),
        )
        session.add.assert_not_called()

    def test_skips_when_no_content(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NEWSBRIEF_DATA_EXTRACTION_ENABLED", raising=False)
        session = MagicMock()
        maybe_extract_data_after_summary(
            session, 1, "Title", "", result=self._success_result()
        )
        session.add.assert_not_called()

    @patch("app.data_extraction.store_extracted_data")
    @patch("app.data_extraction.extract_data_points")
    def test_calls_extract_and_store_on_success(
        self,
        mock_extract: MagicMock,
        mock_store: MagicMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("NEWSBRIEF_DATA_EXTRACTION_ENABLED", raising=False)
        session = MagicMock()
        mock_extract.return_value = [MagicMock()]

        maybe_extract_data_after_summary(
            session, 42, "Title", "Full article content", result=self._success_result()
        )

        mock_extract.assert_called_once()
        mock_store.assert_called_once()

    @patch("app.data_extraction.extract_data_points")
    def test_extraction_exception_is_swallowed(
        self, mock_extract: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("NEWSBRIEF_DATA_EXTRACTION_ENABLED", raising=False)
        mock_extract.side_effect = RuntimeError("boom")
        session = MagicMock()

        # Should not raise -- fire-and-forget, mirrors maybe_embed_item_after_summary.
        maybe_extract_data_after_summary(
            session, 1, "Title", "content", result=self._success_result()
        )


# --- DB integration tests (real Postgres, ADR-0022) -------------------------

if not os.environ.get("DATABASE_URL"):
    pytest.skip(
        "PostgreSQL required for DB integration tests below (set DATABASE_URL)",
        allow_module_level=True,
    )

from app.data_extraction import (  # noqa: E402
    get_extracted_data,
    get_extracted_data_for_story,
    store_extracted_data,
)
from app.llm_output import ExtractedDataItem  # noqa: E402
from app.orm_models import Feed, Item  # noqa: E402
from tests.pg_testutil import (  # noqa: E402
    create_test_story,
    link_test_articles_to_story,
    pg_session_truncate_story_graph,
)


def _seed_feed(session, feed_id: int = 1, name: str = "Feed A") -> None:
    session.add(Feed(id=feed_id, url=f"http://example.com/feed{feed_id}", name=name))
    session.commit()


def _seed_item(session, item_id: int, feed_id: int) -> None:
    session.add(
        Item(
            id=item_id,
            feed_id=feed_id,
            title=f"Article {item_id}",
            url=f"http://example.com/a{item_id}",
            url_hash=f"hash{item_id}",
        )
    )
    session.commit()


class TestStoreAndGetExtractedData:
    def test_store_then_fetch_roundtrip(self) -> None:
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            _seed_item(session, 1, 1)

            points = [
                ExtractedDataItem(
                    data_type="statistic",
                    value="3.4%",
                    context="unemployment context",
                    unit="percent",
                    confidence=0.9,
                ),
                ExtractedDataItem(
                    data_type="quote",
                    value="This is unprecedented",
                    attribution="Jane Smith, CEO",
                    confidence=0.8,
                ),
            ]

            ok = store_extracted_data(session, 1, points)
            assert ok is True

            fetched = get_extracted_data(session, 1)
            assert len(fetched) == 2
            by_type = {f["data_type"]: f for f in fetched}
            assert by_type["statistic"]["value"] == "3.4%"
            assert by_type["statistic"]["unit"] == "percent"
            assert by_type["quote"]["attribution"] == "Jane Smith, CEO"
        finally:
            session.close()

    def test_store_replaces_previous_data(self) -> None:
        """Re-extraction (e.g. re-summarize) replaces old rows rather than
        accumulating duplicates."""
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            _seed_item(session, 1, 1)

            store_extracted_data(
                session,
                1,
                [ExtractedDataItem(data_type="statistic", value="1%", confidence=0.5)],
            )
            store_extracted_data(
                session,
                1,
                [ExtractedDataItem(data_type="statistic", value="2%", confidence=0.5)],
            )

            fetched = get_extracted_data(session, 1)
            assert len(fetched) == 1
            assert fetched[0]["value"] == "2%"
        finally:
            session.close()

    def test_get_extracted_data_empty_for_unknown_article(self) -> None:
        session = pg_session_truncate_story_graph()
        try:
            assert get_extracted_data(session, 999) == []
        finally:
            session.close()


class TestGetExtractedDataForStory:
    def test_aggregates_across_supporting_articles(self) -> None:
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session, 1, "Feed A")
            _seed_feed(session, 2, "Feed B")
            _seed_item(session, 1, 1)
            _seed_item(session, 2, 2)

            from datetime import UTC, datetime

            now = datetime.now(UTC)
            story_id = create_test_story(
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
            link_test_articles_to_story(session, story_id, [1, 2], primary_article_id=1)

            store_extracted_data(
                session,
                1,
                [
                    ExtractedDataItem(
                        data_type="statistic", value="3.4%", confidence=0.9
                    )
                ],
            )
            store_extracted_data(
                session,
                2,
                [
                    ExtractedDataItem(
                        data_type="quote", value="Great news", confidence=0.7
                    )
                ],
            )

            aggregated = get_extracted_data_for_story(session, story_id)

            assert len(aggregated) == 2
            article_ids = {d["article_id"] for d in aggregated}
            assert article_ids == {1, 2}
        finally:
            session.close()

    def test_empty_for_story_with_no_extracted_data(self) -> None:
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            _seed_item(session, 1, 1)

            from datetime import UTC, datetime

            now = datetime.now(UTC)
            story_id = create_test_story(
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
            link_test_articles_to_story(session, story_id, [1], primary_article_id=1)

            assert get_extracted_data_for_story(session, story_id) == []
        finally:
            session.close()

    def test_cascade_delete_on_article_removal(self) -> None:
        """extracted_data rows are removed when the parent article is
        deleted (ON DELETE CASCADE, migration 034)."""
        session = pg_session_truncate_story_graph()
        try:
            _seed_feed(session)
            _seed_item(session, 1, 1)
            store_extracted_data(
                session,
                1,
                [ExtractedDataItem(data_type="statistic", value="1%", confidence=0.5)],
            )
            assert len(get_extracted_data(session, 1)) == 1

            session.query(Item).filter(Item.id == 1).delete()
            session.commit()

            assert get_extracted_data(session, 1) == []
        finally:
            session.close()
