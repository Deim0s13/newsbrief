# ADR-0027: Fine-Tuning Deferral

**Status:** Accepted
**Date:** February 2026
**Deciders:** Development Team
**Related:** Issue #109, ADR-0025, ADR-0026

## Context

As part of the v0.8.1 LLM Quality & Intelligence milestone, we investigated the feasibility of custom fine-tuning to improve NewsBrief's synthesis, entity extraction, and topic classification quality.

Fine-tuning (specifically LoRA/QLoRA) is technically feasible on our hardware (M4 48GB via MLX), and could potentially improve output format consistency and domain-specific terminology alignment.

However, fine-tuning introduces significant complexity:
- 50-100 hours initial investment for dataset creation and training setup
- Ongoing maintenance burden (~5 hours/month)
- Re-training required when base models update
- Adapter versioning and evaluation pipeline requirements

## Decision

**We will defer fine-tuning** until concrete, recurring quality gaps are identified that:

1. Survive prompt engineering improvements
2. Survive RAG implementation (v0.8.3)
3. Are learnable through fine-tuning (format/style/extraction, not reasoning)

Instead, we will:

1. **Deploy Qwen 2.5** (ADR-0025) — May resolve current issues without fine-tuning
2. **Implement Light RAG** (ADR-0026) — Addresses context and continuity gaps
3. **Start a passive data flywheel** — Collect preference data during normal usage for future fine-tuning if needed

## Rationale

### Why Not Now

| Factor | Assessment |
|--------|------------|
| **No quantified gaps** | Quality metrics (v0.8.1) not yet showing specific, recurring failures |
| **Better alternatives first** | Prompt engineering, model upgrade, and RAG likely address most issues |
| **High investment** | 50-100 hours initial + ongoing maintenance for uncertain return |
| **Fine-tuning limitations** | Best for format/style; won't fix reasoning, factuality, or knowledge gaps |

### What Fine-Tuning Can and Cannot Fix

| Can Improve | Cannot Reliably Fix |
|-------------|---------------------|
| Output format consistency | Factual accuracy |
| JSON schema compliance | Missing context/history |
| Domain terminology | Complex reasoning |
| Style/tone alignment | World knowledge gaps |
| Entity extraction patterns | Hallucination (root cause) |

### The "Defer Unless" Trigger

Revisit fine-tuning only when we can identify a concrete failure mode that:
- Happens frequently (>10% of outputs)
- Survives prompt and pipeline fixes
- Survives RAG implementation
- Is clearly learnable (format/style/entity patterns)

## Alternatives Considered

### 1. Proceed with Fine-Tuning Now

Train a LoRA/QLoRA adapter for synthesis and entity extraction.

**Rejected because:**
- No concrete gaps identified to target
- High investment with uncertain return
- Better to exhaust lower-cost alternatives first

### 2. Cloud-Based Fine-Tuning

Use cloud providers (Together.ai, Lambda Labs) for faster training.

**Rejected because:**
- Adds external dependency and cost
- Local training is feasible for pilot scope
- Doesn't address the "no identified gaps" problem

### 3. Teacher-Student Distillation Only

Use stronger models to generate training data without explicit fine-tuning evaluation.

**Deferred:** Could be part of future fine-tuning if warranted, but same "no identified gaps" concern applies.

## Consequences

### Positive

1. **Avoid premature optimisation** — Don't invest in fine-tuning before validating need
2. **Lower complexity** — No adapter versioning, re-training cycles, or evaluation pipelines needed now
3. **Focus on higher-value work** — RAG (v0.8.3) likely provides more benefit
4. **Data preparation** — Passive flywheel builds training data for future if needed

### Negative

1. **Potential delay** — If fine-tuning is eventually needed, we'll have waited
2. **No format consistency gains** — May see continued JSON/schema issues (mitigated by validation)

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Fine-tuning becomes necessary later | Data flywheel collects training examples passively |
| Format/style issues persist | Robust validation, prompt engineering, model upgrade |
| Competitors fine-tune and gain advantage | Monitor; revisit if competitive pressure emerges |

## Preparation for Future Fine-Tuning

While deferring, we will prepare by:

### 1. Passive Data Flywheel

Collect during normal usage (low cost):
- Prompt + inputs
- Model outputs
- Failure tags (format error, missed entity, drift, etc.)
- Chosen vs rejected pairs when corrections made

### 2. Prerequisites Checklist

Before reconsidering fine-tuning:
- [ ] Quality metrics show concrete, recurring gaps
- [ ] Prompt engineering attempted and insufficient
- [ ] RAG implemented (v0.8.3) and gaps persist
- [ ] 500+ labelled examples collected via flywheel
- [ ] Clear acceptance criteria defined

### 3. Acceptance Criteria (When Ready)

| Task | Target |
|------|--------|
| Synthesis | ≥65% human preference vs baseline |
| Entity extraction | F1 +10-15 points |
| Format compliance | ≥99% JSON validity |

## Implementation

No implementation required for deferral.

**Data flywheel** may be implemented as a low-priority enhancement:
- Add `output_feedback` table for capturing preference data
- Log failure tags on validation errors
- Store correction notes when available

## References

- [Fine-Tuning Feasibility Research](../research/FINE-TUNING-FEASIBILITY.md) — Full analysis
- [ADR-0025: LLM Model Selection](0025-llm-model-selection.md) — Qwen 2.5 deployment
- [ADR-0026: RAG Integration Strategy](0026-rag-integration-strategy.md) — Alternative approach
