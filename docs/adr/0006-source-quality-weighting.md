# 0006 — Architecture Decision: Source Quality Weighting for Stories

**Status**: Accepted
**Date**: 2026-01-04
**Issue**: #58
**Milestone**: v0.6.5 - Personalization

## Context

NewsBrief ranks stories by importance (article count, source diversity, entities) and freshness. Issue #57 added interest-based ranking for topic preferences. However, not all sources are equal in quality or credibility.

### Current State (v0.6.4)

- **Feed health scoring**: Tracks response times, success rates (0-100 scale)
- **Source diversity**: Counts unique sources in importance calculation
- **No reputation weighting**: Hacker News treated same as random blog
- **20% source quality**: Based on health, not credibility

### Problem Statement

1. **Equal treatment**: High-quality sources (Hacker News, Ars Technica) weighted same as unknown blogs
2. **No credibility signal**: Stories from reputable sources don't get preference
3. **User expectation**: Users trust some sources more than others
4. **Quality vs health**: A healthy but low-quality source still ranks well

## Decision

### Implement Source Quality Weighting as a Separate Dimension

We will add source reputation weights that factor into story ranking, similar to how interest weights work.

### Key Design Choices

#### 1. Score Application Strategy

**Decision**: Add as a separate dimension, blended with importance (like interests)

| Option | Approach | Selected |
|--------|----------|----------|
| **A: Multiply** | `importance × source_weight` | ❌ |
| **B: Separate + Blend** | Blend importance, interest, AND source quality | ✅ |

**Rationale**:
- Consistent with interest-based ranking approach
- Three distinct dimensions: importance, interest, source quality
- Each can be toggled independently
- Transparent ranking explanation

**New Blend Formula**:
```
blended = (importance × 0.5) + (interest × 0.3) + (source_quality × 0.2)
```

Note: Weights are configurable. Source quality gets 20% influence.

#### 2. Source Matching Strategy

**Decision**: Match by both feed name AND domain

```json
{
  "feed_weights": {
    "Hacker News": 1.5,
    "Ars Technica": 1.3
  },
  "domain_weights": {
    "news.ycombinator.com": 1.5,
    "arstechnica.com": 1.3
  }
}
```

**Matching Priority**:
1. Exact feed name match → use feed weight
2. Domain match → use domain weight
3. Neither → use default weight (1.0)

**Rationale**:
- Feed names can vary ("Hacker News" vs "HN")
- Domain matching provides fallback
- Both needed for comprehensive coverage

#### 3. Default Behavior

**Decision**: Source weighting ON by default, configurable via API

- Default weight: 1.0 (neutral)
- Can be disabled via `apply_source_weights=false`
- Blend weights configurable in config file

#### 4. Configuration Storage

**Decision**: File-based config at `data/source_weights.json`

**Rationale**:
- Consistent with `interests.json` pattern
- Easy to edit manually
- No database changes needed
- Future: can migrate to database when needed

### Configuration Schema

```json
{
  "version": "1.0",
  "description": "Source reputation weights for story ranking",
  "enabled": true,
  "blend_weight": 0.2,
  "feed_weights": {
    "Hacker News": 1.5,
    "Ars Technica": 1.3,
    "TechCrunch": 1.2,
    "The Verge": 1.1,
    "Wired": 1.1,
    "MIT Technology Review": 1.4,
    "IEEE Spectrum": 1.3
  },
  "domain_weights": {
    "news.ycombinator.com": 1.5,
    "arstechnica.com": 1.3,
    "techcrunch.com": 1.2,
    "theverge.com": 1.1,
    "wired.com": 1.1,
    "technologyreview.com": 1.4,
    "spectrum.ieee.org": 1.3
  },
  "default_weight": 1.0
}
```

### Updated Blend Formula

With source quality as a third dimension:

```python
def calculate_full_blended_score(
    importance: float,      # 0.0 - 1.0
    interest: float,        # 0.0 - 2.0 (normalized to 0-1)
    source_quality: float,  # 0.0 - 2.0 (normalized to 0-1)
) -> float:
    # Configurable weights (default: 50/30/20)
    importance_weight = 0.5
    interest_weight = 0.3
    source_weight = 0.2

    normalized_interest = min(interest / 2.0, 1.0)
    normalized_source = min(source_quality / 2.0, 1.0)

    return (
        importance * importance_weight +
        normalized_interest * interest_weight +
        normalized_source * source_weight
    )
```

### API Changes

The `/stories` endpoint will accept an additional parameter:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `apply_source_weights` | boolean | `true` | Apply source quality weighting |

### Score Calculation for Stories

For each story:
1. Get all article source feeds
2. Look up weight for each feed (by name, then domain)
3. Calculate average source weight across all articles
4. Normalize and blend with importance and interest

```python
def calculate_story_source_weight(article_feeds: List[Feed]) -> float:
    """Calculate average source weight for a story's articles."""
    weights = []
    for feed in article_feeds:
        weight = get_feed_weight(feed.name) or get_domain_weight(feed.url)
        weights.append(weight or default_weight)
    return sum(weights) / len(weights) if weights else default_weight
```

## Implementation

### New Files

| File | Purpose |
|------|---------|
| `data/source_weights.json` | Source reputation configuration |
| `app/source_weights.py` | Source weight loading and calculation |

### Modified Files

| File | Changes |
|------|---------|
| `app/interests.py` | Update blend formula to include source quality |
| `app/stories.py` | Pass source weights to blending function |
| `app/main.py` | Add `apply_source_weights` parameter |

### Implementation Plan

| Phase | Task | Effort |
|-------|------|--------|
| 1 | Create `data/source_weights.json` | 15 min |
| 2 | Create `app/source_weights.py` | 30 min |
| 3 | Update blend formula in `app/interests.py` | 30 min |
| 4 | Integrate into `get_stories()` | 30 min |
| 5 | Add API parameter | 15 min |
| 6 | Tests and documentation | 45 min |
| **Total** | | **~2.5 hours** |

## Consequences

### Positive

✅ **Quality signal**: Reputable sources boost story ranking
✅ **Consistent pattern**: Same approach as interest-based ranking
✅ **Three dimensions**: Importance, interest, source quality - transparent ranking
✅ **Configurable**: Easy to adjust weights per source
✅ **Fallback matching**: Feed name OR domain for flexibility

### Negative

⚠️ **Subjectivity**: Source quality is subjective - what's "reputable"?
⚠️ **Maintenance**: Need to add weights for new sources
⚠️ **Complexity**: Three-dimensional blending is more complex

### Mitigation

| Risk | Mitigation |
|------|------------|
| Subjectivity | Default weight is neutral (1.0); users can customize |
| Maintenance | Domain matching provides fallback; unknown sources get neutral weight |
| Complexity | Well-documented code; comprehensive tests |

## Success Metrics

| Metric | Target |
|--------|--------|
| Source matching rate | > 70% of articles match a configured weight |
| Ranking impact | High-quality sources appear in top 5 more often |
| Configuration | At least 10 major sources weighted |

## References

- [Issue #58](https://github.com/Deim0s13/newsbrief/issues/58)
- [ADR 0005: Interest-Based Ranking](0005-interest-based-ranking.md)
- [data/interests.json](../../data/interests.json)

---

**Accepted**: 2026-01-04
**Implementation**: v0.6.5
