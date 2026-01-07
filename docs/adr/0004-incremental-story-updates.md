# 0004 — Architecture Decision: Incremental Story Updates with Versioning

**Status**: Accepted
**Date**: 2025-12-31
**Issue**: #49
**Milestone**: v0.6.3 - Performance

## Context

NewsBrief generates stories by clustering related articles and synthesizing them into unified narratives. As news evolves, new articles appear that relate to existing stories.

### Current Behavior (v0.6.2)

When story generation runs:
1. Articles are clustered by topic + similarity
2. Each cluster gets a `cluster_hash` (hash of sorted article IDs)
3. If `cluster_hash` matches an existing story → **skip entirely**
4. Only truly new clusters create new stories

### Problem

This approach has limitations:
- **Stale stories**: Existing stories don't incorporate new developments
- **Missing context**: Users don't see the latest articles on ongoing topics
- **Duplicate near-misses**: Similar but not identical clusters create redundant stories
- **No evolution tracking**: Can't see how a story developed over time

### Example Scenario

```
Day 1: Articles A, B, C → Story v1 "OpenAI Announces GPT-5"
Day 2: Articles B, C, D, E arrive (D, E are new developments)

Current behavior:
  - Cluster [B,C,D,E] has different hash → Creates Story v2 (duplicate)
  - Or if exact match → Skips entirely (misses new info)

Desired behavior:
  - Detect 70%+ overlap with Story v1
  - Merge articles: A, B, C, D, E
  - Re-synthesize with complete picture
  - Archive v1, create v2 as update
```

## Decision

### Implement Incremental Story Updates with Version History

When generating stories:
1. **Detect overlap**: Check if new cluster shares 70%+ articles with existing story
2. **Merge articles**: Combine old and new article sets
3. **Re-synthesize**: Generate fresh synthesis with complete article set
4. **Version history**: Keep old version as archived record, create new version

### Key Design Choices

#### 1. Overlap Threshold: 70%

**Decision**: Trigger update when 70%+ of cluster articles exist in an active story

```python
overlap_ratio = len(cluster_articles & story_articles) / len(cluster_articles)
if overlap_ratio >= 0.70:
    # Update existing story
else:
    # Create new story
```

**Rationale**:
- 70% is high enough to ensure genuine relationship
- Low enough to catch stories with 1-2 new articles
- Avoids updating unrelated stories

**Alternatives Considered**:
- 50%: Too aggressive, would merge loosely related stories
- 90%: Too conservative, would miss updates with 2+ new articles

#### 2. Update Strategy: Full Re-synthesis

**Decision**: Re-synthesize entire story with all articles (old + new)

**Rationale**:
- Produces coherent, unified narrative
- LLM has full context for accurate synthesis
- Avoids awkward "appended" content
- Synthesis cache (Issue #46) makes re-synthesis efficient

**Alternatives Considered**:
- **Append-only**: Add new content to existing synthesis
  - Rejected: Creates disjointed narrative
- **Differential update**: Only synthesize delta
  - Rejected: Complex, may miss connections between old/new

#### 3. Version History: Keep Previous Versions

**Decision**: Archive previous version as separate record with `status: superseded`

**Schema**:
```sql
ALTER TABLE stories ADD COLUMN version INTEGER DEFAULT 1;
ALTER TABLE stories ADD COLUMN previous_version_id INTEGER REFERENCES stories(id);
```

**New Status Values**:
- `active`: Current version, displayed to users
- `archived`: Old story (time-based archival)
- `superseded`: Replaced by newer version

**Rationale**:
- Full audit trail of story evolution
- Users can view story history if desired
- No data loss
- Supports "story timeline" feature in future

**Alternatives Considered**:
- **Overwrite in place**: Update story record directly
  - Rejected: Loses history, can't track evolution
- **Version number only**: Track version but not history
  - Rejected: Can't reconstruct previous state
- **Separate versions table**: Normalize version history
  - Rejected: Over-engineering for current needs

#### 4. Article Linking on Update

**Decision**: New version links to ALL articles (merged set)

When updating Story v1 → v2:
- v1 keeps its original `story_articles` links (historical record)
- v2 gets links to merged article set (A, B, C, D, E)
- Articles can belong to multiple story versions

**Rationale**:
- Maintains historical accuracy
- v1 snapshot remains valid
- v2 has complete picture

## Implementation

### Schema Changes

```sql
-- Add versioning columns
ALTER TABLE stories ADD COLUMN version INTEGER DEFAULT 1;
ALTER TABLE stories ADD COLUMN previous_version_id INTEGER;

-- Add index for version queries
CREATE INDEX idx_stories_previous_version ON stories(previous_version_id);
```

### New Functions

```python
def find_overlapping_story(
    session: Session,
    cluster_article_ids: List[int],
    overlap_threshold: float = 0.70,
) -> Optional[Story]:
    """Find active story with 70%+ article overlap."""

def update_story_with_new_articles(
    session: Session,
    existing_story: Story,
    merged_article_ids: List[int],
    new_synthesis: Dict[str, Any],
    model: str,
) -> int:
    """
    Create new version of story:
    1. Mark existing story as 'superseded'
    2. Create new story with version = old.version + 1
    3. Link new story to merged articles
    4. Set previous_version_id to old story
    """
```

### Integration Point

In `generate_stories_simple()`, after clustering but before synthesis:

```python
for cluster in clusters:
    # Check for overlapping existing story
    existing = find_overlapping_story(session, cluster.article_ids)

    if existing:
        # Merge article sets
        merged_ids = set(existing.article_ids) | set(cluster.article_ids)
        if merged_ids != set(existing.article_ids):
            # New articles found - update story
            synthesis = _generate_story_synthesis(session, list(merged_ids), model)
            update_story_with_new_articles(session, existing, merged_ids, synthesis, model)
    else:
        # No overlap - create new story
        create_new_story(...)
```

## Consequences

### Positive

✅ **Living stories**: Stories evolve with new developments
✅ **Complete context**: Users see full picture, not fragmented stories
✅ **Audit trail**: Full version history preserved
✅ **Efficient**: Synthesis cache reduces re-synthesis cost
✅ **User value**: "Story timeline" feature enabled for future

### Negative

⚠️ **Storage growth**: Each update creates new record (mitigated by archival)
⚠️ **Complexity**: More logic in generation pipeline
⚠️ **Query overhead**: Must check for overlaps before creating stories

### Mitigation

| Risk | Mitigation |
|------|------------|
| Storage growth | Existing archival deletes old stories after 30 days |
| Complexity | Well-documented code, comprehensive tests |
| Query overhead | Index on story_articles, efficient overlap query |

## Success Metrics

| Metric | Target |
|--------|--------|
| Stories updated vs. duplicated | > 50% of overlapping clusters update rather than duplicate |
| Version chain depth | Average < 3 versions per story topic |
| Query performance | Overlap check < 100ms for typical cluster |

## References

- [Issue #49](https://github.com/Deim0s13/newsbrief/issues/49)
- [ADR 0002: Story-Based Aggregation](0002-story-based-aggregation.md)
- [ADR 0003: Synthesis Caching](0003-synthesis-caching.md)

---

**Accepted**: 2025-12-31
**Implementation**: v0.6.3
