# GitHub Project Management Setup Plan

**Date**: 2025-11-12  
**Purpose**: Organize issues into a structured project board with milestones

---

## 📊 Current State Analysis

### Issues Overview
- **Total Open Issues**: 66
- **Organization**: Flat list with labels (epic:*, priority:P*, phase:*)
- **Problem**: Hard to see what's done, in progress, next, or backlog
- **Milestones**: None exist

### Label Structure (Good!)
We already have solid labels:
- **Epic**: epic:stories, epic:ui, epic:database, epic:security, epic:ops
- **Priority**: priority:P0 (critical), P1 (high), P2 (medium)
- **Phase**: phase:clustering, phase:synthesis, phase:scheduling, phase:ui, phase:api

---

## 🎯 Proposed Solution

### 1. GitHub Project Board Setup

**Create Project**: "NewsBrief Development"

**Board Views**:

#### **View 1: Kanban (Default)**
Columns:
- **📋 Backlog** - Not started, prioritized
- **🔜 Next** - Ready to start, queued
- **🚧 In Progress** - Currently being worked on
- **✅ Done** - Completed (last 30 days, then auto-archive)

#### **View 2: By Milestone**
Group by milestone with progress bars

#### **View 3: By Epic**
Group by epic to see feature areas

---

### 2. Milestone Structure

Based on our roadmap, create these milestones:

#### **v0.5.0 - Story Architecture** (Target: 2025-12-15)
**Description**: Core story-based aggregation MVP

**Completed** (Issues #36-39, #47, #55):
- ✅ Database schema and models
- ✅ Story CRUD operations
- ✅ Story generation pipeline
- ✅ Story API endpoints

**In Scope**:
- Issue #48: Scheduled story generation
- Issues #50-54: Story-First UI (landing page, detail page, navigation)
- Issue #66: Performance optimization (Phase 1-2)

**Out of Scope** (moved to v0.6.0):
- Advanced clustering (Issues #40, #41, #43)
- Interest-based filtering (Issues #57, #58)
- Story synthesis caching (Issue #46)

#### **v0.6.0 - Intelligence & Polish** (Target: 2026-Q1)
**Description**: Enhanced clustering, personalization, optimization

**In Scope**:
- Issues #40, #41, #43: Entity extraction, similarity, quality scoring
- Issue #46: Synthesis caching
- Issue #49: Incremental story updates
- Issues #57, #58: Interest-based filtering and source weighting
- Issue #66: Performance optimization (Phase 3-5)

#### **v0.7.0 - Infrastructure** (Target: 2026-Q2)
**Description**: Database migration, security, deployment

**In Scope**:
- Issues #26-32: Postgres migration
- Issue #34: HTTPS/TLS
- Issue #65: Local CI/CD + GitOps
- Issues #23-25: Apple Containers support

#### **Backlog** (No milestone)
Lower priority or exploratory work

---

### 3. Issue Status Updates

#### **Close as Completed** ✅
These are done and should be closed:
- Issue #36: Story database schema ✅
- Issue #37: Story models ✅
- Issue #38: Story CRUD operations ✅
- Issue #39: Story generation pipeline ✅
- Issue #47: On-demand story generation API ✅
- Issue #55: Story API endpoints ✅

#### **Mark as In Progress** 🚧
Currently being worked on:
- (None at the moment - we're between phases)

#### **Mark as Next** 🔜
Ready to start (v0.5.0 priorities):
- Issue #48: Scheduled story generation
- Issue #50: Story-based landing page UI
- Issue #66: Performance optimization (Phase 1)

#### **Keep in Backlog** 📋
Everything else (organized by milestone)

---

## 📋 Implementation Steps

### Step 1: Create Milestones (5 minutes)
```bash
# v0.5.0 - Story Architecture
gh api repos/Deim0s13/newsbrief/milestones -f title="v0.5.0 - Story Architecture" \
  -f description="Core story-based aggregation MVP" \
  -f due_on="2025-12-15T23:59:59Z"

# v0.6.0 - Intelligence & Polish
gh api repos/Deim0s13/newsbrief/milestones -f title="v0.6.0 - Intelligence & Polish" \
  -f description="Enhanced clustering, personalization, optimization" \
  -f due_on="2026-03-31T23:59:59Z"

# v0.7.0 - Infrastructure
gh api repos/Deim0s13/newsbrief/milestones -f title="v0.7.0 - Infrastructure" \
  -f description="Database migration, security, deployment" \
  -f due_on="2026-06-30T23:59:59Z"
```

### Step 2: Close Completed Issues (5 minutes)
```bash
# Close issues that are done
for issue in 36 37 38 39 47 55; do
  gh issue close $issue --comment "✅ Completed as part of Phase 1 + API (v0.5.0)"
done
```

### Step 3: Assign Issues to Milestones (10 minutes)
```bash
# v0.5.0 issues
gh issue edit 48 --milestone "v0.5.0 - Story Architecture"
gh issue edit 50 51 52 53 54 --milestone "v0.5.0 - Story Architecture"
gh issue edit 66 --milestone "v0.5.0 - Story Architecture"

# v0.6.0 issues
gh issue edit 40 41 43 46 49 57 58 --milestone "v0.6.0 - Intelligence & Polish"

# v0.7.0 issues
gh issue edit 26 27 28 29 30 31 32 33 34 --milestone "v0.7.0 - Infrastructure"
gh issue edit 23 24 25 --milestone "v0.7.0 - Infrastructure"
gh issue edit 65 --milestone "v0.7.0 - Infrastructure"
```

### Step 4: Create GitHub Project (10 minutes)
**Manual Steps** (GitHub CLI doesn't support project creation well):

1. Go to: https://github.com/Deim0s13/newsbrief/projects
2. Click "New project"
3. Choose "Board" template
4. Name: "NewsBrief Development"
5. Description: "Story-based news aggregator development tracking"

6. **Customize Columns**:
   - Rename "Todo" → "📋 Backlog"
   - Rename "In Progress" → "🚧 In Progress"
   - Rename "Done" → "✅ Done"
   - Add column: "🔜 Next"
   - Order: Backlog → Next → In Progress → Done

7. **Add Issues to Project**:
   - Use "Add item" to bulk-add all open issues
   - Drag completed issues (36-39, 47, 55) to "✅ Done"
   - Drag next priorities (48, 50, 66) to "🔜 Next"
   - Leave rest in "📋 Backlog"

8. **Create Views**:
   - View 1: "Kanban" (default board)
   - View 2: "By Milestone" (group by milestone field)
   - View 3: "By Epic" (group by labels starting with "epic:")

### Step 5: Document and Maintain (5 minutes)
- Update README.md with project board link
- Document workflow in DEVELOPMENT.md
- Set up automation (optional: auto-move to "In Progress" when assigned)

---

## 🎯 Workflow Guidelines

### Moving Issues Between Columns

**📋 Backlog → 🔜 Next**:
- When an issue is prioritized for upcoming work
- Issue is well-defined and ready to start
- Dependencies are clear

**🔜 Next → 🚧 In Progress**:
- When you start working on the issue
- Assign to yourself
- Update issue with plan or checklist

**🚧 In Progress → ✅ Done**:
- When PR is merged or work is complete
- Close issue with completion notes
- Reference PR in closing comment

**✅ Done → Archive**:
- Auto-archive after 30 days
- Or manually archive to clean up board

### Labels Usage

Keep using labels for filtering:
- **Epic**: High-level feature areas
- **Priority**: P0 (must have), P1 (should have), P2 (nice to have)
- **Phase**: Implementation phase within epic

---

## 📊 Benefits

### Before (Flat List)
- ❌ Hard to see what's in progress
- ❌ No visibility into what's next
- ❌ Completed work mixed with backlog
- ❌ No milestone tracking

### After (Project Board + Milestones)
- ✅ Clear status at a glance (Backlog → Next → In Progress → Done)
- ✅ Milestones show progress toward releases
- ✅ Multiple views (Kanban, by milestone, by epic)
- ✅ Completed work is visible but not cluttering
- ✅ Easy to prioritize and plan sprints

---

## 🚀 Quick Start (One-Time Setup)

**Time Required**: ~30 minutes

1. **Create milestones** (5 min) - Run bash commands above
2. **Close completed issues** (5 min) - Run bash commands above
3. **Assign milestones** (10 min) - Run bash commands above
4. **Create project board** (10 min) - Manual setup in GitHub UI
5. **Update docs** (5 min) - Add project board link to README.md

**Maintenance**: ~5 minutes per issue (move cards, update status)

---

## 📝 Recommended Milestone Breakdown

### v0.5.0 - Story Architecture (9 issues)
- [ ] Issue #48: Scheduled generation
- [ ] Issue #50: Landing page UI
- [ ] Issue #51: Story filters
- [ ] Issue #52: Empty states
- [ ] Issue #53: Story detail page
- [ ] Issue #54: Navigation
- [ ] Issue #66: Performance optimization
- [x] Issue #36-39, #47, #55: COMPLETE

**Progress**: 6/15 complete (40%)

### v0.6.0 - Intelligence & Polish (8 issues)
All phase:clustering, phase:synthesis, and interest filtering

### v0.7.0 - Infrastructure (15 issues)
Database migration, security, deployment, CI/CD

---

## ❓ Questions to Resolve

1. **Due Dates**: Confirm milestone target dates?
   - Suggested: v0.5.0 (Dec 15), v0.6.0 (Q1 2026), v0.7.0 (Q2 2026)

2. **Project Board Location**: User or organization project?
   - Suggested: User project (easier permissions)

3. **Automation**: Enable GitHub Actions for auto-status updates?
   - Suggested: Start manual, add automation later

4. **Issue Grooming**: Regular review cadence?
   - Suggested: Review project board weekly

---

## 🎯 Success Criteria

- ✅ All issues have clear status (Backlog/Next/In Progress/Done)
- ✅ Active milestone (v0.5.0) has <15 issues (focused scope)
- ✅ Completed work is visible but not cluttering view
- ✅ Easy to answer: "What should I work on next?"
- ✅ Progress tracking: "How far along are we on v0.5.0?"

---

**Next Step**: Review this plan, then I'll execute the setup! 🚀

