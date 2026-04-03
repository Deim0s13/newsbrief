"""
Pure helpers for feed ingest idempotency and re-ingest gating (ADR-0031).

Kept separate from app.feeds so tests and tooling can import without DB setup.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timezone
from typing import Any


def _struct_time_to_utc(entry: dict[str, Any], key: str) -> datetime | None:
    st = entry.get(key)
    if not st:
        return None
    try:
        utc_timestamp = calendar.timegm(st)
        return datetime.fromtimestamp(utc_timestamp, tz=timezone.utc)
    except Exception:
        return None


def entry_published_for_item(entry: dict[str, Any]) -> datetime | None:
    """Prefer published_parsed, then updated_parsed (legacy ingest behaviour)."""
    for key in ("published_parsed", "updated_parsed"):
        dt = _struct_time_to_utc(entry, key)
        if dt:
            return dt
    return None


def entry_updated_instant(entry: dict[str, Any]) -> datetime | None:
    """Feed-reported update time, if any (ADR-0031 re-ingest gate)."""
    return _struct_time_to_utc(entry, "updated_parsed")


def _coerce_utc_datetime(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def should_reingest_existing_item(
    stored_published: Any,
    stored_content: str | None,
    entry_updated: datetime | None,
) -> bool:
    """
    Bounded re-fetch: retry when we have no body, or when the feed's updated_parsed
    is after the stored published instant (ADR-0031).
    """
    if stored_content is None or str(stored_content).strip() == "":
        return True
    if entry_updated is None:
        return False
    stored_dt = _coerce_utc_datetime(stored_published)
    if stored_dt is None:
        return False
    return entry_updated > stored_dt
