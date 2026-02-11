# ADR-0026: RAG Integration Strategy

**Status:** Accepted
**Date:** February 2026
**Deciders:** Development Team
**Related:** Issue #108, ADR-0022, ADR-0023

## Context

NewsBrief uses heuristic approaches (keywords, entity overlap, title similarity) for article grouping, clustering, deduplication, and synthesis context. This has limitations:

- Weak detection of paraphrased duplicates ("same story, different wording")
- Limited ability to link current stories to historically related content
- Synthesis lacks continuity ("what changed since last time?")
- Related content discovery relies on exact keyword/topic matches

Retrieval-Augmented Generation (RAG) using vector embeddings could address these limitations by enabling semantic similarity search.

## Decision

We will adopt **Light RAG (Option 2)** with **PostgreSQL + pgvector** as the target architecture:

### 1. Light RAG Approach

- Generate embeddings for articles and stories at ingestion time
- Use semantic similarity for related content, deduplication, and historical linking
- Inject only 1–3 high-confidence "anchors" (prior story summaries) into synthesis prompts
- Gate anchor injection on confidence thresholds to prevent topic drift

### 2. PostgreSQL + pgvector Storage

- Single datastore for metadata and vectors (no separate vector DB)
- Aligned with existing PostgreSQL architecture (ADR-0022)
- Easy joins/filters with metadata for hybrid search
- Lower operational complexity than dual-database approach

### 3. Staged Implementation

| Phase | Scope |
|-------|-------|
| **Foundation** | Embedding generation, vector storage, retrieval API |
| **Retrieval** | Related content, semantic dedupe, historical linking |
| **Light RAG** | Controlled anchor injection into synthesis (if retrieval quality validates) |

## Alternatives Considered

### Option 0: Improve Heuristics Only

Continue with keyword/entity matching without embeddings.

**Rejected because:** Ceiling on semantic similarity detection; limited historical linking capability.

### Option 1: Embeddings for Retrieval Only

Generate embeddings but don't inject retrieved content into synthesis.

**Considered as foundation:** This is a prerequisite for Light RAG and provides most benefits with lower risk.

### Option 3: Full RAG Pipeline

Chunk articles, embed chunks, retrieve many chunks, rerank, inject into synthesis.

**Rejected because:** Highest complexity, most likely to degrade synthesis quality via topic drift, requires significant operational overhead.

### Alternative Storage: Dedicated Vector DB (Qdrant, Chroma)

Use a separate vector database alongside PostgreSQL.

**Rejected because:** Two datastores to operate and keep consistent; pgvector meets our needs within existing PostgreSQL infrastructure.

## Consequences

### Positive

1. **Semantic similarity** — Find related content even when terminology differs
2. **Better deduplication** — Detect paraphrased duplicates across sources
3. **Historical context** — Connect current stories to past coverage
4. **Synthesis continuity** — "This continues from last month's story about..."
5. **Single datastore** — No additional database to operate

### Negative

1. **Storage overhead** — Embeddings add ~6KB per article (1536-dim float32)
2. **Compute at ingestion** — Embedding generation adds latency
3. **Re-indexing requirement** — Model changes require re-embedding
4. **Complexity increase** — New retrieval layer and tracing infrastructure

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| False relatedness | Metadata filters (topic/date/source), similarity thresholds |
| Topic drift in synthesis | Inject only structured anchors, confidence gating |
| Index drift on model change | Store model/version metadata, background re-indexing |
| Latency impact | Embed on ingestion, cache embeddings, small top-k |

## Go/No-Go Gates for Pilot

Before proceeding to implementation, validate:

| Gate | Threshold |
|------|-----------|
| Relatedness precision | Top-5 retrieval ≥3 related items in ≥75% of cases |
| Semantic dedupe | Reduction in duplicates without collapsing distinct stories |
| Historical linking | ≥80% of proposed links judged accurate by human review |
| No regression | Runtime/latency/quality acceptable for daily use |

## Implementation Outline

### Schema Changes

```sql
-- pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Article embeddings
ALTER TABLE items ADD COLUMN embedding vector(1536);
ALTER TABLE items ADD COLUMN embedding_model VARCHAR(100);
ALTER TABLE items ADD COLUMN embedded_at TIMESTAMP WITH TIME ZONE;

-- Story embeddings
ALTER TABLE stories ADD COLUMN embedding vector(1536);
ALTER TABLE stories ADD COLUMN embedding_model VARCHAR(100);
ALTER TABLE stories ADD COLUMN embedded_at TIMESTAMP WITH TIME ZONE;

-- Similarity search indexes
CREATE INDEX idx_items_embedding ON items USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_stories_embedding ON stories USING ivfflat (embedding vector_cosine_ops);
```

### Embedding Model

- **Primary candidate:** Ollama with `nomic-embed-text` or `bge-base`
- **Dimension:** 1536 (adjustable based on model)
- **Local execution:** Aligned with local-first LLM strategy (ADR-0025)

## References

- [RAG Integration Research](../research/RAG-INTEGRATION.md) — Full analysis document
- [ADR-0022: Dev/Prod Database Parity](0022-dev-prod-database-parity.md) — PostgreSQL foundation
- [ADR-0023: Intelligence Platform Strategy](0023-intelligence-platform-strategy.md) — Roadmap context
- [ADR-0025: LLM Model Selection](0025-llm-model-selection.md) — Local-first LLM approach
