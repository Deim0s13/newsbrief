"""Small datetime helpers for database values."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


def coerce_datetime(value: Any) -> Optional[datetime]:
    """Return a datetime from either driver-native datetimes or ISO strings."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return None
