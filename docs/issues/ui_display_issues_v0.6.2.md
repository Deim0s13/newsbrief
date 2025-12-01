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

### Issue 2: Story Topic Mismatch with Supporting Articles
**Severity**: HIGH  
**User Impact**: Confusing, misleading categorization

**Description**: 
Story shows one topic badge (e.g., "Disaster Response") but ALL supporting articles display a different topic (e.g., "Devtools").

**Example**:
- **Story**: "A devastating fire broke out in Hong Kong..."
- **Story Topic**: "Disaster Response and Construction Safety"
- **Article 1 Topic**: "Devtools" ❌
- **Article 2 Topic**: "Devtools" ❌
- **Article 3 Topic**: "Devtools" ❌

**Expected**:
- Story topic should aggregate/reflect topics of supporting articles
- Articles should show their actual classified topics
- Consistency between story and article topics

**Investigation Needed**:
1. How are story topics assigned? (from synthesis, from articles, or hardcoded?)
2. Are article topics correctly stored in database?
3. Is the UI displaying wrong field (e.g., showing story topic instead of article topic)?

**Database Queries**:
```sql
-- Check article topics for a story
SELECT i.id, i.title, i.topic, sa.story_id
FROM items i
JOIN story_articles sa ON i.id = sa.article_id
WHERE sa.story_id = 769;  -- Example story ID

-- Check story topics
SELECT id, title, topics_json
FROM stories
WHERE id = 769;
```

**Files to Check**:
- `app/stories.py` (topic assignment logic)
- `app/templates/story_detail.html` (topic display)
- `app/ranking.py` (topic classification for articles)

---

## ⚠️ Medium Priority Issues

### Issue 3: All Article Ranking Scores Show 7.000
**Severity**: MEDIUM  
**User Impact**: Cannot differentiate article quality

**Description**: 
All articles display identical ranking score of 7.000, suggesting default values or calculation not running.

**Expected**: 
Varied scores based on article characteristics (0.0-10.0 scale)

**Investigation**:
- Check if ranking calculation is running during feed refresh
- Verify database has actual varied scores
- Check if UI is rounding/defaulting to 7.0

**Database Query**:
```sql
SELECT ranking_score, COUNT(*) as count
FROM items
GROUP BY ranking_score
ORDER BY ranking_score DESC;
```

---

### Issue 4: All Story Importance Scores Show ~0.66
**Severity**: MEDIUM  
**User Impact**: Cannot differentiate story importance

**Description**: 
All stories show nearly identical importance scores around 0.66 (66%), despite varying article counts and characteristics.

**Expected**: 
Varied importance scores (0.0-1.0) based on:
- Article count (more articles = higher importance)
- Source quality (healthier feeds = higher importance)
- Entity richness (more entities = higher importance)

**Algorithm** (from v0.6.1):
```python
importance = 0.4 * article_score + 0.3 * source_score + 0.3 * entity_score
```

**Investigation**:
- Are all stories actually getting similar scores, or is it a display issue?
- Is the scoring calculation working correctly?
- Are default values being used?

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

## ℹ️ Low Priority Issues

### Issue 6: Model and Status Fields Empty in Story Detail
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

### Issue 7: Feed Refresh Takes 2.5 Minutes
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
1. HTML tags (HIGH - user-facing)
2. Topic mismatch (HIGH - data integrity)

**SHOULD FIX**:
3. Ranking scores (MEDIUM - functionality)
4. Importance scores (MEDIUM - functionality)

**NICE TO HAVE**:
5. Skim view (MEDIUM - UX feature)
6. Model/Status display (LOW - metadata)
7. Performance optimization (LOW - acceptable currently)

