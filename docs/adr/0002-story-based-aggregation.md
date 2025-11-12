# 0002 — Architecture Decision: Story-Based Aggregation

**Status**: Accepted  
**Date**: 2025-11-06  
**Supersedes**: v0.4.0 article-centric UI plans  

## Context

NewsBrief v0.3.x evolved into an article-centric RSS reader where users browse individual article summaries. While functional, this approach deviated from the original vision:

**Original Intent**: Replace reading 50+ article summaries (TLDR newsletters, RSS fatigue) with AI-synthesized story briefs.

**Current State**: Users still scroll through 50+ individual article summaries, defeating the purpose.

**Problem**: Information overload persists. Users spend 30+ minutes reading summaries instead of 2 minutes scanning key stories.

## Decision

### Pivot to Story-Based Aggregation (v0.5.0)

**Core Concept**: Aggregate related articles into synthesized "stories" that provide unified narratives, not individual summaries.

### Key Changes

#### 1. Data Model: Stories as First-Class Citizens

```sql
-- New tables
CREATE TABLE stories (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  synthesis TEXT NOT NULL,           -- Unified narrative
  key_points_json TEXT,              -- 3-5 key bullets
  why_it_matters TEXT,               -- Significance analysis
  entities_json TEXT,                -- Companies, products, people
  importance_score REAL,
  generated_at DATETIME
);

CREATE TABLE story_articles (
  story_id INTEGER,
  article_id INTEGER,
  relevance_score REAL,
  is_primary BOOLEAN                 -- Primary source
);
```

**Rationale**: 
- Stories become the primary unit of presentation, not articles
- Articles become supporting evidence for stories
- Many-to-many relationship allows flexible clustering

#### 2. Clustering Algorithm: Entity + Similarity + Time

**Approach**:
```python
def cluster_articles(articles, time_window=24h):
    # Extract entities (companies, products, people)
    entities = extract_entities(articles)
    
    # Calculate similarity matrix
    similarity = (
        entity_overlap_score(articles) * 0.4 +
        text_similarity_score(articles) * 0.4 +
        time_proximity_score(articles) * 0.2
    )
    
    # Cluster using threshold-based grouping
    clusters = group_by_similarity(similarity, threshold=0.65)
    
    return clusters
```

**Rationale**:
- Entity extraction identifies same events/products across sources
- Text similarity catches related topics without exact entity matches
- Time proximity groups concurrent events
- Start simple (TF-IDF), evolve to embeddings later

**Rejected Alternatives**:
- Pure topic clustering: Too coarse, misses nuanced relationships
- Embeddings-only: Overkill for initial implementation, adds complexity
- Manual tagging: Not scalable, requires user input

#### 3. Multi-Document Synthesis

**LLM Model**: Llama 3.1 8B (configurable)
- Better quality than 3B for multi-document synthesis
- Acceptable speed (~30-60s for 5-10 stories)
- Runs locally (privacy-first)

**Synthesis Prompt**:
```
Given these related articles:
[Article 1] Title: {title}, Source: {source}, Summary: {summary}
[Article 2] ...

Synthesize into:
1. Unified title (10-15 words)
2. Synthesis paragraph (100-150 words) 
3. Key points (4-6 bullets, factual)
4. Why it matters (2-3 sentences, significance)
5. Entities and topics

Requirements:
- Grounded in article text (no hallucinations)
- Unified narrative, not concatenation
- Preserve factual accuracy
- Format as JSON
```

**Rationale**:
- Larger model needed for coherent multi-doc synthesis
- Structured prompt prevents hallucinations
- JSON output ensures consistent parsing
- Caching by story hash prevents redundant generation

#### 4. User Experience: Story-First Landing Page

**Landing Page**:
- Shows 5-10 story cards (not 50 articles)
- Each card: Title + snippet + key point preview
- Sort by importance/freshness
- Scannable in < 10 seconds

**Story Detail Page**:
- Full synthesis + all key points
- "Why it matters" highlighted
- Supporting articles (compact list)
- Drill down to full articles if interested

**Article View**: Secondary feature
- Keep `/items` API for power users
- Hide behind "View All Articles" link
- Not promoted in primary UI

**Rationale**:
- Aligns with original vision: 2-minute briefing, not 30-minute scrolling
- Reduces cognitive load: 5-10 decisions vs 50+
- Maintains granularity: Can drill into sources when needed
- Progressive disclosure: Stories → Details → Articles

#### 5. Generation Schedule: Daily + Manual

**Auto-Generation**:
- Once daily at 6 AM (configurable)
- Process articles from last 24 hours
- Generate 5-10 stories

**Manual Refresh**:
- `POST /stories/generate` endpoint
- User-triggered via UI button
- Useful for breaking news

**Rationale**:
- Daily rhythm matches typical news consumption
- Not real-time: No need for WebSockets/streaming
- Manual override for urgency
- Batch efficiency: ~1 minute total for 5-10 stories

**Rejected Alternatives**:
- Real-time generation: Overkill, adds complexity
- On-demand only: Misses convenience of auto-briefing
- Multiple times daily: Noise, redundancy

## Consequences

### Positive

✅ **Aligns with Original Vision**: Story aggregator, not article reader
✅ **Reduces Information Overload**: 5-10 stories vs 50+ articles
✅ **Improves UX**: 2-minute scan vs 30-minute scroll
✅ **Unique Value Prop**: Replaces TLDR newsletters with local, personalized alternative
✅ **Extensible**: Can add topic grouping, configurable windows later

### Negative

⚠️ **Complexity Increase**: New clustering algorithm, synthesis pipeline, data model
⚠️ **LLM Dependency**: Requires Llama 3.1 8B (larger model)
⚠️ **Quality Risk**: Synthesis quality depends on clustering accuracy
⚠️ **Implementation Time**: ~50-70 hours vs simpler article UI

### Mitigation

- **Start Simple**: Basic clustering (topic + entity), iterate based on real data
- **Make Configurable**: Model, schedule, time windows all configurable
- **Preserve Granularity**: Keep article view as secondary feature
- **Phased Rollout**: API-first, then UI, allows testing at each stage

## Implementation

See:
- [Story Architecture Backlog](../STORY_ARCHITECTURE_BACKLOG.md)
- [Implementation Plan](../IMPLEMENTATION_PLAN.md)

**Phases**:
1. Core Infrastructure (8-12 hours)
2. Clustering & Intelligence (10-15 hours)
3. Multi-Document Synthesis (8-10 hours)
4. Scheduling & Automation (4-6 hours)
5. Story-First UI (10-14 hours)
6. API Layer & Refinement (7-10 hours)

**Total**: 50-70 hours

## Success Metrics

**Quantitative**:
- Time to informed: < 2 minutes (vs 30+ minutes)
- Story count: 5-10/day (vs 50+ articles)
- Clustering accuracy: 90%+ related articles grouped
- Generation time: < 5 minutes for daily batch

**Qualitative**:
- User feedback: "Saves me time"
- Behavior: Drill into < 30% of stories (just scan landing page)
- Value: Replaces TLDR/newsletter subscriptions

## References

- Original vision discussion: 2025-11-06
- [ADR 0001](0001-architecture.md): Local-first architecture (still valid)
- Similar systems: TLDR newsletters, Apple News+, Google News digest

## Status

**Accepted** — 2025-11-06  
**Implementation**: Phase 1 Complete ✅ (2025-11-12)

### Progress Update

**Phase 1: Core Infrastructure** (Complete — Issue #39)
- ✅ Database schema: `stories` and `story_articles` tables
- ✅ Pydantic models with validation
- ✅ Story CRUD operations (8 functions)
- ✅ Story generation pipeline with hybrid clustering
- ✅ LLM synthesis via Ollama (llama3.1:8b)
- ✅ Entity extraction and topic classification
- ✅ Graceful fallback when LLM unavailable
- ✅ Comprehensive test coverage

**Implementation Notes**:
- Hybrid clustering uses topic grouping + keyword similarity (Jaccard index)
- LLM synthesis generates structured JSON output (synthesis, key_points, why_it_matters, entities, topics)
- Single-article stories supported (min_articles_per_story=1)
- Configurable parameters: time_window_hours, similarity_threshold, model
- ~10 hours actual effort (target: 8-12 hours) ✅

**Next Phase**: HTTP API endpoints and scheduled generation

---

**Last Updated**: 2025-11-12  
**Next Review**: After Phase 4 (API Endpoints) completion

