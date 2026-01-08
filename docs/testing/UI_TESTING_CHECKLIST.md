# UI Testing Checklist - Story-First Landing Page

**Date**: 2025-11-18
**Context**: Testing changes for Story-First UI implementation

---

## ⚙️ Setup

```bash
# Start the application
cd /Users/pleathen/Projects/newsbrief
source .venv/bin/activate
uvicorn app.main:app --reload --port 8787

# Or with Docker/Podman
podman-compose up -d
```

---

## ✅ Critical Tests

### 1. Landing Page (/)
- [ ] Navigate to `http://localhost:8787/`
- [ ] Should show **Stories** page (not articles)
- [ ] Page title says "NewsBrief - Today's Stories"
- [ ] Navigation highlights "Stories" tab
- [ ] If no stories exist, shows empty state with "Generate Stories" button

### 2. Story Generation
- [ ] Click "Generate Stories" button
- [ ] Shows loading spinner and notification
- [ ] Wait for generation to complete (may take 2-5 minutes)
- [ ] Success notification appears
- [ ] Stories appear on page

### 3. Story Cards Display
- [ ] Story cards show:
  - [ ] Title
  - [ ] Synthesis preview (truncated)
  - [ ] First 2 key points
  - [ ] Topics (colored badges)
  - [ ] Article count
  - [ ] Importance/Freshness scores
  - [ ] Time generated
- [ ] Cards are clickable
- [ ] Hover effect works

### 4. Story Detail Page **CRITICAL - BUG FIX**
- [ ] Click on a story card
- [ ] Navigate to `/story/{id}` page
- [ ] Story details displayed:
  - [ ] Full title
  - [ ] Complete synthesis
  - [ ] All key points
  - [ ] "Why it matters" section
  - [ ] Topics and entities
- [ ] **Supporting Articles section appears** ⚠️ **BUG FIX VERIFICATION**
- [ ] Supporting articles list shows:
  - [ ] Article titles
  - [ ] Article summaries
  - [ ] Links to article detail
  - [ ] Links to original source
- [ ] "Back to Stories" breadcrumb works

### 5. Articles Page (/articles)
- [ ] Navigate to `http://localhost:8787/articles`
- [ ] Shows article list (old view)
- [ ] Page title says "NewsBrief - All Articles"
- [ ] Header says "All Articles" with link to Stories
- [ ] Navigation highlights "Articles" tab

### 6. Navigation
- [ ] Logo click returns to Stories (/)
- [ ] "Stories" tab → `/` (stories page)
- [ ] "Articles" tab → `/articles` (articles page)
- [ ] "Feed Management" tab works
- [ ] "Topics" tab works
- [ ] Search bar present (may not be wired up yet)

### 7. Footer
- [ ] Footer shows "v0.5.0" (not v0.5.1)
- [ ] API Documentation link works → `/docs`
- [ ] GitHub link present

---

## 🎨 Visual Tests

### Dark Mode
- [ ] Click dark mode toggle in nav
- [ ] All pages switch to dark theme
- [ ] Story cards readable in dark mode
- [ ] No white backgrounds flash

### Responsive Design
- [ ] Resize browser to mobile width (~375px)
- [ ] Story cards stack vertically
- [ ] Navigation collapses (mobile menu button visible)
- [ ] Content readable on small screens
- [ ] No horizontal scrolling

---

## 🔄 API Tests

### Story API Endpoints
```bash
# Test story generation (if not already done in UI)
curl -X POST http://localhost:8787/stories/generate \
  -H "Content-Type: application/json" \
  -d '{"time_window_hours": 24, "min_articles_per_story": 2}'

# List stories
curl http://localhost:8787/stories | jq .

# Get specific story with supporting articles
curl http://localhost:8787/stories/1 | jq .

# Check supporting_articles array is populated (not empty)
curl http://localhost:8787/stories/1 | jq '.supporting_articles | length'
# Should return a number > 0

# Get story stats
curl http://localhost:8787/stories/stats | jq .
```

---

## 🐛 Known Issues (Expected)

These are documented but not critical:

1. **Mobile menu button** - Visible but doesn't work (no dropdown)
2. **Articles page view toggle** - Skim/Detail buttons don't switch views
3. **Search bar** - May not be functional yet

These are documented in `UI_POLISH_ISSUES.json` for future fixes.

---

## ❌ What Should NOT Happen

- [ ] Stories page should **NOT** show empty supporting articles
- [ ] Story detail should **NOT** have zero supporting articles
- [ ] Landing page should **NOT** show articles list
- [ ] Navigation should **NOT** highlight wrong tab

---

## 📸 Screenshots (Optional)

If issues found, capture:
1. Landing page (stories view)
2. Story detail page with supporting articles
3. Any error messages
4. Browser console errors (F12 → Console)

---

## ✅ Success Criteria

**PASS** if:
- ✅ Landing page shows stories (not articles)
- ✅ Story generation works
- ✅ Story detail page shows supporting articles (BUG FIX)
- ✅ Navigation works correctly
- ✅ Footer shows v0.5.0
- ✅ No console errors

**Ready for next issue (#48 - Scheduled Generation)** when all critical tests pass.

---

**Testing Date**: _____________
**Tested By**: _____________
**Result**: [ ] PASS  [ ] FAIL
**Notes**:
