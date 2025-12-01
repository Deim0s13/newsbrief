# Story Generation Bug - Root Cause Analysis

**Date**: 2025-12-01  
**Issue**: Story generation failing - 78 unclustered articles  
**Status**: ROOT CAUSE IDENTIFIED

---

## 🎯 Root Cause

**The time window filtering in SQLite is completely broken.**

### The Query
```python
cutoff_time = datetime.now(UTC) - timedelta(hours=2)  # Nov 30 22:48
articles = session.execute(
    text("""
        SELECT id, title, topic, published, summary, ai_summary
        FROM items 
        WHERE published >= :cutoff_time
        ...
    """),
    {"cutoff_time": cutoff_time},
).fetchall()
```

### Expected Behavior
- Cutoff: Nov 30 22:48
- Should return: Only articles >= Nov 30 22:48 (~33 articles)

### Actual Behavior
- Returns: 119 articles
- Oldest article: **Nov 30 01:04** (24 hours ago!)
- **The datetime comparison is not working**

### Proof
```bash
# Query returns 119 articles
sqlite3 data/newsbrief.sqlite3 "SELECT COUNT(*) FROM items WHERE published >= datetime('2025-11-30 22:48:00');"
# Result: 119

# But oldest article is from 01:04, not 22:48
sqlite3 data/newsbrief.sqlite3 "SELECT MIN(datetime(published)) FROM items WHERE published >= datetime('2025-11-30 22:48:00');"
# Result: 2025-11-30 01:04:40
```

---

## 💥 Impact

1. **Time window is ignored** - Always gets ALL recent articles regardless of window
2. **New articles cluster with old articles** - Mixing Dec 1 + Nov 30
3. **Duplicate detection triggers** - Same old articles = same hash = duplicate
4. **No new stories created** - All 19 clusters marked as duplicates
5. **78 fresh articles unclustered** - Can't form their own stories

---

## 🔍 Why This Happens

### Hypothesis 1: Timezone Mismatch
- Python creates: `2025-11-30 22:48:57+00:00` (UTC with timezone)
- SQLite stores: `2025-12-01T00:59:15` (no timezone)
- SQLite comparison may be treating them as different timezones

### Hypothesis 2: String vs DateTime Comparison
- SQLite may be doing string comparison instead of datetime comparison
- `"2025-11-30 22:48"` as string is LESS than `"2025-11-30 01:04"` (string sort)

### Hypothesis 3: SQLAlchemy Parameter Binding
- The `:cutoff_time` parameter may not be binding correctly
- SQLite might be receiving the wrong value or format

---

## 🧪 Testing

### Test 1: Direct SQLite Query
```bash
sqlite3 data/newsbrief.sqlite3 "
SELECT COUNT(*), MIN(published), MAX(published)
FROM items 
WHERE published >= '2025-11-30 22:48:00';
"
```
**Result**: Should show if the issue is in SQLite or SQLAlchemy

### Test 2: Check Parameter Binding
Add logging to see what value SQLite receives:
```python
logger.info(f"Cutoff time: {cutoff_time}")
logger.info(f"Type: {type(cutoff_time)}")
```

### Test 3: Try Different Formats
- ISO format: `2025-11-30T22:48:00`
- Unix timestamp: `1733012897`
- Explicit datetime() function in SQL

---

## ✅ Solution Options

### Option A: Use Unix Timestamps (Recommended)
```python
cutoff_timestamp = int((datetime.now(UTC) - timedelta(hours=time_window_hours)).timestamp())

articles = session.execute(
    text("""
        SELECT id, title, topic, published, summary, ai_summary
        FROM items 
        WHERE CAST(strftime('%s', published) AS INTEGER) >= :cutoff_timestamp
        ...
    """),
    {"cutoff_timestamp": cutoff_timestamp},
).fetchall()
```

### Option B: Store Timestamps as Integers
- Modify database schema to store published as INTEGER (Unix timestamp)
- More reliable for comparisons
- Requires migration

### Option C: Use SQLite datetime() Function
```python
articles = session.execute(
    text("""
        SELECT id, title, topic, published, summary, ai_summary
        FROM items 
        WHERE datetime(published) >= datetime(:cutoff_time)
        ...
    """),
    {"cutoff_time": cutoff_time.isoformat()},
).fetchall()
```

### Option D: Filter in Python (Not Recommended)
- Fetch all articles
- Filter by time in Python
- Slower but guaranteed to work

---

## 📝 Next Steps

1. **Verify the root cause** - Add logging to confirm hypothesis
2. **Implement fix** - Try Option A (Unix timestamps) first
3. **Test thoroughly** - Verify time window filtering works
4. **Validate story generation** - Ensure new articles form stories
5. **Check for other datetime comparisons** - Audit codebase for similar issues

---

## 🔗 Related Code

- `app/stories.py:1156-1170` - Time window query
- `app/db.py` - Database schema (published column type)
- `app/feeds.py` - Feed refresh (may have similar datetime issues)

---

**Priority**: CRITICAL - Blocks v0.6.1 release

