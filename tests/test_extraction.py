#!/usr/bin/env python3
"""
Extraction regression test suite using golden set fixtures.

This module tests content extraction against a curated set of HTML fixtures
with known expected outcomes. It validates that extraction quality remains
consistent across code changes.

Part of Issue #231 - v0.8.0 Content Extraction Pipeline Upgrade
"""
import json
from pathlib import Path

import pytest

# Fixtures directory relative to this test file
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "extraction"


def load_golden_set() -> list[dict]:
    """Load the golden set configuration."""
    golden_set_path = FIXTURES_DIR / "golden_set.json"
    with open(golden_set_path) as f:
        data = json.load(f)
    return data["fixtures"]


def get_fixture_ids() -> list[str]:
    """Get list of fixture IDs for parametrization."""
    return [f["id"] for f in load_golden_set()]


def get_fixture_by_id(fixture_id: str) -> dict:
    """Get a specific fixture by ID."""
    for fixture in load_golden_set():
        if fixture["id"] == fixture_id:
            return fixture
    raise ValueError(f"Fixture {fixture_id} not found")


class TestExtractionGoldenSet:
    """Regression tests using golden set fixtures."""

    @pytest.fixture(scope="class")
    def golden_set(self):
        """Load golden set once per test class."""
        return load_golden_set()

    @pytest.mark.parametrize("fixture_id", get_fixture_ids())
    def test_extraction_succeeds(self, fixture_id: str):
        """Test that extraction produces output for each fixture."""
        fixture = get_fixture_by_id(fixture_id)
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        from app.extraction import extract_content

        result = extract_content(html=html)

        # Basic assertions - extraction should produce something
        assert result.title is not None, f"Title extraction failed for {fixture_id}"
        assert result.content is not None, f"Content extraction failed for {fixture_id}"
        assert len(result.content) > 0, f"Empty content for {fixture_id}"

    @pytest.mark.parametrize("fixture_id", get_fixture_ids())
    def test_content_length_bounds(self, fixture_id: str):
        """Test that extracted content length is within expected bounds."""
        fixture = get_fixture_by_id(fixture_id)
        expected = fixture["expected"]
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        from app.extraction import extract_content

        result = extract_content(html=html)
        content_length = len(result.content) if result.content else 0

        min_length = expected.get("min_content_length", 0)
        max_length = expected.get("max_content_length", float("inf"))

        assert content_length >= min_length, (
            f"Content too short for {fixture_id}: "
            f"{content_length} < {min_length} chars"
        )
        assert content_length <= max_length, (
            f"Content too long for {fixture_id}: "
            f"{content_length} > {max_length} chars"
        )

    @pytest.mark.parametrize("fixture_id", get_fixture_ids())
    def test_title_extraction(self, fixture_id: str):
        """Test that title is extracted correctly."""
        fixture = get_fixture_by_id(fixture_id)
        expected = fixture["expected"]
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        from app.extraction import extract_content

        result = extract_content(html=html)
        title = result.title or ""

        # Check exact title match if specified
        if "title" in expected:
            assert title == expected["title"], (
                f"Title mismatch for {fixture_id}: "
                f"got '{title}', expected '{expected['title']}'"
            )
        # Check partial title match if specified
        elif "title_contains" in expected:
            assert expected["title_contains"].lower() in title.lower(), (
                f"Title doesn't contain '{expected['title_contains']}' "
                f"for {fixture_id}: got '{title}'"
            )

    @pytest.mark.parametrize("fixture_id", get_fixture_ids())
    def test_key_phrases_present(self, fixture_id: str):
        """Test that expected key phrases are present in extracted content."""
        fixture = get_fixture_by_id(fixture_id)
        expected = fixture["expected"]
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        from app.extraction import extract_content

        result = extract_content(html=html)
        # Combine title and content for phrase search
        full_text = f"{result.title or ''} {result.content or ''}".lower()

        key_phrases = expected.get("key_phrases", [])
        missing_phrases = []

        for phrase in key_phrases:
            if phrase.lower() not in full_text:
                missing_phrases.append(phrase)

        assert (
            not missing_phrases
        ), f"Missing key phrases in {fixture_id}: {missing_phrases}"


class TestBoilerplateRemoval:
    """Tests specifically for boilerplate removal quality."""

    def test_no_navigation_in_content(self):
        """Test that navigation elements are not in extracted content."""
        fixture = get_fixture_by_id("heavy_boilerplate_001")
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        from app.extraction import extract_content

        result = extract_content(html=html)
        content_lower = (result.content or "").lower()

        # These navigation items should NOT be in the extracted content
        nav_items = ["trending now", "newsletter", "subscribe for daily"]
        for nav_item in nav_items:
            assert (
                nav_item not in content_lower
            ), f"Navigation/sidebar content found in extraction: '{nav_item}'"

    def test_no_advertisement_markers(self):
        """Test that advertisement markers are not in extracted content."""
        fixture = get_fixture_by_id("heavy_boilerplate_001")
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        from app.extraction import extract_content

        result = extract_content(html=html)
        content_lower = (result.content or "").lower()

        # Ad markers should NOT be in extracted content
        ad_markers = ["advertisement", "ad-placeholder", "sidebar-ad"]
        for marker in ad_markers:
            assert (
                marker not in content_lower
            ), f"Advertisement marker found in extraction: '{marker}'"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_malformed_html_resilience(self):
        """Test that extraction handles malformed HTML gracefully."""
        fixture = get_fixture_by_id("malformed_001")
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        from app.extraction import extract_content

        # Should not raise an exception
        result = extract_content(html=html)

        # Should extract meaningful content despite malformed HTML
        assert (
            len(result.content or "") > 500
        ), "Should extract substantial content from malformed HTML"
        assert (
            "s&p 500" in (result.content or "").lower()
        ), "Key content should be extracted"

    def test_paywall_graceful_degradation(self):
        """Test that paywalled content extracts what's available."""
        fixture = get_fixture_by_id("minimal_content_001")
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        from app.extraction import extract_content

        result = extract_content(html=html)
        content = result.content or ""

        # Should extract the teaser content that is available
        assert len(content) > 50, "Should extract at least teaser content"
        assert (
            "merger" in content.lower() or "$100 billion" in content.lower()
        ), "Should extract visible teaser content"

    def test_international_content_encoding(self):
        """Test that non-English content with special characters is handled."""
        fixture = get_fixture_by_id("international_001")
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        from app.extraction import extract_content

        result = extract_content(html=html)
        content = result.content or ""

        # German umlauts and special characters should be preserved
        assert (
            "ü" in content or "Fortschritte" in content
        ), "German characters should be preserved in extraction"


class TestExtractionMetrics:
    """Tests that generate metrics for monitoring extraction quality."""

    def test_overall_success_rate(self, capsys):
        """Calculate and report overall extraction success rate."""
        golden_set = load_golden_set()
        successes = 0
        failures = []

        from app.extraction import extract_content

        for fixture in golden_set:
            html_path = FIXTURES_DIR / fixture["html_file"]
            html = html_path.read_text(errors="replace")
            expected = fixture["expected"]

            try:
                result = extract_content(html=html)
                content = result.content or ""
                min_length = expected.get("min_content_length", 100)

                if len(content) >= min_length:
                    successes += 1
                else:
                    failures.append(
                        f"{fixture['id']}: content too short ({len(content)} < {min_length})"
                    )
            except Exception as e:
                failures.append(f"{fixture['id']}: {str(e)}")

        success_rate = successes / len(golden_set) * 100

        # Print metrics (visible with pytest -s)
        print(f"\n\nExtraction Success Rate: {success_rate:.1f}%")
        print(f"  Passed: {successes}/{len(golden_set)}")
        if failures:
            print(f"  Failures:")
            for f in failures:
                print(f"    - {f}")

        # We expect at least 75% success rate on the golden set
        assert (
            success_rate >= 75
        ), f"Extraction success rate too low: {success_rate:.1f}%"


# =============================================================================
# Tests for Tiered Extraction Module (app/extraction.py)
# =============================================================================


class TestTieredExtraction:
    """Tests for the new tiered extraction module."""

    def test_extract_content_basic(self):
        """Test basic extraction with trafilatura."""
        from app.extraction import extract_content

        fixture = get_fixture_by_id("clean_article_001")
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        result = extract_content(html)

        assert result.success, f"Extraction failed: {result.error}"
        assert result.content is not None
        assert len(result.content) > 500
        assert result.method in ("trafilatura", "readability")
        assert result.quality_score > 0.5

    def test_extract_content_with_metadata(self):
        """Test that metadata is extracted from content."""
        from app.extraction import extract_content

        fixture = get_fixture_by_id("clean_article_001")
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        result = extract_content(html)

        # Should have metadata object
        assert result.metadata is not None
        # Metadata should be populated (may vary by extractor)
        assert hasattr(result.metadata, "author")
        assert hasattr(result.metadata, "date")
        assert hasattr(result.metadata, "images")

    def test_extract_content_stage_results(self):
        """Test that stage results are tracked."""
        from app.extraction import extract_content

        fixture = get_fixture_by_id("clean_article_001")
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        result = extract_content(html)

        # Should have at least one stage result
        assert len(result.stage_results) >= 1
        # First stage should be trafilatura
        assert result.stage_results[0].stage_name == "trafilatura"
        # Should have timing information
        assert result.stage_results[0].execution_time_ms >= 0

    def test_extract_content_fallback_chain(self):
        """Test that fallback chain works when primary fails."""
        from app.extraction import extract_content

        # Use minimal content fixture - may trigger fallback
        fixture = get_fixture_by_id("minimal_content_001")
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        result = extract_content(
            html, rss_summary="This is a fallback RSS summary for testing purposes."
        )

        # Should have attempted multiple stages
        assert len(result.stage_results) >= 1
        # Each stage should have a result
        for stage in result.stage_results:
            assert stage.attempted
            assert stage.stage_name in ("trafilatura", "readability", "salvage")

    def test_extract_content_salvage_mode(self):
        """Test salvage mode with RSS summary."""
        from app.extraction import extract_content

        # Pass empty HTML to force salvage
        result = extract_content(
            html="<html><body></body></html>",
            rss_summary="This is a fallback RSS summary that should be used when extraction fails completely.",
        )

        # Should eventually use salvage mode or fail gracefully
        assert len(result.stage_results) >= 1
        # If salvage succeeded, method should be rss_summary
        if result.success:
            assert result.method in ("trafilatura", "readability", "rss_summary")

    def test_quality_score_ranges(self):
        """Test that quality scores are in expected ranges."""
        from app.extraction import extract_content

        fixture = get_fixture_by_id("clean_article_001")
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        result = extract_content(html)

        # Quality score should be between 0 and 1
        assert 0.0 <= result.quality_score <= 1.0

        # Successful extraction should have reasonable quality
        if result.success:
            assert result.quality_score >= 0.3

    def test_extraction_result_to_dict(self):
        """Test ExtractionResult serialization."""
        from app.extraction import extract_content

        fixture = get_fixture_by_id("clean_article_001")
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        result = extract_content(html)
        result_dict = result.to_dict()

        # Should be serializable
        assert isinstance(result_dict, dict)
        assert "content" in result_dict
        assert "method" in result_dict
        assert "quality_score" in result_dict
        assert "metadata" in result_dict
        assert "stage_results" in result_dict

    @pytest.mark.parametrize("fixture_id", get_fixture_ids())
    def test_tiered_extraction_golden_set(self, fixture_id: str):
        """Test tiered extraction against full golden set."""
        from app.extraction import extract_content

        fixture = get_fixture_by_id(fixture_id)
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")
        expected = fixture["expected"]

        result = extract_content(html)

        # Check content length bounds if extraction succeeded
        if expected.get("should_succeed", True) and result.success and result.content:
            min_length = expected.get("min_content_length", 0)
            assert len(result.content) >= min_length * 0.8, (
                f"Content too short for {fixture_id}: "
                f"{len(result.content)} < {min_length * 0.8}"
            )


class TestExtractionDataClasses:
    """Tests for extraction data classes."""

    def test_stage_result_creation(self):
        """Test StageResult dataclass."""
        from app.extraction import StageResult

        stage = StageResult(
            stage_name="trafilatura",
            attempted=True,
            success=True,
            failure_reason=None,
            execution_time_ms=150,
            content_length=1500,
        )

        assert stage.stage_name == "trafilatura"
        assert stage.success is True
        assert stage.execution_time_ms == 150

        # Test serialization
        stage_dict = stage.to_dict()
        assert stage_dict["stage_name"] == "trafilatura"

    def test_extraction_metadata_creation(self):
        """Test ExtractionMetadata dataclass."""
        from datetime import datetime

        from app.extraction import ExtractionMetadata

        metadata = ExtractionMetadata(
            author="John Doe",
            date=datetime(2025, 1, 15),
            images=["image1.jpg", "image2.jpg"],
            categories=["tech", "ai"],
            tags=["python", "ml"],
            site_name="Tech Blog",
        )

        assert metadata.author == "John Doe"
        assert len(metadata.images) == 2
        assert "tech" in metadata.categories

        # Test serialization
        meta_dict = metadata.to_dict()
        assert meta_dict["author"] == "John Doe"
        assert meta_dict["date"] == "2025-01-15T00:00:00"

    def test_extraction_result_success_property(self):
        """Test ExtractionResult success property."""
        from app.extraction import ExtractionMetadata, ExtractionResult

        # Successful result
        success_result = ExtractionResult(
            content="Some content here",
            title="Title",
            method="trafilatura",
            quality_score=0.9,
            metadata=ExtractionMetadata(),
            error=None,
            stage_results=[],
            extraction_time_ms=100,
        )
        assert success_result.success is True

        # Failed result (no content)
        failed_result = ExtractionResult(
            content=None,
            title=None,
            method="failed",
            quality_score=0.0,
            metadata=ExtractionMetadata(),
            error="empty_content",
            stage_results=[],
            extraction_time_ms=100,
        )
        assert failed_result.success is False


# Utility function for running manual extraction tests
def manual_test_fixture(fixture_id: str) -> None:
    """
    Manually test a single fixture and print detailed results.

    Usage:
        python -c "from tests.test_extraction import manual_test_fixture; manual_test_fixture('clean_article_001')"
    """
    fixture = get_fixture_by_id(fixture_id)
    html_path = FIXTURES_DIR / fixture["html_file"]
    html = html_path.read_text(errors="replace")

    from app.extraction import extract_content

    result = extract_content(html=html)
    title = result.title or ""
    content = result.content or ""

    print(f"\n{'='*60}")
    print(f"Fixture: {fixture_id}")
    print(f"Category: {fixture['category']}")
    print(f"Description: {fixture['description']}")
    print(f"{'='*60}")
    print(f"\nExtracted Title: {title}")
    print(f"Content Length: {len(content)} chars")
    print(f"Extraction Method: {result.method}")
    print(f"Quality Score: {result.quality_score:.2f}")
    print(f"\nExpected:")
    print(f"  Title: {fixture['expected'].get('title', 'N/A')}")
    print(f"  Min Length: {fixture['expected'].get('min_content_length', 'N/A')}")
    print(f"  Max Length: {fixture['expected'].get('max_content_length', 'N/A')}")
    print(f"\nContent Preview (first 500 chars):")
    print(f"{content[:500]}...")
    print(f"\n{'='*60}")
