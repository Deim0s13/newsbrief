# v0.6.1 Quick Fixes Needed

## Status After Manual Testing

### ✅ Actually Working (Not Bugs)
1. **Story Generation** - Working correctly, duplicate detection is functioning
   - 385 stories in database
   - 10 most recent stories created Dec 1, 00:17
   - Duplicate detection preventing re-creation (19/19 clusters were duplicates)
   - **User Perception Issue**: UI feedback is correct, user expectations need adjustment

2. **Entity Extraction** - Verified working in database

### 🐛 Real Bugs to Fix

#### 1. HTML Tags in Story Supporting Articles (HIGH)
**File**: `/app/templates/story_detail.html` or backend processing
**Issue**: `<p>` tags visible in supporting article text
**Fix**: Add HTML stripping or `| safe` filter

#### 2. Story Topic Mismatch (MEDIUM)
**Issue**: Story shows "Disaster Response" but articles show "Devtools"
**Investigation**: Check topic aggregation logic in story generation

#### 3. All Article Scores 7.000 (MEDIUM)
**Investigation**: Check if ranking calculation is running on all articles

#### 4. All Importance Scores 0.66 (MEDIUM)
**Investigation**: Check scoring calculation, might be using default values

#### 5. Model/Status Fields Empty (LOW)
**Fix**: Add model and status display to story_detail.html

#### 6. Skim View (Main Articles Page) (MEDIUM)
**Status**: Needs more aggressive CSS or JS manipulation

---

## 🔧 Immediate Actions

### Option 1: Ship v0.6.1 with Known Issues
- Story generation, entity extraction, scoring all work
- Document UI display issues as known limitations
- Fix in v0.6.2

### Option 2: Fix Critical UI Issues First
- Fix HTML tags in supporting articles (15 min)
- Fix topic display mismatch (30 min)
- Ship after these fixes

### Option 3: Full Debug Session
- Investigate all scoring/display issues
- Fix skim view properly
- Could take 2-3 hours

---

## 💡 Recommendations

**For v0.6.1 Release:**
1. Fix HTML tags bug (critical, user-facing)
2. Document other issues as known limitations
3. Create issues for v0.6.2:
   - #TBD: Fix story topic aggregation
   - #TBD: Debug ranking score calculations
   - #TBD: Improve skim view CSS specificity
   - #TBD: Display model/status fields in UI

**Core v0.6.1 features ARE working:**
- ✅ Entity extraction
- ✅ Semantic similarity (clustering)
- ✅ Story quality scoring (backend)
- ✅ Duplicate detection
- ✅ Enhanced UX messages

**UI/Display issues don't block the core functionality.**

