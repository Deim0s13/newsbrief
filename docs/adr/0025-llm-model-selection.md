# ADR-0025: LLM Model Selection and Profile Strategy

**Status:** Accepted
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
