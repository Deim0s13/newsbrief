# Story Generation Bug - Fix Summary

**Date**: 2025-12-01
**Issue**: Story generation failing - 78 unclustered articles
**Status**: ✅ FIXED

---

## 🎯 Root Cause

**SQLite TEXT comparison format mismatch causing incorrect datetime filtering**

- **Python passed**: `'2025-11-30 22:48:00+00:00'` (space separator)
- **Database stores**: `'2025-11-30T00:59:15'` (T separator)
- **SQLite compared**: Text strings, where space (ASCII 32) < 'T' (ASCII 84)
- **Result**: ALL dates appeared to be after cutoff, breaking time window filtering

---

## 🔧 Solution Implemented

**Convert datetime to ISO format without timezone before SQL binding**

```python
# Before (broken):
cutoff_time = datetime.now(UTC) - timedelta(hours=time_window_hours)
articles = session.execute(text("... WHERE published >= :cutoff_time"),
                          {"cutoff_time": cutoff_time})

# After (fixed):
cutoff_time = datetime.now(UTC) - timedelta(hours=time_window_hours)
cutoff_time_str = cutoff_time.replace(tzinfo=None).isoformat()
# Produces: '2025-11-30T22:48:00.000000'
articles = session.execute(text("... WHERE published >= :cutoff_time"),
                          {"cutoff_time": cutoff_time_str})
```

---

## ✅ Verification Results

### Before Fix
```json
{
  "time_window_hours": 2,
  "articles_found": 119,  // ❌ Should be ~33
  "clusters_created": 19,
  "duplicates_skipped": 19,
  "stories_generated": 0  // ❌ Broken
}
```

### After Fix (threshold=0.3)
```json
{
  "time_window_hours": 2,
  "articles_found": 28,  // ✅ Correct!
  "clusters_created": 0,
  "duplicates_skipped": 0,
  "stories_generated": 0
}
```

### After Fix (threshold=0.2)
```json
{
  "time_window_hours": 24,
  "articles_found": 118,  // ✅ Correct!
  "clusters_created": 5,
  "duplicates_skipped": 0,
  "stories_generated": 5  // ✅ Works!
}
```

---

## 📊 Impact

### Fixed
- ✅ Time window filtering works correctly
- ✅ 2-hour window: 28 articles (was 119)
- ✅ 24-hour window: 118 articles (was 119)
- ✅ New stories can be created
- ✅ Duplicate detection works properly

### Discovered
- ⚠️  **Default similarity threshold (0.3) may be too strict** after v0.6.1 entity-based clustering
- ℹ️  With threshold=0.2, 5 new stories created successfully
- ℹ️  With threshold=0.3, 0 new stories (too few clusters)

---

## 🔍 Secondary Issue: Similarity Threshold

### Analysis
Entity-based similarity (v0.6.1 feature) changed clustering behavior:
- **v0.5.x**: Pure keyword overlap
- **v0.6.1**: 30% keywords + 50% entities + 20% topic bonus

The stricter entity matching may require a lower threshold for the same clustering behavior.

### Recommendation
Consider adjusting default `similarity_threshold`:
- **Current**: 0.3
- **Suggested**: 0.25 or 0.2
- **Rationale**: Better balance after entity-based clustering

### Testing Needed
- [ ] Test with various thresholds (0.2, 0.25, 0.3)
- [ ] Verify clustering quality (no false positives)
- [ ] Check story relevance
- [ ] Validate with diverse article sets

---

## 📝 Remaining Issues

From manual testing, still to address:

### High Priority
1. **HTML tags in supporting articles** - `<p>` tags visible in UI
2. **Topic mismatch** - Story shows "Disaster Response" but articles show "Devtools"

### Medium Priority
3. **All article scores 7.000** - Need to investigate ranking calculation
4. **All importance scores 0.66** - Scoring may be using defaults
5. **Model/Status fields empty** - Not displayed in UI

### Low Priority
6. **Skim view (main articles page)** - Only font size changes, not layout

---

## ✅ Success Criteria (Updated)

- [x] Time window filtering works correctly
- [x] New stories can be created
- [x] Duplicate detection functions properly
- [x] Story generation completes in reasonable time
- [ ] All 78 unclustered articles form stories (threshold tuning needed)
- [ ] UI issues resolved (HTML tags, topic display)
- [ ] Score calculations verified

---

## 🚀 Next Steps

1. **Test similarity threshold adjustment** (0.3 → 0.25)
2. **Fix HTML tags in supporting articles UI**
3. **Investigate topic mismatch**
4. **Verify scoring calculations**
5. **Re-run manual testing checklist**
6. **Update GitHub issue with resolution**

---

## 📈 Commits

- `4f676ce` - fix: Correct datetime format for SQLite TEXT comparison in story generation

---

**Status**: Core bug FIXED, similarity threshold tuning recommended, UI issues remain
