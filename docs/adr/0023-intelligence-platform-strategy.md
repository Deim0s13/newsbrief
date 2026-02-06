# ADR 0023: Intelligence Platform Strategy

## Status

**Accepted** - February 2026

## Context

NewsBrief has evolved from a simple RSS reader to a story-based news aggregator with LLM-powered synthesis. With the completion of v0.7.x (infrastructure maturity, PostgreSQL parity), we now have a solid foundation to build upon.

However, the current product is fundamentally an **aggregator** - it collects and summarizes content. To create a monetizable, differentiated product, we need to transform NewsBrief into an **intelligence platform** that helps users truly understand what's happening, not just see what's being reported.

### Current Limitations

1. **Surface-level synthesis**: Stories merge articles but don't analyze perspectives
2. **No source intelligence**: All sources treated equally regardless of credibility
3. **Static stories**: No tracking of how stories evolve over time
4. **Limited context**: No historical context or "why this matters" analysis
5. **Single output format**: One-size-fits-all story presentation
6. **No entity intelligence**: People/companies mentioned but not tracked across stories

### Market Opportunity

Premium news intelligence products (Bloomberg Terminal, Feedly Pro, specialized industry newsletters) command significant subscription fees because they provide **insight**, not just information. NewsBrief can differentiate by:

- Offering multi-perspective analysis (what sources agree/disagree on)
- Tracking entities and their sentiment over time
- Providing confidence signals and source transparency
- Delivering tiered depth (headlines → deep dives)
- Surfacing patterns and trends across stories

## Decision

We will transform NewsBrief from a news aggregator into an **intelligence platform** through a phased approach across five major development phases:

### Phase 1: Foundation (v0.8.x)
Build the quality foundation that all intelligence features depend on.

### Phase 2: Intelligence Layer (v0.9.x)
Add entity intelligence, multi-perspective analysis, and story evolution tracking.

### Phase 3: Context Layer (v0.10.x)
Provide "why this matters" context, trend detection, and confidence scoring.

### Phase 4: Experience Layer (v0.11.x)
Deliver content through multiple formats: reading tiers, audio, visualizations.

### Phase 5: Monetization (v1.0)
Enable sustainable business model with premium features, API access, and team capabilities.

## Architecture Evolution

### Current Architecture (v0.7.x)

```
┌─────────────────────────────────────────────────────────────┐
│  RSS Feeds → Content Extraction → Clustering → Synthesis    │
│                         ↓                                   │
│              Single-format Story Output                     │
└─────────────────────────────────────────────────────────────┘
```

### Target Architecture (v1.0)

```
┌─────────────────────────────────────────────────────────────┐
│                     INGESTION LAYER                         │
│  RSS Feeds → Tiered Extraction → Credibility Assessment     │
├─────────────────────────────────────────────────────────────┤
│                   INTELLIGENCE LAYER                        │
│  ┌─────────────┬──────────────────┬───────────────────┐    │
│  │ Entity Graph│ Perspective      │ Trend Detection   │    │
│  │ & Profiles  │ Analysis Engine  │ & Anomalies       │    │
│  └─────────────┴──────────────────┴───────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│                     CONTEXT LAYER                           │
│  ┌─────────────┬──────────────────┬───────────────────┐    │
│  │ Historical  │ Impact           │ Confidence        │    │
│  │ Context     │ Analysis         │ Scoring           │    │
│  └─────────────┴──────────────────┴───────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│                    SYNTHESIS LAYER                          │
│  ┌─────────────┬──────────────────┬───────────────────┐    │
│  │ Multi-      │ Tiered Depth     │ Audio             │    │
│  │ Perspective │ Generation       │ Synthesis         │    │
│  └─────────────┴──────────────────┴───────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│                    DELIVERY LAYER                           │
│  Web UI │ REST API │ Smart Alerts │ Export │ Premium       │
└─────────────────────────────────────────────────────────────┘
```

## Detailed Phase Breakdown

### Phase 1: Foundation (v0.8.x)

#### v0.8.0 - Content Extraction Pipeline Upgrade
**Goal**: Better source material for all downstream processing.

- Tiered extraction: Readability → Trafilatura → LLM fallback
- Extraction quality metrics
- Re-extraction capability for existing articles
- Database schema for extraction metadata

#### v0.8.1 - LLM Quality & Intelligence
**Goal**: Higher quality outputs from existing pipelines.

- Improved synthesis prompts
- Better story title generation
- Enhanced entity extraction accuracy
- Model configuration profiles (fast vs quality)
- Output quality metrics and tracking
- Cloud LLM provider support (OpenAI, Anthropic)

#### v0.8.2 - Source Credibility System (NEW)
**Goal**: Differentiate sources by reliability and perspective.

- Source metadata enrichment (bias rating, fact-check history)
- Credibility scoring algorithm
- Visual credibility indicators in UI
- Source weighting in synthesis

**Schema additions**:
```sql
ALTER TABLE feeds ADD COLUMN credibility_score FLOAT DEFAULT 0.5;
ALTER TABLE feeds ADD COLUMN bias_label VARCHAR(20);
ALTER TABLE feeds ADD COLUMN fact_check_rating VARCHAR(20);
ALTER TABLE feeds ADD COLUMN credibility_source VARCHAR(50);
ALTER TABLE feeds ADD COLUMN last_credibility_update TIMESTAMP;
```

### Phase 2: Intelligence Layer (v0.9.x)

#### v0.9.0 - Entity Intelligence System
**Goal**: Track people, organizations, and topics across all content.

- Entity extraction and normalization
- Entity profile pages (all mentions, sentiment over time)
- Entity relationship mapping
- Cross-story entity linking
- Entity-based alerts

**Schema additions**:
```sql
CREATE TABLE entities (
    id SERIAL PRIMARY KEY,
    canonical_name VARCHAR(255) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,  -- person/org/location/topic
    aliases JSONB DEFAULT '[]',
    description TEXT,
    metadata JSONB DEFAULT '{}',
    first_seen TIMESTAMP DEFAULT NOW(),
    mention_count INT DEFAULT 0,
    avg_sentiment FLOAT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE entity_mentions (
    id SERIAL PRIMARY KEY,
    entity_id INT REFERENCES entities(id) ON DELETE CASCADE,
    article_id INT REFERENCES items(id) ON DELETE CASCADE,
    story_id INT REFERENCES stories(id) ON DELETE SET NULL,
    mention_context TEXT,
    sentiment_score FLOAT,
    prominence_score FLOAT,  -- how central to the article
    mentioned_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_entity_mentions_entity ON entity_mentions(entity_id);
CREATE INDEX idx_entity_mentions_article ON entity_mentions(article_id);
CREATE INDEX idx_entity_mentions_story ON entity_mentions(story_id);
```

#### v0.9.1 - Multi-Perspective Synthesis
**Goal**: Show what sources agree/disagree on, not just merge them.

- Consensus point extraction
- Divergence detection and highlighting
- Coverage gap identification
- Source attribution for each claim
- "Contested fact" flagging

**Schema additions**:
```sql
ALTER TABLE stories ADD COLUMN consensus_points JSONB DEFAULT '[]';
ALTER TABLE stories ADD COLUMN divergence_points JSONB DEFAULT '[]';
ALTER TABLE stories ADD COLUMN coverage_gaps JSONB DEFAULT '[]';
ALTER TABLE stories ADD COLUMN source_agreement_score FLOAT;
```

**Example output structure**:
```json
{
  "consensus": [
    {"claim": "10,000 jobs cut", "sources": ["Reuters", "AP", "WSJ"], "confidence": 0.95}
  ],
  "divergence": [
    {
      "topic": "Cause of layoffs",
      "perspectives": [
        {"view": "AI automation", "sources": ["TechCrunch", "Wired"]},
        {"view": "Economic downturn", "sources": ["Bloomberg", "FT"]}
      ]
    }
  ],
  "gaps": [
    {"missing": "International office impact", "expected_sources": ["Local news"]}
  ]
}
```

#### v0.9.2 - Story Evolution & Timeline
**Goal**: Track how stories develop over time.

- Story event timeline
- "Breaking" → "Developing" → "Established" status
- Correction tracking
- Major update notifications
- Story lifespan analytics

**Schema additions**:
```sql
CREATE TABLE story_events (
    id SERIAL PRIMARY KEY,
    story_id INT REFERENCES stories(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,  -- broke/update/correction/resolved
    event_title VARCHAR(255),
    event_description TEXT,
    source_articles JSONB DEFAULT '[]',
    significance_score FLOAT DEFAULT 0.5,
    occurred_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE stories ADD COLUMN story_status VARCHAR(20) DEFAULT 'active';
ALTER TABLE stories ADD COLUMN first_reported_at TIMESTAMP;
ALTER TABLE stories ADD COLUMN last_major_update TIMESTAMP;
ALTER TABLE stories ADD COLUMN update_count INT DEFAULT 0;

CREATE INDEX idx_story_events_story ON story_events(story_id);
CREATE INDEX idx_story_events_occurred ON story_events(occurred_at);
```

#### v0.9.3 - Smart Data Extraction
**Goal**: Pull structured data from unstructured content.

- Key statistics extraction (numbers, percentages, financial figures)
- Notable quote extraction with attribution
- Geographic tagging and mapping
- Date/timeline extraction from article content
- Structured data storage for search/filter

**Schema additions**:
```sql
CREATE TABLE extracted_data (
    id SERIAL PRIMARY KEY,
    article_id INT REFERENCES items(id) ON DELETE CASCADE,
    data_type VARCHAR(50) NOT NULL,  -- statistic/quote/location/date
    data_value JSONB NOT NULL,
    confidence_score FLOAT,
    extraction_method VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_extracted_data_article ON extracted_data(article_id);
CREATE INDEX idx_extracted_data_type ON extracted_data(data_type);
```

### Phase 3: Context Layer (v0.10.x)

#### v0.10.0 - "Why This Matters" Context Engine
**Goal**: Add meaning beyond the facts.

- Automated context generation
- Historical precedent linking
- Impact analysis (who/what is affected)
- Personal relevance scoring
- Industry/sector context

**Implementation approach**:
- LLM-powered context generation with structured prompts
- Entity-based context (your tracked entities involved)
- Feed-based context (connects to your interests)
- Historical database for precedent matching

#### v0.10.1 - Trend Detection & Analysis
**Goal**: Surface patterns humans might miss.

- Cross-story trend identification
- Volume anomaly detection
- Sentiment trend tracking
- Predictive signals based on patterns
- Trend alerts and dashboards

#### v0.10.2 - Confidence & Transparency System
**Goal**: Be honest about what we know and don't know.

- Per-story confidence scoring
- Source quality indicators
- Claim-level attribution
- "Developing story" warnings
- Uncertainty language in synthesis

**Schema additions**:
```sql
ALTER TABLE stories ADD COLUMN confidence_score FLOAT;
ALTER TABLE stories ADD COLUMN confidence_factors JSONB DEFAULT '{}';
ALTER TABLE stories ADD COLUMN is_developing BOOLEAN DEFAULT false;
ALTER TABLE stories ADD COLUMN verification_status VARCHAR(20);
```

### Phase 4: Experience Layer (v0.11.x)

#### v0.11.0 - Reading Tiers & Depth Control
**Goal**: Let users choose their depth.

- Headline mode (title + 1 line)
- Brief mode (2-3 sentence summary)
- Standard mode (current output)
- Deep dive mode (full analysis with all context)
- Reading time estimates
- Complexity indicators

#### v0.11.1 - Audio & Accessibility
**Goal**: Content consumption beyond reading.

- TTS story narration
- Podcast-style daily briefings
- Audio player with speed controls
- Accessibility improvements (screen reader, high contrast)

#### v0.11.2 - Enhanced Visualizations
**Goal**: Visual intelligence delivery.

- Entity relationship graphs
- Story timeline visualizations
- Geographic story mapping
- Trend charts and dashboards
- Source diversity indicators

### Phase 5: Monetization (v1.0)

#### v1.0.0 - Premium Platform
**Goal**: Sustainable business model.

**Free Tier**:
- Basic synthesis
- Limited feeds (10)
- Standard depth only
- 24-hour delay on new stories
- Web access only

**Premium Tier**:
- Multi-perspective analysis
- Unlimited feeds
- All depth levels
- Real-time updates
- Entity tracking & alerts
- Audio narration
- API access
- Export capabilities
- Priority support

**Team/Enterprise**:
- Shared workspaces
- Custom feed bundles
- Competitive intelligence features
- SSO integration
- Usage analytics

## Consequences

### Positive

1. **Differentiation**: Transforms from commodity aggregator to unique intelligence product
2. **Monetization path**: Clear premium value proposition
3. **Defensibility**: Entity intelligence and context layers create switching costs
4. **Quality focus**: Each phase improves output quality
5. **Incremental delivery**: Each milestone provides standalone value

### Negative

1. **Complexity**: Significant increase in system complexity
2. **LLM costs**: More sophisticated analysis requires more compute
3. **Data requirements**: Entity intelligence needs ongoing maintenance
4. **Timeline**: Full vision requires 12-18 months of development
5. **Scope risk**: Temptation to over-engineer each phase

### Mitigations

1. **Strict phase gating**: Complete each phase before starting next
2. **LLM optimization**: Caching, batching, model selection per task
3. **External data integration**: Use existing credibility databases (Media Bias/Fact Check)
4. **MVP mindset**: Ship minimal viable version of each feature
5. **User feedback loops**: Validate value before expanding scope

## Success Metrics

| Phase | Key Metrics |
|-------|-------------|
| Foundation | Extraction success rate >95%, synthesis quality score improvement |
| Intelligence | Entity coverage >80%, perspective detection accuracy |
| Context | User engagement with context features, time-on-story increase |
| Experience | Tier adoption rates, audio playback minutes |
| Monetization | Conversion rate, MRR, churn rate |

## References

- [ADR-0002: Story-based Aggregation](0002-story-based-aggregation.md)
- [ADR-0022: Dev/Prod Database Parity](0022-dev-prod-database-parity.md)
- [ARCHITECTURAL_ROADMAP.md](ARCHITECTURAL_ROADMAP.md)

## Appendix: Competitive Analysis

| Feature | NewsBrief (Target) | Feedly | Apple News | Google News |
|---------|-------------------|--------|------------|-------------|
| Multi-perspective | ✅ | ❌ | ❌ | ❌ |
| Entity intelligence | ✅ | Partial | ❌ | Partial |
| Story evolution | ✅ | ❌ | ❌ | Partial |
| Source credibility | ✅ | ❌ | Curated | ❌ |
| Confidence signals | ✅ | ❌ | ❌ | ❌ |
| Local LLM option | ✅ | ❌ | ❌ | ❌ |
| Self-hosted | ✅ | ❌ | ❌ | ❌ |
| Privacy-first | ✅ | ❌ | ❌ | ❌ |
