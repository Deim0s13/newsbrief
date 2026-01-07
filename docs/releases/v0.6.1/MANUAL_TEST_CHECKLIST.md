# v0.6.1 Manual Testing Checklist

**Version**: v0.6.1
**Branch**: `feature/enhanced-clustering`
**Date**: 2025-11-27

---

## Pre-Testing Setup

### 1. Environment Preparation
- ✅ Ensure Ollama is running (`ollama serve` or background process)
- ✅ Verify llama3.2:3b model is available (`ollama pull llama3.2:3b`)
- ✅ Check database has recent articles (fetch feeds if needed)
- ✅ Start the application (`uvicorn app.main:app --reload`)

### 2. Database Backup (Optional but Recommended)
```bash
cp data/newsbrief.db data/newsbrief_backup_pre_v0.6.1.db
```

---

## Feature Testing

### 🧪 Issue #40: Entity Extraction

**Goal**: Verify entities are extracted from articles and used in clustering

#### Test Steps:
1. ✅ Navigate to Stories page
2. ✅ Click "Generate Stories" with default settings
3. ✅ Wait for story generation to complete
4. ✅ Open database and verify `items` table:
   ```bash
   sqlite3 data/newsbrief.sqlite3 "SELECT id, title, entities_json, entities_extracted_at, entities_model FROM items WHERE entities_json IS NOT NULL LIMIT 5;"
   ```
5. ✅ Verify `entities_json` contains structured data with keys:
   - `companies`
   - `products`
   - `people`
   - `technologies`
   - `locations`
6. ✅ Verify `entities_model` is set (e.g., "llama3.2:3b")
7. ✅ Verify `entities_extracted_at` has a timestamp

#### Expected Results:
- ✅ Entities are extracted and stored in database
- ✅ Entity cache is populated
- ✅ No errors in logs during extraction
- ✅ Stories cluster based on entity overlap (not just keywords)

#### Validation Queries:
```bash
# Count articles with extracted entities
sqlite3 data/newsbrief.sqlite3 "SELECT COUNT(*) FROM items WHERE entities_json IS NOT NULL;"

# Sample entity data
sqlite3 data/newsbrief.sqlite3 "SELECT title, entities_json FROM items WHERE entities_json IS NOT NULL LIMIT 3;"
```

---

### 🧪 Issue #41: Semantic Similarity

**Goal**: Verify improved clustering with bigrams/trigrams and combined similarity

#### Test Steps:
1. ✅ Generate stories with tech-focused articles (AI, cloud, etc.)
2. ✅ Verify similar articles cluster together (e.g., "OpenAI GPT-4" + "OpenAI launches GPT-4")
3. ✅ Check that articles with shared entities but different keywords cluster correctly
4. ✅ Verify topic bonus works (same topic = higher similarity)

#### Test Scenarios:

**Scenario 1: Similar AI Articles**
- ✅ Find 2+ articles about the same AI topic (e.g., ChatGPT, Gemini)
- ✅ Verify they cluster into the same story
- ✅ Check story synthesis mentions key entities

**Scenario 2: Different Topics**
- ✅ Find articles about different topics (e.g., AI vs Hardware)
- ✅ Verify they do NOT cluster together
- ✅ Check each has its own story

**Scenario 3: Bigrams/Trigrams**
- ✅ Look for articles with phrases like "machine learning", "cloud computing"
- ✅ Verify these phrases are captured (not just individual words)
- ✅ Check clustering considers these multi-word terms

#### Expected Results:
- ✅ Better clustering quality than v0.5.x
- ✅ Fewer false positives (unrelated articles grouped)
- ✅ Fewer false negatives (related articles separated)
- ✅ Topic bonus increases similarity for same-topic articles

#### Logs to Check:
```bash
# Check for similarity calculations in logs
grep "similarity" /path/to/app.log
grep "entity_overlap" /path/to/app.log
```

---

### 🧪 Issue #43: Story Quality & Importance Scoring

**Goal**: Verify stories have importance, freshness, and quality scores

#### Test Steps:
1. ✅ Generate stories
2. ✅ Check `stories` table for new score columns:
   ```bash
   sqlite3 data/newsbrief.sqlite3 "SELECT id, title, importance_score, freshness_score, quality_score, generated_at FROM stories ORDER BY generated_at DESC LIMIT 10;"
   ```
3. ✅ Verify scores are in range `0.0 - 1.0`
4. ✅ Verify scores reflect:
   - **Importance**: More articles = higher score
   - **Freshness**: Newer articles = higher score
   - **Quality**: Better source health = higher score

#### Score Validation:

**High-Quality Story** (Expected: scores > 0.6)
- [ ] Find story with 5+ articles
- [ ] All articles < 12 hours old
- [ ] All from healthy feeds (health score > 80)
- [ ] Verify `importance_score` is high
- [ ] Verify `freshness_score` is high
- [ ] Verify `quality_score` is high

**Low-Quality Story** (Expected: scores < 0.4)
- [ ] Find story with 2-3 articles
- [ ] Articles > 24 hours old
- [ ] Verify scores are lower

#### Expected Results:
- ✅ All stories have calculated scores
- ✅ Scores reflect story characteristics accurately
- ✅ Scores can be used for ranking/filtering (future feature)

#### Validation Queries:
```bash
# Score distribution
sqlite3 data/newsbrief.sqlite3 "SELECT ROUND(importance_score, 1) as importance, ROUND(freshness_score, 1) as freshness, ROUND(quality_score, 1) as quality, COUNT(*) as count FROM stories GROUP BY ROUND(importance_score, 1), ROUND(freshness_score, 1), ROUND(quality_score, 1) ORDER BY importance DESC;"

# Top quality stories
sqlite3 data/newsbrief.sqlite3 "SELECT id, substr(title, 1, 60), importance_score, freshness_score, quality_score FROM stories ORDER BY quality_score DESC LIMIT 5;"
```

---

### 🧪 Issue #67: Improved 0-Stories UX

**Goal**: Verify helpful feedback messages when story generation produces no stories

#### Test Scenarios:

**Scenario 1: No Articles Found**
1. [ ] Set time window to 1 hour when no recent articles exist
2. [ ] Click "Generate Stories"
3. [ ] Verify message: "No new articles found in the specified time window..."

**Scenario 2: All Duplicates**
1. [ ] Generate stories with default settings
2. [ ] Immediately click "Generate Stories" again (same parameters)
3. [ ] Verify message: "All X story clusters were duplicates of existing stories..."

**Scenario 3: No Clusters Formed**
1. [ ] Set similarity threshold very high (e.g., 0.9)
2. [ ] Set min articles per story to 5+
3. [ ] Click "Generate Stories"
4. [ ] Verify message: "Found X articles, but no new story clusters were formed..."

**Scenario 4: Success**
1. [ ] Generate stories normally
2. [ ] Verify message: "Successfully generated X new stories!"
3. [ ] If duplicates skipped, verify: "(Y duplicates skipped)"

#### Expected Results:
- ✅ Clear, actionable messages for each scenario
- ✅ No generic "0 stories generated" message
- ✅ Users understand why no stories were created
- ✅ Messages suggest next steps (fetch feeds, adjust settings, etc.)

---

### 🧪 Issue #70: Skim/Detail View Toggle

**Goal**: Verify article view toggle works and persists

#### Test Steps:
1. [ ] Navigate to Articles page
2. [ ] Verify default view is "Detailed View"
3. [ ] Click "Switch to Skim View" button
4. [ ] Verify:
   - [ ] Article cards become compact (2-line preview)
   - [ ] More articles visible on screen
   - [ ] Button text changes to "Switch to Detailed View"
5. [ ] Refresh the page
6. [ ] Verify view preference persists (still in skim view)
7. [ ] Click "Switch to Detailed View"
8. [ ] Verify:
   - [ ] Article cards expand to full content
   - [ ] Button text changes to "Switch to Skim View"
9. [ ] Refresh the page
10. [ ] Verify view preference persists (back to detailed view)

#### Expected Results:
- ✅ Toggle button is visible and labeled correctly
- ✅ View changes immediately on click
- ✅ Preference persists across page reloads
- ✅ Skim view shows compact cards
- ✅ Detailed view shows full content

---

## Integration Testing

### End-to-End Workflow

1. [ ] **Fresh Start**
   - [ ] Clear database (optional, for clean test)
   - [ ] Fetch feeds (populate articles)
   - [ ] Verify articles appear in Articles page

2. [ ] **Story Generation**
   - [ ] Generate stories with default settings
   - [ ] Verify entities are extracted
   - [ ] Verify stories have quality scores
   - [ ] Verify helpful feedback message appears

3. [ ] **Story Review**
   - [ ] Open generated stories
   - [ ] Verify synthesis is coherent
   - [ ] Verify key points are relevant
   - [ ] Verify article count matches

4. [ ] **Caching & Performance**
   - [ ] Generate stories again (same articles)
   - [ ] Verify entity extraction uses cache (fast)
   - [ ] Check logs for "Using cached entities" messages

5. [ ] **View Toggle**
   - [ ] Switch to skim view on Articles page
   - [ ] Reload and verify persistence
   - [ ] Switch back to detailed view

---

## Performance Testing

### Story Generation Performance
- [ ] Record time to generate 5-10 stories
- [ ] Verify entity extraction doesn't slow generation significantly
- [ ] Check logs for timing information

### Database Performance
- [ ] Verify entity cache queries are fast
- [ ] Check database size after entity extraction
- [ ] Run VACUUM if needed

---

## Browser Testing

### Desktop Browsers
- [ ] Chrome/Chromium
- [ ] Firefox
- [ ] Safari (macOS)

### Mobile (Optional)
- [ ] iOS Safari
- [ ] Android Chrome

### Responsive Design
- [ ] Skim/Detail toggle works on mobile
- [ ] Story cards render correctly
- [ ] No layout issues

---

## Error Handling

### LLM Unavailable
1. [ ] Stop Ollama service
2. [ ] Try generating stories
3. [ ] Verify graceful fallback (no entities, basic clustering)
4. [ ] Verify no crashes or error 500s

### Invalid Data
1. [ ] Create article with empty title/summary
2. [ ] Try generating stories
3. [ ] Verify no crashes

---

## Regression Testing

Ensure existing features still work:

### Articles
- [ ] Fetch feeds works
- [ ] Articles display correctly
- [ ] Ranking scores show
- [ ] Topics display

### Stories
- [ ] Story list displays
- [ ] Story detail page works
- [ ] Story archival works
- [ ] Story deletion works

### Feeds
- [ ] Add feed works
- [ ] Edit feed works
- [ ] Delete feed works
- [ ] OPML import/export works

---

## Sign-Off

### Test Results Summary

**Date Tested**: _____________
**Tester**: _____________

#### Feature Completion
- [ ] Issue #40: Entity Extraction - PASS / FAIL
- [ ] Issue #41: Semantic Similarity - PASS / FAIL
- [ ] Issue #43: Story Scoring - PASS / FAIL
- [ ] Issue #67: UX Improvements - PASS / FAIL
- [ ] Issue #70: Skim/Detail Toggle - PASS / FAIL

#### Overall Assessment
- [ ] All critical features work as expected
- [ ] No regressions in existing functionality
- [ ] Performance is acceptable
- [ ] Ready for release

#### Issues Found (if any)
```
[List any issues discovered during testing]
```

#### Recommendations
- [ ] Proceed to release
- [ ] Fix issues first (list issue numbers)
- [ ] Additional testing needed (specify)

---

## Notes

- If Ollama is unavailable, entity extraction will be skipped (graceful fallback)
- Database changes are backward compatible (new columns have defaults)
- All new features are non-breaking changes
- Cache will build up gradually as stories are generated
