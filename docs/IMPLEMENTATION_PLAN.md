# Story Architecture Implementation Plan

> **Status**: Ready to Start  
> **Approved**: 2025-11-06  
> **Reference**: See [STORY_ARCHITECTURE_BACKLOG.md](STORY_ARCHITECTURE_BACKLOG.md) for detailed phase breakdown

## Executive Summary

**What**: Transform NewsBrief from article-centric RSS reader to story-based news aggregator  
**Why**: Replace reading 50+ article summaries with 5-10 synthesized stories (TLDR-killer)  
**How**: AI clustering + multi-document synthesis + story-first UI  
**Timeline**: ~50-70 hours across 8 phases

---

## Product Decisions Applied

### Core Configuration
- **Time Window**: 24 hours (daily generation)
- **Story Target**: 5-10 curated stories per day
- **LLM Model**: Llama 3.1 8B (configurable)
- **Schedule**: Daily auto-generation + manual refresh
- **Clustering**: Balanced (start specific, tune toward aggregation)

### Architecture Choices
- **Implementation**: API-first with simple UI in parallel
- **Article View**: Secondary feature (hidden but accessible)
- **Future-Ready**: Configurable time windows, models, schedules

---

## Implementation Phases

### Phase 1: Core Infrastructure (8-12 hours) ✅ COMPLETE
**Goal**: Database, models, basic CRUD, simple generation

**Tasks**:
- ✅ Database schema (stories, story_articles) - Issue #36
- ✅ Pydantic models with validation - Issue #37
- ✅ Story CRUD operations (8 functions) - Issue #38
- ✅ Story generation pipeline (hybrid clustering + LLM) - Issue #39

**Deliverable**: ✅ Can generate stories from articles with LLM synthesis

**Implementation Notes**:
- Hybrid clustering: Topic grouping + keyword similarity (Jaccard)
- LLM synthesis via Ollama (llama3.1:8b) with structured JSON output
- Entity extraction and topic classification built into synthesis
- Graceful fallback when LLM unavailable
- ~10 hours actual effort (on target)

---

### Phase 2: Intelligent Clustering (10-15 hours) 🧠
**Goal**: Smart article grouping using entities and similarity

**Tasks**:
- Entity extraction (LLM-based: companies, products, people)
- Text similarity (TF-IDF/keyword overlap, no embeddings yet)
- Clustering algorithm (entity overlap × text similarity × time)
- Quality scoring (importance + freshness)

**Deliverable**: Articles automatically cluster into story candidates

**Configuration**:
```python
# Future config options
CLUSTERING_SIMILARITY_THRESHOLD = 0.65  # Balanced
MIN_ARTICLES_PER_STORY = 2
MAX_ARTICLES_PER_STORY = 20
```

---

### Phase 3: Multi-Document Synthesis (8-10 hours) 📝
**Goal**: Generate coherent story from multiple articles

**Tasks**:
- Design synthesis prompt (multi-article → unified narrative)
- Implement synthesis pipeline
- Parse structured output (title, synthesis, key points, why it matters)
- Caching and performance optimization

**LLM Configuration**:
```python
MODEL = "llama3.1:8b"  # Configurable
SYNTHESIS_MAX_TOKENS = 2000
SYNTHESIS_TEMPERATURE = 0.3  # Lower for factual synthesis
```

**Deliverable**: Each cluster generates a synthesized story

---

### Phase 4: Scheduling & Automation (4-6 hours) ⏰
**Goal**: Daily auto-generation + manual refresh

**Tasks**:
- On-demand API endpoint (POST /stories/generate)
- APScheduler integration (daily at 6 AM)
- Incremental updates (update existing vs create new)
- Archive old stories (7+ days)

**Schedule Configuration**:
```python
# Daily generation (configurable in future)
STORY_GENERATION_SCHEDULE = "0 6 * * *"  # 6 AM daily
STORY_ARCHIVE_DAYS = 7
```

**Deliverable**: Stories auto-generate daily, manual refresh available

---

### Phase 5: Story-Based Landing Page (6-8 hours) 🎨
**Goal**: Replace article list with story cards

**Tasks**:
- Story list view (5-10 story cards)
- Story card design (title, synthesis snippet, key points preview)
- Sort by importance/freshness
- Topic filters
- Manual refresh button
- Loading/empty states

**Design Principles**:
- Scannable: 10-second landing page scan
- Minimal: No clutter, story-focused
- Fast: Instant load

**Deliverable**: Landing page shows stories, not articles

---

### Phase 6: Story Detail Page (4-6 hours) 📄
**Goal**: Deep dive into individual stories

**Tasks**:
- Story detail view (full synthesis, all key points, why it matters)
- Supporting articles list (compact)
- Navigation (story → article → back)
- Breadcrumbs

**Deliverable**: Can read full story and drill into supporting articles

---

### Phase 7: API Layer (3-4 hours) 🔌
**Goal**: RESTful story endpoints

**Tasks**:
- GET /stories (list)
- GET /stories/{id} (detail)
- POST /stories/generate (manual refresh)
- GET /stories/stats
- Update /items to support ?story_id filter

**Deliverable**: Complete API for story operations

---

### Phase 8: Interest-Based Filtering (4-6 hours) 🎯
**Goal**: Surface relevant stories first

**Tasks**:
- Topic-based filtering (Security, AI, DevTools, etc.)
- Source quality weighting (HN > random blog)
- Configurable interest profiles

**Future Enhancement**: Group stories by topic on landing page

**Deliverable**: Users see most relevant stories first

---

## Development Workflow

### Recommended Order
1. **Week 1**: Phases 1-3 (Core engine: 26-37 hours)
   - Get story generation working end-to-end
   - Test via API/database inspection
   
2. **Week 2**: Phases 5-6 (UI: 10-14 hours)
   - Build story-first interface
   - Visual feedback and iteration
   
3. **Week 3**: Phases 4, 7, 8 (Polish: 11-16 hours)
   - Automation, API docs, filtering
   - Testing and refinement

### Testing Strategy
- **Unit Tests**: Clustering, entity extraction, similarity
- **Integration Tests**: End-to-end story generation
- **Manual Tests**: Real feeds, real stories, quality review
- **Performance Tests**: Generation time, LLM token usage

---

## Configuration Management

### Environment Variables
```bash
# LLM Configuration
OLLAMA_BASE_URL=http://localhost:11434
NEWSBRIEF_SYNTHESIS_MODEL=llama3.1:8b  # Configurable
NEWSBRIEF_SYNTHESIS_TEMP=0.3

# Story Generation
STORY_TIME_WINDOW_HOURS=24
STORY_TARGET_COUNT=10
STORY_MIN_ARTICLES=2
STORY_MAX_ARTICLES=20

# Clustering
CLUSTERING_SIMILARITY_THRESHOLD=0.65  # Balanced
CLUSTERING_ENTITY_WEIGHT=0.4
CLUSTERING_TEXT_WEIGHT=0.4
CLUSTERING_TIME_WEIGHT=0.2

# Scheduling
STORY_GENERATION_CRON="0 6 * * *"  # Daily at 6 AM
STORY_ARCHIVE_DAYS=7
```

### Future Configurability
- User-facing config UI (Phase 8+)
- Per-user story preferences
- Multiple time windows (12h, 24h, 48h, 1w)
- Multiple generation schedules (2x daily, hourly)

---

## Success Metrics

### Quantitative
- ✅ **Time to informed**: < 2 minutes (vs 30+ minutes)
- ✅ **Story count**: 5-10 stories/day (vs 50+ articles)
- ✅ **Clustering accuracy**: 90%+ related articles grouped
- ✅ **Synthesis quality**: No hallucinations, factually accurate
- ✅ **Generation time**: < 5 minutes for daily batch

### Qualitative
- User reads landing page, drills into < 30% of stories
- "This saves me so much time" feedback
- Replaces TLDR newsletters

---

## Risk Mitigation

### Technical Risks
1. **Clustering Quality**: Start simple (topic-based), iterate with real data
2. **LLM Hallucinations**: Ground synthesis in article text, show sources
3. **Performance**: Daily batch + caching, not real-time
4. **Model Availability**: Make model configurable, document requirements

### Product Risks
1. **Too Aggressive Aggregation**: Start specific, tune based on feedback
2. **Missing Context**: Show supporting articles, allow drill-down
3. **Stale Stories**: Daily generation + manual refresh
4. **Loss of Granularity**: Keep article view as secondary feature

---

## Next Steps

1. ✅ Product decisions approved
2. ✅ Backlog documented
3. ⏳ **Update documentation** (README, API docs)
4. ⏳ **Start Phase 1**: Core infrastructure implementation

---

## Notes

- **Model Evolution**: Llama 3.1 8B is current choice, but make configurable for future models (Llama 3.2, GPT-4, etc.)
- **Topic Grouping**: Future enhancement to group stories by high-level topics on landing page
- **Embeddings**: Not in initial scope, but could enhance clustering in future (Phase 9+)
- **Real-time Updates**: Not in scope, daily batch is sufficient for use case


