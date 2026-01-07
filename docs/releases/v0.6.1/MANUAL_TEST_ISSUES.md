# v0.6.1 Manual Testing Issues

**Date**: 2025-11-28
**Tester**: User
**Branch**: `feature/enhanced-clustering`

---

## 🐛 Critical Issues (Blocking Release)

### Issue 1: Story Generation Not Working / Not Updating
**Severity**: CRITICAL
**Description**: Story generation takes 5+ minutes but doesn't create new stories or update the UI. Old stories remain visible.

**Steps to Reproduce**:
1. Click "Generate Stories"
2. Wait 5+ minutes
3. No new stories appear
4. Old stories still shown

**Expected**: New stories should be generated and displayed within reasonable time (<1 minute)

**Investigation Needed**:
- Check for errors in terminal/logs during generation
- Verify database writes are happening
- Check if stories are created but UI not refreshing
- Entity extraction might be causing timeout

---

### Issue 2: HTML Tags Visible in Story Supporting Articles
**Severity**: HIGH
**Description**: Supporting articles in stories show raw HTML tags like `<p>blah</p>` instead of plain text.

**Steps to Reproduce**:
1. Open any story detail page
2. Look at supporting articles section
3. HTML tags are visible in the text

**Expected**: Clean text without HTML markup

**Root Cause**: Likely missing `| safe` filter or need to strip HTML in backend

---

### Issue 3: Story Topic Mismatch with Supporting Articles
**Severity**: HIGH
**Description**: Story shows one topic (e.g., "Disaster Response") but all supporting articles are labeled with a different topic (e.g., "Devtools")

**Example**:
- Story: "A devastating fire broke out in Hong Kong..."
- Story Topic Badge: "Disaster Response and Construction Safety"
- Supporting Articles: All labeled "Devtools"

**Expected**: Story topic should match or reflect the topics of its supporting articles

**Investigation Needed**:
- Check how story topics are assigned
- Verify article topics are correct
- May need to aggregate article topics for story

---

## ⚠️ High Priority Issues

### Issue 4: All Articles Have Score 7.000
**Severity**: MEDIUM
**Description**: All articles show identical ranking score of 7.000, suggesting default values or calculation issue.

**Expected**: Articles should have varied ranking scores based on their characteristics

**Investigation Needed**:
- Check if ranking calculation is running
- Verify database has correct scores
- Check if UI is displaying wrong value

---

### Issue 5: Skim View Not Working Properly
**Severity**: MEDIUM
**Description**: Skim view on main Articles page only reduces font size, doesn't create compact 2-line preview cards.

**Expected**:
- Compact cards with less padding
- Only 2 lines of text visible
- Hidden bullet lists and headings

**Note**: Skim view appears to work correctly within individual articles

**Investigation Needed**:
- Check CSS specificity issues with Tailwind
- Verify JavaScript is applying classes correctly
- May need stronger CSS overrides

---

### Issue 6: All Story Importance Scores at 66%
**Severity**: MEDIUM
**Description**: All stories show identical importance score of 66% (0.66)

**Expected**: Stories should have varied importance scores (0.0-1.0) based on:
- Article count
- Source quality
- Entity richness

**Investigation Needed**:
- Check if scoring calculation is working
- Verify default values aren't being used
- Check database for score variations

---

### Issue 7: Model and Status Fields Empty
**Severity**: LOW
**Description**: Model and Status fields in story detail don't show any values

**Expected**:
- Model: Should show LLM model used (e.g., "llama3.1:8b")
- Status: Should show "active" or other status

**Investigation Needed**:
- Check if fields are populated in database
- Verify UI template is displaying these fields

---

## 📊 Performance Issues

### Issue 8: Feed Refresh Takes Too Long
**Severity**: MEDIUM
**Description**: Refreshing all feeds takes approximately 2.5 minutes

**Expected**: Should complete in <1 minute for 22 feeds

**Notes**:
- May be acceptable depending on feed count and content
- Could be optimized with better parallelization
- Not blocking for v0.6.1 but should track for v0.6.2

---

## ✅ Working Features

- Entity extraction (verified in database)
- Story quality scores (stored in database, even if all same value)
- Database schema updates
- Skim/Detail toggle (works within individual articles)

---

## 🔍 Next Steps

### Immediate (Blocking)
1. **Fix Story Generation** - Most critical issue
2. **Fix HTML Tags in Supporting Articles** - User-facing bug
3. **Fix Topic Mismatch** - Data integrity issue

### High Priority
4. **Debug Ranking Scores** - All showing 7.000
5. **Fix Main Articles Skim View** - UX feature not working
6. **Debug Importance Scores** - All showing 0.66

### Medium Priority
7. **Add Model/Status to UI** - Missing display fields
8. **Investigate Performance** - 2.5min feed refresh, 5min story gen

---

## 📝 Testing Status

| Feature | Status | Notes |
|---------|--------|-------|
| Entity Extraction (DB) | ✅ PASS | Verified in database |
| Story Quality Scores (DB) | ✅ PASS | Scores in database |
| Story Generation | ❌ FAIL | Not creating new stories |
| Story UI Display | ❌ FAIL | HTML tags visible, topic mismatch |
| Article Ranking | ⚠️ ISSUE | All scores 7.000 |
| Skim View (Articles Page) | ❌ FAIL | Only font size changes |
| Skim View (Article Detail) | ✅ PASS | Works correctly |
| Feed Refresh | ⚠️ SLOW | 2.5 minutes |

---

## 🔧 Recommended Actions

1. **Story Generation Debug Session**
   - Check terminal logs during generation
   - Run story generation via API with detailed logging
   - Verify entity extraction isn't causing timeout
   - Check database for partial story creation

2. **UI Fixes**
   - Strip HTML from supporting article summaries
   - Fix story topic assignment logic
   - Display model and status fields

3. **Data Validation**
   - Query database for score distribution
   - Verify ranking and importance calculations are running
   - Check if default values are being used

4. **Skim View**
   - Add more aggressive CSS with higher specificity
   - Consider using JavaScript to manipulate DOM directly
   - Test with different article structures
