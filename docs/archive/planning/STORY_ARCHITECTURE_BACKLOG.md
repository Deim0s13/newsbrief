# Story-Based Architecture: Return to Original Vision

> **Status**: Planning Phase
> **Created**: 2025-11-05
> **Priority**: Critical - Foundation for product vision

## Vision Statement

**Current State (Wrong)**: NewsBrief is an RSS feed reader that shows individual article summaries. Users scroll through 50+ articles to stay informed.

**Target State (Original Vision)**: NewsBrief is an AI-powered news aggregator that synthesizes multiple sources into digestible "stories." Users see 5-10 key stories per day and drill down only when interested.

**Value Proposition**: Replace reading TLDR newsletters and 50+ article summaries with a 2-minute landing page showing "what happened today in tech."

---

## Core Concepts

### What is a "Story"?

A **Story** is an AI-synthesized news item that:
- Aggregates 2-20 related articles from different sources
- Provides a unified narrative ("Google announced Gemini 2.0")
- Shows key facts, why it matters, and supporting sources
- Replaces multiple redundant article summaries with one coherent view

### Example Story

```
Title: "Google Announces Gemini 2.0 with Multimodal Capabilities"

Synthesis: Google unveiled Gemini 2.0 today, their next-generation AI model
featuring native image and video understanding. The model shows significant
improvements over GPT-4 in reasoning tasks and offers real-time API access.

Key Points:
• Released December 2024, available via Google AI Studio
• Native multimodal processing (text, image, video, audio)
• 2x faster than Gemini 1.5 with lower latency
• Beats GPT-4 on MMLU and HumanEval benchmarks

Why It Matters:
This represents Google's most significant AI release since Bard, positioning
them as a serious competitor to OpenAI. The multimodal capabilities could
reshape how developers build AI applications.

Supporting Articles (5):
→ TechCrunch: "Google's Gemini 2.0 arrives..."
→ The Verge: "Hands-on with Gemini 2.0..."
→ Ars Technica: "Benchmarks show Gemini beats GPT-4..."
→ Hacker News Discussion (230 comments)
→ Google Blog: Official announcement
```

---

## Architecture Overview

### Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: Article Ingestion (Existing)                        │
│ RSS Feeds → Fetch → Extract → Summarize → Store Articles   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 2: Story Generation (NEW)                              │
│ Articles → Cluster → Extract Entities → Synthesize → Stories│
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Step 3: Presentation (NEW)                                  │
│ Landing Page: Shows 5-10 Stories (not 50 articles)         │
│ Story Detail: Shows synthesis + supporting articles         │
│ Article Detail: Full article (when user wants deep dive)    │
└─────────────────────────────────────────────────────────────┘
```

### Database Schema (NEW)

**stories table**:
- Stores synthesized stories
- Links to multiple articles via junction table
- Tracks importance, freshness, topics, entities

**story_articles table**:
- Many-to-many relationship
- Tracks which articles belong to which stories
- Relevance scoring for each article-story link

---

## Implementation Phases

### Phase 0: Planning & Cleanup ✓
**Status**: Current Phase
**Effort**: 2 hours

- [x] Create this backlog document
- [ ] Review with stakeholder
- [ ] Revert any UI changes that went in wrong direction
- [ ] Update README.md to reflect correct vision
- [ ] Archive old "skim/detail" work (was misguided)

**Exit Criteria**:
- Clear backlog approved
- Team aligned on vision
- No misleading features in codebase

---

### Phase 1: Core Story Infrastructure ✅
**Status**: Complete
**Effort**: 8-12 hours (Actual: ~10 hours)
**Priority**: P0 (Blocking)

#### 1.1 Database Layer (2 hours)
- [x] Add `stories` table schema (done)
- [x] Add `story_articles` junction table (done)
- [x] Add indexes for story queries (done)
- [ ] Create migration path for existing databases
- [ ] Test schema with sample data

**Files**: `app/db.py`

#### 1.2 Story Models (1 hour)
- [x] `StoryOut` model (done)
- [x] `StoryGenerationRequest/Response` (done)
- [ ] Validation logic for story data
- [ ] Serialization helpers (JSON fields)

**Files**: `app/models.py`

#### 1.3 Basic Story CRUD (2 hours)
- [ ] Create story (insert)
- [ ] Link articles to story
- [ ] Retrieve story with articles
- [ ] Update story
- [ ] Delete/archive story
- [ ] Query stories by date/importance

**Files**: New `app/stories.py`

#### 1.4 Simple Story Generation (3-4 hours) ✅
- [x] Get articles from last N hours
- [x] Group by topic/similarity (simple heuristic)
- [x] Create one story per group
- [x] Store in database

**Files**: `app/stories.py` (Issue #39 - Complete)

**Implementation**:
- Hybrid clustering: Topic grouping + keyword similarity (Jaccard)
- LLM-powered multi-document synthesis via Ollama
- Structured JSON output: synthesis, key_points, why_it_matters, topics, entities
- Graceful fallback when LLM unavailable
- Configurable time window, similarity threshold, min articles per story
- Comprehensive test coverage (automated + manual LLM tests)

**Acceptance Criteria**: ✅ All Met
- ✅ Can manually trigger story generation (`generate_stories_simple`)
- ✅ Stories are stored in database (with article links via junction table)
- ✅ Can retrieve stories via API (using existing CRUD operations)
- ✅ Hybrid clustering works (topic + keyword overlap)

---

### Phase 2: Story Clustering & Intelligence
**Status**: Not Started
**Effort**: 10-15 hours
**Priority**: P0 (Core Feature)

#### 2.1 Entity Extraction (3-4 hours)
- [ ] Extract named entities from article titles/summaries
- [ ] Use LLM to identify key entities (companies, products, people)
- [ ] Store entities with articles
- [ ] Use entities for clustering

**Approach**:
- Prompt LLM: "Extract key entities from this title: {title}"
- Return JSON: `{"entities": ["Google", "Gemini 2.0", "AI"]}`
- Cache entity extractions

**Files**: `app/llm.py`, `app/stories.py`

#### 2.2 Semantic Similarity (4-5 hours)
- [ ] Simple text similarity (TF-IDF or keyword overlap)
- [ ] Compare article titles and summaries
- [ ] Calculate similarity scores
- [ ] Use for clustering

**Note**: Start simple. Embeddings can come later (Phase 4).

**Files**: `app/stories.py`

#### 2.3 Clustering Algorithm (3-4 hours)
- [ ] Implement story clustering based on:
  - Entity overlap (same companies/products)
  - Semantic similarity (similar topics)
  - Time proximity (published within hours)
  - Topic classification (existing)
- [ ] Tune clustering parameters
- [ ] Handle edge cases (singleton stories, mega-clusters)

**Algorithm**:
```
1. Get articles from last 24 hours
2. Extract entities for each article
3. Build similarity matrix (entity + text similarity)
4. Cluster articles (threshold-based or DBSCAN)
5. Generate one story per cluster
```

**Files**: `app/stories.py`

#### 2.4 Story Quality Scoring (2 hours)
- [ ] Importance score (based on source quality, article count)
- [ ] Freshness score (how recent)
- [ ] Combined ranking
- [ ] Filter low-quality clusters

**Files**: `app/stories.py`

**Acceptance Criteria**:
- Clustering groups related articles effectively
- Test cases:
  - Multiple articles about same announcement → 1 story
  - Unrelated articles → separate stories
  - Similar but distinct topics → separate stories
- Quality scoring surfaces important stories first

---

### Phase 3: Multi-Document Synthesis
**Status**: Not Started
**Effort**: 8-10 hours
**Priority**: P0 (Core Feature)

#### 3.1 Synthesis Prompt Engineering (2-3 hours)
- [ ] Design prompt for multi-article synthesis
- [ ] Test with various article combinations
- [ ] Iterate on output quality
- [ ] Handle edge cases (conflicting info, missing data)

**Prompt Template**:
```
You are synthesizing multiple news articles into a single story.

Articles:
[Article 1] Title: {title}, Source: {source}, Summary: {summary}
[Article 2] ...

Synthesize these into:
1. A unified title (10-15 words)
2. A synthesis paragraph (100-150 words)
3. Key points (4-6 bullets)
4. Why it matters (2-3 sentences)
5. Topics/entities mentioned

Format as JSON.
```

**Files**: `app/llm.py`

#### 3.2 Synthesis Pipeline (3-4 hours)
- [ ] Gather all articles in cluster
- [ ] Format for LLM prompt
- [ ] Call LLM with multi-doc prompt
- [ ] Parse structured output
- [ ] Store synthesis in stories table
- [ ] Handle LLM failures gracefully

**Files**: `app/llm.py`, `app/stories.py`

#### 3.3 Caching & Performance (2-3 hours)
- [ ] Cache synthesis by story hash (articles + model)
- [ ] Reuse synthesis when articles unchanged
- [ ] Batch synthesis for multiple stories
- [ ] Optimize LLM token usage

**Files**: `app/llm.py`

**Acceptance Criteria**:
- Given 3-5 related articles, generates coherent story
- Synthesis is factually accurate (no hallucinations)
- Key points are distinct and informative
- "Why it matters" provides genuine insight
- Caching prevents redundant LLM calls

---

### Phase 4: Story Generation Scheduling
**Status**: Not Started
**Effort**: 4-6 hours
**Priority**: P1 (Important)

#### 4.1 On-Demand Story Generation (2 hours)
- [ ] API endpoint: `POST /stories/generate`
- [ ] Trigger clustering + synthesis
- [ ] Return generation stats
- [ ] Handle long-running operations

**Files**: `app/main.py`, `app/stories.py`

#### 4.2 Scheduled Generation (2-3 hours)
- [ ] Background task runner (APScheduler or similar)
- [ ] Run story generation every N hours
- [ ] Configurable schedule
- [ ] Logging and error handling

**Options**:
1. In-process scheduler (APScheduler)
2. External cron job
3. Celery/Redis task queue (overkill for now)

**Recommendation**: Start with APScheduler for simplicity.

**Files**: `app/main.py`, new `app/scheduler.py`

#### 4.3 Incremental Updates (1-2 hours)
- [ ] Detect new articles since last generation
- [ ] Update existing stories vs create new ones
- [ ] Archive old stories (7+ days)

**Files**: `app/stories.py`

**Acceptance Criteria**:
- Stories auto-generate every 6 hours
- Manual "refresh stories" works instantly
- Old stories are archived, not deleted
- No duplicate stories created

---

### Phase 5: UI Redesign - Landing Page
**Status**: Not Started
**Effort**: 6-8 hours
**Priority**: P0 (User-Facing)

#### 5.1 Stories Landing Page (4-5 hours)
- [ ] Replace article list with story list
- [ ] Story card design:
  - Story title (large, prominent)
  - Synthesis snippet (2-3 lines)
  - Key point preview (first 2 bullets)
  - Metadata (article count, time, topics)
  - Click → story detail page
- [ ] Sort by importance/freshness
- [ ] Responsive layout
- [ ] Loading states

**Design Principles**:
- **Scannable**: User sees 5-10 stories at once
- **Minimal**: No clutter, just story cards
- **Fast**: Loads instantly, no pagination needed

**Files**: `app/templates/index.html`, `app/static/js/app.js`, `app/static/css/custom.css`

#### 5.2 Story Filters (1-2 hours)
- [ ] Filter by topic
- [ ] Filter by time window (today, this week)
- [ ] Hide/show archived stories

**Files**: `app/templates/index.html`, `app/static/js/app.js`

#### 5.3 Empty States (1 hour)
- [ ] No stories yet → "Refresh feeds to generate stories"
- [ ] No articles in time window → Helpful message
- [ ] Loading state during generation

**Files**: `app/templates/index.html`

**Acceptance Criteria**:
- Landing page shows stories, not articles
- User sees "what's happening" in 10 seconds
- Can click into story for details
- Fast, clean, uncluttered

---

### Phase 6: UI - Story Detail Page
**Status**: Not Started
**Effort**: 4-6 hours
**Priority**: P0 (User-Facing)

#### 6.1 Story Detail View (3-4 hours)
- [ ] Story header (title, metadata)
- [ ] Full synthesis (expanded)
- [ ] All key points (bullets)
- [ ] "Why it matters" (highlighted)
- [ ] Topics/entities (tags)
- [ ] List of supporting articles (compact)
- [ ] Click article → article detail page
- [ ] Back to stories

**Layout**:
```
┌────────────────────────────────────┐
│  [← Back]                          │
│                                    │
│  Story Title                       │
│  [5 articles] [AI/ML] [2h ago]     │
│                                    │
│  Synthesis (full paragraph)        │
│                                    │
│  Key Points:                       │
│  • Point 1                         │
│  • Point 2                         │
│  • Point 3                         │
│                                    │
│  💡 Why It Matters:                │
│  Explanation text here...          │
│                                    │
│  Supporting Articles:              │
│  □ TechCrunch: "Title..." [Read]  │
│  □ The Verge: "Title..." [Read]   │
│  ...                               │
└────────────────────────────────────┘
```

**Files**: `app/templates/story_detail.html`, `app/main.py` (route)

#### 6.2 Navigate to Full Articles (1-2 hours)
- [ ] Click article → article detail page
- [ ] Breadcrumb: Home → Story → Article
- [ ] Context preserved (which story user came from)

**Files**: `app/templates/article_detail.html`, `app/static/js/app.js`

**Acceptance Criteria**:
- Story detail shows full synthesis and context
- User can read all supporting articles
- Navigation is intuitive (stories → article → back)
- Content is beautifully formatted

---

### Phase 7: API Layer ✅
**Status**: Complete
**Effort**: 3-4 hours (Actual: ~3 hours)
**Priority**: P1 (Foundation)
**Completed**: 2025-11-12

#### 7.1 Story Endpoints (2-3 hours) ✅
- [x] `GET /stories` - List stories (landing page)
- [x] `GET /stories/{id}` - Story detail
- [x] `POST /stories/generate` - Trigger generation
- [x] `GET /stories/stats` - Generation statistics

**Files**: `app/main.py` (Issues #47, #55)

**Implementation Details**:
- All 4 HTTP endpoints implemented with comprehensive error handling
- Input validation via Pydantic (StoryGenerationRequest, StoriesListOut)
- Filtering, sorting, and pagination support
- Python API fully functional (direct CRUD access)
- Tested with real data (150 articles → 379 stories)

#### 7.2 Update Existing Endpoints ✅
- [x] `GET /items` - Kept for article browsing (power users)
- [x] API docs updated (docs/API.md)
- [x] Backward compatible (existing endpoints still work)

**Files**: `app/main.py`, `docs/API.md`

**Acceptance Criteria**: ✅ All Met
- ✅ All story endpoints work correctly
- ✅ API docs updated with story endpoints
- ✅ Backward compatible (existing endpoints still work)
- ✅ Comprehensive testing completed (see docs/STORY_API_TESTING_SUMMARY.md)

**Known Issues**:
- Performance: Story generation takes ~171s (tracked in Issue #66)
- HTTP timeout on POST /stories/generate (not blocking, generation completes)

---

### Phase 8: Interest-Based Filtering
**Status**: Not Started
**Effort**: 4-6 hours
**Priority**: P2 (Enhancement)

#### 8.1 User Interests (2-3 hours)
- [ ] Define interest profiles (config or UI)
- [ ] Weight stories by interest match
- [ ] Filter out low-interest stories
- [ ] Show/hide by topic

**Approach**: Start simple with topic preferences.

**Files**: `app/stories.py`, `app/main.py`

#### 8.2 Source Weighting (2-3 hours)
- [ ] Weight sources (Hacker News > random blog)
- [ ] Adjust story importance by source quality
- [ ] Configurable weights

**Files**: `app/stories.py`

**Acceptance Criteria**:
- User sees stories relevant to their interests first
- Can filter by topic/source
- High-quality sources surface important stories

---

## Testing Strategy

### Unit Tests
- [ ] Story clustering algorithm
- [ ] Entity extraction
- [ ] Similarity scoring
- [ ] Story CRUD operations
- [ ] Synthesis caching

### Integration Tests
- [ ] End-to-end story generation
- [ ] Articles → clusters → synthesis → storage
- [ ] API endpoints

### Manual Testing
- [ ] Generate stories from real feeds
- [ ] Validate clustering quality
- [ ] Review synthesis quality
- [ ] UX testing (is it actually faster?)

---

## Success Metrics

### Quantitative
- **Time to informed**: User sees key news in < 2 minutes (vs 30+ min currently)
- **Story count**: 5-10 stories per day (vs 50+ articles)
- **Clustering accuracy**: 90%+ of related articles grouped correctly
- **Synthesis quality**: No hallucinations, factually accurate

### Qualitative
- **User feedback**: "This saves me so much time"
- **Behavior change**: Users drill into < 30% of stories (just skim landing page)
- **Value delivered**: Replaces TLDR newsletters

---

## Risks & Mitigation

### Risk: Clustering Quality
**Issue**: Articles incorrectly grouped or split
**Mitigation**: Start with simple heuristics, iterate based on real data, add manual override

### Risk: LLM Hallucinations
**Issue**: Synthesis contains false information
**Mitigation**: Ground all synthesis in article text, add fact-checking prompt, show source articles

### Risk: Performance
**Issue**: Story generation is slow (10s+ seconds)
**Mitigation**: Run on schedule (not on-demand), cache aggressively, batch operations

### Risk: Scope Creep
**Issue**: Adding features that deviate from vision
**Mitigation**: This document. Refer back frequently. Say no to article-centric features.

---

## Out of Scope (For Now)

These are good ideas but NOT for initial story architecture:

- ❌ Embeddings/semantic search (use simple similarity first)
- ❌ User accounts / personalization
- ❌ Real-time updates (WebSockets)
- ❌ Mobile app
- ❌ Social sharing
- ❌ Saved articles / bookmarks
- ❌ Full-text search
- ❌ Keyboard shortcuts (can add after core works)

---

## Timeline Estimate

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Phase 0: Planning | 2h | None |
| Phase 1: Infrastructure | 8-12h | Phase 0 |
| Phase 2: Clustering | 10-15h | Phase 1 |
| Phase 3: Synthesis | 8-10h | Phase 1, 2 |
| Phase 4: Scheduling | 4-6h | Phase 1, 3 |
| Phase 5: Landing UI | 6-8h | Phase 1, 3 |
| Phase 6: Detail UI | 4-6h | Phase 5 |
| Phase 7: API | 3-4h | Phase 1-6 |
| Phase 8: Interests | 4-6h | Phase 1-7 |

**Total Estimated Effort**: 50-70 hours

**Recommended Approach**:
1. Complete Phases 1-3 first (core engine) - 26-37 hours
2. Then Phases 5-6 (UI) - 10-14 hours
3. Then Phase 4, 7, 8 (polish) - 11-16 hours

---

## Next Steps

1. ✅ Review this document
2. ⏳ Get stakeholder approval
3. ⏳ Revert changes made in wrong direction
4. ⏳ Start Phase 1: Core Story Infrastructure

---

## Product Decisions ✅

**Status**: Approved 2025-11-06

1. **Time Window**: ✅ **24 hours** (once daily)
   - Future: Make configurable (12h, 48h, 1w)

2. **Story Count**: ✅ **5-10 stories** (TLDR-style, curated)
   - Future: Group by high-level topics (Security, AI, DevTools, etc.)
   - Future: Dynamic generation based on quality threshold

3. **Clustering Threshold**: ✅ **Balanced approach**
   - Start specific, tune toward aggregation based on real data
   - Iterate on similarity thresholds

4. **LLM Model**: ✅ **Llama 3.1 8B**
   - Good quality/speed balance for multi-doc synthesis
   - Make model configurable for future upgrades
   - Document model requirements and performance

5. **Scheduling**: ✅ **Daily generation** + **manual refresh**
   - Auto-generate once daily (e.g., 6 AM)
   - Manual "Refresh Stories" button available
   - Future: Make schedule configurable (2x daily, etc.)

6. **Implementation Priority**: ✅ **API-first with simple UI in parallel**
   - Build Phases 1-3 (infrastructure, clustering, synthesis)
   - Add simple UI (Phase 5-6) alongside API development
   - Allows testing and visualization early

7. **Article Browsing**: ✅ **Keep as secondary feature**
   - Keep `/items` API endpoint
   - Add hidden "View All Articles" link in UI
   - Primary focus remains stories, not articles
