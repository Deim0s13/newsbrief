# Issue Tracking

Issue tracking documentation, bug reports, and GitHub issue management.

## 🐛 Contents

### Issue Lists

#### [UI_POLISH_ITEMS.md](UI_POLISH_ITEMS.md)
UI polish items identified during audits:
- Visual improvements
- UX enhancements
- Minor bug fixes
- Accessibility improvements

#### [GITHUB_ISSUES_TO_CLOSE.md](GITHUB_ISSUES_TO_CLOSE.md)
Issues ready to be closed:
- Completed issues pending closure
- Verification checklist
- Closure notes

#### [NEW_GITHUB_ISSUES.md](NEW_GITHUB_ISSUES.md)
New issues to be created:
- Feature requests
- Bug reports
- Enhancement ideas
- Technical debt items

#### [ISSUES_FOUND_2025-11-13.md](ISSUES_FOUND_2025-11-13.md)
Issues discovered on November 13, 2025:
- Testing session findings
- Bug reports
- Performance issues
- UI/UX problems

### Issue Data

#### [UI_POLISH_ISSUES.json](UI_POLISH_ISSUES.json)
JSON data for bulk issue creation:
- Issue templates
- Labels and assignees
- Milestone assignments
- Used by import scripts

---

## 🔄 Issue Workflow

### 1. Issue Discovery
- Testing sessions
- User reports
- Code reviews
- Performance monitoring

### 2. Documentation
- Document in appropriate file
- Add to JSON for GitHub import
- Link to related issues

### 3. Triage
- Prioritize by severity
- Assign to milestone
- Add appropriate labels
- Assign to team member

### 4. Implementation
- Create feature branch
- Implement fix/feature
- Write tests
- Update documentation

### 5. Closure
- Verify fix
- Update related docs
- Close issue with notes
- Link to commits/PRs

---

## 🏷️ Issue Labels

### Priority
- `priority:critical` - Must fix immediately
- `priority:high` - Fix in current sprint
- `priority:medium` - Fix soon
- `priority:low` - Nice to have

### Type
- `bug` - Something broken
- `enhancement` - New feature
- `documentation` - Docs update
- `performance` - Speed/resource issue
- `security` - Security concern

### Area
- `area:ui` - User interface
- `area:api` - API endpoints
- `area:stories` - Story generation
- `area:feeds` - Feed management
- `area:infrastructure` - DevOps/CI

---

## 📊 Current Status

### Open Issues
See [GitHub Issues](https://github.com/Deim0s13/newsbrief/issues)

### Recent Closures
- Issue #48: Scheduled Story Generation ✅
- Issues #51-54: Story UI Components ✅
- Epic: `epic:stories` ✅

---

## 🔧 Issue Management Scripts

### Create Issues from JSON
```bash
python3 scripts/import_ui_polish_issues.py
```

### Bulk Close Issues
```bash
# Using GitHub CLI
gh issue close 123 --comment "Fixed in v0.5.5"
```

---

## 📚 Further Reading

- **Project Management**: See [../project-management/](../project-management/)
- **Testing**: See [../testing/](../testing/)
- **Planning**: See [../planning/](../planning/)

