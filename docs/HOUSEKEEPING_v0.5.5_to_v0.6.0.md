# Housekeeping: v0.5.5 → v0.6.0 Transition

**Date**: November 18, 2025  
**Purpose**: Clean up and prepare for v0.6.0 development

---

## ✅ Items Already Clean

### 1. Git Status
- ✅ **Working tree clean** - No uncommitted changes
- ✅ **Branches synchronized** - main and dev are in sync
- ✅ **No stale branches** - Only main and dev exist (clean structure)

### 2. Release Status
- ✅ **v0.5.5 published** - GitHub Release is live
- ✅ **Tag pushed** - v0.5.5 tag is on GitHub
- ✅ **CI/CD green** - All checks passing

### 3. Documentation
- ✅ **All docs updated** - README, API docs, release notes
- ✅ **Technical debt tracked** - `docs/TECHNICAL_DEBT_v0.6.0.md`
- ✅ **Branching strategy documented** - Ready for feature branches

---

## 🧹 Housekeeping Tasks

### 1. Clean Up Python Cache Files

**Status**: ⚠️ Minor cleanup needed

**What**: `__pycache__` directories exist in `app/` (not in .gitignore)

**Action**:
```bash
# Remove Python cache
find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true

# Verify cleanup
git status
```

**Why**: Keep repo clean, these are regenerated automatically

---

### 2. Clean Up Empty/Unnecessary Directories

**Status**: ⚠️ Minor cleanup needed

**What**: `newsbrief-starter-fresh/` directory is empty

**Action**:
```bash
# Remove if truly empty
rmdir newsbrief-starter-fresh/

# Or investigate if it should contain something
ls -la newsbrief-starter-fresh/
```

**Why**: Avoid confusion with empty directories

---

### 3. Consolidate Database Files

**Status**: ⚠️ Minor issue

**What**: Two database files exist:
- `data/newsbrief.db` (0 bytes - empty)
- `data/newsbrief.sqlite3` (11 MB - the real one)

**Action**:
```bash
# Remove empty database file
rm data/newsbrief.db

# Verify only one DB exists
ls -lh data/*.db data/*.sqlite3
```

**Why**: Avoid confusion about which database is active

---

### 4. Update .gitignore for __pycache__

**Status**: ✅ Already handled

**What**: `.gitignore` already includes `__pycache__/` pattern

**Verification**: `__pycache__` directories won't be committed

---

### 5. Verify Milestone Status

**Status**: ✅ Appears clean

**What**: Check if any issues remain open in v0.5.5 milestone

**Action** (if needed):
```bash
# Check milestone status
gh issue list --milestone "v0.5.5 - Story Architecture" --state open

# Close any stragglers
gh issue close <issue-number> --comment "✅ Completed in v0.5.5 release"
```

**Result**: No open issues found (clean!)

---

### 6. Archive Session Documentation

**Status**: ✅ Already organized

**What**: Multiple session summaries and cleanup docs exist

**Current Structure**:
```
docs/
├── SESSION_SUMMARY_2025-11-13.md
├── SESSION_SUMMARY_2025-11-18.md
├── V0.5.0_CLEANUP_STATUS.md
├── V0.5.0_CLEANUP_SUMMARY.md
├── V0.5.5_RELEASE_COMPLETE.md
├── V0.5.5_FINAL_RELEASE_SUMMARY.md
└── archive/  (for older docs)
```

**Optional**: Move session docs to archive if desired, but current organization is fine

---

### 7. Review TODO/FIXME Comments

**Status**: ⚠️ 27 TODOs found across 15 files

**What**: TODO/FIXME comments in code

**Files with TODOs**:
- `app/feeds.py` (2)
- `app/ranking.py` (2)
- `app/main.py` (1)
- `docs/` (various documentation TODOs)
- `scripts/` (6 in shell scripts)

**Action** (for v0.6.0):
- Review each TODO
- Create GitHub issues for important ones
- Remove completed TODOs
- Mark low-priority ones clearly

**Not Urgent**: These can be addressed during v0.6.0 development

---

### 8. Clean Up Development Scripts

**Status**: ✅ Organized

**What**: Multiple scripts in `scripts/` directory

**Current Scripts**:
- Import/setup scripts (keep)
- Test scripts (keep)
- Fix/cleanup scripts (keep for reference)

**Action**: None needed, all scripts are useful

---

### 9. Verify Container Registry

**Status**: ✅ Assumed clean (CI/CD builds automatically)

**What**: Ensure old container images are tagged correctly

**Container Tags Should Be**:
- `v0.5.5` - Latest release
- `latest` - Points to v0.5.5
- `dev` - Development builds
- `sha-XXXXXXX` - Commit-specific builds

**Verification**: GitHub Actions handles this automatically

---

### 10. Update Issue Templates (Optional)

**Status**: ℹ️ Optional improvement

**What**: Create issue templates for v0.6.0

**Suggestion**:
```
.github/ISSUE_TEMPLATE/
├── bug_report.md
├── feature_request.md
└── technical_debt.md
```

**Priority**: Low - Can be added when v0.6.0 work begins

---

## 📋 Recommended Actions (In Order)

### Critical (Do Now):
1. **Remove empty database file**: `rm data/newsbrief.db`
2. **Clean Python cache**: `find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} +`
3. **Remove empty directory**: `rmdir newsbrief-starter-fresh/` (if truly empty)

### Important (Before v0.6.0 Work):
4. **Review TODOs**: Scan code TODOs and create issues for important ones
5. **Verify milestone**: Ensure all v0.5.5 issues are closed

### Nice to Have:
6. **Archive old session docs**: Move to `docs/archive/sessions/`
7. **Create issue templates**: Add templates for common issue types
8. **Update contributing guide**: Document development workflow

---

## 🎯 Quick Cleanup Commands

Run these to clean up the identified items:

```bash
cd /Users/pleathen/Projects/newsbrief

# 1. Remove empty database
rm -f data/newsbrief.db

# 2. Clean Python cache (already gitignored)
find . -type d -name "__pycache__" -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true

# 3. Remove empty directory
rmdir newsbrief-starter-fresh/ 2>/dev/null || true

# 4. Verify clean state
git status

# 5. If all clean, nothing to commit
# If files were tracked, commit the cleanup:
# git add -A
# git commit -m "chore: housekeeping cleanup for v0.6.0"
# git push origin main
```

---

## ✅ Post-Cleanup Verification

After running cleanup commands:

```bash
# 1. Verify git status
git status  # Should be clean

# 2. Verify only one database
ls -lh data/*.db data/*.sqlite3  # Should only see newsbrief.sqlite3

# 3. Verify no pycache in git
git ls-files | grep __pycache__  # Should return nothing

# 4. Verify branches
git branch -a  # Should show main, dev, and their remotes

# 5. Verify CI/CD still green
# Check GitHub Actions tab
```

---

## 📊 Summary

### Current State:
- ✅ Git: Clean working tree
- ✅ Releases: v0.5.5 published
- ✅ CI/CD: All green
- ✅ Documentation: Complete
- ⚠️ Minor cleanup: Empty files, cache directories

### After Cleanup:
- ✅ No empty database files
- ✅ No Python cache directories
- ✅ No empty directories
- ✅ Clean git status
- ✅ Ready for v0.6.0 development

### Estimated Time: 2-3 minutes

---

## 🚀 Ready for v0.6.0

Once housekeeping is complete:

1. **Switch to dev branch**: `git checkout dev`
2. **Create feature branch**: `git checkout -b feature/issue-XX-description`
3. **Begin v0.6.0 work**: Follow `docs/TECHNICAL_DEBT_v0.6.0.md`
4. **Follow branching strategy**: `docs/BRANCHING_STRATEGY.md`

---

**Status**: Housekeeping tasks identified and documented  
**Action**: Run cleanup commands above  
**Next**: Ready for v0.6.0 development! 🎉

