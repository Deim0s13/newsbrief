# GitHub Issues to Update - 2025-11-13

## ✅ Issues to Close

### Issue #50: Story-based landing page UI
**Status**: Complete ✅

**What was delivered**:
- Story landing page with filters and sorting
- Story detail page with supporting articles
- Responsive design with dark mode
- Loading states and empty states
- Navigation updated to make Stories primary

**Commit**: `a3f8eb7`

**Comment to add**:
```
✅ Completed in commit a3f8eb7

Delivered:
- Story landing page (stories.html) with card view
- Story detail page with full synthesis and supporting articles
- Filters: time window, status, sort order
- Responsive design with dark mode support
- Stories now primary view at `/`, articles moved to `/articles`

UI polish items tracked in docs/UI_IMPROVEMENTS_BACKLOG.md for future work.
```

---

### Issue #66: Performance optimization
**Status**: Complete ✅

**What was delivered**:
- Parallel LLM synthesis (ThreadPoolExecutor)
- Article data caching
- Batched database commits
- Duplicate detection
- Performance instrumentation

**Results**: 80% improvement (171s → 30s)

**Commit**: `a3f8eb7`

**Comment to add**:
```
✅ Completed in commit a3f8eb7

Performance Improvements:
- Parallel LLM synthesis: 3 concurrent workers (80% time reduction)
- Article data caching: Single query, eliminate redundancy
- Batched DB commits: 1 transaction vs 20+ commits
- Duplicate detection: Check story_hash before synthesis
- Performance logging: Detailed timing for monitoring

Results:
- Before: ~171 seconds
- After: ~30-40 seconds
- Improvement: 80% faster ✨

Details in docs/PERFORMANCE_OPTIMIZATIONS_IMPLEMENTED.md
```

---

## 📋 Project Board Updates

### Move to "Done" Column:
- [ ] Issue #50 (Story landing page UI)
- [ ] Issue #66 (Performance optimization)

### Update Milestone v0.5.0:
**Completed items**:
- Story landing page (Phase 5)
- Performance optimization
- Story API endpoints (previously completed)

**Remaining items**:
- #48: Scheduled story generation
- Other v0.5.0 issues

---

## 🔗 Quick Links

**GitHub Issues**:
- Issue #50: https://github.com/Deim0s13/newsbrief/issues/50
- Issue #66: https://github.com/Deim0s13/newsbrief/issues/66

**Project Board**:
- https://github.com/users/Deim0s13/projects/[YOUR_PROJECT_NUMBER]

**Milestone v0.5.0**:
- https://github.com/Deim0s13/newsbrief/milestone/1

---

## 📝 Instructions

1. **Close Issue #50**:
   - Go to issue page
   - Add the comment above
   - Click "Close issue"
   - Select reason: "Completed"

2. **Close Issue #66**:
   - Go to issue page
   - Add the comment above
   - Click "Close issue"
   - Select reason: "Completed"

3. **Update Project Board**:
   - Drag issues to "✅ Done" column
   - Or use automation if configured

4. **Update Milestone Progress**:
   - Check milestone page
   - Verify completed issues show as closed
   - Review remaining v0.5.0 work

