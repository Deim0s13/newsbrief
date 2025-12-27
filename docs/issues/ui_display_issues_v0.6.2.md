# 🎨 UI/Display Issues for v0.6.2

**Milestone**: v0.6.2 - Performance & Quality  
**Priority**: HIGH (user-facing)  
**Type**: Bug fixes and UI polish  
**Created**: 2025-12-01

---

## Summary

While v0.6.1 core intelligence features (entity extraction, semantic clustering, story scoring) are working correctly, several UI/display issues were discovered during manual testing that should be addressed in v0.6.2.

---

## 🐛 High Priority Issues

### Issue 1: HTML Tags Visible in Story Supporting Articles
**Severity**: HIGH  
**User Impact**: Poor readability, unprofessional appearance

**Description**: 
Supporting articles in story detail pages show raw HTML tags like `<p>blah</p>` instead of properly rendered or stripped text.

**Steps to Reproduce**:
1. Navigate to any story detail page
2. Scroll to "Supporting Articles" section
3. Observe HTML markup visible in article summaries

**Example**:
```
<p>The fire broke out at 2am in the apartment complex...</p>
```

**Expected**: 
Clean text without HTML markup, either:
- Rendered as HTML (if intentional formatting)
- Stripped to plain text

**Root Cause**: 
- Backend may be storing HTML in summary field
- Frontend missing `| safe` filter or HTML stripping
- Check: `app/templates/story_detail.html` supporting articles rendering

**Files to Check**:
- `app/templates/story_detail.html` (likely fix location)
- `app/stories.py` (story creation, article linking)
- `app/models.py` (summary field handling)

---

### Issue 2: Story Topic Mismatch with Supporting Articles ✅ FIXED (2025-12-24)
**Severity**: HIGH  
**User Impact**: Confusing, misleading categorization

**Status**: ✅ **FIXED** - Unified topic classification system implemented

**Root Cause**:
- Two competing classification systems: old keyword-only in feeds.py vs. ranking.py
- Non-tech articles incorrectly classified as tech topics (e.g., Gaza news → "chips-hardware")
- Topic display showed raw IDs instead of human-readable names

**Solution Implemented**:
1. Created unified `app/topics.py` with centralized topic classification
2. Expanded vocabulary: ai-ml, security, cloud-k8s, devtools, chips-hardware, **politics**, **business**, **science**, general
3. LLM-based classification (primary) with keyword fallback
4. Auto-migration runs on startup to reclassify existing articles
5. Updated all templates to display human-readable topic names

**New Topic Distribution** (after migration):
```
general: 1170, devtools: 291, politics: 159, chips-hardware: 121, 
science: 95, ai-ml: 74, business: 69, security: 36, cloud-k8s: 10
```

**Files Changed**:
- `app/topics.py` (NEW - unified classification service)
- `app/feeds.py` (uses unified service, removed duplicate code)
- `app/main.py` (migration hook)
- `app/templates/*.html` (human-readable topic display)

---

## ⚠️ Medium Priority Issues

### Issue 3: All Article Ranking Scores Show 7.000 ✅ CLOSED (2025-12-27)
**Severity**: MEDIUM  
**User Impact**: Cannot differentiate article quality

**Status**: ✅ **CLOSED** - Working as Intended (GitHub #78)

**Investigation Found**:
- Database has varied scores: 0.1 to 7.0 (average 3.66)
- Score distribution across 2,025 articles is healthy
- Top articles show 7.0 because they legitimately have highest scores
- Default sort (ranking DESC) surfaces these first

**Resolution**: 
The "all 7.000" observation came from viewing top-ranked articles which correctly have high scores. The ranking calculation is functioning correctly.

**Future Work**: Ranking improvements tracked in v0.8.0 milestone (GitHub #84)

---

### Issue 4: Story Importance Scores Broken - New Stories Hidden
**Severity**: HIGH (upgraded from MEDIUM)  
**User Impact**: New stories hidden from default view, users see stale content

**Description**: 
Story importance scores are severely broken:
- **Old stories (Dec 1)**: importance_score = 1.0 (maximum)
- **New stories (Dec 19)**: importance_score = 0.16-0.32 (very low)

Since the UI defaults to sorting by importance, **new stories are hidden** behind old stories. Users must manually change sort to "Most Recent" to see fresh content.

**Root Cause Investigation (2025-12-19)**:
```sql
-- Old stories have artificially high scores
SELECT id, importance_score, generated_at FROM stories ORDER BY importance_score DESC LIMIT 3;
-- 783 | 1.0 | 2025-12-01
-- 784 | 1.0 | 2025-12-01

-- New stories have very low scores  
SELECT id, importance_score, generated_at FROM stories ORDER BY generated_at DESC LIMIT 3;
-- 932 | 0.16 | 2025-12-19
-- 931 | 0.16 | 2025-12-19
```

**Expected**: 
Varied importance scores (0.0-1.0) based on:
- Article count (more articles = higher importance)
- Source quality (healthier feeds = higher importance)
- Entity richness (more entities = higher importance)

**Algorithm** (from v0.6.1):
```python
importance = 0.4 * article_score + 0.3 * source_score + 0.3 * entity_score
```

**Investigation Needed**:
1. Why do old stories have perfect 1.0 scores? (likely before scoring was implemented properly)
2. Why do new stories get such low scores (0.16)?
3. Should we normalize/recalculate all scores?
4. Consider changing default sort to "Most Recent" instead of "Importance"

**Workaround**: Change sort dropdown to "Most Recent" in the UI

**Database Query**:
```sql
SELECT 
    importance_score, 
    freshness_score, 
    quality_score, 
    article_count,
    COUNT(*) as count
FROM stories
GROUP BY 
    ROUND(importance_score, 2),
    ROUND(freshness_score, 2),
    ROUND(quality_score, 2),
    article_count
ORDER BY importance_score DESC;
```

---

### Issue 5: Skim View Not Fully Working (Main Articles Page)
**Severity**: MEDIUM  
**User Impact**: Feature not working as designed

**Description**: 
On the main Articles page (`/articles`), the "Skim View" toggle only reduces font size instead of creating truly compact cards with 2-line previews.

**Expected Behavior**:
- Compact cards with reduced padding (0.75rem instead of 1.5rem)
- Only 2 lines of text visible (line-clamp)
- Hidden bullet lists and headings
- More articles visible on screen

**Current Behavior**:
- Font size gets smaller ✅
- Card padding stays the same ❌
- Full content still visible ❌

**Note**: Skim view DOES work correctly within individual article detail pages.

**Root Cause**:
- Tailwind CSS (loaded from CDN) overriding custom CSS
- Inline `p-6` class has higher specificity than custom `.skim-view article` styles
- JavaScript attempted to apply inline styles but may not be working

**Attempted Fixes** (in v0.6.1):
- CSS with `!important` flags
- JavaScript applying inline styles
- Cache-busting parameter on CSS file

**Recommendation**: 
- Consider using Tailwind's `@layer` directives
- Or switch to utility classes in JavaScript
- Or build Tailwind locally instead of CDN

**Files**:
- `app/static/css/custom.css`
- `app/static/js/app.js`
- `app/templates/index.html`

---

## ⚠️ Medium Priority Issues (Continued)

### Issue 6: Filter Options Not Working
**Severity**: MEDIUM  
**User Impact**: Cannot filter articles or stories

**Description**: 
None of the filter options (topic filters, sorting options, etc.) are functioning on the Articles page.

**Steps to Reproduce**:
1. Navigate to Articles page
2. Try to select a topic filter (e.g., "AI/ML", "Cloud/K8s")
3. Observe: No filtering occurs, all articles still displayed
4. Try other filter/sort options
5. Observe: No change in displayed articles

**Expected**:
- Topic filter should show only articles matching selected topic
- Sort options should reorder articles
- Filters should persist across page loads

**Investigation Needed**:
- Check if JavaScript event listeners are attached
- Verify API endpoints for filtered queries
- Check if filter state is being managed correctly
- Test if this affects Stories page as well

**Files to Check**:
- `app/static/js/app.js` (filter event handlers)
- `app/static/js/stories.js` (if stories page affected)
- `app/main.py` (filter/sort API endpoints)
- `app/templates/index.html` (filter UI elements)

---

## ℹ️ Low Priority Issues

### Issue 7: Model and Status Fields Empty in Story Detail
**Severity**: LOW  
**User Impact**: Missing metadata display

**Description**: 
Story detail pages don't show the LLM model used or the story status, even though these are stored in the database.

**Expected**:
- Display: "Model: llama3.1:8b"
- Display: "Status: active"

**Database Verification**:
```sql
SELECT id, title, model, status
FROM stories
ORDER BY generated_at DESC
LIMIT 5;
```

**Fix**: Add display fields to `app/templates/story_detail.html`

---

## 📊 Performance Issues (Non-Blocking)

### Issue 8: Feed Refresh Takes 2.5 Minutes
**Severity**: LOW (acceptable for 22 feeds)  
**User Impact**: Longer wait time for feed refresh

**Current**: ~2.5 minutes for 22 feeds  
**Expected**: <1 minute (ideal)

**Notes**:
- May be acceptable depending on feed response times
- Could optimize with better parallelization
- Not blocking for v0.6.1

---

## ✅ Success Criteria for v0.6.2

- [ ] HTML tags stripped/rendered properly in supporting articles
- [ ] Story and article topics display correctly and consistently
- [ ] Article ranking scores show varied values
- [ ] Story importance scores show varied values (not all 0.66)
- [ ] Skim view creates compact cards on main articles page
- [ ] Model and status fields display in story detail
- [ ] (Optional) Feed refresh optimized to <90 seconds

---

## 📝 Recommended Approach

### Phase 1: Data Validation (Quick)
1. Query database to verify if scores are varied or actually all the same
2. Check if issue is calculation or display

### Phase 2: High Priority Fixes
1. Fix HTML tags in supporting articles (~15 min)
2. Fix topic mismatch (~30 min)

### Phase 3: Medium Priority Fixes
3. Debug ranking score calculation/display (~30 min)
4. Debug importance score calculation/display (~30 min)
5. Fix skim view CSS specificity (~45 min)

### Phase 4: Polish
6. Add model/status display (~10 min)
7. Profile and optimize feed refresh (~1-2 hours if needed)

**Estimated Total**: 3-4 hours for all fixes

---

## 🔗 Related Files

**Backend**:
- `app/stories.py` - Story generation, topic assignment
- `app/ranking.py` - Article ranking calculation
- `app/feeds.py` - Feed refresh logic

**Frontend**:
- `app/templates/story_detail.html` - Story display
- `app/templates/index.html` - Articles page
- `app/static/css/custom.css` - Skim view styles
- `app/static/js/app.js` - Skim view toggle

**Models**:
- `app/models.py` - Data validation and display models

---

## 📌 Labels

- `enhancement`: UI/UX improvements
- `bug`: Display/rendering issues  
- `v0.6.2`: Target for next minor release
- `good-first-issue`: Issues 1, 2, 6 are straightforward

---

## 🎯 Priority for v0.6.2

**MUST FIX**:
1. ~~HTML tags (HIGH - user-facing)~~ ✅ FIXED (2025-12-19)
2. ~~Topic mismatch (HIGH - data integrity)~~ ✅ FIXED (2025-12-24)
3. ~~Importance scores (HIGH - new stories hidden from default view)~~ ✅ FIXED (2025-12-27)

**SHOULD FIX**:
4. ~~Ranking scores (MEDIUM - functionality)~~ ✅ CLOSED (2025-12-27) - Working as Intended
5. Filter options not working (MEDIUM - functionality)

**NICE TO HAVE**:
6. Skim view (MEDIUM - UX feature)
7. Model/Status display (LOW - metadata)
8. Performance optimization (LOW - acceptable currently)

---

## 🔗 GitHub Issues

| Local # | GitHub # | Status |
|---------|----------|--------|
| #1 | - | ✅ Fixed |
| #2 | - | ✅ Fixed |
| #3 | #78 | ✅ Closed |
| #4 | #79 | ✅ Fixed |
| #5 | #80 | 📋 Backlog |
| #6 | #81 | 📋 Backlog |
| #7 | #82 | 📋 Backlog |
| #8 | #83 | 📋 Backlog |

