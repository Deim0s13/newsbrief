"""
Robust LLM Output Parsing and Validation Module.

This module provides comprehensive handling of LLM-generated JSON outputs with:
- Pydantic models for structured validation
- JSON repair for common LLM mistakes
- Multi-strategy extraction for resilient parsing
- Retry logic with prompt adjustment
- Circuit breaker for failure protection
- Detailed metrics and logging

Created for Issue #107: Add robust structured output validation
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

# Type variable for generic model handling
T = TypeVar("T", bound=BaseModel)


# =============================================================================
# PYDANTIC MODELS FOR LLM OUTPUTS
# =============================================================================


class SynthesisOutput(BaseModel):
    """
    Validated output from story synthesis LLM calls.

    Used by: app/stories.py _generate_story_synthesis()
    """

    title: str = Field(
        default="",
        min_length=0,
        max_length=200,
        description="Concise news headline (8-12 words, under 80 chars)",
    )
    synthesis: str = Field(
        ...,
        min_length=10,
        description="2-3 sentence summary of the overall story",
    )
    key_points: List[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="List of 3-5 bullet points covering main facts",
    )
    why_it_matters: str = Field(
        default="",
        description="1-2 sentences explaining significance",
    )
    topics: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="List of 1-3 relevant topic tags",
    )
    entities: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="List of 3-7 key entities mentioned",
    )

    @field_validator("key_points", mode="before")
    @classmethod
    def ensure_key_points_list(cls, v: Any) -> List[str]:
        """Ensure key_points is a list, even if LLM returns a string."""
        if isinstance(v, str):
            # Split by newlines or bullet points
            points = re.split(r"[\n•\-\*]+", v)
            return [p.strip() for p in points if p.strip()]
        return v

    @field_validator("topics", "entities", mode="before")
    @classmethod
    def ensure_string_list(cls, v: Any) -> List[str]:
        """Ensure list fields contain strings."""
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return [str(item) for item in v if item]
        return []


class TopicOutput(BaseModel):
    """
    Validated output from topic classification LLM calls.

    Used by: app/topics.py _normalize_topic()
    """

    match: Literal["existing", "new", "general"] = Field(
        ...,
        description="Whether topic matches existing, is new, or general",
    )
    topic_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Topic identifier (lowercase, hyphenated)",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score from 0.0 to 1.0",
    )
    name: Optional[str] = Field(
        default=None,
        description="Human-readable name for new topics",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description for new topics",
    )

    @field_validator("topic_id", mode="before")
    @classmethod
    def normalize_topic_id(cls, v: Any) -> str:
        """Normalize topic ID to lowercase with hyphens."""
        if isinstance(v, str):
            return v.lower().strip().replace(" ", "-").replace("_", "-")
        return str(v)

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v: Any) -> float:
        """Coerce confidence to float, handling string inputs."""
        if isinstance(v, str):
            # Handle percentage strings like "85%"
            v = v.strip().rstrip("%")
            try:
                val = float(v)
                # If it looks like a percentage, convert
                if val > 1.0:
                    val = val / 100.0
                return max(0.0, min(1.0, val))
            except ValueError:
                return 0.5
        if isinstance(v, (int, float)):
            val = float(v)
            if val > 1.0:
                val = val / 100.0
            return max(0.0, min(1.0, val))
        return 0.5


class EntityOutput(BaseModel):
    """
    Validated output from entity extraction LLM calls.

    Used by: app/entities.py extract_entities_with_llm()
    """

    companies: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Company/organization names",
    )
    products: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Product/service names",
    )
    people: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Person names",
    )
    technologies: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Technology/framework names",
    )
    locations: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="Location/place names",
    )

    @field_validator(
        "companies", "products", "people", "technologies", "locations", mode="before"
    )
    @classmethod
    def ensure_string_list_limited(cls, v: Any) -> List[str]:
        """Ensure list contains strings and limit to 5 items."""
        if isinstance(v, str):
            return [v][:5]
        if isinstance(v, list):
            return [str(item).strip() for item in v if item][:5]
        return []


class EntityItem(BaseModel):
    """
    Single entity with metadata.

    Added in v0.8.1 (Issue #103) for enhanced entity extraction.
    """

    name: str = Field(..., min_length=1, max_length=100, description="Entity name")
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence score 0.0-1.0",
    )
    role: str = Field(
        default="mentioned",
        description="Entity role: primary_subject, mentioned, or quoted",
    )
    disambiguation: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Disambiguation hint (e.g., 'Apple Inc., tech company')",
    )

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, v: Any) -> str:
        """Clean and validate entity name."""
        if isinstance(v, str):
            return v.strip()[:100]
        return str(v).strip()[:100]

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v: Any) -> float:
        """Coerce confidence to float."""
        try:
            val = float(v)
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.8

    @field_validator("role", mode="before")
    @classmethod
    def validate_role(cls, v: Any) -> str:
        """Validate role is one of allowed values."""
        allowed = {"primary_subject", "mentioned", "quoted"}
        if isinstance(v, str) and v.lower() in allowed:
            return v.lower()
        return "mentioned"


class EnhancedEntityOutput(BaseModel):
    """
    Validated output from enhanced entity extraction LLM calls.

    Added in v0.8.1 (Issue #103) for richer entity data with:
    - Confidence scores per entity
    - Entity roles (primary_subject, mentioned, quoted)
    - Disambiguation hints

    Used by: app/entities.py extract_entities()
    """

    companies: List[EntityItem] = Field(
        default_factory=list,
        description="Company/organization entities with metadata",
    )
    products: List[EntityItem] = Field(
        default_factory=list,
        description="Product/service entities with metadata",
    )
    people: List[EntityItem] = Field(
        default_factory=list,
        description="Person entities with metadata",
    )
    technologies: List[EntityItem] = Field(
        default_factory=list,
        description="Technology/framework entities with metadata",
    )
    locations: List[EntityItem] = Field(
        default_factory=list,
        description="Location/place entities with metadata",
    )

    @field_validator(
        "companies", "products", "people", "technologies", "locations", mode="before"
    )
    @classmethod
    def normalize_entity_list(cls, v: Any) -> List[Dict[str, Any]]:
        """
        Normalize entity list, handling both simple strings and full objects.

        Supports:
        - List of strings: ["OpenAI", "Google"]
        - List of dicts: [{"name": "OpenAI", "confidence": 0.9, ...}]
        - Mixed: ["OpenAI", {"name": "Google", "confidence": 0.95}]
        """
        if not isinstance(v, list):
            return []

        result = []
        for item in v[:5]:  # Limit to 5 items
            if isinstance(item, str):
                # Simple string - convert to dict with defaults
                result.append(
                    {
                        "name": item.strip(),
                        "confidence": 0.8,
                        "role": "mentioned",
                        "disambiguation": None,
                    }
                )
            elif isinstance(item, dict):
                # Already a dict - ensure name exists
                if "name" in item and item["name"]:
                    result.append(item)
            elif hasattr(item, "name"):
                # Pydantic model or similar
                result.append(
                    {
                        "name": getattr(item, "name", ""),
                        "confidence": getattr(item, "confidence", 0.8),
                        "role": getattr(item, "role", "mentioned"),
                        "disambiguation": getattr(item, "disambiguation", None),
                    }
                )
        return result


class FreeFormTopicOutput(BaseModel):
    """
    Validated output from free-form topic classification.

    Used by: app/topics.py _classify_free_form()
    """

    topic: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Free-form topic description",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence score",
    )

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v: Any) -> float:
        """Coerce confidence to valid float."""
        try:
            val = float(v) if v is not None else 0.5
            if val > 1.0:
                val = val / 100.0
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.5


# =============================================================================
# JSON REPAIR FUNCTIONS
# =============================================================================


def repair_json(text: str) -> Tuple[str, List[str]]:
    """
    Attempt safe repairs on malformed JSON.

    Args:
        text: Potentially malformed JSON string

    Returns:
        Tuple of (repaired_text, list_of_repairs_made)

    Repairs applied (in order):
    1. Strip markdown code blocks
    2. Remove control characters
    3. Fix trailing commas
    4. Convert single quotes to double quotes (carefully)
    5. Quote unquoted keys
    6. Balance unclosed braces (simple cases)
    """
    repairs_made: List[str] = []
    original = text

    # 1. Strip markdown code blocks
    if "```" in text:
        # Handle ```json ... ``` or ``` ... ```
        pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        match = re.search(pattern, text)
        if match:
            text = match.group(1)
            repairs_made.append("markdown_stripped")

    # 2. Remove control characters (except newlines and tabs)
    control_chars = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    if control_chars.search(text):
        text = control_chars.sub("", text)
        repairs_made.append("control_chars_removed")

    # 3. Fix trailing commas before } or ]
    trailing_comma_pattern = r",(\s*[}\]])"
    if re.search(trailing_comma_pattern, text):
        text = re.sub(trailing_comma_pattern, r"\1", text)
        repairs_made.append("trailing_commas_fixed")

    # 4. Convert single quotes to double quotes (only for JSON structure)
    # This is tricky - we only want to convert quotes around keys/values
    # not apostrophes within strings
    if "'" in text and '"' not in text:
        # Simple case: no double quotes at all, likely all single quotes
        text = text.replace("'", '"')
        repairs_made.append("single_quotes_converted")
    elif re.search(r"{\s*'|,\s*'|':", text):
        # Mixed quotes - carefully convert structural single quotes
        # Convert 'key': to "key":
        text = re.sub(r"([{,]\s*)'([^']+)'(\s*:)", r'\1"\2"\3', text)
        # Convert : 'value' to : "value" (but not contractions)
        text = re.sub(r"(:\s*)'([^']*)'(\s*[,}\]])", r'\1"\2"\3', text)
        repairs_made.append("mixed_quotes_normalized")

    # 5. Quote unquoted keys (simple cases)
    # Match { key: or , key: where key is unquoted
    unquoted_key_pattern = r"([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)"
    if re.search(unquoted_key_pattern, text):
        # Check if these are actually unquoted (not already in quotes)
        def quote_if_needed(match: re.Match) -> str:
            prefix, key, suffix = match.groups()
            return f'{prefix}"{key}"{suffix}'

        text = re.sub(unquoted_key_pattern, quote_if_needed, text)
        repairs_made.append("unquoted_keys_fixed")

    # 6. Balance unclosed braces (simple cases only)
    open_braces = text.count("{") - text.count("}")
    open_brackets = text.count("[") - text.count("]")

    if open_braces > 0 and open_braces <= 2:
        text = text.rstrip() + "}" * open_braces
        repairs_made.append(f"added_{open_braces}_closing_braces")

    if open_brackets > 0 and open_brackets <= 2:
        text = text.rstrip() + "]" * open_brackets
        repairs_made.append(f"added_{open_brackets}_closing_brackets")

    return text, repairs_made


# =============================================================================
# MULTI-STRATEGY JSON EXTRACTION
# =============================================================================


class ExtractionStrategy(str, Enum):
    """Strategies for extracting JSON from LLM responses."""

    DIRECT = "direct"
    MARKDOWN_BLOCK = "markdown_block"
    BRACE_MATCH = "brace_match"
    GREEDY_REGEX = "greedy_regex"
    LINE_BY_LINE = "line_by_line"


def extract_json(response: str) -> Tuple[Optional[dict], ExtractionStrategy, List[str]]:
    """
    Try multiple strategies to extract JSON from LLM response.

    Args:
        response: Raw LLM response text

    Returns:
        Tuple of (parsed_dict, strategy_used, repairs_made)
        Returns (None, strategy, repairs) if all strategies fail.
    """
    if not response or not response.strip():
        return None, ExtractionStrategy.DIRECT, []

    strategies = [
        (_try_direct_parse, ExtractionStrategy.DIRECT),
        (_try_markdown_block, ExtractionStrategy.MARKDOWN_BLOCK),
        (_try_brace_match, ExtractionStrategy.BRACE_MATCH),
        (_try_greedy_regex, ExtractionStrategy.GREEDY_REGEX),
        (_try_line_by_line, ExtractionStrategy.LINE_BY_LINE),
    ]

    all_repairs: List[str] = []

    for strategy_func, strategy_name in strategies:
        try:
            result, repairs = strategy_func(response)
            all_repairs.extend(repairs)
            if result is not None:
                logger.debug(
                    f"JSON extraction succeeded with strategy: {strategy_name}"
                )
                return result, strategy_name, all_repairs
        except Exception as e:
            logger.debug(f"Strategy {strategy_name} failed: {e}")
            continue

    return None, ExtractionStrategy.LINE_BY_LINE, all_repairs


def _try_direct_parse(text: str) -> Tuple[Optional[dict], List[str]]:
    """Strategy 1: Direct JSON parse."""
    text = text.strip()
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result, []
    except json.JSONDecodeError:
        pass
    return None, []


def _try_markdown_block(text: str) -> Tuple[Optional[dict], List[str]]:
    """Strategy 2: Extract from markdown code block."""
    pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    match = re.search(pattern, text)
    if match:
        json_text = match.group(1).strip()
        try:
            result = json.loads(json_text)
            if isinstance(result, dict):
                return result, ["markdown_extracted"]
        except json.JSONDecodeError:
            # Try with repairs
            repaired, repairs = repair_json(json_text)
            try:
                result = json.loads(repaired)
                if isinstance(result, dict):
                    return result, ["markdown_extracted"] + repairs
            except json.JSONDecodeError:
                pass
    return None, []


def _try_brace_match(text: str) -> Tuple[Optional[dict], List[str]]:
    """Strategy 3: Find outermost matching braces."""
    # Find first { and match to its closing }
    start = text.find("{")
    if start == -1:
        return None, []

    depth = 0
    in_string = False
    escape_next = False
    end = -1

    for i, char in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if char == "\\":
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end > start:
        json_text = text[start:end]
        try:
            result = json.loads(json_text)
            if isinstance(result, dict):
                return result, ["brace_matched"]
        except json.JSONDecodeError:
            # Try with repairs
            repaired, repairs = repair_json(json_text)
            try:
                result = json.loads(repaired)
                if isinstance(result, dict):
                    return result, ["brace_matched"] + repairs
            except json.JSONDecodeError:
                pass

    return None, []


def _try_greedy_regex(text: str) -> Tuple[Optional[dict], List[str]]:
    """Strategy 4: Greedy regex to find largest JSON object."""
    # Try to find JSON object with regex
    pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
    matches = re.findall(pattern, text, re.DOTALL)

    # Try matches from largest to smallest
    for match in sorted(matches, key=len, reverse=True):
        try:
            result = json.loads(match)
            if isinstance(result, dict):
                return result, ["regex_extracted"]
        except json.JSONDecodeError:
            # Try with repairs
            repaired, repairs = repair_json(match)
            try:
                result = json.loads(repaired)
                if isinstance(result, dict):
                    return result, ["regex_extracted"] + repairs
            except json.JSONDecodeError:
                continue

    return None, []


def _try_line_by_line(text: str) -> Tuple[Optional[dict], List[str]]:
    """Strategy 5: Try to reconstruct JSON line by line."""
    lines = text.split("\n")
    json_lines: List[str] = []
    in_json = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("{"):
            in_json = True
        if in_json:
            json_lines.append(line)
        if stripped.endswith("}") and in_json:
            # Try to parse what we have
            candidate = "\n".join(json_lines)
            try:
                result = json.loads(candidate)
                if isinstance(result, dict):
                    return result, ["line_by_line_reconstructed"]
            except json.JSONDecodeError:
                # Try with repairs
                repaired, repairs = repair_json(candidate)
                try:
                    result = json.loads(repaired)
                    if isinstance(result, dict):
                        return result, ["line_by_line_reconstructed"] + repairs
                except json.JSONDecodeError:
                    pass
            # Reset and continue looking
            json_lines = []
            in_json = False

    return None, []


# =============================================================================
# METRICS AND LOGGING
# =============================================================================


class ErrorCategory(str, Enum):
    """Categories of LLM output parsing errors."""

    JSON_SYNTAX = "json_syntax"
    MISSING_FIELD = "missing_field"
    TYPE_ERROR = "type_error"
    EMPTY_RESPONSE = "empty_response"
    TRUNCATED = "truncated"
    VALIDATION_ERROR = "validation_error"
    UNKNOWN = "unknown"


@dataclass
class LLMParseMetrics:
    """Metrics for a single LLM output parse attempt."""

    success: bool
    strategy_used: str
    repair_applied: bool
    repairs_made: List[str] = field(default_factory=list)
    fields_extracted: List[str] = field(default_factory=list)
    fields_failed: List[str] = field(default_factory=list)
    retry_count: int = 0
    total_time_ms: int = 0
    error_category: Optional[ErrorCategory] = None
    error_message: Optional[str] = None
    model_class: str = ""
    raw_response_length: int = 0


@dataclass
class ParseAttemptLog:
    """Detailed log entry for a parse attempt."""

    timestamp: datetime
    model_class: str
    metrics: LLMParseMetrics
    raw_response_preview: str  # First 500 chars
    context: Dict[str, Any] = field(default_factory=dict)


class LLMOutputLogger:
    """
    Structured logging for LLM output parsing.

    Maintains in-memory log of recent attempts for debugging
    and logs to standard logger for persistence.
    """

    def __init__(self, max_entries: int = 1000):
        self._entries: List[ParseAttemptLog] = []
        self._max_entries = max_entries
        self._failure_counts: Dict[str, int] = {}

    def log_attempt(
        self,
        metrics: LLMParseMetrics,
        raw_response: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log a parse attempt with full context."""
        entry = ParseAttemptLog(
            timestamp=datetime.now(UTC),
            model_class=metrics.model_class,
            metrics=metrics,
            raw_response_preview=raw_response[:500] if raw_response else "",
            context=context or {},
        )

        # Add to in-memory log
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]

        # Update failure counts
        if not metrics.success:
            key = f"{metrics.model_class}:{metrics.error_category}"
            self._failure_counts[key] = self._failure_counts.get(key, 0) + 1

        # Log to standard logger
        if metrics.success:
            logger.debug(
                f"LLM parse success: model={metrics.model_class}, "
                f"strategy={metrics.strategy_used}, "
                f"repairs={metrics.repairs_made}, "
                f"time={metrics.total_time_ms}ms"
            )
        else:
            logger.warning(
                f"LLM parse failure: model={metrics.model_class}, "
                f"error={metrics.error_category}, "
                f"message={metrics.error_message}, "
                f"response_preview={raw_response[:200] if raw_response else 'empty'}"
            )

    def get_failure_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Generate summary of recent failures."""
        cutoff = datetime.now(UTC).timestamp() - (hours * 3600)
        recent = [
            e
            for e in self._entries
            if e.timestamp.timestamp() > cutoff and not e.metrics.success
        ]

        by_category: Dict[str, int] = {}
        by_model: Dict[str, int] = {}

        for entry in recent:
            cat = entry.metrics.error_category or ErrorCategory.UNKNOWN
            by_category[cat] = by_category.get(cat, 0) + 1
            by_model[entry.model_class] = by_model.get(entry.model_class, 0) + 1

        return {
            "total_failures": len(recent),
            "time_window_hours": hours,
            "by_category": by_category,
            "by_model": by_model,
            "recent_errors": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "model": e.model_class,
                    "category": e.metrics.error_category,
                    "message": e.metrics.error_message,
                }
                for e in recent[-10:]  # Last 10 failures
            ],
        }

    def get_success_rate(self, hours: int = 24) -> Dict[str, float]:
        """Calculate success rate by model class."""
        cutoff = datetime.now(UTC).timestamp() - (hours * 3600)
        recent = [e for e in self._entries if e.timestamp.timestamp() > cutoff]

        by_model: Dict[str, Dict[str, int]] = {}
        for entry in recent:
            model = entry.model_class
            if model not in by_model:
                by_model[model] = {"success": 0, "total": 0}
            by_model[model]["total"] += 1
            if entry.metrics.success:
                by_model[model]["success"] += 1

        return {
            model: counts["success"] / counts["total"] if counts["total"] > 0 else 0.0
            for model, counts in by_model.items()
        }


# Global logger instance
_output_logger = LLMOutputLogger()


def get_output_logger() -> LLMOutputLogger:
    """Get the global LLM output logger instance."""
    return _output_logger


# =============================================================================
# PARTIAL EXTRACTION
# =============================================================================


def extract_partial(
    data: dict,
    model_class: Type[T],
    required_fields: Optional[List[str]] = None,
) -> Tuple[Optional[T], List[str], List[str]]:
    """
    Extract as many valid fields as possible from parsed JSON.

    Args:
        data: Parsed JSON dictionary
        model_class: Pydantic model class to validate against
        required_fields: Fields that must be present (defaults to model's required fields)

    Returns:
        Tuple of (validated_model, extracted_fields, failed_fields)
        Returns (None, [], failed_fields) if required fields are missing.
    """
    if not data or not isinstance(data, dict):
        return None, [], list(model_class.model_fields.keys())

    extracted_fields: List[str] = []
    failed_fields: List[str] = []

    # Get model field info
    field_info = model_class.model_fields

    # Determine required fields
    if required_fields is None:
        required_fields = [
            name for name, info in field_info.items() if info.is_required()
        ]

    # Check required fields are present
    for field_name in required_fields:
        if field_name not in data or data[field_name] is None:
            failed_fields.append(field_name)

    if failed_fields and any(f in required_fields for f in failed_fields):
        # Required field missing - try to see what we can salvage
        logger.debug(f"Required fields missing: {failed_fields}")
        # Still attempt partial extraction for logging
        for field_name in field_info:
            if field_name in data and data[field_name] is not None:
                extracted_fields.append(field_name)
            elif field_name not in failed_fields:
                failed_fields.append(field_name)
        return None, extracted_fields, failed_fields

    # Try to create model with available data
    try:
        model = model_class.model_validate(data)
        extracted_fields = list(data.keys())
        return model, extracted_fields, []
    except ValidationError as e:
        # Identify which fields failed
        for error in e.errors():
            field_name = str(error.get("loc", ["unknown"])[0])
            if field_name not in failed_fields:
                failed_fields.append(field_name)

        # Try again without failed fields (use defaults)
        clean_data = {k: v for k, v in data.items() if k not in failed_fields}
        extracted_fields = list(clean_data.keys())

        try:
            model = model_class.model_validate(clean_data)
            return model, extracted_fields, failed_fields
        except ValidationError:
            return None, extracted_fields, failed_fields


# =============================================================================
# RETRY LOGIC
# =============================================================================


@dataclass
class RetryConfig:
    """Configuration for LLM call retry behavior."""

    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 10.0
    exponential_backoff: bool = True
    adjust_prompt_on_retry: bool = True

    # Prompt adjustments for retries
    retry_suffix: str = "\n\nIMPORTANT: Respond with ONLY valid JSON. No other text."
    strict_suffix: str = (
        "\n\nCRITICAL: Your response must be ONLY a valid JSON object. "
        "Do not include any explanation, markdown formatting, or extra text. "
        "Start your response with { and end with }."
    )


def calculate_retry_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay before next retry attempt."""
    if config.exponential_backoff:
        delay = config.base_delay_seconds * (2**attempt)
    else:
        delay = config.base_delay_seconds
    return min(delay, config.max_delay_seconds)


def adjust_prompt_for_retry(prompt: str, attempt: int, config: RetryConfig) -> str:
    """Adjust prompt based on retry attempt number."""
    if not config.adjust_prompt_on_retry:
        return prompt

    if attempt == 1:
        return prompt + config.retry_suffix
    else:
        return prompt + config.strict_suffix


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing fast
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""

    failure_threshold: int = 5  # Failures to open circuit
    success_threshold: int = 2  # Successes in half-open to close
    cooldown_seconds: int = 60  # Time before half-open


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failures exceeded threshold, fail fast
    - HALF_OPEN: After cooldown, testing if service recovered
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, potentially transitioning from OPEN to HALF_OPEN."""
        if self._state == CircuitState.OPEN:
            if self._last_failure_time:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.config.cooldown_seconds:
                    logger.info(
                        f"Circuit breaker '{self.name}' transitioning to HALF_OPEN"
                    )
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
        return self._state

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.config.success_threshold:
                logger.info(f"Circuit breaker '{self.name}' closing after recovery")
                self._state = CircuitState.CLOSED
                self._failure_count = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0  # Reset on success

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            logger.warning(
                f"Circuit breaker '{self.name}' reopening after failure in HALF_OPEN"
            )
            self._state = CircuitState.OPEN
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.config.failure_threshold:
                logger.warning(
                    f"Circuit breaker '{self.name}' opening after "
                    f"{self._failure_count} consecutive failures"
                )
                self._state = CircuitState.OPEN

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        current_state = self.state  # This may transition OPEN -> HALF_OPEN

        if current_state == CircuitState.CLOSED:
            return True
        elif current_state == CircuitState.HALF_OPEN:
            return True  # Allow test request
        else:  # OPEN
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure": self._last_failure_time,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "cooldown_seconds": self.config.cooldown_seconds,
            },
        }


# Circuit breakers for different LLM operations
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """Get or create a circuit breaker by name."""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name)
    return _circuit_breakers[name]


# =============================================================================
# MAIN PARSING INTERFACE
# =============================================================================


def parse_and_validate(
    response: str,
    model_class: Type[T],
    required_fields: Optional[List[str]] = None,
    allow_partial: bool = True,
    circuit_breaker_name: Optional[str] = None,
) -> Tuple[Optional[T], LLMParseMetrics]:
    """
    Parse and validate LLM response into a Pydantic model.

    This is the main entry point for parsing LLM outputs. It:
    1. Checks circuit breaker (if configured)
    2. Attempts JSON extraction with multiple strategies
    3. Applies repairs as needed
    4. Validates against Pydantic model
    5. Attempts partial extraction if full validation fails
    6. Logs metrics for analysis

    Args:
        response: Raw LLM response text
        model_class: Pydantic model class to validate against
        required_fields: Fields that must be present (defaults to model's required fields)
        allow_partial: Whether to attempt partial extraction on validation failure
        circuit_breaker_name: Name of circuit breaker to use (optional)

    Returns:
        Tuple of (validated_model, metrics)
        Model is None if parsing/validation failed.
    """
    start_time = time.time()
    metrics = LLMParseMetrics(
        success=False,
        strategy_used="none",
        repair_applied=False,
        model_class=model_class.__name__,
        raw_response_length=len(response) if response else 0,
    )

    # Check circuit breaker
    if circuit_breaker_name:
        breaker = get_circuit_breaker(circuit_breaker_name)
        if not breaker.allow_request():
            metrics.error_category = ErrorCategory.UNKNOWN
            metrics.error_message = f"Circuit breaker '{circuit_breaker_name}' is OPEN"
            metrics.total_time_ms = int((time.time() - start_time) * 1000)
            get_output_logger().log_attempt(metrics, response)
            return None, metrics

    # Handle empty response
    if not response or not response.strip():
        metrics.error_category = ErrorCategory.EMPTY_RESPONSE
        metrics.error_message = "Empty or whitespace-only response"
        metrics.total_time_ms = int((time.time() - start_time) * 1000)
        get_output_logger().log_attempt(metrics, response)
        if circuit_breaker_name:
            get_circuit_breaker(circuit_breaker_name).record_failure()
        return None, metrics

    # Extract JSON
    data, strategy, repairs = extract_json(response)
    metrics.strategy_used = strategy.value
    metrics.repairs_made = repairs
    metrics.repair_applied = len(repairs) > 0

    if data is None:
        metrics.error_category = ErrorCategory.JSON_SYNTAX
        metrics.error_message = "Failed to extract valid JSON from response"
        metrics.total_time_ms = int((time.time() - start_time) * 1000)
        get_output_logger().log_attempt(metrics, response)
        if circuit_breaker_name:
            get_circuit_breaker(circuit_breaker_name).record_failure()
        return None, metrics

    # Validate with Pydantic
    try:
        model = model_class.model_validate(data)
        metrics.success = True
        metrics.fields_extracted = list(data.keys())
        metrics.total_time_ms = int((time.time() - start_time) * 1000)
        get_output_logger().log_attempt(metrics, response)
        if circuit_breaker_name:
            get_circuit_breaker(circuit_breaker_name).record_success()
        return model, metrics

    except ValidationError as e:
        metrics.error_category = ErrorCategory.VALIDATION_ERROR
        metrics.error_message = str(e.errors()[:3])  # First 3 errors

        # Try partial extraction
        if allow_partial:
            partial_model, extracted, failed = extract_partial(
                data, model_class, required_fields
            )
            metrics.fields_extracted = extracted
            metrics.fields_failed = failed

            if partial_model is not None:
                metrics.success = True
                metrics.total_time_ms = int((time.time() - start_time) * 1000)
                get_output_logger().log_attempt(metrics, response)
                if circuit_breaker_name:
                    get_circuit_breaker(circuit_breaker_name).record_success()
                return partial_model, metrics

        metrics.total_time_ms = int((time.time() - start_time) * 1000)
        get_output_logger().log_attempt(metrics, response)
        if circuit_breaker_name:
            get_circuit_breaker(circuit_breaker_name).record_failure()
        return None, metrics


def parse_with_retry(
    llm_call: Callable[[str], str],
    prompt: str,
    model_class: Type[T],
    required_fields: Optional[List[str]] = None,
    allow_partial: bool = True,
    retry_config: Optional[RetryConfig] = None,
    circuit_breaker_name: Optional[str] = None,
) -> Tuple[Optional[T], LLMParseMetrics]:
    """
    Parse LLM output with automatic retry on failure.

    Args:
        llm_call: Function that takes a prompt and returns LLM response
        prompt: The prompt to send to the LLM
        model_class: Pydantic model class to validate against
        required_fields: Fields that must be present
        allow_partial: Whether to allow partial extraction
        retry_config: Retry configuration (defaults to RetryConfig())
        circuit_breaker_name: Circuit breaker to use

    Returns:
        Tuple of (validated_model, metrics)
    """
    config = retry_config or RetryConfig()
    final_metrics: Optional[LLMParseMetrics] = None

    for attempt in range(config.max_attempts):
        # Adjust prompt for retries
        current_prompt = (
            prompt if attempt == 0 else adjust_prompt_for_retry(prompt, attempt, config)
        )

        # Make LLM call
        try:
            response = llm_call(current_prompt)
        except Exception as e:
            logger.warning(f"LLM call failed on attempt {attempt + 1}: {e}")
            if attempt < config.max_attempts - 1:
                delay = calculate_retry_delay(attempt, config)
                time.sleep(delay)
            continue

        # Parse and validate
        model, metrics = parse_and_validate(
            response,
            model_class,
            required_fields=required_fields,
            allow_partial=allow_partial,
            circuit_breaker_name=circuit_breaker_name,
        )

        metrics.retry_count = attempt
        final_metrics = metrics

        if model is not None:
            return model, metrics

        # Wait before retry
        if attempt < config.max_attempts - 1:
            delay = calculate_retry_delay(attempt, config)
            logger.debug(f"Retrying in {delay:.1f}s after attempt {attempt + 1}")
            time.sleep(delay)

    # All attempts failed
    if final_metrics:
        final_metrics.retry_count = config.max_attempts - 1
        return None, final_metrics

    # No metrics at all (all LLM calls failed)
    return None, LLMParseMetrics(
        success=False,
        strategy_used="none",
        repair_applied=False,
        model_class=model_class.__name__,
        retry_count=config.max_attempts - 1,
        error_category=ErrorCategory.UNKNOWN,
        error_message="All LLM calls failed",
    )
