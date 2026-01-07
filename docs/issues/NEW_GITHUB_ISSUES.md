# New GitHub Issues - 2025-11-13

Issues identified during testing of story landing page and performance optimizations.

---

## Issue #1: Story Generation Returns 0 Stories (UX Improvement)

**Title**: Improve UX when story generation returns 0 new stories due to duplicates

**Labels**: `enhancement`, `ux`, `stories`
**Milestone**: v0.5.0 or v0.6.0
**Priority**: Medium

### Problem

When clicking "Generate Stories" in the UI, users get a success message but 0 stories are generated, with no explanation why. This happens when duplicate detection correctly identifies that all current article combinations already have stories.

**Current behavior**:
- User clicks "Generate Stories"
- System returns: `{"success": true, "stories_generated": 0}`
- UI shows: "Successfully generated 0 stories!"
- No explanation provided
- User confused why nothing happened

### Root Cause

Story generation uses deterministic clustering with duplicate detection:
```python
cluster_hash = hashlib.md5(json.dumps(sorted(article_ids)).encode()).hexdigest()
```

Same articles → same clusters → same story_hash → duplicate detected → skipped

**This is actually good behavior** (prevents wasted LLM calls, prevents duplicate stories), but the UX is poor.

### Steps to Reproduce

1. Generate stories from a set of articles
2. Wait some time (but < 24 hours)
3. Click "Generate Stories" again
4. Observe: 0 new stories generated with no explanation

### Current System State

From testing:
- 138 articles in last 24 hours
- 3 existing stories
- Duplicate detection working correctly
- All article combinations already covered by existing stories

### Proposed Solutions

#### Option A: Better UI Feedback (Quick Fix)
```javascript
// In stories.js
if (result.stories_generated === 0) {
    showNotification(
        'No new stories generated. All article combinations already exist. ' +
        'Refresh feeds for new content or archive old stories to regenerate.',
        'info'
    );
}
```

#### Option B: Add "Force Regenerate" Button
```html
<button onclick="forceRegenerateStories()">
    Force Regenerate (Ignore Duplicates)
</button>
```

API change:
```python
POST /stories/generate
{
    "time_window_hours": 24,
    "force_regenerate": true  // Skip duplicate check
}
```

#### Option C: Auto-Archive Old Stories (Recommended)
- Automatically archive stories older than 24 hours
- Only check duplicates against "active" stories
- Allows natural regeneration with fresh perspective
- Old stories still accessible in "Archived" view

#### Option D: Smart Refresh Indicator
Show stats BEFORE generating:
```
Found 138 articles in last 24 hours
3 existing stories cover these articles
Generate anyway? [Yes] [No]
```

### Implementation Files

- `app/static/js/stories.js` - UI feedback
- `app/templates/stories.html` - Force regenerate button
- `app/stories.py` - Skip duplicate check if force=True
- `app/main.py` - Add force_regenerate parameter

### Workaround (Current)

Users can manually clear old stories:
```bash
cd /Users/pleathen/Projects/newsbrief
echo "yes" | .venv/bin/python scripts/clear_stories.py
```

Or archive via SQL:
```sql
UPDATE stories SET status='archived' WHERE generated_at < datetime('now', '-24 hours');
```

### Related Issues

- Issue #48: Scheduled story generation (would solve this naturally)
- Issue #50: Story landing page UI (completed)

### Additional Context

This issue was discovered after implementing:
- Parallel LLM synthesis (commit a3f8eb7)
- Duplicate detection via story_hash
- Story landing page

The duplicate detection is working as designed and provides significant value (prevents expensive LLM calls). This is purely a UX improvement.

---

## Issue #2: Feed Refresh Returns HTTP 500 (SSL Permission Error)

**Title**: Feed refresh endpoint fails with SSL permission error

**Labels**: `bug`, `feeds`, `critical`
**Milestone**: v0.5.0
**Priority**: High

### Problem

The feed refresh functionality is broken. When clicking "Refresh Feeds" in the UI or calling POST /refresh, the server returns HTTP 500 Internal Server Error.

**Error**: `PermissionError: [Errno 1] Operation not permitted`

### Root Cause

httpx library is unable to load SSL certificates due to permission error:

```
File "httpx/_config.py", line 149, in load_ssl_context_verify
    context.load_verify_locations(cafile=cafile)
PermissionError: [Errno 1] Operation not permitted
```

This occurs when httpx tries to access system CA certificates for SSL/TLS verification.

### Steps to Reproduce

1. Open NewsBrief web UI at http://localhost:8787
2. Click "Refresh Feeds" button
3. Observe: HTTP 500 Internal Server Error

**OR** via API:
```bash
curl -X POST http://localhost:8787/refresh
# Returns: Internal Server Error
```

### Full Error Traceback

```
Traceback (most recent call last):
  File "app/feeds.py", line 613, in fetch_and_store
    with httpx.Client(
        timeout=HTTP_TIMEOUT, headers={"User-Agent": "newsbrief/0.1"}
    ) as client:
  ...
  File "httpx/_config.py", line 149, in load_ssl_context_verify
    context.load_verify_locations(cafile=cafile)
PermissionError: [Errno 1] Operation not permitted
```

### Environment

- Python: 3.13
- httpx: (version from requirements.txt)
- OS: macOS (darwin 25.2.0)
- Running: Local development server

### Impact

**Critical**: Users cannot fetch new articles from RSS feeds via UI
- Feed refresh completely broken
- No new articles = no new stories
- Manual CLI workaround required

### Possible Causes

1. **macOS Security**: Sandbox/permission restrictions on system certificate access
2. **Python 3.13 Change**: SSL certificate handling changed in Python 3.13
3. **httpx Configuration**: Missing verify=False or custom cert path
4. **Virtual Environment**: CA certificates not properly installed in venv

### Proposed Solutions

#### Option A: Disable SSL Verification (Quick Fix - Development Only)
```python
with httpx.Client(
    timeout=HTTP_TIMEOUT,
    headers={"User-Agent": "newsbrief/0.1"},
    verify=False  # WARNING: Development only!
) as client:
```

⚠️ **Not recommended for production**

#### Option B: Use certifi Package (Recommended)
```python
import certifi

with httpx.Client(
    timeout=HTTP_TIMEOUT,
    headers={"User-Agent": "newsbrief/0.1"},
    verify=certifi.where()  # Use bundled certificates
) as client:
```

Add to requirements.txt:
```
certifi>=2024.0.0
```

#### Option C: Install Certificates in venv
```bash
cd /Applications/Python\ 3.13/
./Install\ Certificates.command
```

#### Option D: Switch to requests Library
Replace httpx with requests (which handles certificates differently):
```python
import requests

response = requests.get(url, timeout=30, headers={"User-Agent": "newsbrief/0.1"})
```

### Recommended Solution

**Option B** - Use certifi package:
1. Most reliable across platforms
2. Doesn't disable security
3. Bundled certificates that work in venv
4. Simple implementation

### Files to Modify

- `app/feeds.py` - Add certifi for SSL verification
- `requirements.txt` - Add certifi dependency

### Workaround (Current)

Refresh feeds via command line:
```bash
cd /Users/pleathen/Projects/newsbrief

# May need to run with appropriate permissions
sudo .venv/bin/python -c "from app.feeds import fetch_and_store; fetch_and_store()"
```

Or fetch feeds manually and import.

### Testing

After fix, verify:
```bash
# Test feed refresh
curl -X POST http://localhost:8787/refresh

# Should return success with stats
```

### Related Issues

- Story generation (Issue #1) - Depends on fresh articles from feeds

### Additional Context

This issue was discovered during post-deployment testing of:
- Story landing page (Issue #50)
- Performance optimizations (Issue #66)

The feed refresh worked in previous versions, so this may be related to:
- Python version upgrade
- httpx library version
- macOS security changes

---

## Summary

| Issue | Type | Priority | Blocking |
|-------|------|----------|----------|
| #1: Story generation returns 0 | Enhancement | Medium | No |
| #2: Feed refresh HTTP 500 | Bug | High | Yes |

### Recommended Fix Order

1. **Issue #2 first** - Blocks ability to get new articles
2. **Issue #1 second** - UX improvement, has workaround

Both issues have clear solutions and should be straightforward to implement.

---

## Instructions

### Creating Issues on GitHub

1. Go to: https://github.com/Deim0s13/newsbrief/issues/new
2. Copy the issue content above (each issue separately)
3. Add appropriate labels and milestone
4. Assign to yourself or leave unassigned

### Labels to Create (if not exist)

- `enhancement` - Feature improvements
- `ux` - User experience issues
- `critical` - High priority bugs

### Milestones

- Add to **v0.5.0** if should be fixed before release
- Add to **v0.6.0** if can wait for next iteration
