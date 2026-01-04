# 0005 — Architecture Decision: Interest-Based Story Ranking

**Status**: Accepted  
**Date**: 2026-01-04  
**Issue**: #57  
**Milestone**: v0.6.5 - Personalization

## Context

NewsBrief ranks stories by `importance_score` (based on article count, source quality, and recency) with no personalization. Users have different interests and want stories relevant to them prioritized.

### Current State (v0.6.4)

- **Single ranking dimension**: Stories sorted only by importance, freshness, or generated_at
- **Topic filtering only**: Can filter to one topic, but can't weight multiple topics
- **No preferences**: All users see the same story order
- **Topics defined**: 10 topics in `data/topics.json` (ai-ml, security, cloud-k8s, etc.)

### Problem Statement

1. **One-size-fits-all**: A security-focused user sees politics stories ranked equally
2. **No customization**: Can't boost preferred topics without filtering out others
3. **Lost signal**: Users interested in niche topics must scroll past mainstream stories
4. **Future blocker**: No foundation for personalized recommendations

## Decision

### Implement Separate Interest Score with Blended Ranking

We will calculate an `interest_score` at query time and blend it with `importance_score` for personalized ranking.

### Key Design Choices

#### 1. Score Application Strategy

**Decision**: Separate `interest_score` calculated at query time, blended with importance

| Option | Approach | Selected |
|--------|----------|----------|
| **A: Multiply** | `adjusted = importance × interest_weight` | ❌ |
| **B: Separate + Blend** | `blended = (importance × 0.6) + (interest × 0.4)` | ✅ |

**Rationale**:
- **Two distinct dimensions**: "What matters globally" vs "What I care about"
- **Toggle-able**: Can easily enable/disable interest weighting
- **Transparent**: Can show users why a story ranks where it does
- **Multiple sort modes**: Future UI can offer "By Importance", "By Interest", "Blended"

**Alternatives Considered**:
- **Multiply importance by weight**: Conflates two concepts, can't toggle easily
- **Filter by interest**: Too aggressive, hides potentially important stories

#### 2. Default Behavior

**Decision**: Interest-based ranking ON by default, with API parameter to disable

**Rationale**:
- Users benefit from personalization immediately
- Power users can disable via `apply_interests=false`
- Matches user expectation of "show me what I care about"

#### 3. Zero Weight Behavior

**Decision**: Weight of 0 demotes to bottom, does NOT hide stories

**Rationale**:
- Users may still want to see "uninteresting" topics occasionally
- Avoids accidentally hiding important breaking news
- Preserves user agency - they can scroll to see everything
- Hiding can be achieved via topic filtering if truly desired

#### 4. Configuration Storage

**Decision**: File-based config at `data/interests.json`

**Rationale**:
- No database changes needed (simpler implementation)
- Easy to edit manually
- Matches pattern of `data/topics.json`
- Future: Can migrate to database when user accounts are added

### Configuration Schema

```json
{
  "version": "1.0",
  "description": "User interest weights for story ranking",
  "enabled": true,
  "blend": {
    "importance_weight": 0.6,
    "interest_weight": 0.4
  },
  "topic_weights": {
    "ai-ml": 1.5,
    "security": 1.2,
    "cloud-k8s": 1.0,
    "devtools": 1.0,
    "chips-hardware": 0.8,
    "politics": 0.5,
    "business": 0.7,
    "science": 1.0,
    "general": 0.5,
    "sports": 0.3
  },
  "default_weight": 1.0
}
```

### API Changes

The `/stories` endpoint will accept a new parameter:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `apply_interests` | boolean | `true` | Whether to apply interest-based ranking |

When `apply_interests=true`:
- Stories sorted by: `(importance × 0.6) + (normalized_interest × 0.4)`
- Interest score normalized to 0-1 range

When `apply_interests=false`:
- Stories sorted by raw `importance_score` (current behavior)

### Score Calculation

```python
def calculate_interest_score(
    story_topics: List[str], 
    topic_weights: Dict[str, float],
    default_weight: float = 1.0
) -> float:
    """Calculate interest score for a story based on its topics."""
    if not story_topics:
        return default_weight
    
    weights = [topic_weights.get(topic, default_weight) for topic in story_topics]
    return sum(weights) / len(weights)

def calculate_blended_score(
    importance: float, 
    interest: float, 
    importance_weight: float = 0.6,
    interest_weight: float = 0.4
) -> float:
    """Blend importance and interest scores."""
    # Normalize interest to 0-1 range (assuming max weight is 2.0)
    normalized_interest = min(interest / 2.0, 1.0)
    return (importance * importance_weight) + (normalized_interest * interest_weight)
```

## Implementation

### New Files

| File | Purpose |
|------|---------|
| `data/interests.json` | Interest configuration |
| `app/interests.py` | Interest loading and scoring functions |

### Modified Files

| File | Changes |
|------|---------|
| `app/stories.py` | Add `apply_interests` parameter to `get_stories()` |
| `app/main.py` | Add `apply_interests` query parameter to `/stories` endpoint |
| `app/static/js/stories.js` | Add toggle for interest-based sorting |

### Implementation Plan

| Phase | Task | Effort |
|-------|------|--------|
| 1 | Create `data/interests.json` with schema | 15 min |
| 2 | Add `app/interests.py` with loading and scoring | 30 min |
| 3 | Modify `get_stories()` to apply interest weighting | 45 min |
| 4 | Add `apply_interests` parameter to API | 15 min |
| 5 | Update UI with interest toggle | 30 min |
| 6 | Tests and documentation | 45 min |
| **Total** | | **~3 hours** |

## Consequences

### Positive

✅ **Personalized experience**: Stories ranked by what user cares about  
✅ **No data loss**: All stories still visible, just reordered  
✅ **Transparent**: Two separate scores explain ranking  
✅ **Toggle-able**: Power users can disable if desired  
✅ **Future-ready**: Foundation for per-user preferences  
✅ **Simple config**: Edit JSON file to adjust preferences  

### Negative

⚠️ **Query-time calculation**: Interest score computed on each request  
⚠️ **Config file**: No UI for editing (future enhancement)  
⚠️ **Single user**: No per-user preferences until accounts added  

### Mitigation

| Risk | Mitigation |
|------|------------|
| Query performance | Calculation is O(n) with small n; negligible overhead |
| No editing UI | JSON is human-editable; UI planned in settings epic |
| Single user | Matches current single-user architecture |

## Success Metrics

| Metric | Target |
|--------|--------|
| Interest scoring overhead | < 5ms for typical query |
| Config load time | < 10ms (cached after first load) |
| User satisfaction | Preferred topics appear in top 5 stories |

## References

- [Issue #57](https://github.com/Deim0s13/newsbrief/issues/57)
- [ADR 0003: Synthesis Caching](0003-synthesis-caching.md)
- [data/topics.json](../../data/topics.json)

---

**Accepted**: 2026-01-04  
**Implementation**: v0.6.5
