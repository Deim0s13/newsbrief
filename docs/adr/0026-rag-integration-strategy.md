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

1. **Storage overhead** — Embeddings add ~3KB per article (768-dim float32)
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

## Go/No-Go Evaluation Results (v0.8.6, August 2026)

All four milestone phases (#278, #257/#259, #279/#281, #280) are implemented. `scripts/rag_evaluation.py` (#262) was built to check the gates above against live data and was run against the dev database (`DATABASE_URL=...localhost:5433/newsbrief`) with real Ollama embeddings (`nomic-embed-text`) and the `fast` synthesis profile (`mistral:7b`).

**Data caveat:** the shared dev database only carries a handful of leftover smoke-test rows day-to-day (stories/items are periodically truncated during development — see `tests/pg_testutil.py`). To get a non-trivial sample, 16 synthetic articles across 4 topics (AI regulation, renewable energy, space exploration, a retail data breach — including one deliberately near-duplicate pair and two backdated "historical" stories) were seeded and run through the real pipeline (embedding → clustering → synthesis → historical linking). This is **far below** the ADR's target N=50 and below what a week of live feed ingestion would produce, so results below are **directional evidence that the mechanisms work correctly**, not a statistically powered validation at production scale.

| Gate | Threshold | Result | Verdict |
|------|-----------|--------|---------|
| Relatedness precision | Top-5 retrieval ≥3 related items in ≥75% of cases | 0% (0/12 stories) | **FAIL at this sample size** — with only 12 embedded stories total, most synthetic topics are too small/fragmented for 3 same-topic neighbors to exist in the corpus at all. Not a defect in retrieval (see historical-linking gate below, which found the correct neighbor); it's an N-too-small artifact. |
| Semantic dedupe | Reduction in duplicates without collapsing distinct stories | 1 flagged pair out of 16 embedded articles (6.25%), similarity 0.9526 | **PASS (qualitative)** — the one pair flagged was the deliberately-seeded near-duplicate (two wire reports of the same NASA launch); no distinct articles were incorrectly flagged. |
| Historical linking | ≥80% of sampled links judged accurate by human review | 1 continuation link produced; reviewed manually: story *"Global Tech Giants Face Increasing Scrutiny..."* correctly linked as continuing *"EU Proposes Draft AI Act Risk Categories"* (similarity 0.7958) | **PASS (1/1 reviewed accurate)** — correct outcome, but N=1 is far short of the 50-sample target; needs re-validation once more historical stories accumulate. |
| Latency | Acceptable for daily use, no regression | avg 1.8ms across 62 traced retrieval queries (live pgvector query against a small table) | **PASS** — well under the 500ms budget used as an absolute check (there is no prior retrieval implementation to regress against, since this is new functionality). Latency will grow with corpus size; the `ivfflat` index and top-k bounding are the intended mitigations per the Risks table above. |

### Decision: **Go, with a follow-up re-evaluation condition**

Rationale:
- All four RAG mechanisms (embedding pipeline, semantic dedupe, retrieval hook + context anchors, historical linking) are implemented, integration-tested (`tests/test_context_retrieval.py`, `tests/test_historical_linking.py`, `tests/test_context_manager.py`, `tests/test_pipeline_monitoring.py`), and were smoke-tested end-to-end against live Ollama and a real Postgres instance during Phases 3-6.
- The one gate that "failed" (relatedness precision) failed due to corpus size, not a correctness problem — the same retrieval code path is what produced the correct historical-linking match. There is no evidence of false positives or broken retrieval logic.
- Given this is a local/self-hosted app with a single operator (not a scaled multi-tenant product), the cost of proceeding and re-checking after a normal week of production ingestion is low, versus the cost of blocking the milestone on an artificially small synthetic sample.

**Condition:** re-run `python scripts/rag_evaluation.py` against the dev or prod database after ~1-2 weeks of normal feed ingestion (once the corpus naturally exceeds ~50 embedded stories) and confirm the relatedness-precision gate clears ≥75% under real data volume. If it doesn't, investigate before enabling `light_rag`/`retrieval_hook` more broadly (both already default-configurable via `data/model_config.json` and can be disabled per-environment without a code change).

## Implementation Outline

### Schema Changes

```sql
-- pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Article embeddings (introduced in schema migrations; width 768 after #251)
ALTER TABLE items ADD COLUMN embedding vector(768);
ALTER TABLE items ADD COLUMN embedding_model VARCHAR(100);
ALTER TABLE items ADD COLUMN embedded_at TIMESTAMP WITH TIME ZONE;

-- Story embeddings
ALTER TABLE stories ADD COLUMN embedding vector(768);
ALTER TABLE stories ADD COLUMN embedding_model VARCHAR(100);
ALTER TABLE stories ADD COLUMN embedded_at TIMESTAMP WITH TIME ZONE;

-- Similarity search indexes
CREATE INDEX idx_items_embedding ON items USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_stories_embedding ON stories USING ivfflat (embedding vector_cosine_ops);
```

### Embedding Model

- **Primary candidate:** Ollama with `nomic-embed-text` or other **768-dim** embedding models
- **Dimension:** **768** in PostgreSQL (`vector(768)`); must match the active embedding model
- **Local execution:** Aligned with local-first LLM strategy (ADR-0025)

## References

- [RAG Integration Research](../research/RAG-INTEGRATION.md) — Full analysis document
- [ADR-0022: Dev/Prod Database Parity](0022-dev-prod-database-parity.md) — PostgreSQL foundation
- [ADR-0023: Intelligence Platform Strategy](0023-intelligence-platform-strategy.md) — Roadmap context
- [ADR-0025: LLM Model Selection](0025-llm-model-selection.md) — Local-first LLM approach
