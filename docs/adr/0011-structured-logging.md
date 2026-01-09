# ADR 0011: Structured JSON Logging

## Status
Accepted

## Date
2026-01-10

## Context

NewsBrief currently uses Python's standard `logging` module with default text formatting across 13 modules. While functional for development, this approach has limitations:

1. **Parsing difficulty**: Text logs are hard to parse programmatically for monitoring tools
2. **Inconsistent context**: No standard way to include timing, counts, or request metadata
3. **Environment mismatch**: Same log format in development (where human readability matters) and production (where machine parsing matters)
4. **No request timing**: Key operations (feed refresh, story generation, LLM calls) lack duration tracking

As we move toward production readiness, structured logging becomes essential for:
- Integration with log aggregation tools (ELK, Loki, CloudWatch)
- Performance monitoring and alerting
- Debugging production issues
- Capacity planning based on timing data

## Decision

Implement environment-aware structured logging:

### 1. JSON Format for Production
```json
{
  "timestamp": "2026-01-10T12:00:00.000Z",
  "level": "INFO",
  "logger": "app.feeds",
  "message": "Feed refresh completed",
  "duration_ms": 1234,
  "feeds_processed": 15,
  "articles_ingested": 42,
  "environment": "production"
}
```

### 2. Human-Readable Format for Development
```
2026-01-10 12:00:00 INFO  [app.feeds] Feed refresh completed (1234ms, 15 feeds, 42 articles)
```

### 3. Implementation Approach

- **Centralized configuration**: Single `app/logging_config.py` module
- **Environment detection**: Uses `ENVIRONMENT` variable (already in use for DEV banner)
- **Timing decorator**: `@log_timing` decorator for key operations
- **Structured context**: `extra={}` parameter for additional fields
- **Backward compatible**: Existing `logger.info()` calls continue to work

### 4. Key Operations to Instrument

| Operation | Module | Metrics |
|-----------|--------|---------|
| Feed refresh | `feeds.py` | duration_ms, feeds_count, articles_ingested |
| Story generation | `stories.py` | duration_ms, stories_created, articles_clustered |
| LLM synthesis | `llm.py` | duration_ms, model, prompt_tokens, completion_tokens |
| Database queries | `db.py` | duration_ms, query_type |

## Alternatives Considered

### 1. Third-party Logging Library (structlog, loguru)
- **Pros**: Rich features, better structured logging support
- **Cons**: Additional dependency, learning curve
- **Decision**: Standard library is sufficient for current needs

### 2. OpenTelemetry
- **Pros**: Industry standard, traces + metrics + logs
- **Cons**: Significant complexity, requires collector infrastructure
- **Decision**: Defer to v0.8.x when adding full observability stack

### 3. Keep Current Approach
- **Pros**: No changes needed
- **Cons**: Doesn't meet production observability requirements
- **Decision**: Rejected

## Consequences

### Positive
- Logs are machine-parseable in production
- Developers retain readable logs during development
- Performance timing data available for monitoring
- Foundation for future alerting and dashboards
- No additional dependencies

### Negative
- Slight increase in log message size (JSON overhead)
- Existing log consumers may need updates (minimal impact)
- Need to update existing log calls to include context (gradual migration)

### Neutral
- Log level configuration unchanged
- File rotation/retention not addressed (separate concern)

## Implementation Notes

1. Create `app/logging_config.py` with `configure_logging()` function
2. Call `configure_logging()` in `app/main.py` startup
3. Add `@log_timing` decorator to key functions
4. Gradually add `extra={}` context to existing log calls
5. Update `compose.yaml` to set `ENVIRONMENT=production`

## References

- [Python Logging Cookbook](https://docs.python.org/3/howto/logging-cookbook.html)
- [12 Factor App - Logs](https://12factor.net/logs)
- Issue #20: Structured logging
