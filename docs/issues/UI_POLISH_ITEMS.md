# UI Polish Items - Story-First Landing Page

**Date**: 2025-11-18  
**Context**: Post-implementation audit of Story-First UI (Issues #50-54)

---

## ✅ FIXED (Critical)

### 1. Supporting Articles Not Loading ⚠️ **CRITICAL BUG - FIXED**
**Status**: ✅ Fixed  
**Issue**: `get_story_by_id()` was returning empty list for supporting articles  
**Impact**: Story detail pages showed no supporting articles  
**Fix**: Updated `app/stories.py` lines 246-315 to properly query items table  
**Files**: `app/stories.py`

---

## 🎨 POLISH ITEMS (Minor)

### 1. Articles Page References (Low Priority)
**Status**: 📝 Needs Update  
**Issue**: `/articles` page (index.html) still has article-centric copy  
**Impact**: Minor - articles page is now secondary, but still accessible  
**Recommendation**: Update header/description to clarify it's a "legacy" view  
**Files**: `app/templates/index.html` (lines 3, 9-10)

```html
<!-- Current -->
<h1>Latest Articles</h1>
<p>Intelligently ranked news from your feeds</p>

<!-- Suggested -->
<h1>All Articles</h1>
<p>Browse individual articles (legacy view - try Stories for synthesized news)</p>
```

### 2. View Switching Not Implemented (Low Priority)
**Status**: 📝 TODO  
**Issue**: Skim/Detailed view toggle in articles page has no functionality  
**Impact**: Minor - just a visual toggle with no backend logic  
**Location**: `app/static/js/app.js` line 38  
**Recommendation**: Either implement or remove the toggle  
**Files**: `app/static/js/app.js`, `app/templates/index.html`

### 3. Version Number in Footer (Cosmetic)
**Status**: 📝 Needs Update  
**Issue**: Footer says "v0.5.1" but we're working on v0.5.0  
**Impact**: Cosmetic only  
**Recommendation**: Update to "v0.5.0" or "v0.5.0-dev"  
**Files**: `app/templates/base.html` line 99

### 4. Mobile Navigation (Enhancement)
**Status**: 📝 Not Implemented  
**Issue**: Mobile menu button exists but has no functionality  
**Impact**: Minor - mobile navigation doesn't work  
**Location**: `app/templates/base.html` lines 80-84  
**Recommendation**: Implement mobile menu dropdown or hide button  
**Priority**: P2 (Nice to have)

---

## ⚙️ FUTURE ENHANCEMENTS (Deferred)

### 1. Response Time Tracking
**Status**: 📝 TODO (Future)  
**Issue**: Feed health monitoring doesn't track response times  
**Location**: `app/main.py` line 459  
**Priority**: P2 (Future enhancement)  
**Milestone**: v0.6.0 or v0.7.0

### 2. LLM-Based Topic Classification
**Status**: 📝 TODO (Future)  
**Issue**: Currently using keyword-based classification  
**Location**: `app/ranking.py` line 418  
**Priority**: P2 (Future enhancement)  
**Milestone**: v0.6.0 (Intelligence enhancements)

---

## ✅ WORKING WELL (No Changes Needed)

1. **Story Landing Page** (`/stories`) - Clean, responsive, loads properly
2. **Story Detail Page** - Now shows supporting articles correctly
3. **Story Generation** - Manual trigger works, API endpoints functional
4. **Navigation** - Stories is default, Articles accessible at `/articles`
5. **Dark Mode** - Fully functional across all pages
6. **API Documentation** - Available at `/docs`
7. **Filters & Sorting** - All working on stories page

---

## 📋 RECOMMENDATIONS

### For Immediate Action (Before Next Issue)
- [x] Fix supporting articles bug (DONE)
- [ ] Update footer version to v0.5.0-dev
- [ ] Add breadcrumb or note to articles page clarifying it's a legacy view

### For GitHub Issues (Later)
Create GitHub issues for:
1. **Mobile navigation implementation** (P2, ~2 hours)
2. **Articles page skim/detail view** (P2, ~1 hour) - OR remove toggle
3. **Response time tracking for feeds** (P2, v0.6.0, ~3 hours)

### Not Needed
- LLM topic classification - defer to v0.6.0 epic

---

## 🎯 NEXT STEPS

1. ✅ Critical bug fixed (supporting articles)
2. Apply quick polish items (version, articles page note)
3. Create GitHub issues for deferred items
4. **READY TO MOVE TO NEXT ISSUE**: #48 (Scheduled Story Generation)

---

**Audit Completed**: 2025-11-18  
**Result**: 1 critical bug fixed, 3 minor polish items identified, UI ready for use

