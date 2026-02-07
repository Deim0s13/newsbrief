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

        # Import extraction function
        # TODO: Update to use app.extraction once #181 is complete
        from app.readability import extract_readable

        title, content = extract_readable(html)

        # Basic assertions - extraction should produce something
        assert title is not None, f"Title extraction failed for {fixture_id}"
        assert content is not None, f"Content extraction failed for {fixture_id}"
        assert len(content) > 0, f"Empty content for {fixture_id}"

    @pytest.mark.parametrize("fixture_id", get_fixture_ids())
    def test_content_length_bounds(self, fixture_id: str):
        """Test that extracted content length is within expected bounds."""
        fixture = get_fixture_by_id(fixture_id)
        expected = fixture["expected"]
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        from app.readability import extract_readable

        _, content = extract_readable(html)
        content_length = len(content)

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

        from app.readability import extract_readable

        title, _ = extract_readable(html)

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

        from app.readability import extract_readable

        title, content = extract_readable(html)
        # Combine title and content for phrase search
        full_text = f"{title} {content}".lower()

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

        from app.readability import extract_readable

        _, content = extract_readable(html)
        content_lower = content.lower()

        # These navigation items should NOT be in the extracted content
        nav_items = ["trending now", "newsletter", "subscribe for daily"]
        for nav_item in nav_items:
            assert (
                nav_item not in content_lower
            ), f"Navigation/sidebar content found in extraction: '{nav_item}'"

    @pytest.mark.xfail(
        reason="readability-lxml doesn't filter inline ad markers - trafilatura should improve this"
    )
    def test_no_advertisement_markers(self):
        """Test that advertisement markers are not in extracted content."""
        fixture = get_fixture_by_id("heavy_boilerplate_001")
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        from app.readability import extract_readable

        _, content = extract_readable(html)
        content_lower = content.lower()

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

        from app.readability import extract_readable

        # Should not raise an exception
        title, content = extract_readable(html)

        # Should extract meaningful content despite malformed HTML
        assert (
            len(content) > 500
        ), "Should extract substantial content from malformed HTML"
        assert "s&p 500" in content.lower(), "Key content should be extracted"

    def test_paywall_graceful_degradation(self):
        """Test that paywalled content extracts what's available."""
        fixture = get_fixture_by_id("minimal_content_001")
        html_path = FIXTURES_DIR / fixture["html_file"]
        html = html_path.read_text(errors="replace")

        from app.readability import extract_readable

        title, content = extract_readable(html)

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

        from app.readability import extract_readable

        title, content = extract_readable(html)

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

        from app.readability import extract_readable

        for fixture in golden_set:
            html_path = FIXTURES_DIR / fixture["html_file"]
            html = html_path.read_text(errors="replace")
            expected = fixture["expected"]

            try:
                title, content = extract_readable(html)
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

    from app.readability import extract_readable

    title, content = extract_readable(html)

    print(f"\n{'='*60}")
    print(f"Fixture: {fixture_id}")
    print(f"Category: {fixture['category']}")
    print(f"Description: {fixture['description']}")
    print(f"{'='*60}")
    print(f"\nExtracted Title: {title}")
    print(f"Content Length: {len(content)} chars")
    print(f"\nExpected:")
    print(f"  Title: {fixture['expected'].get('title', 'N/A')}")
    print(f"  Min Length: {fixture['expected'].get('min_content_length', 'N/A')}")
    print(f"  Max Length: {fixture['expected'].get('max_content_length', 'N/A')}")
    print(f"\nContent Preview (first 500 chars):")
    print(f"{content[:500]}...")
    print(f"\n{'='*60}")
