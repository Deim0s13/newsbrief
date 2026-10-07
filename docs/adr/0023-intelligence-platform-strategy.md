# ADR 0023: Intelligence Platform Strategy

## Status

**Accepted** - February 2026

## Context

NewsBrief has evolved from a simple RSS reader to a story-based news aggregator with LLM-powered synthesis. With the completion of v0.7.x (infrastructure maturity, PostgreSQL parity), we now have a solid foundation to build upon.

However, the current product is fundamentally an **aggregator** - it collects and summarizes content. To create a high-quality, differentiated personal tool, we need to transform NewsBrief into an **intelligence platform** that helps truly understand what's happening, not just see what's being reported.

### Current Limitations

1. **Surface-level synthesis**: Stories merge articles but don't analyze perspectives
2. **No source intelligence**: All sources treated equally regardless of credibility
3. **Static stories**: No tracking of how stories evolve over time
4. **Limited context**: No historical context or "why this matters" analysis
5. **Single output format**: One-size-fits-all story presentation
6. **No entity intelligence**: People/companies mentioned but not tracked across stories

### Design Standard

Professional news intelligence products (Bloomberg Terminal, Feedly Pro) are built to provide **insight**, not just information. NewsBrief is built to that same quality standard — not because it will be sold, but because a tool used daily deserves the same depth and rigour. That means:

- Multi-perspective analysis (what sources agree/disagree on)
- Entity tracking and sentiment over time
- Confidence signals and source transparency
- Tiered depth (headlines → deep dives)
- Pattern and trend detection across stories

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

### Phase 5: Production Ready (v1.0)
Polish for long-term personal production use: authentication, API access, data portability, and multi-machine capability.

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

**Implementation status (v0.9.0, shipped Aug 2026)**: The schema above shipped
as designed, plus one addition (`entities.last_seen`, needed by the profile
pages below but only implicit in this ADR's `first_seen`). Delivered against
issues #199-#202 and #284:
- Entity extraction/normalization/dedup wired into the existing per-article
  LLM extraction at cluster time, plus a one-time backfill script
  (`app/entity_normalization.py`, `app/entity_backfill.py`) — #199, extends #200.
- Entity-based story connections: stories sharing entities, ranked by shared
  count + prominence + temporal proximity, surfaced via
  `GET /stories/{id}/entity-connections` and clickable entity chips
  (`app/entity_connections.py`) — #202.
- Entity profile pages (`/entities/{id}`) with mention timeline and
  co-mentioned entities, plus basic name/alias search (`/entities?q=`)
  (`app/entity_profile.py`) — #201.
- Entity overlap as a secondary, capped re-ranking signal alongside the
  existing embedding-based continuity check in `historical_linking.py`
  (never overrides a stronger embedding match, only breaks near-ties) — #284.

**Deferred** (out of this pass, tracked separately): per-entity sentiment
(`avg_sentiment`/`sentiment_score` ship in the schema but stay unpopulated —
the extraction prompt doesn't currently produce it), entity-based alerts, and
fuzzy/LLM-based disambiguation beyond exact-match-after-canonicalization
(e.g. "Amazon" vs "Amazon.com Inc." still register as distinct entities).

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

**Implementation status (v0.9.1, shipped Sep 2026)**: Delivered against
issues #203, #204, #229, #205, in four phases with two review checkpoints
against real/synthetic data (see commit history for details). Several
deviations from the design above, agreed with the user at each phase:

- **Perspective detection (#203)** extends the existing per-article entity
  extraction LLM call rather than adding a new one — `PerspectiveOutput`
  (`app/llm_output.py`) classifies `stakeholder`/`political_leaning`/
  `regional`/`tone`, cached in `items.perspective_json` alongside entities.
  `applicable=False` is the expected/common case (confirmed against real
  feed data: 6/6 tech articles in the Checkpoint 1 sample were not
  applicable — this feed is tech/product news, not general political
  coverage).
- **Consensus/divergence (#204)** extends the synthesis LLM call
  (`SynthesisOutput.consensus_points`/`divergence_points`/
  `source_agreement_score`) rather than a separate pass, grounded by tagging
  each source article in the prompt with its feed name + cached perspective
  hint. `sources` values are required (via explicit prompt instruction added
  after a Checkpoint 2 finding) to be the article's publication name, not an
  in-text stakeholder/actor name the model might otherwise pick up on (e.g.
  "TechCorp" instead of the outlet that reported on TechCorp). Only wired
  for the direct synthesis strategy (≤8 articles/cluster) — map-reduce/
  hierarchical clusters leave these null.
- **Coverage gaps (#229)** is rule-based, not LLM-based — no story-type
  classifier exists in this codebase, so `app/perspective_gaps.py` instead
  checks the 3 populated perspective dimensions from #203 (`stakeholder`,
  `political_leaning`, `regional`; `tone` excluded as framing, not a
  viewpoint gap) for one-sided coverage across a cluster, requiring ≥2
  articles with a value before evaluating a dimension. Output drops the
  `expected_sources` field from the example above (a rule-based check can't
  know what a missing source would say) in favor of `{dimension, present,
  missing}`. Same direct-strategy-only scoping as consensus/divergence.
- **UI (#205)** ships a reduced scope, agreed with the user given how
  sparse perspective data is in practice on this feed: a collapsible
  "Multi-Perspective Coverage" panel (consensus/divergence/gaps/agreement
  score) plus per-article source name + perspective chips on the story
  detail page. The visual spectrum bar and click-to-filter-by-perspective
  from the original issue are deferred as a possible fast-follow — nothing
  shipped here is throwaway if that's built later, it's additive on the
  same markup/data.

**Deferred** (out of this pass, tracked separately): the spectrum
bar/click-to-filter UI noted above; "contested fact" flagging as its own
concept distinct from divergence_points; extending consensus/divergence/gaps
to the map-reduce and hierarchical synthesis strategies (>8 articles/
cluster).

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

**Implementation status (v0.9.2, shipped Sep 2026)**: Delivered against
issues #206, #207, #283, #208, #209, with one review checkpoint. Notable
deviations from the design above, agreed with the user:

- **`story_status` default is `'breaking'`, not `'active'`** as shown in
  the schema sketch above — `'active'` is already the meaning of the
  existing `stories.status` column (pipeline/publish lifecycle, ADR-0004/
  #287); reusing it for `story_status` (narrative-development lifecycle)
  would have made two differently-scoped concepts look like the same
  value by coincidence.
- **Event detection (#207) is entirely rule-based, not LLM-classified.**
  Unlike perspective/consensus/divergence in v0.9.1, this deliberately
  does *not* extend the update-synthesis LLM call: `broke` fires once
  automatically when a story is first created; `update` vs. `development`
  is classified from new-article ratio + dormancy-then-reactivation
  (`app/story_events.py`), not narrative judgment. This was a checkpoint
  decision — LLM-based "what changed" summarization was considered and
  deferred (see Deferred below) rather than reintroducing v0.9.1's
  LLM-output-quality-tuning cycle for a first pass.
- **`correction` and `resolved` event types are defined but not yet
  auto-detected.** Reliably flagging "this update contradicts earlier
  reporting" needs an actual old-synthesis-vs-new-synthesis comparison;
  doing it cheaply risked false-positive corrections eroding trust (the
  same trust concern that motivated the v0.9.1 grounding-block hotfix).
  Both values remain valid for manual/future use.
- **`story_status` transitions are lazy, not push-based.** Set at
  write-time when a `broke`/`update` event is created, plus a bulk
  `refresh_stale_story_statuses()` sweep run opportunistically at the end
  of every story-generation pass (scheduled or manual) to catch stories
  that simply went quiet without a new event triggering a write.
- **#283 (continuity linking) is satisfied mostly by existing
  infrastructure**, not a new build: cross-story semantic linking already
  existed (`continues_story_id`, `app/historical_linking.py`, v0.8.6); the
  richer same-story version-chain relationship (continues/development)
  is now covered by #207's events instead of a separate relationship
  taxonomy.
- **#208 (timeline UI) ships a reduced scope**, matching the v0.9.1 UI
  precedent: a collapsible "Story Timeline" panel plus a lifecycle badge,
  hidden entirely for stories that haven't evolved (single-event
  timeline, `update_count == 0`) rather than showing low-signal chrome on
  every story. No scrubbing, animation, or "view as of date".
- **#209 (update notifications) is descoped from personalized
  notifications to a non-personalized indicator.** The issue's own
  requirements ("track which stories users have viewed") depend on
  read/view tracking that doesn't exist anywhere in this codebase yet
  (tracked separately as #125, not scheduled until v0.11.2) — building
  personalized "notify me" without that foundation isn't possible.
  Shipped instead: an "Updated Xh ago" badge on the stories list and a
  new `order_by=updated` sort option (`stories.last_major_update`
  coalesced with `generated_at`).

**Deferred** (out of this pass, tracked separately): LLM-generated
"what's new" event descriptions (current descriptions are deterministic
strings, e.g. "3 new articles from 2 sources added"); automatic
`correction`/`resolved` event detection; personalized per-user update
notifications (blocked on #125 read-tracking); timeline scrubbing/
animation/"view as of date" UI.

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

**Implementation status (v0.9.3, shipped Sep 2026)**: Delivered against
issues #210, #211, #212, #213, with one review checkpoint. Notable
deviations from the design above, agreed with the user:

- **`data_type` taxonomy is `statistic`/`quote`/`claim`/`date`/`amount`,
  not `statistic`/`quote`/`location`/`date`** as sketched above —
  `location` is dropped and `claim` is added. Location *names* are
  already covered by the existing NER pipeline (`Entity`/`EntityMention`,
  v0.9.0); a coordinate-less "location" data point here would just
  duplicate that without adding value. `claim` (specific factual
  assertions worth verifying) was added because it turned out to be one
  of the most common data-point shapes in real article content that
  didn't fit `statistic`/`quote`/`date`/`amount`.
- **Extraction is its own dedicated LLM call, not piggybacked onto
  summarization or entity extraction** (unlike v0.9.1's perspective-on-
  entities piggyback). It runs on the article's full content (not the
  summary) so specific numbers/quotes aren't lost to summarization's
  compression, and keeps its own circuit breaker (`data_extraction`) so a
  bad run doesn't couple to summarization's or entity extraction's
  failure modes.
- **`extracted_data.context` (surrounding sentence, for verification) was
  added** beyond the original schema sketch — every trackable data point
  needs some text to judge "is this really the same statistic as that
  other one" (see #213 below), and `context` is what that comparison
  runs against.
- **A real prompt-quality bug was found and fixed during the checkpoint**:
  the model was silently normalizing currency symbols (writing `"$250"`
  for a `£250` figure while correctly labeling `unit: "pounds"`). Fixed
  with an explicit "preserve the original currency symbol" prompt
  instruction; confirmed fixed by re-running against the same article.
- **Per-data-point confidence scores are sometimes uniform across a
  whole extraction response** (e.g. all `0.6`, or all `0.9`) rather than
  differentiated per item — confirmed (by inspecting raw LLM JSON
  directly) to be real sampling variance in the underlying 8B model's
  output, not a defect in the parsing/storage pipeline, which faithfully
  preserves whatever the model returns. Left as a known limitation:
  `#212`'s UI sorts by `confidence_score`, so sort order is occasionally
  arbitrary within one article.
- **#212 (Key Facts UI) does not include a corpus-wide search/filter
  endpoint** — "structured data storage for search/filter" from the goal
  above is satisfied only as a client-side type filter (statistic/quote/
  claim/date/amount) within one story's Key Facts panel, not a new
  `/search`-style API across all `extracted_data` rows. No existing UI
  pattern or issue asked for a dedicated cross-story data-point search
  page; descoped as out of scope for a first pass.
- **#213 (cross-story tracking) ships a much smaller scope than "aggregate
  statistics across ALL stories."** A corpus-wide version needs a
  canonical "subject of this statistic" label this codebase has no
  infrastructure for (no embeddings/index over data points). Scoped down
  at the v0.9.3 proposal checkpoint to two bounded, rule-based (no LLM)
  checks instead: same-story conflict detection (two different articles
  in one story reporting a different value for what looks like the same
  statistic) and continuation-chain change detection (diffing against the
  story this one continues, via the existing `continues_story_id` link,
  v0.8.6) — both using word-overlap (Jaccard similarity on `context`) as
  a deliberately coarse, explainable "same subject" heuristic (see
  `app/data_trends.py`). No geographic/location-based tracking (see the
  `data_type` deviation above).
- **Geographic tagging and mapping** (from the goal bullets above) was
  not attempted at all — no coordinates, no map UI, no location data
  type. This has no supporting infrastructure anywhere in this codebase
  and is tracked separately for the v0.11.2 visualization milestone.

**Deferred** (out of this pass, tracked separately): geographic tagging/
mapping (v0.11.2); corpus-wide data-point search/aggregation across all
stories, not just a continuation chain; multi-chunk extraction for very
long articles (current cap is a single ~6000-char prompt window, no
map-reduce); LLM-based (rather than word-overlap) same-subject matching
for #213, if the heuristic's false-positive/negative rate proves too
coarse in practice.

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

**Schema additions**:
```sql
CREATE TABLE story_context (
    id SERIAL PRIMARY KEY,
    story_id INT REFERENCES stories(id) ON DELETE CASCADE,
    context_type VARCHAR(20) NOT NULL,  -- significance/background/glossary/precedent
    content JSONB NOT NULL,
    source_story_ids JSONB,
    confidence_score FLOAT,
    generation_method VARCHAR(20) DEFAULT 'llm',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_story_context_story ON story_context(story_id);
CREATE INDEX idx_story_context_type ON story_context(context_type);
```

**Implementation status (v0.10.0, shipped Sep 2026)**: Delivered against
issues #285, #214, #215, #216, with one review checkpoint against a
real-world sample story. Notable deviations from the design above, agreed
with the user:

- **Additive, not a replacement, for the pre-existing
  `stories.why_it_matters` column.** That column (a single free-text
  paragraph generated inline in the core synthesis prompt since early
  versions) already partially satisfied this milestone's goal before
  #285 was even scoped. Rather than risk a breaking change to synthesis
  prompts, quality scoring, and the tests that already assert on
  `why_it_matters`, the new `story_context` table/stage sits alongside
  it — the story detail page now renders both in the same "Why It
  Matters" box (legacy paragraph + new multi-angle significance
  breakdown underneath).
- **#285's "formal pipeline stage" is a dedicated LLM call
  (`app/context_generation.py`), not a blend into synthesis** — same
  separation rationale as v0.9.3's data extraction: it runs on the
  story's own synthesis text (not raw articles) so every context type is
  grounded in what was actually published, and it has its own circuit
  breaker (`context_generation`) so a bad run doesn't couple to
  synthesis's failure mode.
- **One combined LLM call produces all four context types
  (significance/background/glossary/precedent), not four separate
  calls** — cost/latency reasons. `background` and `precedent` are
  gated in code, not left to the LLM to decide whether to volunteer:
  - `background` (#215's "complex stories" requirement) requires
    `article_count >= 5` OR `complexity_score >= 0.5` (reusing #280's
    existing advisory score rather than adding new config).
  - `precedent` requires the story to already have a resolved
    `continues_story_id` or light_rag anchor — it must reference a prior
    story this codebase already identified as related, never free-text
    historical trivia the LLM might invent.
  - `significance` and `glossary` are requested for every story.
- **"Reference previous related stories" (#215) reuses existing
  infrastructure rather than rebuilding it** — `context_anchors_json`/
  `continues_story_id` (#258/#279/#281) already covers this and is
  unchanged; `precedent` only adds a short narrative note on top of an
  already-resolved link, it doesn't do its own related-story search.
- **#216's "context personalization toggle" / "Customize my context"
  was not attempted.** This is a single-user app with no per-user
  auth/preferences infrastructure anywhere in the codebase (see ADR-0023
  Phase 5's "Optional user authentication" as the first point anything
  like this could hang off); tracked as a gap, not silently dropped.
- **Glossary uses hover tooltips (`title` attribute) for definitions**,
  not a separate on-click popover component — the simplest option that
  satisfies #216's "inline term definitions" AC without a new JS
  interaction pattern.

**Deferred** (out of this pass, tracked separately): context
personalization/preferences (#216, blocked on no auth system, see
v1.0.0 below); entity-based and feed-based context inputs to the prompt
beyond the topics/entities already on the `Story` row; a dedicated
historical-precedent database/index (precedent is currently limited to
whatever `continues_story_id`/light_rag anchors already resolved, not a
broader precedent search).

#### v0.10.1 - Trend Detection & Analysis
**Goal**: Surface patterns humans might miss.

- Cross-story trend identification
- Volume anomaly detection
- Sentiment trend tracking
- Predictive signals based on patterns
- Trend alerts and dashboards

**Implementation status (v0.10.1, shipped Oct 2026)**: Delivered against
issues #217, #218, #219, with one review checkpoint against real production
data (69 feeds, ~15-70 articles/day across ~10 topics). Notable deviations
from the design above, agreed with the user at the planning and checkpoint
stages:

- **Live computation, no new table or scheduled job.** At this app's real
  volume (confirmed against prod before designing anything), a few
  `GROUP BY items` queries answer this cheaply — a persisted daily-snapshot
  table would be premature infrastructure. A short in-process TTL cache
  (`app/trend_detection.py`, mirroring `app/topics.py`'s existing
  `_topics_cache` mtime-reload pattern) avoids recomputing on every request
  without a migration.
- **Daily buckets, not hourly.** The design goal above implies hourly
  granularity ("articles per hour/day"); at this volume, hourly buckets
  would be almost entirely zeros/ones with no real signal. Descoped to
  daily only.
- **"Sentiment trend tracking" is explicitly descoped, not built.**
  `items.perspective_json.tone` (v0.9.1) is only populated on ~8% of
  articles (confirmed by a live prod query during scoping) and is `null`
  even then unless an article reads as clearly opinionated — a signal
  built on it would almost always be empty. Flagged here rather than
  silently dropped; revisit if perspective coverage improves.
- **"Predictive signals" was not attempted.** No labeled historical
  dataset exists in this codebase to validate a predictive model against;
  descoped to the two bounded, explainable signals that shipped (velocity/
  acceleration, and the three anomaly types below) rather than guessing at
  forecasting.
- **Anomaly detection (#219) adds a wider, stricter check than #217's
  "hot" classification** — a fixed 2x-baseline ratio (velocity) is a
  different signal from a z-score over a 30-day trailing baseline
  (`app/anomaly_detection.py`): a topic that normally varies a lot needs a
  bigger jump to count as a statistical anomaly than one that's always
  steady. Three types shipped: **spike** (z-score jump), **silence** (a
  reliably-covered topic going quiet), and **new_entrant** (a feed
  covering an already-established topic for the first time in 30 days —
  explicitly distinct from a topic itself being new, which is #217's
  "emerging" classification, not an anomaly).
- **Dashboard (#218) is a server-rendered page, not a JSON API + client
  fetch.** `app/templates/stories.html` (the only other page on this
  app's "trending" surface) turned out to be a JS-driven, client-filtered
  SPA-style page — the new `/trends` page instead follows the
  `story_detail.html`/`entity_profile.html` convention (data computed in
  the route handler, rendered server-side), consistent with how every
  other v0.9.x/v0.10.x feature in this codebase ships its UI. A compact
  "Trending Now" widget (hot/growing/emerging topics only) was added to
  the homepage to satisfy the "trends visible on homepage" acceptance
  criterion without duplicating the full dashboard there.
- **A real latent bug was found and fixed before building the dashboard
  on top of it**: `compute_topic_trends()`'s acceleration calculation
  (today's velocity vs. yesterday's) needs data further back than its own
  sparkline window fetches once the requested day-range is small relative
  to the baseline window — e.g. a 7-day dashboard view with the default
  7-day baseline. Fixed by decoupling "how far back to query" from "how
  many days to display"; covered by a regression test.

**Deferred** (out of this pass, tracked separately): sentiment-shift
tracking (needs broader perspective-tag coverage first); predictive/
forecasting signals (needs a labeled dataset to validate against);
cross-story (as opposed to cross-topic) trend identification — the design
goal's "cross-story trend identification" is satisfied here at the topic
level, not by linking individual stories into trend narratives.

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

### Phase 5: Production Ready (v1.0)

#### v1.0.0 - Production Ready
**Goal**: Polish the app for stable long-term personal use with the quality bar of a production product.

- Optional user authentication and API key management
- REST API access for external tooling and widgets
- Data export and portability (feeds, stories, entities)
- Full-text search (PostgreSQL FTS)
- Multi-machine capability (auth enables clean state separation)
- Platform polish: macOS widget, packaging for clean install

## Consequences

### Positive

1. **Quality**: Transforms from commodity aggregator to a genuinely insightful personal tool
2. **Depth**: Entity intelligence and context layers make stories more meaningful over time
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
| Context | Context generation success rate, historical link accuracy |
| Experience | Reading tier usage, audio playback completions |
| Production Ready | Auth stability, API response times, data export integrity |

## References

- [ADR-0002: Story-based Aggregation](0002-story-based-aggregation.md)
- [ADR-0022: Dev/Prod Database Parity](0022-dev-prod-database-parity.md)
- [ARCHITECTURAL_ROADMAP.md](ARCHITECTURAL_ROADMAP.md)

## Appendix: Competitive Analysis

| Feature | NewsBrief (Goal) | Feedly | Apple News | Google News |
|---------|-------------------|--------|------------|-------------|
| Multi-perspective | ✅ | ❌ | ❌ | ❌ |
| Entity intelligence | ✅ | Partial | ❌ | Partial |
| Story evolution | ✅ | ❌ | ❌ | Partial |
| Source credibility | ✅ | ❌ | Curated | ❌ |
| Confidence signals | ✅ | ❌ | ❌ | ❌ |
| Local LLM option | ✅ | ❌ | ❌ | ❌ |
| Self-hosted | ✅ | ❌ | ❌ | ❌ |
| Privacy-first | ✅ | ❌ | ❌ | ❌ |
