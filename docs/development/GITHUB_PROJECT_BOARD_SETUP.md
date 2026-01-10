# GitHub Project Board Setup Instructions

**Date**: 2025-11-12
**Status**: ✅ COMPLETED - Board is up and running
**Completed**: 2025-11-18

---

## ✅ Completed Automation

The following has been set up automatically:

1. **✅ Milestones Created** (3 milestones)
   - v0.5.0 - Story Architecture (Due: Dec 15, 2025)
   - v0.6.0 - Intelligence & Polish (Due: Mar 31, 2026)
   - v0.7.0 - Infrastructure (Due: Jun 30, 2026)

2. **✅ Issues Closed** (6 completed issues)
   - #36, #37, #38, #39: Phase 1 infrastructure
   - #47, #55: Story API endpoints

3. **✅ Issues Assigned to Milestones** (28 issues organized)
   - v0.5.0: 7 issues (scheduled gen + UI + performance)
   - v0.6.0: 8 issues (clustering + personalization)
   - v0.7.0: 13 issues (infrastructure + security)

---

## 🎯 Next Step: Create GitHub Project Board

GitHub Projects (v2) must be created through the web UI. Follow these steps:

### Step 1: Create the Project (5 minutes)

1. **Navigate to Projects**:
   ```
   https://github.com/Deim0s13/newsbrief/projects
   ```

2. **Click "New project"** (green button, top right)

3. **Choose Template**: Select "Board" (Kanban-style)

4. **Project Details**:
   - **Name**: `NewsBrief Development`
   - **Description**: `Story-based news aggregator development tracking`
   - **Visibility**: Private (or Public if you want community visibility)

5. **Click "Create project"**

### Step 2: Customize Board Columns (5 minutes)

The default board has "Todo", "In Progress", "Done". Let's customize:

1. **Rename Columns**:
   - Click column header → "..." menu → "Rename"
   - "Todo" → `📋 Backlog`
   - "In Progress" → `🚧 In Progress`
   - "Done" → `✅ Done`

2. **Add "Next" Column**:
   - Click "+ New column" at the right
   - Name: `🔜 Next`
   - Move it between "Backlog" and "In Progress"

3. **Final Column Order** (left to right):
   - 📋 Backlog
   - 🔜 Next
   - 🚧 In Progress
   - ✅ Done

### Step 3: Add Issues to Project (5 minutes)

1. **Bulk Add Issues**:
   - Click "+ Add item" at the bottom of any column
   - Type `#` to see all issues
   - Select repository: `Deim0s13/newsbrief`
   - Click "Add all open issues" or select individually

2. **Organize Issues into Columns**:

   **📋 Backlog** (keep most issues here):
   - All v0.6.0 issues (#40, #41, #43, #46, #49, #56, #57, #58)
   - All v0.7.0 issues (#23-34, #65)

   **🔜 Next** (ready to start):
   - #48: Scheduled story generation
   - #50: Story-based landing page UI
   - #66: Performance optimization

   **🚧 In Progress** (none currently):
   - Leave empty for now

   **✅ Done** (recently completed):
   - Closed issues will auto-appear here
   - #36, #37, #38, #39, #47, #55

3. **Drag and Drop**:
   - Simply drag issue cards between columns

### Step 4: Create Additional Views (10 minutes)

#### View 2: By Milestone

1. **Create New View**:
   - Click "+" next to "Board" tab
   - Choose "Board" layout
   - Name: `By Milestone`

2. **Configure Grouping**:
   - Click "Group" → "Milestone"
   - This creates swim lanes for each milestone

3. **Result**: Issues grouped by v0.5.0, v0.6.0, v0.7.0

#### View 3: By Epic

1. **Create New View**:I
   - Click "+" next to views
   - Choose "Board" layout
   - Name: `By Epic`

2. **Configure Grouping**:
   - Click "Group" → "Labels"
   - Filter to show only labels starting with "epic:"

3. **Result**: Issues grouped by epic:stories, epic:ui, epic:database, etc.

### Step 5: Configure Automation (Optional, 5 minutes)

GitHub Projects can auto-move issues based on status:

1. **Settings** (gear icon, top right)

2. **Workflows**:
   - Enable "Item closed" → Move to "✅ Done"
   - Enable "Item reopened" → Move to "📋 Backlog"

3. **Custom Workflows** (optional):
   - When PR is merged → Move to "✅ Done"
   - When issue is assigned → Move to "🚧 In Progress"

---

## 🎯 Expected Result

After setup, you should have:

### **Board View**
```
📋 Backlog         🔜 Next           🚧 In Progress    ✅ Done
─────────────────  ────────────────  ────────────────  ──────────────
#40 Entity extract #48 Scheduled gen  (empty)          #36 DB schema
#41 Semantic sim   #50 Landing page                    #37 Models
#43 Quality score  #66 Performance                     #38 CRUD
#46 Synthesis cache                                    #39 Generation
... (21 more)                                          #47 On-demand API
                                                       #55 API endpoints
```

### **By Milestone View**
```
v0.5.0 - Story Architecture (7 issues)
  📋 Backlog: #51, #52, #53, #54
  🔜 Next: #48, #50, #66

v0.6.0 - Intelligence & Polish (8 issues)
  📋 Backlog: #40, #41, #43, #46, #49, #56, #57, #58

v0.7.0 - Infrastructure (13 issues)
  📋 Backlog: #23-34, #65
```

### **By Epic View**
```
epic:stories (12 issues)
epic:ui (5 issues)
epic:database (9 issues)
epic:security (1 issue)
epic:ops (1 issue)
```

---

## 📝 Workflow Guide

### Daily Use

**Moving Issues**:
- Drag cards between columns as work progresses
- Or use issue labels/status to auto-move (if automation enabled)

**Starting New Work**:
1. Pick issue from "🔜 Next"
2. Assign to yourself
3. Move to "🚧 In Progress"

**Completing Work**:
1. Create PR with "Fixes #XX" in description
2. Merge PR
3. Issue auto-closes and moves to "✅ Done"

### Weekly Review

1. **Review Progress**:
   - Check "By Milestone" view for v0.5.0 progress
   - How many issues completed this week?

2. **Prioritize Next**:
   - Move 2-3 issues from "Backlog" to "Next"
   - Based on dependencies and priority

3. **Clean Up**:
   - Archive old completed issues (30+ days)
   - Update issue descriptions if scope changed

---

## 🔗 Quick Links

After creating the project, save these links:

- **Project Board**: `https://github.com/users/Deim0s13/projects/X`
- **v0.5.0 Milestone**: https://github.com/Deim0s13/newsbrief/milestone/1
- **v0.6.0 Milestone**: https://github.com/Deim0s13/newsbrief/milestone/2
- **v0.7.0 Milestone**: https://github.com/Deim0s13/newsbrief/milestone/3
- **All Issues**: https://github.com/Deim0s13/newsbrief/issues

Add project board link to:
- README.md (under Roadmap section)
- DEVELOPMENT.md (Project Management section)

---

## ✅ Success Criteria

After setup, you should be able to:
- [ ] See project board with 4 columns
- [ ] View issues grouped by milestone
- [ ] View issues grouped by epic
- [ ] Easily answer "What should I work on next?" (look at "Next" column)
- [ ] Track progress toward v0.5.0 (milestone view)
- [ ] Drag issues between columns

---

## 🚀 Time to Complete

- **Automated** (already done): ~2 minutes
- **Manual UI steps**: ~25 minutes (first time)
- **Total**: ~27 minutes

---

**Status**: ✅ COMPLETED
**Board Created**: 2025-11-18
