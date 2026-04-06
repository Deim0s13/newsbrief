"""Tests for stage-aware pipeline monitoring (#276)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.pipeline_monitoring import (
    get_pipeline_run_metrics,
    get_processing_stage_snapshot,
    list_stuck_pipeline_runs,
    pipeline_stuck_threshold_seconds,
)


def test_pipeline_stuck_threshold_seconds_env(monkeypatch) -> None:
    monkeypatch.delenv("PIPELINE_STUCK_AFTER_SECONDS", raising=False)
    assert pipeline_stuck_threshold_seconds() == 3600
    monkeypatch.setenv("PIPELINE_STUCK_AFTER_SECONDS", "120")
    assert pipeline_stuck_threshold_seconds() == 120
    monkeypatch.setenv("PIPELINE_STUCK_AFTER_SECONDS", "30")
    assert pipeline_stuck_threshold_seconds() == 60
    assert pipeline_stuck_threshold_seconds(1800) == 1800


def _mock_query_chain(all_rows):
    m = MagicMock()
    m.group_by.return_value.all.return_value = all_rows
    return m


@patch("app.pipeline_monitoring.session_scope")
def test_get_processing_stage_snapshot_shape(mock_scope) -> None:
    mock_session = MagicMock()
    mock_scope.return_value.__enter__.return_value = mock_session
    mock_scope.return_value.__exit__.return_value = None

    ts = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    mock_session.query.side_effect = [
        _mock_query_chain([("fetched", 2), ("enriched", 1)]),
        _mock_query_chain([("candidate", 1)]),
        _mock_query_chain([("fetched", ts)]),
        _mock_query_chain([("candidate", ts)]),
    ]

    out = get_processing_stage_snapshot()
    assert out["articles"]["by_state"]["fetched"] == 2
    assert out["articles"]["by_state"]["enriched"] == 1
    assert out["articles"]["oldest_waiting_at_by_state"]["fetched"] == ts.isoformat()
    assert out["stories"]["by_state"]["candidate"] == 1
    assert "generated_at" in out


@patch("app.pipeline_monitoring.session_scope")
def test_get_pipeline_run_metrics_shape(mock_scope) -> None:
    mock_session = MagicMock()
    mock_scope.return_value.__enter__.return_value = mock_session
    mock_scope.return_value.__exit__.return_value = None

    row = (
        "ingest",
        10,
        8,
        9,
        1,
        45.5,
        12,
        2,
    )
    qm = MagicMock()
    qm.filter.return_value.group_by.return_value.all.return_value = [row]
    mock_session.query.return_value = qm

    out = get_pipeline_run_metrics(window_hours=6.0)
    assert out["window_hours"] == 6.0
    assert len(out["by_stage"]) == 1
    s0 = out["by_stage"][0]
    assert s0["stage"] == "ingest"
    assert s0["started_in_window"] == 10
    assert s0["finished"] == 9
    assert s0["unfinished_started_in_window"] == 1
    assert s0["succeeded_among_finished"] == 8
    assert s0["success_rate_finished"] == pytest.approx(8 / 9, rel=1e-3)
    assert s0["avg_duration_seconds"] == 45.5
    assert s0["sum_attempts"] == 12
    assert s0["runs_with_attempts_gt_1"] == 2


@patch("app.pipeline_monitoring.session_scope")
@patch("app.pipeline_monitoring.datetime")
def test_list_stuck_pipeline_runs(mock_dt, mock_scope) -> None:
    fixed = datetime(2026, 4, 2, 15, 0, 0, tzinfo=UTC)
    mock_dt.now.return_value = fixed
    mock_dt.UTC = UTC

    old_start = fixed - timedelta(seconds=7200)
    run = SimpleNamespace(
        id=42,
        run_group_id="rg-1",
        stage="ingest",
        trigger="manual",
        started_at=old_start,
        target_type=None,
        target_id=None,
        attempts=1,
    )

    mock_session = MagicMock()
    mock_scope.return_value.__enter__.return_value = mock_session
    mock_scope.return_value.__exit__.return_value = None
    qm = MagicMock()
    qm.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        run
    ]
    mock_session.query.return_value = qm

    out = list_stuck_pipeline_runs(max_age_seconds=3600, limit=20)
    assert out["threshold_seconds"] == 3600
    assert out["count"] == 1
    assert out["runs"][0]["id"] == 42
    assert out["runs"][0]["age_seconds"] == 7200
