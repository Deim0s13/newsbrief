"""
MBFC source credibility data import.

Handles fetching, parsing, and importing credibility data from the
MBFC community dataset into the source_credibility table.

Part of Issue #271: Import and auto-refresh MBFC source credibility data
See ADR-0028: Source Credibility Architecture
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

import httpx

from app.credibility import calculate_credibility_score, is_eligible_for_synthesis
from app.db import session_scope
from app.orm_models import SourceCredibility

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# MBFC community dataset URL
MBFC_DATA_URL = (
    "https://raw.githubusercontent.com/drmikecrowe/mbfcext/main/docs/sources.json"
)

# Request timeout in seconds
REQUEST_TIMEOUT = 30


@dataclass
class ImportStats:
    """Statistics from a credibility data import."""

    total_records: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    duration_ms: int = 0
    dataset_version: Optional[str] = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "total_records": self.total_records,
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "failed": self.failed,
            "duration_ms": self.duration_ms,
            "dataset_version": self.dataset_version,
            "errors": self.errors[:10] if self.errors else [],  # Limit errors
        }


def fetch_mbfc_data() -> tuple[dict, str]:
    """
    Fetch MBFC source data from GitHub.

    Returns:
        Tuple of (data dict keyed by domain, dataset version string)

    Raises:
        httpx.HTTPError: If request fails
        json.JSONDecodeError: If response is not valid JSON
    """
    logger.info(f"Fetching MBFC data from {MBFC_DATA_URL}")

    with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
        response = client.get(MBFC_DATA_URL)
        response.raise_for_status()

        data = response.json()

        # Use Last-Modified header or current timestamp as version
        last_modified = response.headers.get("Last-Modified")
        dataset_version = last_modified or datetime.now(UTC).isoformat()

        logger.info(f"Fetched {len(data)} sources, version: {dataset_version}")
        return data, dataset_version


def map_mbfc_to_record(domain: str, data: dict, dataset_version: str) -> dict:
    """
    Map MBFC source entry to database record fields.

    Args:
        domain: The domain key from sources.json
        data: The source data dict
        dataset_version: Version string for provenance

    Returns:
        Dict of fields for SourceCredibility record
    """
    # Determine source_type from bias field
    bias_raw = data.get("bias", "").lower()

    if bias_raw == "satire":
        source_type = "satire"
        eligible = False
    elif bias_raw in ("conspiracy", "conspiracy-pseudoscience"):
        source_type = "conspiracy"
        eligible = False
    elif bias_raw in ("fake-news", "questionable"):
        source_type = "fake_news"
        eligible = False
    elif bias_raw == "pro-science":
        source_type = "pro_science"
        eligible = True
    else:
        source_type = "news"
        eligible = True

    # Normalize political bias for standard spectrum
    political_bias = None
    bias_mapping = {
        "left": "left",
        "leftcenter": "left_center",
        "left-center": "left_center",
        "center": "center",
        "least biased": "center",
        "right-center": "right_center",
        "rightcenter": "right_center",
        "right": "right",
    }
    political_bias = bias_mapping.get(bias_raw)

    # Normalize factual reporting
    reporting_raw = data.get("reporting", "")
    factual_mapping = {
        "very high": "very_high",
        "high": "high",
        "mostly factual": "mostly_factual",
        "mixed": "mixed",
        "low": "low",
        "very low": "very_low",
    }
    factual = factual_mapping.get(reporting_raw.lower()) if reporting_raw else None

    # Calculate credibility score
    score = calculate_credibility_score(factual)

    return {
        "domain": domain.lower().strip(),
        "name": data.get("name"),
        "homepage_url": data.get("homepage"),
        "source_type": source_type,
        "factual_reporting": factual,
        "bias": political_bias,
        "credibility_score": score,
        "is_eligible_for_synthesis": eligible,
        "provider": "mbfc_community",
        "provider_url": data.get("url"),
        "dataset_version": dataset_version,
        "raw_payload": json.dumps(data),
    }


def import_mbfc_sources(
    data: Optional[dict] = None,
    dataset_version: Optional[str] = None,
    session: Optional[Session] = None,
) -> ImportStats:
    """
    Import MBFC sources into the database.

    Args:
        data: Pre-fetched data dict (if None, will fetch from URL)
        dataset_version: Version string (if None, will be set during fetch)
        session: Optional SQLAlchemy session (if None, will create one)

    Returns:
        ImportStats with counts of inserted/updated/failed records
    """
    start_time = datetime.now(UTC)
    stats = ImportStats()

    # Fetch data if not provided
    if data is None:
        try:
            data, dataset_version = fetch_mbfc_data()
        except Exception as e:
            logger.error(f"Failed to fetch MBFC data: {e}")
            stats.errors.append(f"Fetch failed: {e}")
            return stats

    stats.total_records = len(data)
    stats.dataset_version = dataset_version

    # Ensure we have a version string for records
    version_str = dataset_version or datetime.now(UTC).isoformat()

    def _do_import(db: Session):
        nonlocal stats

        for domain, source_data in data.items():
            try:
                # Skip invalid domains
                if not domain or "." not in domain:
                    stats.skipped += 1
                    continue

                # Map to record fields
                record_data = map_mbfc_to_record(domain, source_data, version_str)

                # Check if record exists
                existing = (
                    db.query(SourceCredibility)
                    .filter_by(domain=record_data["domain"])
                    .first()
                )

                if existing:
                    # Update if data changed
                    changed = False
                    for key, value in record_data.items():
                        if key in ("raw_payload",):
                            continue  # Don't compare raw payload
                        if getattr(existing, key) != value:
                            setattr(existing, key, value)
                            changed = True

                    if changed:
                        existing.last_updated = datetime.now(UTC)
                        existing.raw_payload = record_data["raw_payload"]
                        stats.updated += 1
                    else:
                        stats.skipped += 1
                else:
                    # Insert new record
                    new_record = SourceCredibility(**record_data)
                    db.add(new_record)
                    stats.inserted += 1

            except Exception as e:
                logger.warning(f"Failed to import {domain}: {e}")
                stats.failed += 1
                if len(stats.errors) < 10:
                    stats.errors.append(f"{domain}: {e}")

        db.commit()

    # Use provided session or create new one
    if session is not None:
        _do_import(session)
    else:
        with session_scope() as db:
            _do_import(db)

    # Calculate duration
    end_time = datetime.now(UTC)
    stats.duration_ms = int((end_time - start_time).total_seconds() * 1000)

    logger.info(
        f"MBFC import complete: {stats.inserted} inserted, "
        f"{stats.updated} updated, {stats.skipped} skipped, "
        f"{stats.failed} failed ({stats.duration_ms}ms)"
    )

    return stats


def get_credibility_count() -> int:
    """
    Get the count of records in source_credibility table.

    Returns:
        Number of records in the table
    """
    with session_scope() as db:
        return db.query(SourceCredibility).count()


def is_credibility_data_empty() -> bool:
    """
    Check if the source_credibility table is empty.

    Returns:
        True if table has no records, False otherwise
    """
    return get_credibility_count() == 0


def ensure_credibility_data() -> Optional[ImportStats]:
    """
    Ensure credibility data exists, importing if necessary.

    This is called on startup to auto-populate the table if empty.

    Returns:
        ImportStats if import was performed, None if data already existed
    """
    if is_credibility_data_empty():
        logger.info("Source credibility table is empty, importing MBFC data...")
        return import_mbfc_sources()
    else:
        count = get_credibility_count()
        logger.info(f"Source credibility data exists ({count} records)")
        return None
