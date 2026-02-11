# NewsBrief RAG Architectural Options Analysis

**Issue**: #108 - Research RAG integration for better context
**Date**: February 2026
**Status**: Research Complete

---

## 1. Executive Summary

NewsBrief can likely gain meaningful value from semantic retrieval—especially for:
- **Related content discovery** (beyond keyword matches)
- **Semantic deduplication / clustering**
- **Historical storyline awareness** (e.g., "this continues from last month…")

However, "full RAG" (chunking + retrieval + large context injection into synthesis prompts) introduces significant complexity and can degrade summary quality via topic drift unless retrieval is highly precise and tightly controlled.

### Recommendation

Adopt a staged approach:
- **Target direction**: Option 2 – Light RAG (inject 1–3 controlled "anchors" into synthesis)
- **Foundation**: Option 1 – Embeddings for retrieval (semantic layer) as prerequisite
- **Storage**: PostgreSQL + pgvector (single datastore, aligned with existing architecture)
- **Defer/avoid**: Option 3 – Full RAG unless NewsBrief becomes a research product

### Next Step

Paper-based design sign-off → proceed to a small, time-boxed pilot only if the go/no-go gates look achievable.

---

## 2. Problem Statement

NewsBrief currently generates briefs primarily from a recent time window and uses heuristic approaches (keywords/entity overlap/title similarity) for grouping, clustering, dedupe, and synthesis context.

### Current Limitations

| Area | Current Approach | Limitation |
|------|------------------|------------|
| Duplicate detection | Hash-based, title similarity | Weak detection of paraphrased duplicates |
| Historical context | None | Limited ability to link "today's story" to related past stories |
| Synthesis continuity | Manual/none | May miss "what changed since last time?" |
| Related content | Keyword/topic matching | Can't find semantically similar content with different terminology |

We need to determine whether RAG/embeddings will deliver enough benefit to justify the additional architecture, storage, compute, and operational complexity.

---

## 3. Desired Outcomes and Success Measures

### Outcomes (Prioritized)

| Priority | Outcome | Goal | Measure |
|----------|---------|------|---------|
| 1 | **Related content discovery** | Retrieve genuinely related articles/stories even when terminology differs | Top-K semantic retrieval precision improves vs current approach |
| 2 | **Semantic dedupe / clustering** | Reduce repeated coverage of the same story across outlets | Fewer duplicates without collapsing distinct stories |
| 3 | **Historical storyline awareness** | Connect current stories to relevant prior stories | "This relates to X from last month…" links are accurate and helpful |
| 4 | **Synthesis quality uplift** | Better continuity and context with minimal drift | Human evaluation: more coherent briefs, no muddiness |

**Key insight**: If outcomes 1–3 don't materially improve, outcome 4 rarely will.

---

## 4. Constraints and Non-Functional Requirements

- **Containerised application** run "as if monetised": stateless app + persistent data service/volume
- **Predictable runtime and latency** (daily usage)
- **Storage growth and retention policy** must be manageable (30/90/365 days)
- **Re-indexing strategy** when embedding model changes
- **Explainability**: ability to see why something was retrieved ("retrieval trace")

---

## 5. Decision Drivers and Weighting

| Driver | Weight |
|--------|--------|
| Quality uplift potential | 30% |
| Operational complexity | 20% |
| Implementation complexity | 15% |
| Latency impact | 10% |
| Cost/compute | 10% |
| Explainability & debuggability | 10% |
| Future extensibility | 5% |

---

## 6. Options Considered

### Option 0 — No Embeddings / No RAG (Improve Heuristics Only)

**Description**: Keep improving keyword/entity/title similarity rules; enhance entity resolution, source weighting, story lifecycle, etc.

| Pros | Cons |
|------|------|
| Lowest complexity and fastest iteration | Ceiling on paraphrases/semantic similarity |
| Minimal ops and zero additional moving parts | Limited historical linking without heavy bespoke logic |

**Best fit when**: NewsBrief stays "daily brief" and continuity is not a key product feature.

---

### Option 1 — Embeddings for Retrieval Only (Semantic Layer)

**Description**: Generate and store embeddings for articles and/or stories. Use semantic similarity for:
- Related content discovery
- Semantic dedupe and clustering support
- Cross-story linking
- Historical anchor retrieval

Do not inject large retrieved text into synthesis prompts initially.

| Pros | Cons |
|------|------|
| Captures most benefit with lower risk | Doesn't guarantee synthesis uplift without further design |
| Enables storyline linking + semantic dedupe | Requires embedding indexing + versioning discipline |
| Sets foundation for semantic search later | |
| Low chance of degrading synthesis quality | |

**Best fit when**: You want improved discovery/dedupe/linking with controlled risk.

---

### Option 2 — Light RAG (Small, Controlled Anchors in Synthesis) ⭐ RECOMMENDED

**Description**: Build on Option 1; retrieve only 1–3 high-confidence anchors (prior story bullet summaries/snippets) and include them in synthesis prompts.

| Pros | Cons |
|------|------|
| Meaningful continuity improvements possible | Needs careful prompt design and confidence gating |
| Still manageable if context is strictly limited | Can introduce topic drift if retrieval is noisy |

**Best fit when**: Option 1 retrieval is strong and you want measurable synthesis uplift.

---

### Option 3 — Full RAG Pipeline (Chunking + Retrieval + Reranking + Prompt Injection)

**Description**: Chunk article bodies; embed chunks; retrieve many chunks; optionally rerank; feed into synthesis.

| Pros | Cons |
|------|------|
| Maximum capability for deep "research-like" synthesis | Highest complexity and maintenance overhead |
| | Higher latency and more tuning |
| | Most likely to degrade output quality without rigorous evaluation |

**Best fit when**: NewsBrief becomes a research assistant product and you accept higher ops.

---

## 7. Storage Topology Options

### A) PostgreSQL + pgvector (Single Datastore) ⭐ RECOMMENDED

| Pros | Cons |
|------|------|
| One DB for metadata + vectors, easy joins/filters | Extension lifecycle management |
| "SaaS-like" posture | |
| Aligned with existing architecture (ADR-0022) | |

**Best fit**: Containerised monetisation posture, likely future hosting

### B) PostgreSQL + Dedicated Vector DB (e.g., Qdrant)

| Pros | Cons |
|------|------|
| Vector-native features, scalable retrieval | Two datastores to operate and keep consistent |

**Best fit**: Vector search becomes a primary product capability

### C) SQLite + sqlite-vec (Local-First, Simple)

| Pros | Cons |
|------|------|
| Lowest ops, single file, fast to iterate | Less aligned with "multi-tenant SaaS" posture |

**Best fit**: Single-instance/personal usage, minimal ops

---

## 8. Comparative Scoring

| Option | Quality Uplift | Ops Complexity | Impl Complexity | Latency | Debuggability | Overall |
|--------|----------------|----------------|-----------------|---------|---------------|---------|
| 0 Heuristics only | Medium | Low | Low | Low | High | Safe |
| 1 Retrieval only | High | Medium | Medium | Low–Med | High | Foundation |
| **2 Light RAG** | **High** | **Medium** | **Medium** | **Medium** | **Medium** | **Best measured uplift** |
| 3 Full RAG | Very high (potential) | High | High | High | Low–Med | Highest risk |

---

## 9. Key Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| **False relatedness** (incorrect linking) | Metadata filters (topic/date/source), similarity thresholds, allow "no link" |
| **Topic drift in synthesis** (anchors derail summary) | Inject only structured anchors (bullets), only if confidence is high |
| **Index drift** (embedding model changes) | Store embedding_model, embedding_version, text_hash; support background re-indexing |
| **Latency & compute** | Embed on ingestion; cache embeddings; keep retrieval top-k small |
| **Explainability** | Persist retrieval traces (IDs + similarity score + reason used) |

---

## 10. Final Recommendation

### Chosen Direction

- **Option 2 (Light RAG)** as target architecture
- **PostgreSQL + pgvector** for storage (single datastore)
- **Option 1 (Retrieval only)** as foundation/prerequisite

### Rationale

Option 2 offers the best trade-off: strong improvements to relatedness/dedupe/linking and storyline awareness with controlled synthesis uplift potential. PostgreSQL + pgvector aligns with existing architecture (ADR-0022) and avoids operational complexity of separate vector DB.

---

## 11. Go/No-Go Gates for Pilot

Move to a pilot only if these are credible and testable:

| Gate | Threshold |
|------|-----------|
| **Relatedness precision** | Top-5 retrieval contains ≥3 genuinely related items in ≥75% of cases |
| **Semantic dedupe** | Demonstrable reduction in "rewritten duplicates" without collapsing distinct stories |
| **Historical linking** | ≥80% of proposed links judged accurate/helpful by human review |
| **No regression** | Runtime, latency, and brief quality remain acceptable for daily use |

---

## 12. Pilot Scope (If Approved)

### Pilot Goals

Validate retrieval, dedupe, linking, and (optionally) a minimal anchor injection strategy.

### Pilot Deliverables

- [ ] Embedding/indexing design + data model
- [ ] Retrieval trace logging
- [ ] Small evaluation dataset + results
- [ ] Final recommendation: Adopt / Defer / No-go

---

## 13. Architecture Implications (High Level)

If Light RAG is adopted, NewsBrief needs:

1. **Embedding generation** at ingestion (articles/stories)
2. **Vector storage** + metadata indexing (pgvector)
3. **Retrieval API/service layer**
4. **Retrieval tracing** and versioning strategy
5. **Retention and re-index strategy**

### Proposed Schema Additions

```sql
-- Add pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add embedding columns to articles
ALTER TABLE items ADD COLUMN embedding vector(1536);
ALTER TABLE items ADD COLUMN embedding_model VARCHAR(100);
ALTER TABLE items ADD COLUMN embedding_version VARCHAR(50);
ALTER TABLE items ADD COLUMN embedded_at TIMESTAMP WITH TIME ZONE;

-- Add embedding columns to stories
ALTER TABLE stories ADD COLUMN embedding vector(1536);
ALTER TABLE stories ADD COLUMN embedding_model VARCHAR(100);
ALTER TABLE stories ADD COLUMN embedding_version VARCHAR(50);
ALTER TABLE stories ADD COLUMN embedded_at TIMESTAMP WITH TIME ZONE;

-- Create indexes for similarity search
CREATE INDEX idx_items_embedding ON items USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_stories_embedding ON stories USING ivfflat (embedding vector_cosine_ops);

-- Retrieval trace table
CREATE TABLE retrieval_traces (
    id SERIAL PRIMARY KEY,
    query_type VARCHAR(50) NOT NULL,  -- 'related', 'dedupe', 'historical'
    source_id INTEGER NOT NULL,
    source_type VARCHAR(20) NOT NULL,  -- 'article', 'story'
    retrieved_ids INTEGER[] NOT NULL,
    similarity_scores FLOAT[] NOT NULL,
    retrieval_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

## 14. Related Documents

- [ADR-0026: RAG Integration Strategy](../adr/0026-rag-integration-strategy.md) — Decision record
- [ADR-0022: Dev/Prod Database Parity](../adr/0022-dev-prod-database-parity.md) — PostgreSQL foundation
- [ADR-0023: Intelligence Platform Strategy](../adr/0023-intelligence-platform-strategy.md) — Roadmap context
