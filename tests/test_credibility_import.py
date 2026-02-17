#!/usr/bin/env python3
"""
Tests for MBFC credibility data import.

Tests the import logic, mapping, and database operations.

Part of Issue #271: Import and auto-refresh MBFC source credibility data
"""

from unittest.mock import MagicMock, patch

import pytest

from app.credibility_import import (
    ImportStats,
    fetch_mbfc_data,
    import_mbfc_sources,
    map_mbfc_to_record,
)

# -----------------------------------------------------------------------------
# Map MBFC Record Tests
# -----------------------------------------------------------------------------


class TestMapMbfcToRecord:
    """Tests for MBFC record mapping."""

    def test_basic_news_source(self):
        """Map a standard news source."""
        data = {
            "name": "New York Times",
            "bias": "leftcenter",
            "reporting": "HIGH",
            "url": "https://mediabiasfactcheck.com/new-york-times/",
            "homepage": "https://www.nytimes.com",
        }
        result = map_mbfc_to_record("nytimes.com", data, "test-v1")

        assert result["domain"] == "nytimes.com"
        assert result["name"] == "New York Times"
        assert result["source_type"] == "news"
        assert result["factual_reporting"] == "high"
        assert result["bias"] == "left_center"
        assert result["credibility_score"] == 0.85
        assert result["is_eligible_for_synthesis"] is True
        assert result["provider"] == "mbfc_community"
        assert result["dataset_version"] == "test-v1"

    def test_satire_source(self):
        """Satire sources should be ineligible."""
        data = {
            "name": "The Onion",
            "bias": "satire",
        }
        result = map_mbfc_to_record("theonion.com", data, "test-v1")

        assert result["source_type"] == "satire"
        assert result["is_eligible_for_synthesis"] is False

    def test_conspiracy_source(self):
        """Conspiracy sources should be ineligible."""
        data = {
            "name": "Conspiracy Site",
            "bias": "conspiracy-pseudoscience",
        }
        result = map_mbfc_to_record("conspiracy.example.com", data, "test-v1")

        assert result["source_type"] == "conspiracy"
        assert result["is_eligible_for_synthesis"] is False

    def test_fake_news_source(self):
        """Fake news sources should be ineligible."""
        data = {
            "name": "Fake Site",
            "bias": "questionable",
        }
        result = map_mbfc_to_record("fake.example.com", data, "test-v1")

        assert result["source_type"] == "fake_news"
        assert result["is_eligible_for_synthesis"] is False

    def test_pro_science_source(self):
        """Pro-science sources should be eligible."""
        data = {
            "name": "Science News",
            "bias": "pro-science",
            "reporting": "VERY HIGH",
        }
        result = map_mbfc_to_record("sciencenews.org", data, "test-v1")

        assert result["source_type"] == "pro_science"
        assert result["is_eligible_for_synthesis"] is True
        assert result["credibility_score"] == 1.0

    def test_factual_rating_mapping(self):
        """Test all factual rating mappings."""
        ratings = [
            ("VERY HIGH", "very_high", 1.0),
            ("HIGH", "high", 0.85),
            ("MOSTLY FACTUAL", "mostly_factual", 0.70),
            ("MIXED", "mixed", 0.50),
            ("LOW", "low", 0.30),
            ("VERY LOW", "very_low", 0.15),
        ]

        for raw, expected_factual, expected_score in ratings:
            data = {"reporting": raw, "bias": "center"}
            result = map_mbfc_to_record("test.com", data, "v1")
            assert result["factual_reporting"] == expected_factual, f"Failed for {raw}"
            assert (
                result["credibility_score"] == expected_score
            ), f"Score wrong for {raw}"

    def test_bias_normalization(self):
        """Test political bias normalization."""
        bias_mappings = [
            ("left", "left"),
            ("leftcenter", "left_center"),
            ("left-center", "left_center"),
            ("center", "center"),
            ("least biased", "center"),
            ("right-center", "right_center"),
            ("rightcenter", "right_center"),
            ("right", "right"),
        ]

        for raw, expected in bias_mappings:
            data = {"bias": raw, "reporting": "HIGH"}
            result = map_mbfc_to_record("test.com", data, "v1")
            assert result["bias"] == expected, f"Failed for {raw}"

    def test_missing_fields(self):
        """Handle missing optional fields gracefully."""
        data = {}  # Empty data
        result = map_mbfc_to_record("empty.com", data, "v1")

        assert result["domain"] == "empty.com"
        assert result["source_type"] == "news"
        assert result["factual_reporting"] is None
        assert result["credibility_score"] is None
        assert result["is_eligible_for_synthesis"] is True

    def test_raw_payload_stored(self):
        """Raw payload should be stored as JSON."""
        data = {"name": "Test", "bias": "center"}
        result = map_mbfc_to_record("test.com", data, "v1")

        assert '"name": "Test"' in result["raw_payload"]
        assert '"bias": "center"' in result["raw_payload"]


# -----------------------------------------------------------------------------
# Import Stats Tests
# -----------------------------------------------------------------------------


class TestImportStats:
    """Tests for ImportStats dataclass."""

    def test_default_values(self):
        """Test default initialization."""
        stats = ImportStats()
        assert stats.total_records == 0
        assert stats.inserted == 0
        assert stats.errors == []

    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = ImportStats(
            total_records=100,
            inserted=50,
            updated=30,
            skipped=15,
            failed=5,
            duration_ms=1234,
            dataset_version="v1",
        )
        result = stats.to_dict()

        assert result["total_records"] == 100
        assert result["inserted"] == 50
        assert result["duration_ms"] == 1234

    def test_errors_limited(self):
        """Errors should be limited to 10 in to_dict()."""
        stats = ImportStats()
        stats.errors = [f"error{i}" for i in range(20)]

        result = stats.to_dict()
        assert len(result["errors"]) == 10


# -----------------------------------------------------------------------------
# Fetch Tests (mocked)
# -----------------------------------------------------------------------------


class TestFetchMbfcData:
    """Tests for MBFC data fetching."""

    @patch("app.credibility_import.httpx.Client")
    def test_fetch_success(self, mock_client_class):
        """Test successful data fetch."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"example.com": {"name": "Example"}}
        mock_response.headers = {"Last-Modified": "Sun, 16 Feb 2026 12:00:00 GMT"}

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        data, version = fetch_mbfc_data()

        assert "example.com" in data
        assert version == "Sun, 16 Feb 2026 12:00:00 GMT"

    @patch("app.credibility_import.httpx.Client")
    def test_fetch_uses_timestamp_if_no_last_modified(self, mock_client_class):
        """Use current timestamp if no Last-Modified header."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"example.com": {"name": "Example"}}
        mock_response.headers = {}  # No Last-Modified

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_class.return_value = mock_client

        data, version = fetch_mbfc_data()

        assert "example.com" in data
        # Version should be an ISO timestamp
        assert "202" in version  # Year prefix


# -----------------------------------------------------------------------------
# Import Tests (with mock DB)
# -----------------------------------------------------------------------------


class TestImportMbfcSources:
    """Tests for the import function."""

    def test_import_skips_invalid_domains(self):
        """Invalid domains should be skipped."""
        data = {
            "valid.com": {"name": "Valid"},
            "invalid": {"name": "No TLD"},
            "": {"name": "Empty"},
        }

        # Mock the session
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        stats = import_mbfc_sources(
            data=data, dataset_version="v1", session=mock_session
        )

        assert stats.total_records == 3
        assert stats.skipped >= 2  # At least the invalid ones


# -----------------------------------------------------------------------------
# Run with pytest
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
