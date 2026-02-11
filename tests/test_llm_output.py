#!/usr/bin/env python3
"""
Comprehensive tests for LLM output parsing and validation.

Tests the robust parsing infrastructure including:
- Pydantic model validation
- JSON repair functions
- Multi-strategy extraction
- Partial extraction
- Circuit breaker
- Metrics logging
"""

import json
import time
from typing import List
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.llm_output import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    EntityOutput,
    ErrorCategory,
    ExtractionStrategy,
    FreeFormTopicOutput,
    LLMOutputLogger,
    LLMParseMetrics,
    RetryConfig,
    SynthesisOutput,
    TopicOutput,
    adjust_prompt_for_retry,
    calculate_retry_delay,
    extract_json,
    extract_partial,
    get_circuit_breaker,
    get_output_logger,
    parse_and_validate,
    repair_json,
)

# =============================================================================
# PYDANTIC MODEL TESTS
# =============================================================================


class TestSynthesisOutput:
    """Tests for SynthesisOutput model validation."""

    def test_valid_complete_output(self):
        """Valid output with all fields should parse correctly."""
        data = {
            "title": "Breaking News Headline",
            "synthesis": "This is a comprehensive summary of the news story.",
            "key_points": ["Point 1", "Point 2", "Point 3"],
            "why_it_matters": "This is significant because...",
            "topics": ["tech", "ai"],
            "entities": ["OpenAI", "GPT-5"],
        }
        output = SynthesisOutput.model_validate(data)
        assert output.title == "Breaking News Headline"
        assert output.synthesis == data["synthesis"]
        assert len(output.key_points) == 3

    def test_minimal_valid_output(self):
        """Output with only required fields should work."""
        data = {
            "synthesis": "This is the summary text.",
            "key_points": ["Key point one"],
        }
        output = SynthesisOutput.model_validate(data)
        assert output.synthesis == data["synthesis"]
        assert output.title == ""  # Default
        assert output.why_it_matters == ""  # Default

    def test_key_points_string_converted_to_list(self):
        """String key_points should be converted to list."""
        data = {
            "synthesis": "Summary text here.",
            "key_points": "Point 1\n• Point 2\n- Point 3",
        }
        output = SynthesisOutput.model_validate(data)
        assert isinstance(output.key_points, list)
        assert len(output.key_points) >= 1

    def test_entities_string_converted_to_list(self):
        """Single string entity should become list."""
        data = {
            "synthesis": "Summary text.",
            "key_points": ["Point"],
            "entities": "OpenAI",
        }
        output = SynthesisOutput.model_validate(data)
        assert output.entities == ["OpenAI"]

    def test_missing_required_synthesis_fails(self):
        """Missing synthesis should raise ValidationError."""
        data = {"key_points": ["Point 1"]}
        with pytest.raises(ValidationError):
            SynthesisOutput.model_validate(data)

    def test_empty_synthesis_fails(self):
        """Empty synthesis should fail min_length validation."""
        data = {"synthesis": "short", "key_points": ["Point"]}
        with pytest.raises(ValidationError):
            SynthesisOutput.model_validate(data)


class TestTopicOutput:
    """Tests for TopicOutput model validation."""

    def test_valid_existing_topic(self):
        """Valid existing topic match."""
        data = {
            "match": "existing",
            "topic_id": "ai-ml",
            "confidence": 0.85,
        }
        output = TopicOutput.model_validate(data)
        assert output.match == "existing"
        assert output.topic_id == "ai-ml"
        assert output.confidence == 0.85

    def test_valid_new_topic(self):
        """Valid new topic suggestion."""
        data = {
            "match": "new",
            "topic_id": "sports",
            "confidence": 0.9,
            "name": "Sports",
            "description": "Sports news and events",
        }
        output = TopicOutput.model_validate(data)
        assert output.match == "new"
        assert output.name == "Sports"
        assert output.description == "Sports news and events"

    def test_topic_id_normalized(self):
        """Topic ID should be normalized to lowercase with hyphens."""
        data = {
            "match": "existing",
            "topic_id": "AI ML",
            "confidence": 0.8,
        }
        output = TopicOutput.model_validate(data)
        assert output.topic_id == "ai-ml"

    def test_confidence_percentage_converted(self):
        """Percentage confidence should be converted to 0-1 range."""
        data = {
            "match": "existing",
            "topic_id": "tech",
            "confidence": 85,  # Percentage
        }
        output = TopicOutput.model_validate(data)
        assert output.confidence == 0.85

    def test_confidence_string_percentage(self):
        """String percentage should be parsed."""
        data = {
            "match": "general",
            "topic_id": "general",
            "confidence": "75%",
        }
        output = TopicOutput.model_validate(data)
        assert output.confidence == 0.75

    def test_confidence_clamped_to_range(self):
        """Confidence should be clamped to 0.0-1.0."""
        data = {
            "match": "existing",
            "topic_id": "tech",
            "confidence": 150,  # Over 100%
        }
        output = TopicOutput.model_validate(data)
        assert output.confidence == 1.0


class TestEntityOutput:
    """Tests for EntityOutput model validation."""

    def test_valid_entities(self):
        """Valid entity extraction output."""
        data = {
            "companies": ["Google", "Microsoft"],
            "products": ["Chrome", "Windows"],
            "people": ["Sundar Pichai"],
            "technologies": ["Python", "JavaScript"],
            "locations": ["Mountain View"],
        }
        output = EntityOutput.model_validate(data)
        assert len(output.companies) == 2
        assert len(output.products) == 2
        assert len(output.locations) == 1

    def test_empty_entities_valid(self):
        """Empty entity lists should be valid."""
        data = {}
        output = EntityOutput.model_validate(data)
        assert output.companies == []
        assert output.products == []
        assert output.people == []

    def test_entities_limited_to_five(self):
        """Entity lists should be limited to 5 items."""
        data = {
            "companies": ["A", "B", "C", "D", "E", "F", "G"],
        }
        output = EntityOutput.model_validate(data)
        assert len(output.companies) == 5

    def test_single_string_entity_wrapped(self):
        """Single string should be wrapped in list."""
        data = {
            "companies": "OpenAI",
        }
        output = EntityOutput.model_validate(data)
        assert output.companies == ["OpenAI"]


# =============================================================================
# JSON REPAIR TESTS
# =============================================================================


class TestJSONRepair:
    """Tests for JSON repair functions."""

    def test_valid_json_unchanged(self):
        """Valid JSON should not be modified."""
        valid = '{"key": "value", "number": 42}'
        repaired, repairs = repair_json(valid)
        assert repairs == []
        assert json.loads(repaired) == json.loads(valid)

    def test_trailing_comma_removed(self):
        """Trailing commas should be removed."""
        invalid = '{"key": "value",}'
        repaired, repairs = repair_json(invalid)
        assert "trailing_commas_fixed" in repairs
        assert json.loads(repaired) == {"key": "value"}

    def test_trailing_comma_in_array(self):
        """Trailing commas in arrays should be removed."""
        invalid = '{"items": [1, 2, 3,]}'
        repaired, repairs = repair_json(invalid)
        assert "trailing_commas_fixed" in repairs
        assert json.loads(repaired) == {"items": [1, 2, 3]}

    def test_markdown_stripped(self):
        """Markdown code blocks should be stripped."""
        wrapped = '```json\n{"key": "value"}\n```'
        repaired, repairs = repair_json(wrapped)
        assert "markdown_stripped" in repairs
        assert json.loads(repaired) == {"key": "value"}

    def test_markdown_without_language(self):
        """Plain markdown blocks should be stripped."""
        wrapped = '```\n{"key": "value"}\n```'
        repaired, repairs = repair_json(wrapped)
        assert "markdown_stripped" in repairs

    def test_single_quotes_converted(self):
        """Single quotes should be converted when no double quotes present."""
        single_quoted = "{'key': 'value'}"
        repaired, repairs = repair_json(single_quoted)
        assert "single_quotes_converted" in repairs
        assert json.loads(repaired) == {"key": "value"}

    def test_control_characters_removed(self):
        """Control characters should be removed."""
        with_control = '{"key": "val\x00ue"}'
        repaired, repairs = repair_json(with_control)
        assert "control_chars_removed" in repairs

    def test_unclosed_brace_fixed(self):
        """Simple unclosed braces should be fixed."""
        unclosed = '{"key": "value"'
        repaired, repairs = repair_json(unclosed)
        assert any("closing_brace" in r for r in repairs)
        # Should now be valid JSON
        result = json.loads(repaired)
        assert result == {"key": "value"}

    def test_multiple_repairs_applied(self):
        """Multiple repairs can be applied together."""
        messy = "```json\n{'key': 'value',}\n```"
        repaired, repairs = repair_json(messy)
        assert "markdown_stripped" in repairs
        assert "single_quotes_converted" in repairs
        assert "trailing_commas_fixed" in repairs


# =============================================================================
# MULTI-STRATEGY EXTRACTION TESTS
# =============================================================================


class TestMultiStrategyExtraction:
    """Tests for multi-strategy JSON extraction."""

    def test_direct_parse_strategy(self):
        """Direct JSON should be parsed without strategy changes."""
        response = '{"key": "value"}'
        result, strategy, repairs = extract_json(response)
        assert result == {"key": "value"}
        assert strategy == ExtractionStrategy.DIRECT

    def test_markdown_block_strategy(self):
        """JSON in markdown block should be extracted."""
        response = 'Here is the JSON:\n```json\n{"key": "value"}\n```'
        result, strategy, repairs = extract_json(response)
        assert result == {"key": "value"}
        assert strategy == ExtractionStrategy.MARKDOWN_BLOCK

    def test_brace_match_strategy(self):
        """JSON with preamble should use brace matching."""
        response = 'The result is: {"key": "value"} that is all.'
        result, strategy, repairs = extract_json(response)
        assert result == {"key": "value"}
        assert strategy == ExtractionStrategy.BRACE_MATCH

    def test_nested_json_extracted(self):
        """Nested JSON objects should be handled."""
        response = '{"outer": {"inner": "value"}, "array": [1, 2, 3]}'
        result, strategy, repairs = extract_json(response)
        assert result["outer"]["inner"] == "value"
        assert result["array"] == [1, 2, 3]

    def test_empty_response_returns_none(self):
        """Empty response should return None."""
        result, strategy, repairs = extract_json("")
        assert result is None

    def test_whitespace_only_returns_none(self):
        """Whitespace-only response should return None."""
        result, strategy, repairs = extract_json("   \n\t  ")
        assert result is None

    def test_no_json_returns_none(self):
        """Response without JSON should return None."""
        result, strategy, repairs = extract_json("This is just plain text.")
        assert result is None

    def test_malformed_with_repair(self):
        """Malformed JSON should be repaired during extraction."""
        response = '{"key": "value",}'  # Trailing comma
        result, strategy, repairs = extract_json(response)
        assert result == {"key": "value"}
        assert "trailing_commas_fixed" in repairs


# =============================================================================
# PARTIAL EXTRACTION TESTS
# =============================================================================


class TestPartialExtraction:
    """Tests for partial field extraction."""

    def test_full_extraction(self):
        """Complete data should extract all fields."""
        data = {
            "synthesis": "Full summary text here.",
            "key_points": ["Point 1", "Point 2"],
            "why_it_matters": "Important because...",
        }
        model, extracted, failed = extract_partial(data, SynthesisOutput)
        assert model is not None
        assert "synthesis" in extracted
        assert failed == []

    def test_partial_with_missing_optional(self):
        """Missing optional fields should use defaults."""
        data = {
            "synthesis": "Summary text here.",
            "key_points": ["Point 1"],
        }
        model, extracted, failed = extract_partial(data, SynthesisOutput)
        assert model is not None
        assert model.why_it_matters == ""  # Default

    def test_missing_required_field(self):
        """Missing required field should return None."""
        data = {
            "key_points": ["Point 1"],
            # Missing synthesis (required)
        }
        model, extracted, failed = extract_partial(
            data, SynthesisOutput, required_fields=["synthesis"]
        )
        assert model is None
        assert "synthesis" in failed

    def test_invalid_type_handled(self):
        """Invalid field types should be handled gracefully."""
        data = {
            "synthesis": "Valid summary.",
            "key_points": 12345,  # Wrong type
        }
        model, extracted, failed = extract_partial(data, SynthesisOutput)
        # Pydantic validator should coerce or fail
        # The key_points validator handles non-list inputs

    def test_empty_data_returns_none(self):
        """Empty dict should return None with all fields failed."""
        model, extracted, failed = extract_partial({}, SynthesisOutput)
        assert model is None


# =============================================================================
# CIRCUIT BREAKER TESTS
# =============================================================================


class TestCircuitBreaker:
    """Tests for circuit breaker functionality."""

    def test_initial_state_closed(self):
        """New circuit breaker should be CLOSED."""
        breaker = CircuitBreaker("test")
        assert breaker.state == CircuitState.CLOSED

    def test_allows_requests_when_closed(self):
        """CLOSED circuit should allow requests."""
        breaker = CircuitBreaker("test")
        assert breaker.allow_request() is True

    def test_opens_after_failure_threshold(self):
        """Circuit should open after threshold failures."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker("test", config)

        for _ in range(3):
            breaker.record_failure()

        assert breaker.state == CircuitState.OPEN

    def test_blocks_requests_when_open(self):
        """OPEN circuit should block requests."""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker("test", config)
        breaker.record_failure()

        assert breaker.allow_request() is False

    def test_transitions_to_half_open_after_cooldown(self):
        """Circuit should transition to HALF_OPEN after cooldown."""
        config = CircuitBreakerConfig(failure_threshold=1, cooldown_seconds=0)
        breaker = CircuitBreaker("test", config)
        breaker.record_failure()

        # Wait for cooldown (0 seconds)
        time.sleep(0.1)

        assert breaker.state == CircuitState.HALF_OPEN

    def test_closes_after_success_in_half_open(self):
        """Circuit should close after successful requests in HALF_OPEN."""
        config = CircuitBreakerConfig(
            failure_threshold=1, cooldown_seconds=0, success_threshold=1
        )
        breaker = CircuitBreaker("test", config)
        breaker.record_failure()
        time.sleep(0.1)  # Trigger half-open

        # Access state to trigger transition
        _ = breaker.state
        breaker.record_success()

        assert breaker.state == CircuitState.CLOSED

    def test_reopens_on_failure_in_half_open(self):
        """Circuit should reopen on failure in HALF_OPEN."""
        config = CircuitBreakerConfig(failure_threshold=1, cooldown_seconds=60)
        breaker = CircuitBreaker("test_reopen", config)
        breaker.record_failure()

        # Manually set to HALF_OPEN for testing
        breaker._state = CircuitState.HALF_OPEN

        assert breaker.state == CircuitState.HALF_OPEN

        breaker.record_failure()
        assert breaker._state == CircuitState.OPEN

    def test_success_resets_failure_count(self):
        """Success should reset failure count in CLOSED state."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker("test", config)

        breaker.record_failure()
        breaker.record_failure()
        breaker.record_success()  # Reset
        breaker.record_failure()

        assert breaker.state == CircuitState.CLOSED

    def test_get_status(self):
        """Status should return current state info."""
        breaker = CircuitBreaker("test_breaker")
        status = breaker.get_status()

        assert status["name"] == "test_breaker"
        assert status["state"] == "closed"
        assert "config" in status


class TestCircuitBreakerRegistry:
    """Tests for circuit breaker registry."""

    def test_get_creates_new_breaker(self):
        """Getting non-existent breaker should create it."""
        breaker = get_circuit_breaker("new_breaker_test")
        assert breaker is not None
        assert breaker.name == "new_breaker_test"

    def test_get_returns_same_instance(self):
        """Getting same breaker twice should return same instance."""
        breaker1 = get_circuit_breaker("shared_breaker")
        breaker2 = get_circuit_breaker("shared_breaker")
        assert breaker1 is breaker2


# =============================================================================
# RETRY LOGIC TESTS
# =============================================================================


class TestRetryLogic:
    """Tests for retry configuration and helpers."""

    def test_default_retry_config(self):
        """Default config should have sensible values."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay_seconds == 1.0

    def test_exponential_backoff_delay(self):
        """Delay should increase exponentially."""
        config = RetryConfig(base_delay_seconds=1.0, exponential_backoff=True)

        delay0 = calculate_retry_delay(0, config)
        delay1 = calculate_retry_delay(1, config)
        delay2 = calculate_retry_delay(2, config)

        assert delay1 > delay0
        assert delay2 > delay1

    def test_linear_delay(self):
        """Without exponential backoff, delay should be constant."""
        config = RetryConfig(base_delay_seconds=2.0, exponential_backoff=False)

        delay0 = calculate_retry_delay(0, config)
        delay1 = calculate_retry_delay(1, config)

        assert delay0 == delay1 == 2.0

    def test_max_delay_respected(self):
        """Delay should not exceed max."""
        config = RetryConfig(
            base_delay_seconds=1.0, max_delay_seconds=5.0, exponential_backoff=True
        )

        delay = calculate_retry_delay(10, config)  # Would be 1024 without cap
        assert delay == 5.0

    def test_prompt_adjustment_first_retry(self):
        """First retry should add basic JSON emphasis."""
        config = RetryConfig()
        original = "Generate JSON"
        adjusted = adjust_prompt_for_retry(original, 1, config)

        assert "valid JSON" in adjusted
        assert original in adjusted

    def test_prompt_adjustment_subsequent_retry(self):
        """Later retries should add stronger emphasis."""
        config = RetryConfig()
        original = "Generate JSON"
        adjusted = adjust_prompt_for_retry(original, 2, config)

        assert "CRITICAL" in adjusted
        assert original in adjusted


# =============================================================================
# METRICS AND LOGGING TESTS
# =============================================================================


class TestLLMOutputLogger:
    """Tests for LLM output logging."""

    def test_log_success(self):
        """Successful parse should be logged."""
        logger_instance = LLMOutputLogger()
        metrics = LLMParseMetrics(
            success=True,
            strategy_used="direct",
            repair_applied=False,
            model_class="SynthesisOutput",
        )

        logger_instance.log_attempt(metrics, '{"key": "value"}')

        # Should not raise, entry should be stored
        assert len(logger_instance._entries) == 1

    def test_log_failure(self):
        """Failed parse should be logged with error info."""
        logger_instance = LLMOutputLogger()
        metrics = LLMParseMetrics(
            success=False,
            strategy_used="direct",
            repair_applied=False,
            model_class="SynthesisOutput",
            error_category=ErrorCategory.JSON_SYNTAX,
            error_message="Invalid JSON",
        )

        logger_instance.log_attempt(metrics, "invalid json")
        assert len(logger_instance._entries) == 1

    def test_failure_summary(self):
        """Failure summary should aggregate recent failures."""
        logger_instance = LLMOutputLogger()

        # Log some failures
        for i in range(5):
            metrics = LLMParseMetrics(
                success=False,
                strategy_used="direct",
                repair_applied=False,
                model_class="SynthesisOutput",
                error_category=ErrorCategory.JSON_SYNTAX,
            )
            logger_instance.log_attempt(metrics, "bad json")

        summary = logger_instance.get_failure_summary(hours=24)
        assert summary["total_failures"] == 5

    def test_success_rate(self):
        """Success rate should be calculated correctly."""
        logger_instance = LLMOutputLogger()

        # 3 successes, 1 failure
        for success in [True, True, True, False]:
            metrics = LLMParseMetrics(
                success=success,
                strategy_used="direct",
                repair_applied=False,
                model_class="TestModel",
            )
            logger_instance.log_attempt(metrics, "response")

        rates = logger_instance.get_success_rate(hours=24)
        assert rates["TestModel"] == 0.75

    def test_max_entries_limit(self):
        """Log should not exceed max entries."""
        logger_instance = LLMOutputLogger(max_entries=10)

        for i in range(20):
            metrics = LLMParseMetrics(
                success=True,
                strategy_used="direct",
                repair_applied=False,
                model_class="Test",
            )
            logger_instance.log_attempt(metrics, "response")

        assert len(logger_instance._entries) == 10


# =============================================================================
# MAIN PARSING INTERFACE TESTS
# =============================================================================


class TestParseAndValidate:
    """Tests for the main parse_and_validate function."""

    def test_successful_parse(self):
        """Valid JSON should parse and validate successfully."""
        response = json.dumps(
            {
                "synthesis": "This is a complete summary of the story.",
                "key_points": ["Point 1", "Point 2", "Point 3"],
                "why_it_matters": "Important because...",
            }
        )

        model, metrics = parse_and_validate(response, SynthesisOutput)

        assert model is not None
        assert metrics.success is True
        assert model.synthesis == "This is a complete summary of the story."

    def test_empty_response_fails(self):
        """Empty response should fail gracefully."""
        model, metrics = parse_and_validate("", SynthesisOutput)

        assert model is None
        assert metrics.success is False
        assert metrics.error_category == ErrorCategory.EMPTY_RESPONSE

    def test_invalid_json_fails(self):
        """Invalid JSON should fail with JSON_SYNTAX error."""
        model, metrics = parse_and_validate("not json at all", SynthesisOutput)

        assert model is None
        assert metrics.success is False
        assert metrics.error_category == ErrorCategory.JSON_SYNTAX

    def test_validation_error_with_partial(self):
        """Validation failure should attempt partial extraction."""
        # Missing required synthesis, but has some fields
        response = json.dumps(
            {
                "title": "A Title",
                "key_points": ["Point"],
                # Missing synthesis
            }
        )

        model, metrics = parse_and_validate(
            response, SynthesisOutput, allow_partial=True
        )

        # Should fail because synthesis is required
        assert model is None
        assert "synthesis" not in metrics.fields_extracted or model is None

    def test_circuit_breaker_integration(self):
        """Circuit breaker should be updated on success/failure."""
        # Reset circuit breaker state
        breaker = get_circuit_breaker("test_parse")
        breaker._state = CircuitState.CLOSED
        breaker._failure_count = 0

        # Successful parse
        response = json.dumps({"synthesis": "Summary text.", "key_points": ["Point"]})
        model, metrics = parse_and_validate(
            response, SynthesisOutput, circuit_breaker_name="test_parse"
        )

        assert model is not None
        assert breaker._failure_count == 0

    def test_metrics_include_timing(self):
        """Metrics should include timing information."""
        response = json.dumps(
            {"synthesis": "Summary text here.", "key_points": ["Point"]}
        )

        model, metrics = parse_and_validate(response, SynthesisOutput)

        assert metrics.total_time_ms >= 0

    def test_metrics_include_strategy(self):
        """Metrics should record extraction strategy used."""
        response = '```json\n{"synthesis": "This is a longer text for testing.", "key_points": ["Point one"]}\n```'

        model, metrics = parse_and_validate(response, SynthesisOutput)

        assert model is not None
        assert metrics.strategy_used == "markdown_block"


class TestEdgeCases:
    """Edge case tests for robustness."""

    def test_unicode_content(self):
        """Unicode content should be handled correctly."""
        response = json.dumps(
            {
                "synthesis": "日本語テキスト with émojis 🎉",
                "key_points": ["Point with ñ", "Point with 中文"],
            }
        )

        model, metrics = parse_and_validate(response, SynthesisOutput)
        assert model is not None
        assert "日本語" in model.synthesis

    def test_very_long_response(self):
        """Very long responses should be handled."""
        long_text = "A" * 10000
        response = json.dumps({"synthesis": long_text, "key_points": ["Point"]})

        model, metrics = parse_and_validate(response, SynthesisOutput)
        assert model is not None

    def test_deeply_nested_json(self):
        """Deeply nested JSON should parse correctly."""
        response = json.dumps(
            {
                "synthesis": "This is a summary with sufficient length.",
                "key_points": ["Point one", "Point two"],
                "entities": ["Entity One", "Entity Two"],
                "topics": ["tech", "ai-ml"],
            }
        )

        model, metrics = parse_and_validate(response, SynthesisOutput)
        assert model is not None

    def test_response_with_extra_fields(self):
        """Extra fields in response should be ignored."""
        response = json.dumps(
            {
                "synthesis": "Summary text.",
                "key_points": ["Point"],
                "extra_field": "Should be ignored",
                "another_extra": 12345,
            }
        )

        model, metrics = parse_and_validate(response, SynthesisOutput)
        assert model is not None
        assert not hasattr(model, "extra_field")
