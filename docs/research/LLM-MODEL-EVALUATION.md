# LLM Model Evaluation for NewsBrief

**Issue**: #99 - Evaluate alternative LLM models for synthesis quality
**Date**: February 2026
**Status**: Research Complete

## Executive Summary

This document evaluates LLM options for NewsBrief's story synthesis pipeline, focusing on:
- **Synthesis quality** (coherence, accuracy, narrative flow)
- **Structured output reliability** (JSON parsing success)
- **Factual grounding** (claims traceable to source articles)
- **Performance** (generation speed on Apple Silicon)
- **Local/private operation** (no cloud dependency, zero cost)

**Key Recommendations**:
1. **Stay on Ollama** during evaluation — reduces variables and allows quick model swaps
2. **Test Qwen 2.5 14B first** as the balanced candidate (quality + speed)
3. **Test Qwen 2.5 32B second** for quality comparison (your 48GB makes this practical)
4. **Only test Llama 70B Q4** if 32B quality is insufficient (significant time overhead)
5. **Use quality profile selectively** — apply to top stories, not entire batches

---

## 1. Current Setup

| Aspect | Current Configuration |
|--------|----------------------|
| Platform | Ollama |
| Model | Llama 3.1 8B |
| Hardware | MacBook Pro M4, 48GB RAM |
| Context | 8,192 tokens |
| Use Cases | Story synthesis, entity extraction, topic classification |

### Current Pain Points
- Generation time can reach 30-40 minutes for large batches
- JSON parsing sometimes requires repair strategies
- Quality varies with cluster size

---

## 2. Hardware Capabilities

**MacBook Pro M4 with 48GB Unified Memory**

| Model Size | VRAM Required (Q4) | VRAM Required (Q8) | Feasibility on 48GB |
|------------|-------------------|-------------------|---------------------|
| 7-8B | ~4-5 GB | ~8-9 GB | Excellent |
| 13-14B | ~7-8 GB | ~14-15 GB | Excellent |
| 32-34B | ~18-20 GB | ~35-38 GB | Good |
| 70B | ~35-40 GB | ~70+ GB | Possible (Q4 only, tight) |

**Your 48GB unified memory enables:**
- Any model up to 32B at high quantization (Q8) - comfortable headroom
- Models up to 70B at Q4 quantization - will work but leaves little margin
- Multiple smaller models simultaneously for different tasks

**Note**: Smaller memory configurations (8GB) are realistically limited to 7-8B models quantized, with 13-14B being a stretch. The 48GB on your M4 is specifically why 32B models are practical for daily use.

---

## 3. Inference Platform Comparison

### 3.1 Platform Overview

| Platform | Type | Apple Silicon | API | Ease of Use | Best For |
|----------|------|---------------|-----|-------------|----------|
| **Ollama** | CLI + Desktop | Good (Metal) | REST | Very Easy | Current setup, broad compatibility |
| **MLX** | Framework | Native/Optimal | Python | Moderate | Maximum M-series performance |
| **LM Studio** | GUI + API | Good | REST | Very Easy | Non-technical users, experimentation |
| **llama.cpp** | CLI | Good (Metal) | Server mode | Technical | Maximum control, custom builds |
| **LocalAI** | Server | Good | OpenAI-compatible | Easy | Drop-in OpenAI replacement |
| **vLLM** | Server | Emerging (MLX-backed) | OpenAI-compatible | Complex | High-throughput production (historically CUDA-focused, Apple Silicon paths emerging) |

### 3.2 Performance Hierarchy (Apple Silicon)

Based on 2025 community benchmarks (results vary by model, quantization, batch size, and prompt length):

1. **MLX** - Often fastest on Apple Silicon
   - Native Metal optimization
   - Unified memory advantage (no CPU↔GPU transfers)
   - Apple actively developing for M-series chips
   - Community benchmarks commonly show ~10-20% wins over llama.cpp in some setups (not guaranteed)

2. **llama.cpp** - Strong raw performance
   - Can be faster than Ollama when compiled with optimal flags for your hardware
   - Requires manual compilation for best results
   - More configuration overhead

3. **Ollama** - Best developer experience
   - Built on llama.cpp but adds abstraction overhead
   - Excellent model library and easy updates
   - New desktop app (July 2025) improves UX
   - Trade-off: slightly slower than raw llama.cpp, but much easier to use

### 3.3 Recommendation

**Short-term**: Stay with Ollama for stability and ease of model switching during evaluation.

**Medium-term**: Consider MLX migration if performance becomes critical. The mlx-community on Hugging Face has pre-converted models.

---

## 4. Model Family Comparison

### 4.1 Candidates

| Model | Sizes | Strengths | Weaknesses | Structured Output |
|-------|-------|-----------|------------|-------------------|
| **Llama 3.1** | 8B, 70B, 405B | Strong general quality, good instruction following | Large models slow | Good |
| **Llama 3.2** | 1B, 3B, 11B, 90B | Newer, multimodal options | Less tested | Good |
| **Qwen 2.5** | 0.5B-72B | Strong structured output, multilingual, up to 128K context* | Less common in Western use | **Very Good** |
| **Mistral** | 7B | Efficient, good summarization | Smaller context | Good |
| **Mixtral 8x7B** | 46.7B (12.9B active) | MoE efficiency, good quality | Complex architecture | Good |
| **Phi-3** | 3.8B, 14B | Very efficient for size | Smaller scale | Moderate |
| **Gemma 2** | 2B, 9B, 27B | Good quality/size ratio | Google ecosystem | Good |
| **DeepSeek-V2** | Various | Strong reasoning | Less tested locally | Good |

*\*Qwen 2.5 supports up to 128K context, but Ollama tags commonly run at ~32K by default. Longer context may require additional configuration.*

### 4.2 Structured Output Performance

From JSONSchemaBench (January 2025) and StructEval benchmarks:

**Key Finding**: Even state-of-the-art models achieve only ~75% on structured output benchmarks. Open-source models typically lag ~10 points behind proprietary ones. Benchmark results vary significantly by setup and evaluation methodology.

**Models with good JSON/structured output reputation**:
1. **Qwen 2.5** - Widely used for structured output tasks in local setups; we'll validate with our own parse-success metric
2. **Llama 3.1** - Good with proper prompting and our existing repair strategies
3. **Mistral** - Reliable but benefits from client-side validation

**Our source of truth**: NewsBrief's own JSON parse-success rate and repair frequency will be the definitive metric for our use case.

### 4.3 Summarization Quality

From 2025 academic research:

- **Llama 3** and **Qwen 2.5** perform comparably to GPT-4 on CNN/DailyMail summarization
- Both match GPT-4 in ROUGE and METEOR scores (zero-shot and few-shot)
- **DeepSeek-V3** excels in factual accuracy
- Models generally struggle on technical domains but perform well on news/conversational content

---

## 5. Recommended Models for Testing

Based on your hardware (48GB) and priorities (quality + structured output + reasonable speed):

### Tier 1: Primary Candidates (Test in This Order)

| Model | Size | Why Test | Expected Performance |
|-------|------|----------|---------------------|
| **Qwen 2.5 14B** | 14B | **Test first** - Good balance of quality/speed, strong structured output | ~25-35 tok/s on M4 |
| **Qwen 2.5 32B** | 32B | **Test second** - Best quality-while-practical choice on 48GB | ~15-20 tok/s on M4 |
| **Llama 3.1 70B Q4** | 70B | **Test only if 32B insufficient** - Highest quality but time-sink | ~5-10 tok/s on M4 |

**Note on context**: Qwen 2.5 supports up to 128K context, but Ollama commonly serves at ~32K. NewsBrief typically uses 8K-32K contexts, so this is rarely a limitation.

### Tier 2: Speed-Focused Alternatives

| Model | Size | Why Test | Expected Performance |
|-------|------|----------|---------------------|
| **Llama 3.2 11B** | 11B | Newer architecture | ~30-40 tok/s on M4 |
| **Mistral 7B** | 7B | Fast, efficient | ~50-60 tok/s on M4 |
| **Phi-3 14B** | 14B | Efficient for size | ~25-35 tok/s on M4 |

### Tier 3: Experimental

| Model | Size | Why Test | Notes |
|-------|------|----------|-------|
| **Mixtral 8x7B** | 46.7B | MoE - only 12.9B active | Interesting efficiency trade-off |
| **Gemma 2 27B** | 27B | Google's best open model | Good quality/size ratio |

---

## 6. Proposed Evaluation Methodology

### 6.1 Test Dataset

Use a fixed set of article clusters from NewsBrief:
- 5 small clusters (2-3 articles)
- 5 medium clusters (4-6 articles)
- 5 large clusters (7+ articles)
- Mix of topics (AI/ML, Security, DevTools, etc.)

### 6.2 Metrics

| Metric | How to Measure | Weight |
|--------|----------------|--------|
| **JSON Parse Success** | % of outputs that parse without repair | 25% |
| **Synthesis Quality** | Manual review (1-5 scale) on coherence, narrative flow | 20% |
| **Factual Grounding** | % of claims traceable to source articles (see below) | 20% |
| **Generation Speed** | Tokens/second, total time per story | 15% |
| **Entity Accuracy** | % of key entities correctly identified | 10% |
| **Title Quality** | LLM-generated vs fallback rate | 10% |

**Factual Grounding (Critical for NewsBrief)**

Because NewsBrief synthesizes multiple articles, the failure mode isn't just "bad writing" — it's **confidently wrong synthesis**. We need to measure:

- **Claim traceability score**: % of bullet claims supported by at least one source article
- **Unsupported claim count**: Number of claims found in a 5-minute audit that cannot be traced to sources
- **Hallucination detection**: Claims that contradict or have no basis in source material

This distinguishes "sounds great" from "trustworthy."

### 6.3 Test Protocol

1. **Baseline**: Run test set with current Llama 3.1 8B
2. **Candidate Testing**: Run same test set with each candidate model
3. **Scoring**: Apply metrics, calculate weighted score
4. **Analysis**: Document quality vs speed trade-offs

---

## 7. Model Profile Strategy

Based on evaluation results, implement configurable profiles (Issue #100):

| Profile | When Used | Recommended Model | Expected Time |
|---------|-----------|-------------------|---------------|
| **Fast** | Ingestion-time tasks (classification, tagging, quick summaries) | Mistral 7B or Llama 3.2 11B | ~30s per story |
| **Balanced** | Daily scheduled generation runs | Qwen 2.5 14B | ~60-90s per story |
| **Quality** | Re-run top stories, weekly wrap-ups, important topics | Qwen 2.5 32B | ~2-3 min per story |

**Workflow Recommendation**: Use "Quality" profile **selectively** (e.g., top 3-5 stories, specific topics), not for the entire batch. This gives you high-quality output where it matters without 30+ minute generation times.

**Testing Priority**:
1. **First**: Test Qwen 2.5 14B as balanced candidate
2. **Second**: Test Qwen 2.5 32B for quality comparison
3. **Third**: Only test Llama 70B Q4 if 32B quality is insufficient (70B adds significant time overhead)

---

## 8. Implementation Considerations

### 8.1 Ollama Model Installation

```bash
# Tier 1 candidates
ollama pull qwen2.5:32b
ollama pull qwen2.5:14b
ollama pull llama3.1:70b-instruct-q4_0

# Tier 2 candidates
ollama pull llama3.2:11b
ollama pull mistral:7b
ollama pull phi3:14b

# Check available models
ollama list
```

### 8.2 Configuration Changes

Current model is configured via `LLM_MODEL` environment variable. To support profiles:

1. Add `MODEL_PROFILE` environment variable (fast/balanced/quality)
2. Create `data/model_profiles.json` with model mappings
3. Update `app/llm.py` to support profile-based model selection

### 8.3 MLX Migration Path (Future)

If MLX provides significant speedup:

1. Install MLX: `pip install mlx mlx-lm`
2. Download MLX-optimized models from `mlx-community` on Hugging Face
3. Create abstraction layer to support both Ollama and MLX backends
4. Benchmark same test set on MLX

---

## 9. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Larger models too slow | Test Q4 quantization, consider MLX |
| Quality regression | Keep Llama 3.1 8B as fallback |
| Memory pressure | Monitor with `htop`, set appropriate batch sizes |
| Model download time | Pre-download during off-hours |

---

## 10. Next Steps

1. **Immediate**: Install Tier 1 candidate models via Ollama
2. **This week**: Run baseline benchmark with current setup
3. **Next week**: Run comparative benchmarks with candidates
4. **Following week**: Implement model profiles based on results

---

## 11. References

- JSONSchemaBench: Rigorous Benchmark of Structured Outputs (January 2025)
- StructEval: Comprehensive Structured Output Benchmark
- Artificial Analysis LLM Leaderboard (2025)
- Apple MLX Documentation
- Qwen 2.5 Speed Benchmarks
- Academic: "Bridging the LLM Accessibility Divide" (ACL 2025)

---

## Appendix A: Model Download Sizes

| Model | Quantization | Download Size | RAM Required |
|-------|--------------|---------------|--------------|
| Qwen 2.5 32B | Q4_K_M | ~18 GB | ~20-22 GB |
| Qwen 2.5 14B | Q4_K_M | ~8 GB | ~10-12 GB |
| Llama 3.1 70B | Q4_0 | ~40 GB | ~42-45 GB |
| Llama 3.2 11B | Q4_K_M | ~6 GB | ~8-10 GB |
| Mistral 7B | Q4_K_M | ~4 GB | ~6-8 GB |

## Appendix B: Ollama Commands Reference

```bash
# List installed models
ollama list

# Run model interactively
ollama run qwen2.5:32b

# Show model details
ollama show qwen2.5:32b

# Remove model
ollama rm model-name

# Pull specific quantization
ollama pull qwen2.5:32b-instruct-q4_K_M
```

---

## Related Documents

- [ADR-0025: LLM Model Selection and Profile Strategy](../adr/0025-llm-model-selection.md) — Decision record based on this research
- [ADR-0023: Intelligence Platform Strategy](../adr/0023-intelligence-platform-strategy.md) — Overall roadmap context
