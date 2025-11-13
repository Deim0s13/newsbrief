# Git Branching Strategy

**Date**: 2025-11-12  
**Status**: Active

---

## 🌳 Branch Structure

### **`main`** (Protected)
- **Purpose**: Stable, production-ready code
- **Protection**: Require pull requests, reviews
- **Releases**: Tagged releases (v0.5.0, v0.6.0, etc.)
- **Deploy**: Could deploy directly to production

### **`dev`** (Integration)
- **Purpose**: Integration branch for completed features
- **Merges from**: Feature branches
- **Merges to**: `main` (via PR for releases)
- **Testing**: All features tested together before release

### **`feature/*`** (Working branches)
- **Purpose**: Individual feature development
- **Naming**: `feature/issue-48-scheduled-generation`, `feature/story-ui`
- **Lifetime**: Created for work, deleted after merge
- **Merges to**: `dev` (via PR)

---

## 📋 Workflow

### Starting New Work

1. **Create feature branch from dev**:
   ```bash
   git checkout dev
   git pull origin dev
   git checkout -b feature/issue-48-scheduled-generation
   ```

2. **Work on feature**:
   ```bash
   # Make changes
   git add .
   git commit -m "feat: add scheduled story generation"
   git push origin feature/issue-48-scheduled-generation
   ```

3. **Create Pull Request**:
   - From: `feature/issue-48-scheduled-generation`
   - To: `dev`
   - Title: "feat: Scheduled story generation (Issue #48)"
   - Description: Link issue, describe changes

4. **After PR merged**:
   ```bash
   git checkout dev
   git pull origin dev
   git branch -d feature/issue-48-scheduled-generation
   ```

### Release Process

When ready to release (e.g., v0.5.0 complete):

1. **Create release PR**:
   - From: `dev`
   - To: `main`
   - Title: "Release v0.5.0 - Story Architecture"

2. **After merge to main**:
   ```bash
   git checkout main
   git pull origin main
   git tag -a v0.5.0 -m "Release v0.5.0 - Story Architecture"
   git push origin v0.5.0
   ```

3. **Create GitHub Release**:
   - Tag: v0.5.0
   - Title: "v0.5.0 - Story Architecture"
   - Release notes: Completed features, breaking changes

---

## 🔧 Initial Setup (One-Time)

### Create `dev` Branch

```bash
# From main
git checkout main
git pull origin main

# Create dev branch
git checkout -b dev
git push origin dev

# Set up tracking
git branch --set-upstream-to=origin/dev dev
```

### Protect `main` Branch

In GitHub:
1. Settings → Branches → Branch protection rules
2. Add rule for `main`:
   - ✅ Require pull request before merging
   - ✅ Require approvals (1+)
   - ✅ Require status checks to pass
   - ✅ Include administrators (optional)

---

## 🏷️ Branch Naming Conventions

### Features
- `feature/issue-48-scheduled-generation`
- `feature/story-landing-page`
- `feature/performance-optimization`

### Bugfixes
- `bugfix/issue-99-fix-clustering`
- `fix/story-api-timeout`

### Hotfixes (emergency fixes to main)
- `hotfix/critical-security-patch`
- `hotfix/database-migration-fix`

### Documentation
- `docs/update-api-documentation`
- `docs/add-architecture-diagrams`

### Refactoring
- `refactor/story-generation-pipeline`
- `refactor/cleanup-tests`

---

## 📝 Commit Message Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting, missing semicolons, etc.
- `refactor`: Code change that neither fixes bug nor adds feature
- `test`: Adding tests
- `chore`: Maintenance tasks (deps, config, etc.)

### Examples
```bash
feat(stories): add scheduled story generation

Implements APScheduler for daily story generation at 6 AM.
Configurable schedule via STORY_GENERATION_SCHEDULE env var.

Closes #48

---

fix(api): resolve story API timeout on POST /stories/generate

Move story generation to background task to prevent HTTP timeouts.

Relates to #66

---

docs: update README with v0.5.0 milestone progress

Added milestone links and updated project tracking section.
```

---

## 🚫 What NOT to Commit Directly to Main

- ❌ Feature development
- ❌ Experimental changes
- ❌ Untested code
- ❌ Work in progress
- ❌ Breaking changes without review

### Exceptions (Emergency Only)
- ✅ Critical security patches (via hotfix branch → PR)
- ✅ Hotfixes for production issues (via hotfix branch → PR)
- ✅ Documentation typos (very minor, or via PR)

---

## 🔄 Current State Correction

**Issue**: We've been committing directly to `main` during development.

**Action Plan**:

1. **Create `dev` branch** from current `main`:
   ```bash
   git checkout -b dev
   git push origin dev
   ```

2. **For future work**: Always branch from `dev`:
   ```bash
   git checkout dev
   git checkout -b feature/my-feature
   ```

3. **Going forward**: Use PRs for all changes:
   - Feature branches → `dev` (via PR)
   - `dev` → `main` (via PR for releases)

**Note**: Past commits to `main` are fine (they're done), but from now on we follow the proper workflow.

---

## 📊 Example Workflow for Issue #48

```bash
# Start work
git checkout dev
git pull origin dev
git checkout -b feature/issue-48-scheduled-generation

# Make changes
vim app/scheduler.py
vim app/main.py
git add .
git commit -m "feat(stories): implement scheduled story generation

- Add APScheduler for background tasks
- Configure daily generation schedule
- Add health checks and error handling
- Update API to integrate scheduler

Closes #48"

# Push and create PR
git push origin feature/issue-48-scheduled-generation
gh pr create --base dev --title "feat: Scheduled story generation (Issue #48)"

# After PR approved and merged
git checkout dev
git pull origin dev
git branch -d feature/issue-48-scheduled-generation
git push origin --delete feature/issue-48-scheduled-generation
```

---

## 🎯 Benefits

### With Proper Branching
- ✅ `main` always stable
- ✅ Can rollback easily
- ✅ Review before merge
- ✅ Test features in isolation
- ✅ Multiple people can work in parallel
- ✅ Clear history via PRs

### Without (Direct to Main)
- ❌ Unstable `main` branch
- ❌ Hard to revert changes
- ❌ No review process
- ❌ Messy commit history
- ❌ Risky for collaboration

---

## 📚 Additional Resources

- [Git Feature Branch Workflow](https://www.atlassian.com/git/tutorials/comparing-workflows/feature-branch-workflow)
- [GitHub Flow](https://docs.github.com/en/get-started/quickstart/github-flow)
- [Conventional Commits](https://www.conventionalcommits.org/)

---

**Next Steps**:
1. Create `dev` branch
2. Set up branch protection on `main`
3. Use feature branches for all new work

---

**Status**: Ready to implement  
**Impact**: Better code quality, safer releases, clearer history

