"""Tests for failed entity admin helpers (#293 M3)."""

from unittest.mock import MagicMock, patch

import pytest

from app.failed_entities import discard_failed_item


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
