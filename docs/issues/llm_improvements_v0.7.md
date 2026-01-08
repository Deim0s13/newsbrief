# LLM Improvements Milestone (v0.7)

## Overview

This milestone focuses on enhancing the LLM capabilities in NewsBrief to improve story generation quality, classification accuracy, and overall application intelligence.

## Current State

- **Default Model**: `llama3.1:8b` (upgraded from llama3.2:3b)
- **Available Models**: llama3.1:8b, llama3.2:3b, mistral:latest
- **LLM Usage**: Topic classification, entity extraction, story synthesis

---

## Issues / Enhancement Tasks

### Issue #1: Model Selection & Configuration
**Priority**: High
**Status**: Planning

**Problem**: Currently using a single model for all tasks. Different tasks may benefit from different models (speed vs accuracy trade-offs).

**Proposed Solution**:
- [ ] Add task-specific model configuration in `config.yaml` or environment variables
- [ ] Fast model for simple classification
- [ ] Capable model for story synthesis
- [ ] Optional cloud API fallback (OpenAI, Anthropic) for complex tasks

**Files to modify**: `app/llm.py`, `app/config.py`, environment setup

---

### Issue #2: Story Generation Quality
**Priority**: High
**Status**: Planning

**Problem**: Story synthesis may produce generic or inconsistent narratives.

**Proposed Solutions**:
- [ ] Improve story synthesis prompts with better examples
- [ ] Add story quality scoring/validation
- [ ] Implement regeneration with feedback loop
- [ ] Consider larger models (llama3.1:70b) for synthesis
- [ ] Evaluate cloud APIs for critical synthesis tasks

**Files to modify**: `app/stories.py`, prompts configuration

---

### Issue #3: Prompt Engineering & Templates
**Priority**: Medium
**Status**: Planning

**Problem**: Prompts are scattered across code files. No systematic approach to prompt versioning or A/B testing.

**Proposed Solutions**:
- [ ] Centralize prompts into a `prompts/` directory or config
- [ ] Add prompt versioning for experimentation
- [ ] Create prompt templates with variable substitution
- [ ] Document prompt design patterns that work well

**Files to create**: `app/prompts/`, `docs/prompt-engineering.md`

---

### Issue #4: LLM Response Caching
**Priority**: Medium
**Status**: Planning

**Problem**: Repeated LLM calls for similar content waste compute resources.

**Proposed Solutions**:
- [ ] Implement semantic caching for similar queries
- [ ] Cache classification results by article hash
- [ ] Add cache invalidation strategy
- [ ] Consider Redis or SQLite for persistent cache

**Files to modify**: `app/llm.py`, new `app/llm_cache.py`

---

### Issue #5: Model Evaluation & Benchmarking
**Priority**: Medium
**Status**: Planning

**Problem**: No systematic way to compare model performance on NewsBrief tasks.

**Proposed Solutions**:
- [ ] Create evaluation dataset with expected outputs
- [ ] Build benchmarking scripts for classification accuracy
- [ ] Add story quality metrics (coherence, factual consistency)
- [ ] Track inference time and resource usage
- [ ] Generate comparison reports

**Files to create**: `scripts/benchmark_models.py`, `tests/eval/`

---

### Issue #6: Cloud API Integration
**Priority**: Low (Optional)
**Status**: Planning

**Problem**: Local models have capability limits. Cloud APIs offer more powerful options.

**Proposed Solutions**:
- [ ] Add OpenAI API integration as optional backend
- [ ] Add Anthropic Claude integration
- [ ] Implement fallback chain: local → cloud
- [ ] Add cost tracking and usage limits
- [ ] Handle API rate limiting gracefully

**Files to modify**: `app/llm.py`, new `app/llm_cloud.py`

---

### Issue #7: Fine-tuning for Domain-Specific Tasks
**Priority**: Low (Future)
**Status**: Research

**Problem**: General models may not be optimal for news aggregation tasks.

**Research Areas**:
- [ ] Investigate LoRA fine-tuning for classification
- [ ] Collect training data from user feedback
- [ ] Evaluate fine-tuned vs base model performance
- [ ] Consider Ollama's fine-tuning workflow

---

## Priority Order

1. **Issue #2**: Story Generation Quality (core value proposition)
2. **Issue #1**: Model Selection (foundation for optimization)
3. **Issue #3**: Prompt Engineering (quick wins)
4. **Issue #5**: Benchmarking (measure improvements)
5. **Issue #4**: Caching (efficiency)
6. **Issue #6**: Cloud APIs (capability boost)
7. **Issue #7**: Fine-tuning (long-term)

---

## Success Metrics

- Story generation produces coherent, accurate narratives
- Topic classification accuracy > 95% on test set
- Reduced LLM inference time through caching
- Positive user feedback on story quality
- Clear documentation of prompts and model usage

---

## Notes

- The upgrade from llama3.2:3b to llama3.1:8b already improved classification significantly
- Consider memory/compute constraints when evaluating larger models
- Cloud APIs add cost but may be worthwhile for critical tasks
