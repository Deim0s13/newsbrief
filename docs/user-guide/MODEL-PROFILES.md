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

*Last updated: v0.8.1*
