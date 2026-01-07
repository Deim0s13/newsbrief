# Documentation Reorganization Plan

**Date**: November 18, 2025
**Purpose**: Restructure docs/ folder for better organization

---

## 📊 Current State (39+ files in docs/)

### Current Structure:
```
docs/
├── adr/                    # Architecture Decision Records
├── archive/                # Old documentation
├── (37 markdown files)     # Flat structure - hard to navigate
└── (2 JSON files)          # Issue/polish data
```

---

## 🎯 Proposed New Structure

```
docs/
├── README.md                          # Guide to documentation structure
│
├── adr/                               # Architecture Decision Records (keep)
│   ├── 0001-architecture.md
│   └── 0002-story-based-aggregation.md
│
├── user-guide/                        # User-facing documentation
│   ├── README.md                      # User guide index
│   ├── QUICK-START.md
│   ├── API.md
│   └── MIGRATION_v0.5.0.md
│
├── development/                       # Developer documentation
│   ├── README.md                      # Dev guide index
│   ├── DEVELOPMENT.md
│   ├── CI-CD.md
│   ├── BRANCHING_STRATEGY.md
│   └── TECHNICAL_DEBT_v0.6.0.md
│
├── project-management/                # Project tracking
│   ├── README.md                      # PM docs index
│   ├── GITHUB_PROJECT_BOARD_SETUP.md
│   ├── backlog.md
│   └── IMPLEMENTATION_PLAN.md
│
├── releases/                          # Release documentation
│   ├── README.md                      # Releases index
│   ├── v0.5.5/
│   │   ├── RELEASE_v0.5.5.md
│   │   ├── GITHUB_RELEASE_v0.5.5.md
│   │   ├── V0.5.5_FINAL_RELEASE_SUMMARY.md
│   │   ├── V0.5.5_RELEASE_COMPLETE.md
│   │   ├── MYPY_STATUS_v0.5.5.md
│   │   ├── V0.5.0_CLEANUP_STATUS.md
│   │   └── V0.5.0_CLEANUP_SUMMARY.md
│   └── archive/
│       └── (older release docs)
│
├── sessions/                          # Development session notes
│   ├── README.md                      # Sessions index
│   ├── 2025-11-13-session-summary.md
│   └── 2025-11-18-session-summary.md
│
├── planning/                          # Planning and analysis
│   ├── README.md                      # Planning docs index
│   ├── STORY_ARCHITECTURE_BACKLOG.md
│   ├── UI_IMPROVEMENTS_BACKLOG.md
│   ├── PERFORMANCE_ANALYSIS.md
│   ├── PERFORMANCE_OPTIMIZATION.md
│   └── PERFORMANCE_OPTIMIZATIONS_IMPLEMENTED.md
│
├── testing/                           # Testing documentation
│   ├── README.md                      # Testing docs index
│   ├── UI_TESTING_CHECKLIST.md
│   ├── TEST_RESULTS_2025-11-13.md
│   └── STORY_API_TESTING_SUMMARY.md
│
├── issues/                            # Issue tracking data
│   ├── README.md                      # Issue docs index
│   ├── UI_POLISH_ITEMS.md
│   ├── UI_POLISH_ISSUES.json
│   ├── GITHUB_ISSUES_TO_CLOSE.md
│   ├── ISSUES_FOUND_2025-11-13.md
│   └── NEW_GITHUB_ISSUES.md
│
├── archive/                           # Archived/obsolete docs
│   ├── README.md                      # Archive index
│   ├── v0.4.0-plan.md
│   ├── PROJECT_MANAGEMENT_SETUP.md
│   ├── DOCUMENTATION_AUDIT.md
│   └── (other archived docs)
│
└── HOUSEKEEPING_v0.5.5_to_v0.6.0.md  # Latest housekeeping doc (root)
```

---

## 📁 Categorization of Current Files

### 1. **User-Facing Documentation** → `user-guide/`
- `API.md` - API reference
- `QUICK-START.md` - Quick start guide
- `MIGRATION_v0.5.0.md` - Migration guide

### 2. **Developer Documentation** → `development/`
- `DEVELOPMENT.md` - Development setup
- `CI-CD.md` - CI/CD pipeline docs
- `BRANCHING_STRATEGY.md` - Git workflow
- `TECHNICAL_DEBT_v0.6.0.md` - Technical debt tracking

### 3. **Project Management** → `project-management/`
- `GITHUB_PROJECT_BOARD_SETUP.md` - Project board setup
- `backlog.md` - Backlog items
- `IMPLEMENTATION_PLAN.md` - Implementation plan

### 4. **Release Documentation** → `releases/v0.5.5/`
- `RELEASE_v0.5.5.md` - Release notes
- `GITHUB_RELEASE_v0.5.5.md` - GitHub release guide
- `V0.5.5_FINAL_RELEASE_SUMMARY.md` - Final summary
- `V0.5.5_RELEASE_COMPLETE.md` - Completion status
- `MYPY_STATUS_v0.5.5.md` - Mypy status
- `V0.5.0_CLEANUP_STATUS.md` - Cleanup status
- `V0.5.0_CLEANUP_SUMMARY.md` - Cleanup summary

### 5. **Session Notes** → `sessions/`
- `SESSION_SUMMARY_2025-11-13.md` → `2025-11-13-session-summary.md`
- `SESSION_SUMMARY_2025-11-18.md` → `2025-11-18-session-summary.md`

### 6. **Planning & Analysis** → `planning/`
- `STORY_ARCHITECTURE_BACKLOG.md` - Story backlog
- `UI_IMPROVEMENTS_BACKLOG.md` - UI backlog
- `PERFORMANCE_ANALYSIS.md` - Performance analysis
- `PERFORMANCE_OPTIMIZATION.md` - Optimization plan
- `PERFORMANCE_OPTIMIZATIONS_IMPLEMENTED.md` - Implemented optimizations

### 7. **Testing Documentation** → `testing/`
- `UI_TESTING_CHECKLIST.md` - UI test checklist
- `TEST_RESULTS_2025-11-13.md` - Test results
- `STORY_API_TESTING_SUMMARY.md` - API test summary

### 8. **Issue Tracking** → `issues/`
- `UI_POLISH_ITEMS.md` - Polish items list
- `UI_POLISH_ISSUES.json` - Polish issues data
- `GITHUB_ISSUES_TO_CLOSE.md` - Issues to close
- `ISSUES_FOUND_2025-11-13.md` - Found issues
- `NEW_GITHUB_ISSUES.md` - New issues

### 9. **Keep in Root**
- `HOUSEKEEPING_v0.5.5_to_v0.6.0.md` - Current housekeeping (keep visible)

### 10. **Archive** → `archive/` (move from current location)
- Already archived items in `archive/` subdirectory

---

## 🔄 Migration Commands

### Step 1: Create New Directory Structure
```bash
cd /Users/pleathen/Projects/newsbrief/docs

# Create new directories
mkdir -p user-guide
mkdir -p development
mkdir -p project-management
mkdir -p releases/v0.5.5
mkdir -p sessions
mkdir -p planning
mkdir -p testing
mkdir -p issues
```

### Step 2: Move Files to New Locations

**User Guide:**
```bash
git mv API.md user-guide/
git mv QUICK-START.md user-guide/
git mv MIGRATION_v0.5.0.md user-guide/
```

**Development:**
```bash
git mv DEVELOPMENT.md development/
git mv CI-CD.md development/
git mv BRANCHING_STRATEGY.md development/
git mv TECHNICAL_DEBT_v0.6.0.md development/
```

**Project Management:**
```bash
git mv GITHUB_PROJECT_BOARD_SETUP.md project-management/
git mv backlog.md project-management/
git mv IMPLEMENTATION_PLAN.md project-management/
```

**Releases:**
```bash
git mv RELEASE_v0.5.5.md releases/v0.5.5/
git mv GITHUB_RELEASE_v0.5.5.md releases/v0.5.5/
git mv V0.5.5_FINAL_RELEASE_SUMMARY.md releases/v0.5.5/
git mv V0.5.5_RELEASE_COMPLETE.md releases/v0.5.5/
git mv MYPY_STATUS_v0.5.5.md releases/v0.5.5/
git mv V0.5.0_CLEANUP_STATUS.md releases/v0.5.5/
git mv V0.5.0_CLEANUP_SUMMARY.md releases/v0.5.5/
```

**Sessions:**
```bash
git mv SESSION_SUMMARY_2025-11-13.md sessions/2025-11-13-session-summary.md
git mv SESSION_SUMMARY_2025-11-18.md sessions/2025-11-18-session-summary.md
```

**Planning:**
```bash
git mv STORY_ARCHITECTURE_BACKLOG.md planning/
git mv UI_IMPROVEMENTS_BACKLOG.md planning/
git mv PERFORMANCE_ANALYSIS.md planning/
git mv PERFORMANCE_OPTIMIZATION.md planning/
git mv PERFORMANCE_OPTIMIZATIONS_IMPLEMENTED.md planning/
```

**Testing:**
```bash
git mv UI_TESTING_CHECKLIST.md testing/
git mv TEST_RESULTS_2025-11-13.md testing/
git mv STORY_API_TESTING_SUMMARY.md testing/
```

**Issues:**
```bash
git mv UI_POLISH_ITEMS.md issues/
git mv UI_POLISH_ISSUES.json issues/
git mv GITHUB_ISSUES_TO_CLOSE.md issues/
git mv ISSUES_FOUND_2025-11-13.md issues/
git mv NEW_GITHUB_ISSUES.md issues/
```

### Step 3: Create README Files for Each Directory

Each directory should have a README.md explaining its contents.

---

## 📝 Benefits of New Structure

### Before:
- ❌ 39 files in flat structure
- ❌ Hard to find specific documentation
- ❌ No clear organization
- ❌ Mix of current and archived content

### After:
- ✅ Organized by purpose/category
- ✅ Easy to navigate
- ✅ Clear separation of concerns
- ✅ Each category has index/README
- ✅ Release docs grouped by version
- ✅ Session notes chronologically organized

---

## 🎯 Implementation Plan

### Phase 1: Structure Creation (5 minutes)
1. Create all new directories
2. Create README.md for each directory

### Phase 2: File Migration (10 minutes)
3. Move files using `git mv` commands
4. Verify no broken links

### Phase 3: Verification (5 minutes)
5. Verify all files moved correctly
6. Check git status
7. Test that docs are still accessible

### Phase 4: Commit
8. Single commit: "docs: reorganize documentation structure"
9. Review before pushing

---

## ⚠️ Considerations

### Links to Update:
- README.md in project root may reference docs/
- Other files may link to moved documentation
- GitHub wiki/issues may reference doc paths

### Search Required:
```bash
# Find all markdown files that reference docs/
grep -r "docs/" README.md --include="*.md"

# Check for broken links after move
find . -name "*.md" -exec grep -l "\[.*\](docs/" {} \;
```

---

## 🤔 Questions for Review

1. **Naming Convention**: Use `kebab-case` or `PascalCase` for directories?
   - Proposed: `kebab-case` (user-guide, project-management)
   - Current: `PascalCase` for files

2. **Release Structure**: Group by version or keep flat?
   - Proposed: `releases/v0.5.5/` (easier to archive)
   - Alternative: `releases/RELEASE_v0.5.5.md` (flat)

3. **Session Notes**: Keep in docs or move to archive immediately?
   - Proposed: Keep recent sessions in `sessions/`
   - Archive after 2-3 months

4. **README Files**: Generate automatically or write manually?
   - Proposed: Write manually with file descriptions
   - Ensures quality and context

---

## ✅ Ready to Execute?

**Estimated Time**: 20-25 minutes
**Risk Level**: Low (using git mv preserves history)
**Reversibility**: High (can undo with git reset)

---

**Status**: Plan documented, awaiting approval
**Next**: Review and approve structure, then execute migration
