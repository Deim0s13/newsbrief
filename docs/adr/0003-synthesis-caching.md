# 0003 — Architecture Decision: LLM Synthesis Caching

**Status**: Accepted
**Date**: 2025-12-31
**Issue**: #46
**Milestone**: v0.6.3 - Performance

## Context

Story generation in NewsBrief synthesizes multiple articles into unified narratives using a local LLM (Ollama). Each synthesis requires an LLM call that takes 5-15 seconds depending on article count and model.

### Current State (v0.6.2)

- **No synthesis caching**: Each story generation calls the LLM, even for identical article sets
- **Duplicate prevention only**: `story_hash` prevents creating duplicate *stories*, but doesn't cache *synthesis results*
- **Performance impact**: Regenerating stories (e.g., after prompt improvements) re-synthesizes everything
- **No visibility**: No tracking of LLM token usage or synthesis performance over time

### Problem Statement

1. **Wasted LLM calls**: Same articles → same synthesis, but we call the LLM every time
2. **Slow iteration**: Testing prompt changes requires full regeneration
3. **No metrics**: Can't track performance trends or token costs
4. **Cache correctness**: If articles change, cached synthesis becomes stale

## Decision

### Implement Database-Backed Synthesis Cache with TTL and Invalidation

We will add a `synthesis_cache` table that stores LLM synthesis results keyed by a deterministic hash of the input (sorted article IDs + model name).

### Key Design Choices

#### 1. Database Cache vs In-Memory Cache

**Decision**: Database cache (SQLite)

| Option | Pros | Cons |
|--------|------|------|
| **In-memory (dict/LRU)** | Fast, simple | Lost on restart, memory limits, no persistence |
| **Redis/Memcached** | Fast, distributed | New dependency, overkill for local-first app |
| **Database (SQLite)** | Persistent, queryable, no new deps | Slightly slower than memory |

**Rationale**: SQLite is already our data store. A database cache:
- Survives application restarts
- Can be queried for metrics/debugging
- Doesn't add dependencies
- Performance is acceptable (cache lookup is ~1ms vs 5-15s LLM call)

#### 2. Cache Key Strategy

**Decision**: Hash of sorted article IDs + model name

```python
cache_key = hashlib.sha256(
    f"{sorted(article_ids)}:{model}".encode()
).hexdigest()
```

**Rationale**:
- **Sorted IDs**: Order-independent (articles [1,2,3] and [3,1,2] produce same synthesis)
- **Include model**: Different models produce different outputs
- **Exclude prompt**: Prompt changes should invalidate cache (handled by TTL/manual clear)

#### 3. Cache Invalidation Strategy

**Decision**: Three-layer invalidation

| Layer | Trigger | Mechanism |
|-------|---------|-----------|
| **TTL** | Time-based expiry | `expires_at` column, configurable (default 7 days) |
| **Article change** | Source article updated | Soft invalidation via `invalidated_at` |
| **Manual** | Prompt changes, debugging | API endpoint to clear cache |

**Rationale**:
- **TTL**: Ensures cache doesn't serve indefinitely stale data; allows prompt improvements to propagate
- **Article change**: Correctness - if an article's summary changes, synthesis may be wrong
- **Manual**: Operational control for developers

#### 4. Token Tracking

**Decision**: Estimate tokens using tiktoken, store per-synthesis

**Rationale**:
- Visibility into LLM usage patterns
- Helps optimize prompts for token efficiency
- No runtime cost (estimation, not API counting)

### Schema Design

```sql
CREATE TABLE synthesis_cache (
    id INTEGER PRIMARY KEY,
    cache_key TEXT UNIQUE NOT NULL,
    article_ids_json TEXT NOT NULL,
    model TEXT NOT NULL,
    synthesis TEXT NOT NULL,
    key_points_json TEXT,
    why_it_matters TEXT,
    topics_json TEXT,
    entities_json TEXT,
    token_count_input INTEGER,
    token_count_output INTEGER,
    generation_time_ms INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    invalidated_at DATETIME
);

CREATE INDEX idx_synthesis_cache_key ON synthesis_cache(cache_key);
CREATE INDEX idx_synthesis_cache_expires ON synthesis_cache(expires_at);
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNTHESIS_CACHE_ENABLED` | `true` | Feature flag to disable caching |
| `SYNTHESIS_CACHE_TTL_HOURS` | `168` (7 days) | Cache entry lifetime |
| `SYNTHESIS_TOKEN_TRACKING` | `true` | Enable token estimation |

## Consequences

### Positive

✅ **Performance**: Skip LLM calls for previously synthesized article combinations
✅ **Faster iteration**: Test UI/display changes without regenerating stories
✅ **Visibility**: Track token usage and synthesis performance over time
✅ **Correctness**: Invalidation ensures stale data doesn't persist
✅ **Operational control**: TTL + manual clear for production management
✅ **No new dependencies**: Uses existing SQLite database

### Negative

⚠️ **Storage growth**: Cache table grows with unique article combinations
⚠️ **Complexity**: Invalidation logic adds code paths
⚠️ **Cache misses on first run**: No benefit for brand-new article sets

### Mitigation

| Risk | Mitigation |
|------|------------|
| Storage growth | TTL auto-expires old entries; add cleanup job |
| Complexity | Well-documented code; comprehensive tests |
| Cold cache | Acceptable trade-off; cache warms over time |

## Implementation Plan

| Phase | Task | Effort |
|-------|------|--------|
| 1 | Schema + SQLAlchemy model | 30 min |
| 2 | Cache key generation | 20 min |
| 3 | Cache lookup/storage in `_generate_story_synthesis()` | 1 hour |
| 4 | Article change invalidation | 45 min |
| 5 | TTL configuration + cleanup | 30 min |
| 6 | Token tracking with tiktoken | 30 min |
| 7 | Performance metrics storage | 30 min |
| 8 | Testing | 45 min |
| **Total** | | **~4.5 hours** |

## Alternatives Considered

### Alternative 1: In-Memory LRU Cache

Use Python's `functools.lru_cache` or a simple dict.

**Rejected because**:
- Lost on restart (defeats purpose for long-running app)
- No persistence for metrics
- Memory constraints for large caches

### Alternative 2: No Caching (Status Quo)

Continue regenerating synthesis every time.

**Rejected because**:
- Wastes LLM resources
- Slow development iteration
- No visibility into performance trends

### Alternative 3: File-Based Cache

Store synthesis results as JSON files.

**Rejected because**:
- Harder to query for metrics
- File management complexity
- No benefit over SQLite for our use case

## Success Metrics

| Metric | Target |
|--------|--------|
| Cache hit rate | > 50% for regeneration scenarios |
| Synthesis time (cached) | < 10ms |
| Storage overhead | < 10MB for typical usage |

## References

- [Issue #46](https://github.com/Deim0s13/newsbrief/issues/46)
- [ADR 0002: Story-Based Aggregation](0002-story-based-aggregation.md)
- [Performance Optimizations](../planning/PERFORMANCE_OPTIMIZATIONS_IMPLEMENTED.md)

---

**Accepted**: 2025-12-31
**Implementation**: v0.6.3
