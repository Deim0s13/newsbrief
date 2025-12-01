# 🐛 Story generation failing: 78 unclustered articles but all clusters marked as duplicates

## Problem Summary

Story generation is not creating new stories despite having 78 unclustered articles (65% of recent articles). All 19 new clusters are being marked as duplicates.

## Symptoms

- **User Impact**: Cannot generate new stories with fresh articles
- **Time**: Story generation takes 5+ minutes but produces 0 new stories
- **API Response**: `All 19 story clusters were duplicates of existing stories`
- **Database**: 78 articles from last 24h not included in any story

## Verified Working

✅ Entity extraction (all 119 articles have entities)  
✅ Feed refresh (22 feeds, 2.5 min)  
✅ Clustering algorithm (creates 19 clusters)  
✅ Duplicate detection (works, but may be too aggressive)

## Investigation Needed

### 1. Duplicate Detection Logic
**File**: `app/stories.py` lines ~1404-1509

Current logic uses MD5 hash of sorted article IDs:
```python
"cluster_hash": hashlib.md5(
    json.dumps(sorted(cluster_article_ids)).encode()
).hexdigest()
```

**Issue**: If clustering consistently groups same articles, all new clusters appear as duplicates.

**Questions**:
- Are new articles being added to existing clusters (with old articles)?
- Should hash exclude old articles or use time-windowed approach?
- Is similarity threshold too strict (0.3 default)?

### 2. Clustering Algorithm
**File**: `app/stories.py` lines ~1200-1300

**Questions**:
- Why aren't 78 unclustered articles forming their own clusters?
- Is `min_articles_per_story=2` preventing single-article stories?
- Are similarity scores too low to cluster these articles?

### 3. Time Window Logic
**Default**: 24 hours  
**Question**: Are old and new articles clustering together, triggering duplicate detection?

## Debugging Queries

```bash
# Articles without stories
sqlite3 data/newsbrief.sqlite3 "SELECT COUNT(DISTINCT i.id) FROM items i WHERE datetime(i.published) > datetime('now', '-24 hours') AND i.id NOT IN (SELECT article_id FROM story_articles);"
# Result: 78

# Total recent articles
sqlite3 data/newsbrief.sqlite3 "SELECT COUNT(*) FROM items WHERE datetime(published) > datetime('now', '-24 hours');"
# Result: 119

# Recent articles with entities
sqlite3 data/newsbrief.sqlite3 "SELECT COUNT(*) FROM items WHERE datetime(published) > datetime('now', '-24 hours') AND entities_json IS NOT NULL;"
# Result: 119 (all have entities)
```

## Reproduction Steps

1. Ensure database has recent articles (last 24h)
2. Run story generation via UI or API:
   ```bash
   curl -X POST http://localhost:8787/stories/generate \
     -H 'Content-Type: application/json' \
     -d '{"time_window_hours": 24, "min_articles_per_story": 2, "similarity_threshold": 0.3}'
   ```
3. Observe: `stories_generated: 0`, `duplicates_skipped: 19`

## Success Criteria

- [ ] 78 unclustered articles form new stories
- [ ] Story generation completes in <2 minutes (not 5+)
- [ ] New stories appear in UI after generation
- [ ] Duplicate detection works but doesn't block legitimate new stories
- [ ] Integration test: fetch articles → generate stories → verify all articles in stories

## Potential Fixes

### Option A: Loosen Duplicate Detection
- Only mark as duplicate if >80% of articles overlap (not exact match)
- Allow partial story updates instead of complete duplicates

### Option B: Improve Clustering
- Lower similarity threshold for new articles
- Ensure time-windowed clustering doesn't mix old/new too aggressively
- Consider min_articles_per_story=1 for breaking news

### Option C: Investigate Entity Overlap
- Check if entity-based similarity (v0.6.1 feature) is too strict
- Verify keyword+entity weighting (30%/50% currently)

## Related Files

- `app/stories.py`: `generate_stories_simple()` function
- `app/entities.py`: Entity extraction and overlap calculation
- `app/db.py`: Database schema (items, stories, story_articles tables)

## Priority

**CRITICAL** - Blocks v0.6.1 release. Core story generation feature is non-functional for users with fresh articles.

## Labels

- `bug`: Core functionality broken
- `priority-critical`: Blocks release
- `v0.6.1`: Must fix before release

## Milestone

v0.6.0 - Enhanced Intelligence & Polish

---

**Created**: 2025-12-01  
**Found During**: v0.6.1 manual testing  
**Assignee**: TBD

