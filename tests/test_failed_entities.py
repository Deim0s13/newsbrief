"""Tests for failed entity admin helpers (#293 M3–M4)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.failed_entities import discard_failed_item, list_failed_entities


@patch("app.failed_entities.session_scope")
def test_discard_failed_item_rejects_non_failed(mock_scope) -> None:
    mock_session = MagicMock()
    mock_scope.return_value.__enter__.return_value = mock_session
    mock_scope.return_value.__exit__.return_value = None
    exec_result = MagicMock()
    exec_result.first.return_value = ("enriched",)
    mock_session.execute.return_value = exec_result

    with pytest.raises(ValueError, match="not in failed"):
        discard_failed_item(1)


@patch("app.failed_entities.discard_article_failure", return_value=True)
@patch("app.failed_entities.session_scope")
def test_discard_failed_item_succeeds(mock_scope, _mock_discard) -> None:
    mock_session = MagicMock()
    mock_scope.return_value.__enter__.return_value = mock_session
    mock_scope.return_value.__exit__.return_value = None
    exec_result = MagicMock()
    exec_result.first.return_value = ("failed",)
    mock_session.execute.return_value = exec_result

    out = discard_failed_item(99)
    assert out == {"id": 99, "entity": "item", "discarded": True}


@patch("app.failed_entities.session_scope")
def test_list_failed_entities_shape(mock_scope) -> None:
    mock_session = MagicMock()
    mock_scope.return_value.__enter__.return_value = mock_session
    mock_scope.return_value.__exit__.return_value = None
    ts = datetime.now(UTC)
    res_items = MagicMock()
    res_items.fetchall.return_value = [
        (1, "Hi", "bad", ts, "story_generation", "rg-1"),
    ]
    res_stories = MagicMock()
    res_stories.fetchall.return_value = [
        (2, "Story title", None, None, None, None),
    ]
    mock_session.execute.side_effect = [res_items, res_stories]

    out = list_failed_entities(limit_items=5, limit_stories=5)
    assert out["items"][0]["id"] == 1
    assert out["items"][0]["failure_stage"] == "story_generation"
    assert out["items"][0]["processing_failed_at"] == ts.isoformat()
    assert out["stories"][0]["id"] == 2
    assert out["stories"][0]["title"] == "Story title"
