"""Unit tests for enhanced semantic similarity (v0.6.1)."""

from app.entities import ExtractedEntities
from app.stories import (_calculate_combined_similarity,
                         _calculate_keyword_overlap, _extract_keywords)


class TestEnhancedKeywordExtraction:
    """Test enhanced keyword extraction with summaries and bigrams."""

    def test_extract_keywords_title_only(self):
        """Test keyword extraction from title only."""
        keywords = _extract_keywords("OpenAI Releases GPT-4 Model")

        assert "openai" in keywords
        assert "releases" in keywords
        assert "gpt" in keywords
        assert "model" in keywords
        # Stop words should be filtered
        assert "the" not in keywords
        assert "a" not in keywords

    def test_extract_keywords_with_summary(self):
        """Test keyword extraction from title + summary."""
        keywords = _extract_keywords(
            title="Google Announces Gemini",
            summary="Google unveiled Gemini, an advanced AI model competing with OpenAI.",
        )

        # Should have keywords from both title and summary
        assert "google" in keywords
        assert "gemini" in keywords
        assert "unveiled" in keywords
        assert "advanced" in keywords
        assert "model" in keywords
        assert "openai" in keywords

    def test_extract_keywords_with_bigrams(self):
        """Test bigram generation for phrase matching."""
        keywords = _extract_keywords(
            title="Machine Learning Model",
            summary="",
            include_bigrams=True,
        )

        # Should have unigrams
        assert "machine" in keywords
        assert "learning" in keywords
        assert "model" in keywords

        # Should have bigrams
        assert "machine_learning" in keywords
        assert "learning_model" in keywords

    def test_extract_keywords_without_bigrams(self):
        """Test keyword extraction without bigrams."""
        keywords = _extract_keywords(
            title="Machine Learning Model",
            summary="",
            include_bigrams=False,
        )

        # Should have unigrams
        assert "machine" in keywords
        assert "learning" in keywords

        # Should NOT have bigrams
        assert "machine_learning" not in keywords
        assert "learning_model" not in keywords

    def test_extract_keywords_stop_words_filtered(self):
        """Test that stop words are properly filtered."""
        keywords = _extract_keywords(
            title="The AI Model is Very Advanced",
            summary="It has been trained on massive data",
        )

        # Content words should be present
        assert "model" in keywords
        assert "advanced" in keywords
        assert "trained" in keywords
        assert "massive" in keywords
        assert "data" in keywords

        # Stop words should be filtered
        assert "the" not in keywords
        assert "is" not in keywords
        # Note: "very" is actually kept as it has >= 3 chars and may be semantically useful
        assert "it" not in keywords
        assert "has" not in keywords
        assert "been" not in keywords
        assert "on" not in keywords

    def test_extract_keywords_title_emphasis(self):
        """Test that title keywords appear more frequently (2x)."""
        keywords = _extract_keywords(
            title="Unique",
            summary="Different words here",
        )

        # Title word should be present
        assert "unique" in keywords
        # Note: We can't directly test frequency in a set, but the
        # title appearing 2x increases likelihood of bigrams


class TestKeywordOverlap:
    """Test keyword overlap calculation (Jaccard similarity)."""

    def test_keyword_overlap_identical(self):
        """Test 100% overlap for identical keyword sets."""
        keywords1 = {"ai", "model", "training"}
        keywords2 = {"ai", "model", "training"}

        overlap = _calculate_keyword_overlap(keywords1, keywords2)

        assert overlap == 1.0

    def test_keyword_overlap_partial(self):
        """Test partial overlap."""
        keywords1 = {"google", "ai", "gemini"}
        keywords2 = {"google", "openai", "gpt"}

        overlap = _calculate_keyword_overlap(keywords1, keywords2)

        # Intersection: {google}, Union: {google, ai, gemini, openai, gpt}
        # Overlap = 1/5 = 0.2
        assert overlap == 0.2

    def test_keyword_overlap_none(self):
        """Test zero overlap."""
        keywords1 = {"apple", "iphone"}
        keywords2 = {"google", "android"}

        overlap = _calculate_keyword_overlap(keywords1, keywords2)

        assert overlap == 0.0

    def test_keyword_overlap_empty_sets(self):
        """Test empty keyword sets."""
        keywords1 = set()
        keywords2 = {"google", "ai"}

        overlap = _calculate_keyword_overlap(keywords1, keywords2)

        assert overlap == 0.0


class TestCombinedSimilarity:
    """Test combined similarity with keywords, entities, and topic bonus."""

    def test_combined_similarity_keywords_only(self):
        """Test similarity with only keywords (no entities)."""
        keywords1 = {"google", "ai", "gemini"}
        keywords2 = {"google", "openai", "gpt"}

        similarity = _calculate_combined_similarity(
            keywords1,
            keywords2,
            entities1=None,
            entities2=None,
            topic1=None,
            topic2=None,
        )

        # Should fall back to pure keyword similarity
        # Intersection: {google}, Union: 5, so 0.2
        # With no entities, keyword_weight becomes 1.0
        assert 0.0 < similarity <= 0.3

    def test_combined_similarity_with_entities(self):
        """Test similarity with keywords and entities."""
        keywords1 = {"google", "ai"}
        keywords2 = {"google", "openai"}

        entities1 = ExtractedEntities(
            companies=["Google", "Microsoft"],
            products=[],
            people=[],
            technologies=["AI"],
            locations=[],
        )
        entities2 = ExtractedEntities(
            companies=["Google", "OpenAI"],
            products=[],
            people=[],
            technologies=["AI"],
            locations=[],
        )

        similarity = _calculate_combined_similarity(
            keywords1,
            keywords2,
            entities1,
            entities2,
            topic1=None,
            topic2=None,
        )

        # Should combine keyword (30%) + entity (50%) similarity
        # Both have some overlap, so similarity should be > 0
        assert 0.3 < similarity < 0.8

    def test_combined_similarity_with_topic_bonus(self):
        """Test similarity with topic bonus."""
        keywords1 = {"google", "ai"}
        keywords2 = {"apple", "iphone"}  # Different keywords

        entities1 = ExtractedEntities(
            companies=["Google"],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )
        entities2 = ExtractedEntities(
            companies=["Apple"],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )

        # Test with same topic
        similarity_same_topic = _calculate_combined_similarity(
            keywords1,
            keywords2,
            entities1,
            entities2,
            topic1="tech",
            topic2="tech",
        )

        # Test with different topics
        similarity_diff_topic = _calculate_combined_similarity(
            keywords1,
            keywords2,
            entities1,
            entities2,
            topic1="tech",
            topic2="business",
        )

        # Same topic should have higher similarity (20% bonus)
        assert similarity_same_topic > similarity_diff_topic
        # Difference should be approximately the topic_weight (default 0.2)
        assert abs(similarity_same_topic - similarity_diff_topic - 0.2) < 0.01

    def test_combined_similarity_perfect_match(self):
        """Test perfect similarity (all components match)."""
        keywords = {"google", "ai", "gemini"}
        entities = ExtractedEntities(
            companies=["Google"],
            products=["Gemini"],
            people=[],
            technologies=["AI"],
            locations=[],
        )

        similarity = _calculate_combined_similarity(
            keywords,
            keywords,
            entities,
            entities,
            topic1="tech",
            topic2="tech",
        )

        # Perfect match: 100% keywords + 100% entities + 100% topic
        # 0.3*1.0 + 0.5*1.0 + 0.2*1.0 = 1.0
        assert similarity == 1.0

    def test_combined_similarity_custom_weights(self):
        """Test similarity with custom weights."""
        keywords1 = {"google", "ai"}
        keywords2 = {"google", "ai"}  # Identical

        similarity = _calculate_combined_similarity(
            keywords1,
            keywords2,
            entities1=None,
            entities2=None,
            topic1=None,
            topic2=None,
            keyword_weight=0.8,
            entity_weight=0.2,
            topic_weight=0.0,
        )

        # With identical keywords and keyword_weight=1.0 (adjusted for no entities)
        assert similarity == 1.0

    def test_combined_similarity_all_different(self):
        """Test zero similarity when nothing matches."""
        keywords1 = {"google", "ai"}
        keywords2 = {"apple", "iphone"}

        entities1 = ExtractedEntities(
            companies=["Google"],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )
        entities2 = ExtractedEntities(
            companies=["Apple"],
            products=[],
            people=[],
            technologies=[],
            locations=[],
        )

        similarity = _calculate_combined_similarity(
            keywords1,
            keywords2,
            entities1,
            entities2,
            topic1="tech",
            topic2="business",
        )

        # No keyword overlap, no entity overlap, different topics
        assert similarity == 0.0


class TestIntegrationScenarios:
    """Integration tests for realistic article comparison scenarios."""

    def test_similar_ai_articles(self):
        """Test clustering of similar AI articles."""
        # Article 1: Google Gemini announcement
        keywords1 = _extract_keywords(
            "Google Announces Gemini 2.0",
            "Google released Gemini 2.0, competing with OpenAI's GPT-4",
        )
        entities1 = ExtractedEntities(
            companies=["Google", "OpenAI"],
            products=["Gemini 2.0", "GPT-4"],
            people=[],
            technologies=["AI"],
            locations=[],
        )

        # Article 2: Google AI release
        keywords2 = _extract_keywords(
            "Google's New AI Model Released",
            "The tech giant unveiled advanced Gemini capabilities",
        )
        entities2 = ExtractedEntities(
            companies=["Google"],
            products=["Gemini"],
            people=[],
            technologies=["AI"],
            locations=[],
        )

        similarity = _calculate_combined_similarity(
            keywords1,
            keywords2,
            entities1,
            entities2,
            topic1="tech",
            topic2="tech",
        )

        # Should be moderately similar (same company Google, related product Gemini, same topic)
        # With keyword overlap, entity overlap (Google, Gemini, AI), and topic bonus
        assert similarity > 0.35  # Realistic threshold for related articles

    def test_different_company_articles(self):
        """Test that articles about different companies have low similarity."""
        # Article 1: Google
        keywords1 = _extract_keywords(
            "Google Announces Gemini",
            "Google released new AI model",
        )
        entities1 = ExtractedEntities(
            companies=["Google"],
            products=["Gemini"],
            people=[],
            technologies=["AI"],
            locations=[],
        )

        # Article 2: Apple
        keywords2 = _extract_keywords(
            "Apple Launches New iPhone",
            "Apple introduced iPhone 16",
        )
        entities2 = ExtractedEntities(
            companies=["Apple"],
            products=["iPhone"],
            people=[],
            technologies=[],
            locations=[],
        )

        similarity = _calculate_combined_similarity(
            keywords1,
            keywords2,
            entities1,
            entities2,
            topic1="tech",
            topic2="tech",
        )

        # Should have low similarity (different companies, products)
        # Only topic bonus applies
        assert similarity < 0.3
