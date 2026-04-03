"""Tests for operator audit logging (#277)."""

from unittest.mock import MagicMock, patch

from fastapi import Request

from app.operator_audit import record_operator_action


def _fake_request(
    operator_label: str | None = "qa-user", ip: str = "203.0.113.1"
) -> Request:
    req = MagicMock(spec=Request)

    def _get(key: str, default=None):
        if key == "X-Operator-Label" and operator_label:
            return operator_label
        return default

    req.headers.get.side_effect = _get
    req.client = MagicMock(host=ip)
    return req


@patch("app.operator_audit.session_scope")
def test_record_operator_action_writes_row(mock_scope) -> None:
    mock_session = MagicMock()
    mock_scope.return_value.__enter__.return_value = mock_session
    mock_scope.return_value.__exit__.return_value = None

    record_operator_action(
        request=_fake_request(),
        action_type="pipeline_run",
        details={"success": True, "run_group_id": "abc"},
    )

    mock_session.add.assert_called_once()
    added = mock_session.add.call_args[0][0]
    assert added.action_type == "pipeline_run"
    assert added.operator_label == "qa-user"
    assert added.client_ip == "203.0.113.1"
    assert "abc" in (added.details_json or "")


@patch("app.operator_audit.session_scope")
def test_record_operator_action_swallows_db_error(mock_scope) -> None:
    mock_scope.return_value.__enter__.side_effect = RuntimeError("db down")

    # should not raise
    record_operator_action(
        request=_fake_request(),
        action_type="pipeline_replay",
        details={},
    )
