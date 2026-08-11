# Model Profiles Guide

> **Configure LLM models for optimal story synthesis**

---

## Overview

NewsBrief supports multiple LLM model profiles to balance speed and quality for different use cases. Each profile is optimized for specific scenarios.

## Available Profiles

### Fast Profile
| Setting | Value |
|---------|-------|
| **Model** | `mistral:7b` |
| **Speed** | ~45-60 tok/s |
| **Time per Story** | ~20-30s |
| **Quality Level** | Good |
| **Output Length** | Shorter, concise |

**Best for:**
- Quick testing and development
- Ingestion-time tasks (classification, tagging)
- High-volume batch processing
- When speed matters more than detail

### Balanced Profile (Recommended)
| Setting | Value |
|---------|-------|
| **Model** | `qwen2.5:14b` |
| **Speed** | ~25-35 tok/s |
| **Time per Story** | ~60-90s |
| **Quality Level** | Very Good |
| **Output Length** | Moderate |

**Best for:**
- Daily story generation
- Standard synthesis tasks
- Entity extraction
- General use - best trade-off between quality and speed

### Quality Profile
| Setting | Value |
|---------|-------|
| **Model** | `qwen2.5:32b` |
| **Speed** | ~10-15 tok/s |
| **Time per Story** | ~3-5 min |
| **Quality Level** | Excellent |
| **Output Length** | Longer, more detailed |

**Best for:**
- Important stories requiring deep analysis
- Weekly summaries and reports
- Content requiring nuanced understanding
- When quality is paramount

## Switching Profiles

### Via Web UI
1. Navigate to **Settings** → **Model Configuration**
2. Select the desired profile card
3. The change takes effect immediately

### Via API
```bash
# Get current profile
curl http://localhost:8787/api/models/profiles/active

# Switch to a different profile
curl -X PUT "http://localhost:8787/api/models/profiles/active?profile_id=balanced"

# Available profile IDs: fast, balanced, quality
```

## Output Characteristics

### Synthesis Length by Profile

| Profile | Typical Length | Max Length |
|---------|---------------|------------|
| Fast | 200-500 chars | 1,500 chars |
| Balanced | 500-1,500 chars | 3,000 chars |
| Quality | 1,000-3,000 chars | 5,000 chars |

The quality profile produces more comprehensive synthesis including:
- Detailed context and background
- Multiple perspectives when available
- Nuanced analysis of implications
- More thorough key points

### Example Output Comparison

**Fast Profile:**
> "Google announced Gemini 2.0 today, featuring improved multimodal capabilities. The model shows significant performance improvements over its predecessor."

**Quality Profile:**
> "Google unveiled Gemini 2.0, their next-generation AI model featuring native image and video understanding capabilities that represent a significant leap forward in multimodal AI. The announcement, made at their annual developer conference, showcased improvements in reasoning, code generation, and real-time processing. Industry analysts note this positions Google competitively against OpenAI's GPT-4, with particular strengths in visual understanding tasks. The model will be available through Google Cloud and integrated into consumer products starting next quarter."

## Hardware Requirements

| Profile | Minimum VRAM | Recommended VRAM |
|---------|--------------|------------------|
| Fast | 6 GB | 8 GB |
| Balanced | 12 GB | 16 GB |
| Quality | 20 GB | 24 GB |

## Best Practices

1. **Daily Operations**: Use **Balanced** for scheduled story generation
2. **Development**: Use **Fast** for testing and iteration
3. **Important Content**: Switch to **Quality** for featured stories
4. **Batch Processing**: Use **Fast** to process large article backlogs quickly

## Troubleshooting

### Model Not Responding
If a model isn't responding, it may need to be pulled:
```bash
ollama pull qwen2.5:14b
```

### Out of Memory
If you see OOM errors, switch to a smaller profile or ensure Ollama has sufficient VRAM allocated.

### Slow Generation
Quality profile is intentionally slower for better output. For faster results, switch to Balanced or Fast.

---

## Embedding Model

Separate from the synthesis profiles above — used for semantic search, semantic dedup, related/similar lookups, and light RAG. Configured under `data/model_config.json` → `embedding`:

```json
{
  "embedding": {
    "enabled": true,
    "active_profile": "fast",
    "profiles": {
      "fast": { "model": "nomic-embed-text", "dimensions": 768 }
    }
  }
}
```

`enabled: false` disables all embedding writes; the rest of the pipeline (summarization, clustering, synthesis) is unaffected since embeddings are fire-and-forget. The `dimensions` value must match the database column width (`_EMBEDDING_DIMENSIONS = 768` in `app/orm_models.py`) — changing to a different-dimension model requires a migration.

## Synthesis Routing (standard vs deep)

Clusters are classified as **standard** or **deep** synthesis based on complexity, via `synthesis_routing` in `data/model_config.json`:

```json
{
  "synthesis_routing": {
    "deep_min_articles": 6,
    "deep_min_topic_diversity": 0.6
  }
}
```

A cluster routes to the deep path if it has at least `deep_min_articles` articles **and** topic diversity above `deep_min_topic_diversity`. The chosen path is recorded per story (`Story.synthesis_path`). See also `synthesis_strategies` (`direct` / `map_reduce` / `hierarchical`), which controls chunking strategy independently of standard/deep routing — a cluster is sized into one of those three strategies regardless of which synthesis path it takes.

## Publish Gate (confidence gating)

Every story gets a calibrated confidence score; `publish_gate` in `data/model_config.json` decides what happens next:

```json
{
  "publish_gate": {
    "enabled": true,
    "hold_threshold": 0.4,
    "warn_threshold": 0.65
  }
}
```

| Confidence | Outcome |
|------------|---------|
| `< hold_threshold` | **Held** — not shown in default views until an operator promotes or discards it (`/admin/pipeline`) |
| `hold_threshold` – `warn_threshold` | **Published with warning** — visible but flagged |
| `>= warn_threshold` | **Published normally** |

## RAG / Semantic Retrieval Configuration (v0.8.6)

Three related-but-independent knobs control the RAG features shipped in v0.8.6 (see [ADR-0026](../adr/0026-rag-integration-strategy.md)). Each has its own `enabled` flag and can be turned off per-environment without a code change.

### `semantic_dedupe` — post-hoc duplicate detection

```json
{
  "semantic_dedupe": {
    "enabled": true,
    "threshold": 0.92,
    "window_days": 7,
    "action": "flag"
  }
}
```

Runs after an article is embedded: compares against other embedded items from the last `window_days` days, and if cosine similarity ≥ `threshold`, sets `duplicate_of_id`/`duplicate_similarity` on the newer item. `action: "flag"` only marks the row for operator review (`/api/admin/semantic-duplicates`) — it does not delete or hide anything; other `action` values are reserved for future use.

### `retrieval_hook` — bounded retrieval between clustering and synthesis

```json
{
  "retrieval_hook": {
    "enabled": true,
    "threshold": 0.65,
    "top_k": 5,
    "window_days": 30
  }
}
```

For every cluster (all synthesis strategies), fetches up to `top_k` related prior stories above `threshold` similarity from the last `window_days` days. Every call is recorded as a `RetrievalTrace` row for observability (`/api/admin/retrieval-traces`) and evaluation (`scripts/rag_evaluation.py`). Results are supporting context, not treated as canonical source facts. This threshold is deliberately looser than `light_rag`'s, since results here don't get injected into the prompt — they populate the `context_anchors` payload and drive `/stories/{id}/related`.

### `light_rag` — historical context injected into synthesis prompts

```json
{
  "light_rag": {
    "enabled": true,
    "threshold": 0.78,
    "max_anchors": 3,
    "window_days": 30
  }
}
```

A stricter subset of retrieval: only historical stories above `threshold` (higher than `retrieval_hook`'s) get injected as up to `max_anchors` structured anchors directly into the synthesis prompt, giving the LLM continuity context for evolving stories. Independent of `historical_linking` (`app/historical_linking.py`), which decides whether the *new* story should be marked as continuing a specific prior story (`continues_story_id`) — light RAG can inject anchors without that story being marked as a continuation, and vice versa.

### Disabling RAG features

Each block above can be set to `"enabled": false` independently in `data/model_config.json` — e.g. to disable light RAG injection while keeping the retrieval hook (for `/stories/{id}/related`) active. No restart-time flag or environment variable is needed; changes take effect on the next read of `model_config.json`.

---

*Last updated: v0.8.6*
