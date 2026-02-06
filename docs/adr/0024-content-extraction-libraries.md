# ADR-0024: Content Extraction Library Selection

**Status:** Accepted
**Date:** February 2026
**Deciders:** Development Team
**Related:** v0.8.0 - Content Extraction Pipeline Upgrade

## Context

NewsBrief extracts article content from RSS feed links to provide full-text for LLM synthesis. The current implementation uses `readability-lxml` which has limitations:

- Only extracts title and plain text
- No metadata extraction (author, publication date, images)
- No fallback mechanism when extraction fails
- No quality scoring or failure tracking
- Benchmark performance (F-Score: 0.801) leaves room for improvement

As part of v0.8.0, we evaluated alternative content extraction libraries to improve extraction quality and reliability.

## Decision

We will implement a **tiered extraction strategy** using multiple libraries:

| Tier | Library | Use Case | Quality Score Range |
|------|---------|----------|---------------------|
| **Primary** | trafilatura | Best quality, handles most sites | 0.9 - 1.0 |
| **Fallback** | readability-lxml | When trafilatura fails | 0.7 - 0.9 |
| **Last Resort** | RSS summary | When all extraction fails | 0.3 - 0.5 |

### Primary: Trafilatura

Trafilatura (v2.0.0, December 2024) is selected as the primary extractor based on:

**Benchmark Performance:**
- F-Score: 0.909 (vs readability-lxml's 0.801) — **13.5% improvement**
- Accuracy: 0.910 (vs readability-lxml's 0.820) — **11% improvement**
- Precision: 0.914, Recall: 0.904 — best balance

**Features:**
- Metadata extraction (author, date, site name, categories, tags)
- Multiple output formats (TXT, JSON, XML, Markdown)
- Built-in fallback mechanisms (jusText integration)
- Actively maintained with comprehensive documentation
- Adopted by HuggingFace, IBM, Microsoft Research, Stanford

**Performance:**
- 7.1x baseline speed (acceptable for our use case)
- Pure Python, no system dependencies

### Fallback: Readability-lxml

Retained as fallback because:
- Already installed and tested
- Faster (5.8x baseline)
- Good precision (0.891) for simple cases
- Zero migration risk for existing functionality

### Not Selected: Newspaper4k

Rejected despite being "news-focused" because:
- Poor recall (0.593) — misses significant content
- Heavy dependencies (NLP libraries)
- Recently revived from abandoned project (newspaper3k)
- F-Score (0.713) significantly below alternatives

## Consequences

### Positive

1. **Better extraction quality** — ~13% improvement in F-Score
2. **Rich metadata** — author, dates, tags available for future features
3. **Improved reliability** — tiered fallback prevents complete failures
4. **Observability** — each tier reports success/failure reasons
5. **Future-proof** — trafilatura actively maintained

### Negative

1. **New dependency** — trafilatura adds to dependency footprint
2. **Slightly slower** — primary extractor is ~20% slower than current
3. **Migration effort** — existing code needs refactoring

### Neutral

1. **Backward compatible** — readability-lxml retained as fallback
2. **No database schema changes** — extraction metadata will be added separately (#182)

## Implementation

The tiered extraction will be implemented in a new `app/extraction.py` module:

```python
@dataclass
class ExtractionResult:
    content: str | None
    title: str | None
    method: str  # 'trafilatura', 'readability', 'rss_summary', 'failed'
    quality_score: float  # 0.0 - 1.0
    metadata: dict  # author, date, images, etc.
    error: str | None
    stage_results: list[StageResult]  # Results from each attempted stage
```

Each stage will emit success/failure reasons to enable tuning over time.

## References

- [Trafilatura Documentation](https://trafilatura.readthedocs.io/)
- [Trafilatura Evaluation Benchmark](https://trafilatura.readthedocs.io/en/latest/evaluation.html)
- [ScrapingHub Article Extraction Benchmark](https://github.com/scrapinghub/article-extraction-benchmark)
- Issue #180: Research & benchmark content extraction libraries
- Issue #181: Implement tiered content extraction module
