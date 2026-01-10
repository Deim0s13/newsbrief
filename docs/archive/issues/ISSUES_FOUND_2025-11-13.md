# Issues Found During Testing - 2025-11-13

**Date**: 2025-11-13
**Status**: Active Issues
**Severity**: Medium-High

---

## Issue 1: No New Stories Generated (Duplicate Detection Working Too Well)

**Severity**: Medium
**Status**: By Design (but needs UX improvement)

### Problem:
- User clicks "Generate Stories"
- System returns `success: true, stories_generated: 0`
- No new stories appear even after 12+ hours

### Root Cause:
The duplicate detection is working correctly. We have:
- **138 articles in last 24 hours**
- **3 existing stories** with these exact article combinations
- Duplicate detection sees same articles → same story_hash → skips

### Why It Happens:
Story clustering is **deterministic** - same articles + same algorithm = same clusters = same story_hash

### Solution Options:

#### Option A: Time-based Story Refresh (Recommended)
Add a `regenerate` flag or `force` parameter:
```python
POST /stories/generate
{
  "time_window_hours": 24,
  "force_regenerate": true  // Skip duplicate check
}
```

#### Option B: Archive Old Stories Automatically
Stories older than X hours get archived, allowing regeneration:
- Archive stories > 24 hours old
- Only check duplicates against "active" stories
- Old stories still viewable in "archived" view

#### Option C: Smart Refresh Logic
Only regenerate if:
- New articles added since last generation
- Significant number of new articles (e.g., 20+)
- Time since last generation > threshold (e.g., 12 hours)

### Immediate Workaround:
```bash
# Clear old stories to allow regeneration
cd /Users/pleathen/Projects/newsbrief
echo "yes" | .venv/bin/python scripts/clear_stories.py

# Or archive them manually via SQL
UPDATE stories SET status='archived' WHERE generated_at < datetime('now', '-24 hours');
```

---

## Issue 2: Feed Refresh Returns HTTP 500

**Severity**: High
**Status**: Needs Investigation

### Problem:
- Clicking "Refresh Feeds" in UI gives HTTP 500 error
- POST /refresh endpoint not working properly

### Symptoms:
```bash
curl -X POST http://localhost:8787/refresh
# Returns empty or invalid response
```

### Need to Investigate:
1. What is the actual error from the endpoint?
2. Is it a network issue (fetching feeds)?
3. Is it a database issue?
4. Is it an LLM issue (summarization)?

### Debug Steps:
```bash
# Check server logs for errors
tail -100 /tmp/uvicorn.log | grep ERROR

# Try refresh with verbose output
curl -v -X POST http://localhost:8787/refresh

# Test feed fetch manually
python3 -c "
from app.feeds import fetch_and_store
stats = fetch_and_store()
print(stats)
"
```

---

## Issue 3: UI Polish Items (Backlogged)

**Severity**: Low
**Status**: Tracked in UI_IMPROVEMENTS_BACKLOG.md

- Feed management rendering issues
- Responsive design improvements
- Browser compatibility

---

## Recommended Action Plan

### Immediate (Unblock User):
1. ✅ **Document workaround** for story generation (clear/archive old stories)
2. 🔧 **Fix feed refresh** - investigate and fix HTTP 500
3. 📝 **Update UI** - show better message when 0 stories generated

### Short Term (Next Session):
4. ⚡ **Implement Option B** - Auto-archive old stories
5. 🎯 **Add force regenerate** flag for manual refresh
6. 📊 **Add UI indicator** - "X new articles since last generation"

### Medium Term:
7. 🤖 **Scheduled generation** (Issue #48) - solves this naturally
8. 🧠 **Smart refresh logic** - only regenerate when meaningful

---

## Technical Details

### Current Behavior:
```python
# Story generation with duplicate detection
cluster_hash = hashlib.md5(json.dumps(sorted(article_ids)).encode()).hexdigest()

# Check if exists
existing = session.query(Story).filter(Story.story_hash == cluster_hash).first()
if existing:
    skip  # Don't regenerate
```

### Why This Is Actually Good:
- Prevents wasted LLM calls (expensive)
- Prevents duplicate stories (good UX)
- Deterministic (predictable)

### Why This Feels Bad:
- User expects "Generate" to always generate
- No feedback about WHY nothing was generated
- No way to force regeneration

---

## Quick Fixes Needed

### 1. Better UI Feedback
```javascript
// In stories.js
if (result.stories_generated === 0) {
    showNotification(
        'No new stories generated. All article combinations already exist. ' +
        'Refresh feeds for new content or clear old stories.',
        'info'
    );
}
```

### 2. Add Force Regenerate Button
```html
<button onclick="forceRegenerateStories()">
    Force Regenerate (Ignore Duplicates)
</button>
```

### 3. Show Article Count
```javascript
// Before generating, show:
"Found 138 new articles. Generating stories..."
// After:
"0 new stories (3 existing stories cover all articles)"
```

---

## Files to Modify

1. `app/main.py` - Add `force_regenerate` parameter
2. `app/stories.py` - Skip duplicate check if force=True
3. `app/static/js/stories.js` - Better UI feedback
4. `app/templates/stories.html` - Add force regenerate button

---

## Success Criteria

User should:
1. ✅ Understand WHY no stories were generated
2. ✅ Be able to force regeneration if desired
3. ✅ See how many new articles are available
4. ✅ Have feeds refresh working properly
