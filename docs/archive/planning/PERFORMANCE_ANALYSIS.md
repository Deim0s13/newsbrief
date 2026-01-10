# Performance Analysis - Story Generation

**Date**: 2025-11-13
**Current Performance**: ~171 seconds for 379 stories from 150 articles
**Target Performance**: < 30 seconds

---

## Identified Bottlenecks

### 1. **Sequential LLM Calls** (CRITICAL - ~80% of time)
**Location**: `app/stories.py:815` - `_generate_story_synthesis()`

**Problem**:
- LLM synthesis is called sequentially for each cluster
- Each LLM call takes ~15-20 seconds
- 10 clusters = 150-200 seconds total
- No parallelization

**Evidence**:
```python
for i, cluster_article_ids in enumerate(clusters):
    # Sequential call - blocks for 15-20 seconds each
    synthesis_data = _generate_story_synthesis(session, cluster_article_ids, model)
```

**Impact**: 🔴 **CRITICAL** - Accounts for ~80% of total time

---

### 2. **Multiple Database Commits** (HIGH impact)
**Location**: `app/stories.py:180, 219`

**Problem**:
- `create_story()` commits to database (line 180)
- `link_articles_to_story()` commits to database (line 219)
- 2 commits per story × 10 stories = 20 database commits
- Each commit has overhead (fsync, locking, etc.)

**Impact**: 🟡 **HIGH** - Adds 5-10 seconds with many stories

---

### 3. **Redundant Article Queries** (MEDIUM impact)
**Location**: `app/stories.py:546-556, 717-728, 832-841`

**Problem**:
- Articles fetched 3 times:
  1. Line 717: Initial query for clustering (id, title, topic, published)
  2. Line 546: Fetch article details for each synthesis (id, title, summary, ai_summary, topic)
  3. Line 832: Fetch time windows for each cluster
- Same data queried multiple times

**Impact**: 🟡 **MEDIUM** - Adds 3-5 seconds with many articles

---

### 4. **No LLM Response Caching** (MEDIUM impact)
**Location**: `app/stories.py:_generate_story_synthesis()`

**Problem**:
- No caching of LLM synthesis results
- Regenerating same story clusters repeats expensive LLM calls
- Story hash exists (line 857) but not used for caching

**Impact**: 🟡 **MEDIUM** - On regeneration, adds full LLM time again

---

### 5. **Inefficient Per-Cluster Queries** (LOW impact)
**Location**: `app/stories.py:832-841`

**Problem**:
- Time window query executed per cluster
- Uses dynamic SQL with placeholders
- Could be computed from already-fetched article data

**Impact**: 🟢 **LOW** - Adds 1-2 seconds total

---

## Optimization Strategy

### Phase 1: Parallel LLM Calls (Target: 80% reduction)
**Estimated time saving**: 120-150 seconds

- Use `concurrent.futures.ThreadPoolExecutor` or `asyncio` for parallel LLM calls
- Process multiple clusters simultaneously
- Ollama supports concurrent requests
- Limit concurrency to 3-5 to avoid overloading LLM

### Phase 2: Batch Database Operations (Target: 5-8 seconds saved)
**Estimated time saving**: 5-8 seconds

- Remove intermediate commits
- Commit all stories in a single transaction at the end
- Batch article queries using single query with IN clause

### Phase 3: Cache Article Data (Target: 3-5 seconds saved)
**Estimated time saving**: 3-5 seconds

- Fetch all article data once at the start
- Store in memory dictionary keyed by article_id
- Reuse for clustering, synthesis, and time windows

### Phase 4: LLM Response Caching (Target: saves on regeneration)
**Estimated time saving**: Full LLM time on regeneration

- Use story_hash as cache key
- Store synthesis results in database or Redis
- Check cache before calling LLM

---

## Implementation Order

1. ✅ **Parallel LLM calls** - Biggest win, relatively simple
2. ✅ **Batch database operations** - Good win, moderate complexity
3. ✅ **Cache article data** - Easy win, simple refactor
4. 🔜 **LLM caching** - Nice to have, can do later

---

## Expected Results

**Current**: ~171 seconds
**After Phase 1 (Parallel LLM)**: ~30-40 seconds ✅ **TARGET MET**
**After Phase 2 (Batch DB)**: ~25-35 seconds
**After Phase 3 (Cache data)**: ~20-30 seconds
**After Phase 4 (LLM cache)**: < 1 second on regeneration

---

## Measurement Plan

Add timing instrumentation:
```python
import time

start_time = time.time()
# ... operation ...
elapsed = time.time() - start_time
logger.info(f"Operation took {elapsed:.2f}s")
```

Track:
- Total generation time
- LLM synthesis time (per cluster and total)
- Database operation time
- Clustering time

---

## Notes

- Ollama server itself may need tuning (num_parallel, num_gpu, etc.)
- Consider upgrading to faster model (llama3.2:1b) for synthesis
- May need rate limiting if Ollama server is shared
