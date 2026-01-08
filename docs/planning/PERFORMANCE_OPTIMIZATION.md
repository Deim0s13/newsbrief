# Story Generation Performance Optimization

## 📊 Current Performance (Baseline)

**Test Date**: 2025-11-12
**Environment**: Local development (MacBook)
**LLM**: Ollama (llama3.1:8b)

### Metrics

| Metric | Value | Notes |
|--------|-------|-------|
| **Story Generation Time** | 171 seconds | 150 articles → 379 stories |
| **Throughput** | ~0.88 articles/sec | Very slow |
| **LLM Success Rate** | 100% | All stories LLM-generated (despite warnings) |
| **Fallback Rate** | 0% | No fallbacks used |
| **HTTP Timeout Rate** | High | `/stories/generate` times out |

### Observed Issues

1. **Blocking LLM Calls**: Sequential calls to Ollama for each story cluster
2. **No Concurrency**: Single-threaded processing
3. **No Caching**: Repeated similar prompts not cached
4. **HTTP Timeouts**: Long-running generation blocks HTTP requests
5. **No Progress Feedback**: User doesn't know if generation is working

---

## 🎯 Optimization Strategies

### **Priority 1: Background Job Processing** ⭐️

**Problem**: Story generation blocks HTTP requests for 2-3 minutes
**Solution**: Move generation to background worker

**Options**:

**A) Celery + Redis** (Standard, battle-tested)
- Pros: Mature, excellent monitoring, retries, scheduling
- Cons: Additional infrastructure (Redis)
- Effort: Medium (4-6 hours)

**B) Huey** (Lightweight alternative)
- Pros: Minimal dependencies, SQLite backend option
- Cons: Less feature-rich than Celery
- Effort: Low (2-3 hours)

**C) FastAPI BackgroundTasks** (Built-in, simplest)
- Pros: No dependencies, immediate solution
- Cons: No persistence, progress tracking limited
- Effort: Very Low (1 hour)

**Recommendation**: Start with **FastAPI BackgroundTasks** for MVP, migrate to Celery later if needed.

---

### **Priority 2: Concurrent LLM Calls** ⭐️

**Problem**: Sequential LLM calls waste time
**Solution**: Process story clusters concurrently

**Implementation**:
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

async def generate_stories_concurrent(session, clusters, model):
    with ThreadPoolExecutor(max_workers=5) as executor:
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(
                executor,
                _generate_story_synthesis,
                session,
                cluster_articles,
                model
            )
            for cluster_articles in clusters
        ]
        return await asyncio.gather(*tasks)
```

**Expected Impact**: 5-10x speedup (171s → 20-35s)
**Effort**: Low-Medium (2-4 hours)

---

### **Priority 3: LLM Response Caching** ⭐

**Problem**: Similar prompts generate same content repeatedly
**Solution**: Cache LLM responses by content hash

**Implementation**:
```python
import hashlib

def cache_key(article_ids: List[int]) -> str:
    return hashlib.sha256("".join(map(str, sorted(article_ids))).encode()).hexdigest()

# Check cache before LLM call
cached = redis.get(f"story_synthesis:{cache_key(article_ids)}")
if cached:
    return json.loads(cached)
```

**Expected Impact**: 50-80% cache hit rate (after initial run)
**Effort**: Low (2-3 hours)

---

### **Priority 4: Batch LLM Requests**

**Problem**: One HTTP request per story cluster
**Solution**: Batch multiple stories into single LLM call

**Note**: Ollama doesn't natively support batching. Consider:
- Switch to OpenAI/Anthropic API (supports batching)
- Use Ollama's experimental batch API
- Keep current approach but optimize prompts

**Expected Impact**: 2-3x speedup
**Effort**: Medium-High (depends on API choice)

---

### **Priority 5: Progress Tracking & Webhooks**

**Problem**: No feedback during long-running generation
**Solution**: WebSocket or polling endpoint for progress

**Implementation**:
```python
@app.websocket("/ws/stories/generate/{job_id}")
async def story_generation_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()
    while True:
        progress = get_job_progress(job_id)
        await websocket.send_json(progress)
        await asyncio.sleep(1)
```

**Expected Impact**: Better UX, no timeouts
**Effort**: Medium (3-4 hours)

---

## 📝 Implementation Roadmap

### **Phase 1: Quick Wins** (4-6 hours)
- [ ] FastAPI BackgroundTasks for `/stories/generate`
- [ ] Concurrent LLM calls (ThreadPoolExecutor)
- [ ] Progress tracking via polling endpoint

**Expected Result**: 171s → 30-40s, no HTTP timeouts

### **Phase 2: Scalability** (6-8 hours)
- [ ] Celery + Redis for robust job queue
- [ ] LLM response caching (Redis)
- [ ] WebSocket progress updates

**Expected Result**: 30s → 10-15s (cached), better reliability

### **Phase 3: Advanced** (8-12 hours)
- [ ] Batch LLM requests (if API supports)
- [ ] Incremental story updates (don't regenerate everything)
- [ ] Smart clustering (reduce story count, increase quality)

**Expected Result**: Sub-10s generation, high-quality stories

---

## 🧪 Testing Strategy

### Load Testing
```bash
# Generate stories with varying article counts
time curl -X POST http://localhost:8787/stories/generate \
  -d '{"time_window_hours": 24}'

# Concurrent requests
for i in {1..5}; do
  curl -X POST http://localhost:8787/stories/generate &
done
```

### Metrics to Track
- Generation time (total, per-story)
- LLM call latency (p50, p95, p99)
- Cache hit rate
- HTTP timeout rate
- Resource usage (CPU, memory)

---

## 🚀 Immediate Action Items

**Option A: Optimize Now**
1. Implement Phase 1 (Quick Wins)
2. Re-test with real data
3. Move to Phase 2 if needed

**Option B: Ship MVP, Optimize Later**
1. Document known performance issues
2. Add warning to `/stories/generate` docs
3. Focus on UI/UX (scheduled generation runs async anyway)

**Option C: Hybrid**
1. Implement BackgroundTasks only (1 hour)
2. Ship with async generation
3. Optimize concurrency later

---

## 📌 Recommendation

**Go with Option C (Hybrid)**:
1. Quick fix: BackgroundTasks (prevents timeouts)
2. Test endpoints with cached stories (fast)
3. Optimize concurrency in next sprint

**Why**: Unblocks current work, provides immediate value, allows iterative improvement.

---

## 📚 Related Issues

- Issue #55: Story API Endpoints (current)
- Issue #48: Scheduled Story Generation (needs background jobs anyway)
- Future: Story UI (benefits from fast API)

---

**Last Updated**: 2025-11-12
**Author**: AI Assistant (based on real testing)
