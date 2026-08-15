# ADR-0025: LLM Model Selection and Profile Strategy

**Status:** Accepted (amended August 2026 — see [Amendment](#amendment-august-2026-platform-selectable-backend) below)
**Date:** February 2026
**Deciders:** Development Team
**Related:** v0.8.1 - LLM Quality & Intelligence, Issue #99, Issue #100

## Context

NewsBrief uses local LLMs for story synthesis, entity extraction, and topic classification. The current setup (Llama 3.1 8B via Ollama) has limitations:

- Generation time can reach 30-40 minutes for large batches
- JSON parsing sometimes requires repair strategies
- Quality varies with cluster size
- Single model used for all tasks regardless of complexity

As part of v0.8.1, we evaluated alternative LLM models and inference platforms to improve synthesis quality while maintaining local/private operation. The target hardware is a MacBook Pro M4 with 48GB unified memory.

See [LLM Model Evaluation Report](../research/LLM-MODEL-EVALUATION.md) for detailed benchmarks and analysis.

## Decision

### 1. Primary Model Family: Qwen 2.5

We will adopt **Qwen 2.5** as the primary model family for NewsBrief's LLM tasks:

| Variant | Use Case |
|---------|----------|
| Qwen 2.5 14B | Balanced daily generation |
| Qwen 2.5 32B | Quality-focused synthesis |

**Rationale:**
- Strong structured output reliability (critical for JSON parsing)
- Good summarization quality for news synthesis
- Fits comfortably within 48GB memory constraints
- Active development and community support

### 2. Inference Platform: Ollama (Retained)

We will **continue using Ollama** rather than migrating to alternatives (MLX, llama.cpp, LM Studio):

**Rationale:**
- Reduces variables during model evaluation
- Excellent developer experience and model library
- Easy model switching via simple pull commands
- Performance is adequate; MLX migration can be revisited if needed

### 3. Model Profile Strategy

Implement three configurable profiles (Issue #100):

| Profile | When Used | Model | Expected Time |
|---------|-----------|-------|---------------|
| **Fast** | Ingestion tasks (classification, tagging) | Mistral 7B or Llama 3.2 11B | ~30s per story |
| **Balanced** | Daily scheduled generation | Qwen 2.5 14B | ~60-90s per story |
| **Quality** | Top stories, weekly wrap-ups | Qwen 2.5 32B | ~2-3 min per story |

**Key principle:** Use the Quality profile **selectively** (top 3-5 stories, specific topics), not for entire batches.

### 4. Evaluation Methodology

Model selection validated using these metrics:

| Metric | Weight | Description |
|--------|--------|-------------|
| JSON Parse Success | 25% | % of outputs that parse without repair |
| Synthesis Quality | 20% | Manual review on coherence, narrative flow |
| Factual Grounding | 20% | % of claims traceable to source articles |
| Generation Speed | 15% | Tokens/second, total time per story |
| Entity Accuracy | 10% | Key entities correctly identified |
| Title Quality | 10% | LLM-generated vs fallback rate |

**Factual grounding** is critical because NewsBrief synthesizes multiple articles—the failure mode isn't just "bad writing" but "confidently wrong synthesis."

## Alternatives Considered

### Models

| Model | Why Not Selected |
|-------|------------------|
| **Llama 3.1 70B** | Viable for peak quality experiments, but significant time overhead; only use if 32B insufficient |
| **Mixtral 8x7B** | MoE architecture interesting but more complex; defer to future evaluation |
| **Phi-3** | Good efficiency but less proven for structured output |
| **GPT-4 / Claude** | Excellent quality but violates local/private operation requirement |

### Platforms

| Platform | Why Not Selected |
|----------|------------------|
| **MLX** | Potentially faster on Apple Silicon, but adds complexity; revisit if performance becomes critical |
| **LM Studio** | Good for experimentation but Ollama already serves this need |
| **vLLM** | Emerging Apple Silicon support but historically CUDA-focused; too complex for current needs |

## Consequences

### Positive

1. **Improved structured output reliability** — Qwen 2.5's JSON handling reduces parse failures
2. **Flexible performance/quality trade-off** — Profile system allows task-appropriate model selection
3. **Maintained simplicity** — Staying on Ollama avoids migration complexity
4. **Clear evaluation framework** — Metrics including factual grounding ensure quality focus

### Negative

1. **Model download overhead** — Multiple models (7B, 14B, 32B) require ~40GB storage
2. **Profile switching latency** — Switching between loaded models adds delay
3. **Learning curve** — Team needs to understand when to use each profile

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Qwen 2.5 underperforms in practice | Retain Llama 3.1 as fallback; evaluate before full migration |
| 32B model too slow for daily use | Use Quality profile selectively, not for all stories |
| Ollama performance becomes bottleneck | MLX migration path documented; can revisit if needed |

## Implementation

1. **Phase 1**: Install and test Qwen 2.5 14B alongside current Llama 3.1 8B
2. **Phase 2**: Run evaluation suite on both models with fixed test dataset
3. **Phase 3**: If Qwen 2.5 14B performs well, implement profile switching (Issue #100)
4. **Phase 4**: Add Qwen 2.5 32B as Quality profile option
5. **Phase 5**: Deprecate Llama 3.1 8B as default (retain as fast option if needed)

## References

- [LLM Model Evaluation Report](../research/LLM-MODEL-EVALUATION.md) — Full benchmarks and analysis
- [ADR-0023: Intelligence Platform Strategy](0023-intelligence-platform-strategy.md) — Overall roadmap context
- Issue #99: Evaluate alternative LLM models
- Issue #100: Model configuration profiles

## Amendment (August 2026): Platform-Selectable Backend

**Original decision preserved above for history.** Section 2 ("Inference Platform: Ollama (Retained)") is superseded as follows; everything else in this ADR (model family, profile strategy, evaluation methodology, local/private-only principle) still holds.

### What changed

> ~~We will continue using Ollama rather than migrating to alternatives (MLX, llama.cpp, LM Studio)~~

**The local inference backend is now platform-selectable, configured per-host via `data/model_config.json` → `device_profiles.<platform>.backend`:**

- **Windows:** unchanged — Ollama remains the sole backend.
- **macOS:** [oMLX](https://github.com/omlx-org/omlx) (`device_profiles.darwin.backend = "mlx"`) is now the default, with Ollama retained as a fallback via the same abstraction (`app/llm_backends.py`, ADR-0033 addendum below has full detail).

The core local-only, no-cloud-LLM principle (Consequences/Risks sections above) is unchanged — this is a swap of *which local runtime*, not a move away from local inference.

### Why the original recommendation was reversed

The February 2026 decision rejected MLX specifically to "reduce variables during model evaluation" and because "performance is adequate." Neither held once story generation ran at real production scale on macOS:

- A real end-to-end run hit **~3h19m wall-clock for 227 clusters** — confirmed via profiling to be **99.98% LLM call time**, not database/clustering overhead. This is the "performance becomes a bottleneck" condition this ADR's own Risks table flagged as the trigger to revisit MLX.
- A same-model, same-hardware, same-workload-shape benchmark (`qwen2.5:14b`, single call vs. 3-concurrent matching `app/stories.py`'s `ThreadPoolExecutor(max_workers=3)` pattern) showed Ollama's own concurrency is real (not a serialization bug — 31.4s → 37.9s for 3 concurrent, i.e. genuine parallelism), but MLX was still **~2x faster on identical single calls** and its concurrent-batch cost was near-zero (16.1s → 13.8s).
- Switching to a MoE architecture (`Qwen3-30B-A3B`, ~3B active params of 30B total) on top of the runtime swap compounded further: **7.5s for 3 concurrent oMLX calls vs. 37.9s on Ollama — a 5x improvement on the exact concurrency pattern the pipeline actually uses.**
- A real end-to-end validation run post-migration (#339; 753 articles, 113 clusters, oMLX balanced tier) completed in **24.9 minutes**, vs. the ~3h+ baseline for a comparably-sized batch — full numbers, methodology, and the model-fitness harness results (including the fast/quality tier candidates) are in the [ADR-0033 addendum](0033-hardware-informed-model-selection.md#addendum-august-2026-omlx-adoption-on-macos).

### Consequence update

The original Risks table's mitigation for "Ollama performance becomes bottleneck" ("MLX migration path documented; can revisit if needed") has now been exercised. See ADR-0033's addendum for the full before/after evidence, the Newsbrief-specific model-fitness methodology, and the go/no-go decision record.
