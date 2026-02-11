# Custom Fine-Tuning Feasibility Research

**Issue**: #109 - Investigate custom fine-tuning feasibility
**Date**: February 2026
**Status**: Research Complete

---

## 1. Executive Summary

Fine-tuning offers potential quality improvements for NewsBrief's specific tasks (news synthesis, entity extraction, topic classification), but introduces significant complexity. Modern efficient fine-tuning techniques (LoRA, QLoRA) make local training feasible on Apple Silicon for narrow pilots, though the cost/benefit ratio depends heavily on identifying concrete, recurring failure modes that survive prompt engineering.

### Initial Assessment

| Factor | Assessment |
|--------|------------|
| Technical Feasibility | ✅ Feasible for narrow pilot (7B-14B via MLX) |
| Dataset Requirements | ⚠️ Moderate-high effort (varies by task complexity) |
| Expected Improvement | ⚠️ Best for format/style; limited for reasoning |
| Operational Complexity | ⚠️ Significant ongoing maintenance |
| Recommendation | **Defer** - Validate need before investing |

---

## 2. Fine-Tuning Approaches

### 2.1 Full Fine-Tuning

Train all model parameters on custom dataset.

| Aspect | Details |
|--------|---------|
| Memory Required | ~4x model size (14B model → 56GB+ VRAM) |
| Training Time | Hours to days |
| Quality Potential | Highest |
| Local Feasibility | ❌ Not feasible on 48GB for useful model sizes |

### 2.2 LoRA (Low-Rank Adaptation)

Train small adapter layers while freezing base model.

| Aspect | Details |
|--------|---------|
| Memory Required | ~1.2x model size |
| Training Time | 30 min - 4 hours |
| Quality Potential | Can approach full fine-tuning on many instruction-style tasks |
| Local Feasibility | ✅ Feasible for 7B-14B models |

### 2.3 QLoRA (Quantized LoRA)

LoRA on quantized (4-bit) base model.

| Aspect | Details |
|--------|---------|
| Memory Required | ~0.5x model size |
| Training Time | 1-6 hours |
| Quality Potential | Good for format/style consistency; varies by task |
| Local Feasibility | ✅ Feasible for 14B models; 32B possible with constraints |

**Note on improvement claims**: LoRA/QLoRA can approach full fine-tuning results on many instruction-style tasks, but outcomes vary significantly by task complexity, base model quality, dataset quality, and training setup. Expect bigger gains for format/style consistency than for factuality or reasoning.

**Recommendation**: QLoRA is the most practical approach for local fine-tuning on your hardware.

---

## 3. Hardware Assessment (M4 48GB)

### 3.1 What's Trainable Locally

| Model Size | Full FT | LoRA | QLoRA |
|------------|---------|------|-------|
| 7B | ❌ | ✅ | ✅ |
| 14B | ❌ | ⚠️ Tight | ✅ |
| 32B | ❌ | ❌ | ⚠️ Possible but slow |
| 70B | ❌ | ❌ | ❌ |

### 3.2 Training Time Estimates (Ballpark)

These are rough estimates; actual training time depends on sequence length, batch size, LoRA rank, dataset formatting, and MLX tooling/model support.

| Model | Time per Epoch (est.) | Total 3 Epochs (est.) |
|-------|----------------------|----------------------|
| Qwen 2.5 7B | ~15-30 min | ~1-1.5 hours |
| Qwen 2.5 14B | ~45-90 min | ~2.5-4.5 hours |
| Qwen 2.5 32B | ~2-4 hours | ~6-12 hours |

### 3.3 Apple Silicon Training Tools

| Tool | Status | Notes |
|------|--------|-------|
| **MLX** | ✅ Recommended | Apple's framework, native Metal support |
| **mlx-lm** | ✅ Ready | Fine-tuning scripts included |
| **Unsloth** | ⚠️ Limited | Primarily CUDA, some MPS support |
| **Axolotl** | ⚠️ Limited | CUDA-focused |
| **llama.cpp** | ❌ | Inference only, no training |

### 3.4 Feasibility Constraints

A pilot on 7B–14B is feasible locally using MLX; larger models may be possible but will have longer iteration cycles and higher risk of tooling friction.

Key constraints:
- Training throughput on Apple Silicon is materially slower than CUDA setups
- Some fine-tuning stacks assume CUDA; MLX reduces friction but tooling maturity varies
- Model support in MLX may lag behind the latest releases

**MLX is the primary viable option for local fine-tuning on Apple Silicon.**

---

## 4. Dataset Requirements

### 4.1 Dataset Size by Task Type

| Task Type | Examples Needed | Notes |
|-----------|-----------------|-------|
| **Entity extraction / formatting** | 200-600 | Single-step tasks; high-quality examples can move the needle |
| **Topic classification** | 200-400 | Relatively bounded task |
| **Title generation** | 300-500 | Style/format alignment |
| **Multi-doc synthesis** | 800-3,000+ | Harder task; "gold" outputs are subjective, consistency critical |

**Hidden cost**: Multi-document synthesis labels are expensive because "gold" outputs are subjective and inter-annotator consistency matters significantly.

### 4.2 Training Data Types

| Type | Description | Use Case |
|------|-------------|----------|
| **Instruction fine-tuning** | Input → Output pairs | Format compliance, task alignment |
| **Preference tuning (DPO)** | Chosen vs Rejected pairs | Style preferences, quality ranking |
| **Teacher distillation** | Strong model outputs | Consistency and tone transfer |

### 4.3 Dataset Creation Options

#### Option A: Manual Curation
- Review and correct LLM outputs
- Time: 2-4 hours per 100 examples
- Quality: Highest, but expensive for synthesis

#### Option B: Teacher Model Distillation
- Use stronger model (GPT-4, Claude) to generate training data
- Fine-tune smaller local model to replicate style and structure
- Time: Minutes for generation
- Quality: Good for style/tone transfer; introduces bias from teacher

#### Option C: Preference Data (DPO)
- Collect "chosen" vs "rejected" output pairs
- Build naturally from user corrections over time
- Quality: Task-specific optimization

### 4.4 Data Governance and Licensing

**Important**: Even if not monetising, fine-tuning on raw copyrighted news content is a legal and compliance minefield.

**Safer approach**: Fine-tune on derived outputs, not raw article bodies:
- ✅ Your generated summaries and syntheses
- ✅ Human-written labels and corrections
- ✅ Metadata and classification labels
- ✅ Preference pairs (chosen/rejected outputs)
- ❌ Minimise storage and reuse of full copyrighted article text

**Dataset composition guideline**: Training data should be derived from your own intermediate representations, not raw source content.

---

## 5. Expected Quality Improvements

### 5.1 What Fine-Tuning Can Improve

| Area | Potential Gain | Confidence |
|------|----------------|------------|
| Output format consistency | High | ✅ High |
| JSON schema compliance | High | ✅ High |
| Domain-specific terminology | Medium-High | ✅ High |
| Synthesis style/tone | Medium | ⚠️ Medium |
| Entity recognition patterns | Medium | ⚠️ Medium |

### 5.2 What Fine-Tuning Won't Reliably Fix

| Area | Why Not | Better Alternative |
|------|---------|-------------------|
| **Factual accuracy** | Requires retrieval/verification | RAG, fact-checking pipeline |
| **Missing context** | Knowledge cutoff limitation | RAG, historical linking |
| **Complex reasoning** | Emergent capability | Larger model, chain-of-thought |
| **World knowledge gaps** | Training data limitation | RAG, external APIs |

### 5.3 Nuance on Hallucination

Fine-tuning may reduce certain types of hallucination:
- ✅ Patterned hallucinations (consistent errors)
- ✅ Abstention behaviour ("I don't know")
- ✅ Citation/attribution compliance

But fine-tuning won't reliably increase factuality without retrieval/verification systems.

### 5.4 Alternative Approaches (Often Better)

| Problem | Fine-Tuning Helps? | Better Alternative |
|---------|-------------------|-------------------|
| Inconsistent JSON | Yes | Better prompting, validation |
| Wrong entities | Slight | RAG + verification |
| Bad summaries | Moderate | Better prompts, chain-of-thought |
| Topic errors | Moderate | Calibrated confidence, human review |
| Missing history | No | RAG (v0.8.3) |
| Factual errors | No | Retrieval + verification |

### 5.5 Teacher-Student Distillation

A NewsBrief-specific option worth considering:
- Use a stronger model (Claude, GPT-4) to generate high-quality outputs
- Fine-tune smaller local model to replicate that style and structure
- Benefits: Consistency, tone alignment, reduced inference cost
- Risks: Teacher model bias propagation

---

## 6. Operational Considerations

### 6.1 Ongoing Maintenance

Fine-tuned models require:
- **Re-training** when base model updates
- **Dataset maintenance** as requirements change
- **Evaluation pipeline** to detect regression
- **Version management** for multiple fine-tuned variants

### 6.2 Deployment Complexity

| Aspect | Base Model | Fine-Tuned |
|--------|------------|------------|
| Model updates | Pull new version | Re-train + validate |
| Storage | ~8GB (14B Q4) | +50-200MB adapter |
| Inference | Standard | Load base + adapter |
| Rollback | Trivial | Requires adapter versioning |

### 6.3 Risk Factors

| Risk | Impact | Mitigation |
|------|--------|------------|
| Overfitting | Model worse on edge cases | Held-out test set, regularization |
| Catastrophic forgetting | Loses general capabilities | LoRA (preserves base model) |
| Dataset bias | Amplifies existing biases | Diverse training data |
| Maintenance burden | Time sink | Clear improvement threshold |

### 6.4 Model Lifecycle and Rollback

**Required discipline for quality-first operation:**

| Component | Versioning Strategy |
|-----------|-------------------|
| Base model | Pin version (e.g., `qwen2.5-14b-instruct-v1.0`) |
| Adapter | Semantic versioning (`adapter_v1.2.0`) |
| Evaluation set | Frozen and versioned with adapter |
| Config | Version-controlled with adapter |

**Rollback plan**: Revert to previous adapter in one config change:
```python
# config/model_config.json
{
  "adapter_version": "v1.1.0",  # Rollback: change to previous
  "adapter_path": "adapters/synthesis_v1.1.0.safetensors"
}
```

**Evaluation gates**: Before deploying new adapter:
1. Run against frozen evaluation set
2. Compare metrics to previous version
3. No deploy if any critical metric regresses

---

## 7. Data Flywheel Strategy

Since NewsBrief is used daily, training signals can be harvested cheaply over time. This turns "defer fine-tuning" into "prepare for fine-tuning without extra effort."

### 7.1 What to Capture (Low Cost)

| Data Point | Storage | Use |
|------------|---------|-----|
| Prompt + inputs | JSON | Instruction tuning |
| Model output | JSON | Baseline for comparison |
| User rating (optional) | Integer | Quality signal |
| Correction notes | Text | Error pattern analysis |
| Chosen vs rejected pairs | JSON pair | DPO training |
| Failure tags | Enum | Pattern identification |

### 7.2 Failure Tag Taxonomy

```python
class FailureTag(Enum):
    FORMAT_ERROR = "format_error"      # JSON/schema failure
    MISSED_ENTITY = "missed_entity"    # Entity extraction gap
    WRONG_ENTITY = "wrong_entity"      # Entity extraction error
    TOPIC_DRIFT = "topic_drift"        # Off-topic content
    HALLUCINATION = "hallucination"    # Unsupported claim
    DUPLICATION = "duplication"        # Repeated content
    STYLE_MISMATCH = "style_mismatch"  # Tone/style issue
    TRUNCATION = "truncation"          # Incomplete output
```

### 7.3 Schema Addition (Future)

```sql
CREATE TABLE output_feedback (
    id SERIAL PRIMARY KEY,
    output_type VARCHAR(50),  -- 'synthesis', 'entity', 'topic'
    source_id INTEGER,
    prompt_hash VARCHAR(64),
    output_json JSONB,
    rating INTEGER,  -- 1-5 or NULL
    failure_tags TEXT[],
    correction_notes TEXT,
    rejected_output_json JSONB,  -- For DPO pairs
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Goal**: After 3-6 months of normal usage, have 500+ labelled examples ready if fine-tuning becomes warranted.

---

## 8. Acceptance Criteria (If Fine-Tuning Proceeds)

Explicit, measurable targets per task:

### 8.1 Synthesis (Multi-Document)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Human preference | ≥65% wins vs baseline | Blind A/B on 50 clusters |
| Topic drift rate | ≤10% with irrelevant content | Manual review |
| Key fact coverage | ≥90% present | Rubric-based audit |

### 8.2 Entity Extraction

| Metric | Target | Measurement |
|--------|--------|-------------|
| F1 score | +10-15 points vs baseline | Labelled test set (100+ articles) |
| Example | 0.70 → 0.82+ | |

### 8.3 Topic Classification

| Metric | Target | Measurement |
|--------|--------|-------------|
| Macro-F1 | +8-12 points | Labelled test set |
| Confidence calibration | Improved ECE | Calibration curve |

### 8.4 Format Compliance

| Metric | Target | Measurement |
|--------|--------|-------------|
| JSON validity | ≥99% | Schema validation on eval set |
| Schema compliance | ≥98% | Full schema check |

### 8.5 Go/No-Go Decision Rule

**Proceed beyond pilot only if:**
- At least 2 critical metrics improve to target
- No metrics regress beyond margin of error
- Maintenance burden is acceptable given improvement

---

## 9. Cost/Benefit Analysis

### 9.1 Costs

| Category | One-Time | Ongoing |
|----------|----------|---------|
| Dataset creation | 20-60 hours | 2-4 hours/month |
| Training infrastructure | Already have (M4) | Electricity |
| Evaluation setup | 4-8 hours | 1-2 hours/month |
| Learning curve | 8-16 hours | - |
| **Total** | **~50-100 hours** | **~5 hours/month** |

### 9.2 Benefits (If Successful)

- More consistent output format
- Better alignment with NewsBrief style
- Potentially faster inference (smaller fine-tuned model)
- Domain-specific improvements

### 9.3 Break-Even Analysis

Fine-tuning is worthwhile if:
1. Current model has concrete, recurring failure modes
2. Failures survive prompt engineering fixes
3. Failures are learnable (format/style/extraction, not reasoning)
4. Time saved > time invested within 6 months

**Current assessment**: Gaps not yet quantified. Need baseline metrics first.

---

## 10. Recommendation: Defer with Preparation

### 10.1 Decision: Defer

**Do not pursue fine-tuning now.** Instead:

1. **Complete v0.8.1** - Quality metrics will identify actual gaps
2. **Deploy Qwen 2.5** - May resolve current issues without fine-tuning
3. **Implement RAG (v0.8.3)** - May address remaining gaps
4. **Start data flywheel** - Passively collect preference data
5. **Revisit post-v0.9.x** - Reassess with concrete data

### 10.2 Defer Unless

You can name one concrete, recurring failure mode that:

1. **Happens frequently** (>10% of outputs)
2. **Survives prompt and pipeline fixes**
3. **Is clearly learnable** (format/style/entity extraction)

### 10.3 Fine-Tuning-Worthy Gaps (Examples)

| Gap Type | Fine-Tuning Appropriate? |
|----------|-------------------------|
| Persistent JSON schema failures | ✅ Yes |
| Recurring entity extraction pattern misses | ✅ Yes |
| Consistent tone/style mismatch | ✅ Yes |
| Factual errors from missing context | ❌ No (use RAG) |
| Missing background history | ❌ No (use RAG) |
| Reasoning mistakes across topics | ❌ No (use larger model) |

### 10.4 Prerequisites for Future Fine-Tuning

Before reconsidering:
- [ ] Quality metrics show concrete, recurring gaps
- [ ] Prompt engineering attempted and insufficient
- [ ] RAG implemented and gaps persist
- [ ] 500+ preference/correction examples collected via flywheel
- [ ] Clear success criteria defined (Section 8)

---

## 11. If Fine-Tuning Is Pursued Later

### 11.1 Recommended Stack

```
Base Model:     Qwen 2.5 14B (or 7B for faster iteration)
Method:         QLoRA (4-bit quantization)
Framework:      MLX + mlx-lm
Dataset Format: JSONL with instruction/input/output
Evaluation:     Held-out test set + manual review
```

### 11.2 Pilot Scope

| Phase | Scope | Success Criteria |
|-------|-------|------------------|
| 1 | Format compliance only | JSON validity ≥99% |
| 2 | Entity extraction | F1 improvement ≥10 points |
| 3 | Synthesis (if 1-2 succeed) | Human preference ≥65% |

### 11.3 Training Configuration (QLoRA)

```python
# Example MLX fine-tuning config
{
    "model": "qwen2.5-14b",
    "adapter_type": "lora",
    "lora_rank": 16,
    "lora_alpha": 32,
    "learning_rate": 1e-4,
    "batch_size": 4,
    "epochs": 3,
    "quantization": "4bit"
}
```

---

## 12. Conclusion

### Key Findings

1. **Technically feasible for narrow pilot** - QLoRA on M4 48GB can fine-tune 7B-14B models via MLX
2. **Significant investment** - 50-100 hours initial, ongoing maintenance
3. **Best for format/style** - Not for reasoning, factuality, or knowledge gaps
4. **Uncertain ROI** - Benefits depend on gaps not yet quantified
5. **Better alternatives exist** - Prompting, RAG likely solve most issues first

### Decision Record

| Decision | Rationale |
|----------|-----------|
| **Defer fine-tuning** | No concrete recurring gaps identified; better alternatives available |
| **Start data flywheel** | Low-cost preparation; builds training data passively |
| **Revisit post-v0.9.x** | After RAG and entity intelligence, reassess with data |

### Trigger for Revisiting

Reconsider fine-tuning when:
- Quality metrics show specific, frequent failure mode
- Prompt engineering has been exhausted
- RAG has been implemented
- 500+ labelled examples available
- Clear acceptance criteria can be defined

---

## Related Documents

- [ADR-0025: LLM Model Selection](../adr/0025-llm-model-selection.md) — Model strategy
- [ADR-0026: RAG Integration Strategy](../adr/0026-rag-integration-strategy.md) — Alternative approach
- [LLM Model Evaluation](LLM-MODEL-EVALUATION.md) — Model research
