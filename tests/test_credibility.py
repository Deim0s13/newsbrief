#!/usr/bin/env python3
"""
Tests for source credibility module.

Tests domain canonicalization, score calculation, MBFC mapping,
and synthesis eligibility per ADR-0028.

Part of Issue #196: Create source_credibility database schema
"""
from app.credibility import (
    FactualReporting,
    MBFCMapping,
    PoliticalBias,
    SourceType,
    calculate_credibility_score,
    canonicalize_domain,
    extract_domain_from_url,
    is_eligible_for_synthesis,
    map_mbfc_record,
    validate_mbfc_dataset,
)

# -----------------------------------------------------------------------------
# Domain Canonicalization Tests
# -----------------------------------------------------------------------------


class TestCanonicalizeDomain:
    """Tests for domain canonicalization."""

    def test_full_url_https(self):
        """Extract domain from HTTPS URL."""
        assert (
            canonicalize_domain("https://www.nytimes.com/article/foo") == "nytimes.com"
        )

    def test_full_url_http(self):
        """Extract domain from HTTP URL."""
        assert canonicalize_domain("http://bbc.co.uk/news") == "bbc.co.uk"

    def test_strips_www(self):
        """Strip www. prefix."""
        assert canonicalize_domain("www.theguardian.com") == "theguardian.com"

    def test_strips_mobile_m(self):
        """Strip m. mobile prefix."""
        assert canonicalize_domain("m.bbc.co.uk") == "bbc.co.uk"

    def test_strips_mobile_full(self):
        """Strip mobile. prefix."""
        assert canonicalize_domain("mobile.reuters.com") == "reuters.com"

    def test_strips_amp(self):
        """Strip amp. prefix."""
        assert (
            canonicalize_domain("https://amp.theguardian.com/story")
            == "theguardian.com"
        )

    def test_strips_news(self):
        """Strip news. prefix."""
        assert canonicalize_domain("news.ycombinator.com") == "ycombinator.com"

    def test_bare_domain(self):
        """Handle bare domain input."""
        assert canonicalize_domain("nytimes.com") == "nytimes.com"

    def test_bare_domain_with_path(self):
        """Handle bare domain with path."""
        assert canonicalize_domain("nytimes.com/section/article") == "nytimes.com"

    def test_removes_port(self):
        """Remove port number."""
        assert canonicalize_domain("localhost:8080") is None  # No TLD
        assert canonicalize_domain("example.com:443") == "example.com"

    def test_lowercase(self):
        """Convert to lowercase."""
        assert canonicalize_domain("NYTimes.COM") == "nytimes.com"
        assert canonicalize_domain("https://BBC.CO.UK/News") == "bbc.co.uk"

    def test_empty_input(self):
        """Handle empty input."""
        assert canonicalize_domain("") is None
        assert canonicalize_domain("   ") is None
        assert canonicalize_domain(None) is None

    def test_invalid_input(self):
        """Handle invalid input."""
        assert canonicalize_domain("not-a-domain") is None  # No TLD
        assert canonicalize_domain("://") is None

    def test_protocol_relative_url(self):
        """Handle protocol-relative URLs."""
        assert canonicalize_domain("//www.example.com/path") == "example.com"

    def test_preserves_subdomains(self):
        """Preserve non-stripped subdomains."""
        assert canonicalize_domain("blog.example.com") == "blog.example.com"
        assert canonicalize_domain("api.nytimes.com") == "api.nytimes.com"


class TestExtractDomainFromUrl:
    """Tests for extract_domain_from_url (alias for canonicalize_domain)."""

    def test_extracts_domain(self):
        """Basic domain extraction."""
        assert (
            extract_domain_from_url("https://www.reuters.com/article/123")
            == "reuters.com"
        )


# -----------------------------------------------------------------------------
# Credibility Score Calculation Tests (ADR-0028: factual only)
# -----------------------------------------------------------------------------


class TestCalculateCredibilityScore:
    """Tests for credibility score calculation."""

    def test_very_high(self):
        """Very high factual reporting = 1.0."""
        assert calculate_credibility_score("very_high") == 1.0
        assert calculate_credibility_score("VERY_HIGH") == 1.0
        assert calculate_credibility_score("very high") == 1.0

    def test_high(self):
        """High factual reporting = 0.85."""
        assert calculate_credibility_score("high") == 0.85

    def test_mostly_factual(self):
        """Mostly factual = 0.70."""
        assert calculate_credibility_score("mostly_factual") == 0.70
        assert calculate_credibility_score("mostly factual") == 0.70

    def test_mixed(self):
        """Mixed = 0.50."""
        assert calculate_credibility_score("mixed") == 0.50

    def test_low(self):
        """Low = 0.30."""
        assert calculate_credibility_score("low") == 0.30

    def test_very_low(self):
        """Very low = 0.15."""
        assert calculate_credibility_score("very_low") == 0.15

    def test_unknown_returns_none(self):
        """Unknown factual rating returns None."""
        assert calculate_credibility_score("unknown") is None
        assert calculate_credibility_score("") is None
        assert calculate_credibility_score(None) is None

    def test_bias_not_used(self):
        """Verify bias is not used in score (ADR-0028)."""
        # Score should be the same regardless of what we might imagine bias to be
        # This is a conceptual test - bias is a separate field
        score_left = calculate_credibility_score("high")
        score_right = calculate_credibility_score("high")
        assert score_left == score_right == 0.85


# -----------------------------------------------------------------------------
# Synthesis Eligibility Tests (ADR-0028)
# -----------------------------------------------------------------------------


class TestSynthesisEligibility:
    """Tests for synthesis eligibility by source type."""

    def test_news_eligible(self):
        """Standard news sources are eligible."""
        assert is_eligible_for_synthesis("news") is True
        assert is_eligible_for_synthesis("NEWS") is True

    def test_pro_science_eligible(self):
        """Pro-science sources are eligible."""
        assert is_eligible_for_synthesis("pro_science") is True

    def test_satire_ineligible(self):
        """Satire is not eligible."""
        assert is_eligible_for_synthesis("satire") is False

    def test_conspiracy_ineligible(self):
        """Conspiracy sources are not eligible."""
        assert is_eligible_for_synthesis("conspiracy") is False

    def test_fake_news_ineligible(self):
        """Fake news is not eligible."""
        assert is_eligible_for_synthesis("fake_news") is False

    def test_unknown_defaults_eligible(self):
        """Unknown types default to eligible."""
        assert is_eligible_for_synthesis("unknown_type") is True
        assert is_eligible_for_synthesis("") is True
        assert is_eligible_for_synthesis(None) is True


# -----------------------------------------------------------------------------
# MBFC Mapping Tests
# -----------------------------------------------------------------------------


class TestMapMbfcRecord:
    """Tests for MBFC record mapping."""

    def test_basic_mapping(self):
        """Map a basic MBFC record."""
        record = {
            "url": "https://www.nytimes.com",
            "name": "New York Times",
            "bias": "left-center",
            "factual": "high",
            "mbfc_url": "https://mediabiasfactcheck.com/new-york-times/",
        }
        result = map_mbfc_record(record)

        assert result is not None
        assert result.domain == "nytimes.com"
        assert result.name == "New York Times"
        assert result.source_type == "news"
        assert result.factual_reporting == "high"
        assert result.bias == "left_center"
        assert result.credibility_score == 0.85
        assert result.is_eligible_for_synthesis is True
        assert result.provider_url == "https://mediabiasfactcheck.com/new-york-times/"

    def test_satire_mapping(self):
        """Map satire source - should be ineligible."""
        record = {
            "url": "https://theonion.com",
            "name": "The Onion",
            "category": "satire",
        }
        result = map_mbfc_record(record)

        assert result is not None
        assert result.source_type == "satire"
        assert result.is_eligible_for_synthesis is False

    def test_conspiracy_mapping(self):
        """Map conspiracy source - should be ineligible."""
        record = {
            "url": "https://example-conspiracy.com",
            "name": "Conspiracy Site",
            "category": "conspiracy-pseudoscience",
        }
        result = map_mbfc_record(record)

        assert result is not None
        assert result.source_type == "conspiracy"
        assert result.is_eligible_for_synthesis is False

    def test_questionable_mapping(self):
        """Map questionable source (MBFC term) to fake_news."""
        record = {
            "url": "https://fake-news-site.com",
            "name": "Fake News Site",
            "category": "questionable",
        }
        result = map_mbfc_record(record)

        assert result is not None
        assert result.source_type == "fake_news"
        assert result.is_eligible_for_synthesis is False

    def test_missing_url_returns_none(self):
        """Record without URL should return None."""
        record = {"name": "Missing URL Source"}
        result = map_mbfc_record(record)
        assert result is None

    def test_invalid_url_returns_none(self):
        """Record with invalid URL should return None."""
        record = {"url": "not-a-valid-url-at-all"}
        result = map_mbfc_record(record)
        assert result is None

    def test_handles_domain_field(self):
        """Handle 'domain' field as alternative to 'url'."""
        record = {
            "domain": "bbc.co.uk",
            "name": "BBC",
            "bias": "center",
            "factual": "very high",
        }
        result = map_mbfc_record(record)

        assert result is not None
        assert result.domain == "bbc.co.uk"
        assert result.credibility_score == 1.0

    def test_least_biased_maps_to_center(self):
        """MBFC 'least biased' should map to 'center'."""
        record = {
            "url": "https://apnews.com",
            "name": "AP News",
            "bias": "least biased",
            "factual": "very high",
        }
        result = map_mbfc_record(record)

        assert result is not None
        assert result.bias == "center"


# -----------------------------------------------------------------------------
# Dataset Validation Tests
# -----------------------------------------------------------------------------


class TestValidateMbfcDataset:
    """Tests for MBFC dataset validation."""

    def test_validates_dataset(self):
        """Validate a small dataset."""
        records = [
            {"url": "https://nytimes.com", "name": "NYT", "factual": "high"},
            {"url": "https://bbc.co.uk", "name": "BBC", "factual": "very high"},
            {"name": "Missing URL"},  # Invalid
        ]
        stats = validate_mbfc_dataset(records)

        assert stats["total"] == 3
        assert stats["valid"] == 2
        assert stats["invalid"] == 1
        assert stats["by_factual"].get("high") == 1
        assert stats["by_factual"].get("very_high") == 1

    def test_empty_dataset(self):
        """Handle empty dataset."""
        stats = validate_mbfc_dataset([])
        assert stats["total"] == 0
        assert stats["valid"] == 0
        assert stats["invalid"] == 0


# -----------------------------------------------------------------------------
# Enum Tests
# -----------------------------------------------------------------------------


class TestEnums:
    """Tests for credibility enums."""

    def test_source_type_values(self):
        """SourceType enum has expected values."""
        assert SourceType.NEWS.value == "news"
        assert SourceType.SATIRE.value == "satire"
        assert SourceType.CONSPIRACY.value == "conspiracy"
        assert SourceType.FAKE_NEWS.value == "fake_news"
        assert SourceType.PRO_SCIENCE.value == "pro_science"

    def test_factual_reporting_values(self):
        """FactualReporting enum has expected values."""
        assert FactualReporting.VERY_HIGH.value == "very_high"
        assert FactualReporting.LOW.value == "low"

    def test_political_bias_values(self):
        """PoliticalBias enum has expected values."""
        assert PoliticalBias.LEFT.value == "left"
        assert PoliticalBias.CENTER.value == "center"
        assert PoliticalBias.RIGHT.value == "right"


# -----------------------------------------------------------------------------
# Run tests with pytest
# -----------------------------------------------------------------------------


def main():
    """Run all tests and report results."""
    print("Testing Source Credibility Module\n")
    print("=" * 60)

    # Domain canonicalization
    tests = [
        (
            "www.example.com -> example.com",
            canonicalize_domain("www.example.com") == "example.com",
        ),
        ("m.bbc.co.uk -> bbc.co.uk", canonicalize_domain("m.bbc.co.uk") == "bbc.co.uk"),
        (
            "https://amp.site.com/x -> site.com",
            canonicalize_domain("https://amp.site.com/x") == "site.com",
        ),
        ("Empty returns None", canonicalize_domain("") is None),
    ]

    # Score calculation
    tests.extend(
        [
            ("very_high = 1.0", calculate_credibility_score("very_high") == 1.0),
            ("high = 0.85", calculate_credibility_score("high") == 0.85),
            ("mixed = 0.50", calculate_credibility_score("mixed") == 0.50),
            ("unknown = None", calculate_credibility_score("unknown") is None),
        ]
    )

    # Eligibility
    tests.extend(
        [
            ("news is eligible", is_eligible_for_synthesis("news") is True),
            ("satire is ineligible", is_eligible_for_synthesis("satire") is False),
            (
                "fake_news is ineligible",
                is_eligible_for_synthesis("fake_news") is False,
            ),
        ]
    )

    passed = 0
    failed = 0

    for name, result in tests:
        if result:
            print(f"PASS: {name}")
            passed += 1
        else:
            print(f"FAIL: {name}")
            failed += 1

    print("=" * 60)
    print(f"\nSummary: {passed}/{len(tests)} tests passed")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())
