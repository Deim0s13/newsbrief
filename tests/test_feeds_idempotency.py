"""Tests for feed ingest idempotency helpers (ADR-0031)."""

from datetime import datetime, timezone

from app.ingest_idempotency import (
    entry_published_for_item,
    entry_updated_instant,
    should_reingest_existing_item,
)


def test_entry_published_prefers_published_parsed() -> None:
    entry = {
        "published_parsed": (2024, 6, 1, 12, 0, 0, 5, 153, 0),
        "updated_parsed": (2024, 6, 2, 12, 0, 0, 6, 154, 0),
    }
    got = entry_published_for_item(entry)
    assert got == datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)


def test_entry_updated_uses_updated_parsed_only() -> None:
    entry = {
        "published_parsed": (2024, 6, 1, 12, 0, 0, 5, 153, 0),
        "updated_parsed": (2024, 6, 2, 12, 0, 0, 6, 154, 0),
    }
    got = entry_updated_instant(entry)
    assert got == datetime(2024, 6, 2, 12, 0, tzinfo=timezone.utc)


def test_should_reingest_no_body() -> None:
    assert should_reingest_existing_item(
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        None,
        None,
    )
    assert should_reingest_existing_item(
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        "   ",
        None,
    )


def test_should_reingest_feed_updated_after_stored() -> None:
    stored = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    updated = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)
    assert should_reingest_existing_item(stored, "hello", updated)


def test_should_not_reingest_when_no_updated_and_has_body() -> None:
    stored = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert not should_reingest_existing_item(stored, "hello", None)


def test_should_not_reingest_when_updated_not_after_stored() -> None:
    stored = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)
    updated = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert not should_reingest_existing_item(stored, "hello", updated)
